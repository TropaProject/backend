from django.conf import settings
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from openai import OpenAI
from rest_framework import status, permissions
from .models import City, CitySuggestion, CitySuggestionVote, Mood, CityArea, Feedback, Route, Interest, PointEmbedding, Tag, Point
from .serializers import CitySerializer, CitySuggestionSerializer, InterestSerializer, MoodSerializer
from .services.generate_route import RoutePipeline, build_yandex_map_url
from .services.route_metrics import calculate_total_cost, calculate_total_meters, haversine, calculate_route_times
from rest_framework.views import APIView
from rest_framework.response import Response
from numpy import dot
from numpy.linalg import norm
from django.db import models
from django.db.models import Count, Exists, F, OuterRef
from django.db import transaction
from ..core.services import generate_embedding
from django.utils import timezone

# Форма ввода
class FormDataView(APIView):
    def get(self, request):
        cities = City.objects.all()
        interests = Interest.objects.exclude(category__id="food")
        moods = Mood.objects.all()

        return Response({
            "status": "success",
            "data": {
                "cities": CitySerializer(cities, many=True).data,
                "interests": InterestSerializer(interests, many=True).data,
                "moods": MoodSerializer(moods, many=True).data,
            }
        }, status=status.HTTP_200_OK)

class FormFoodView(APIView):
    def get(self, request):
        interests = Interest.objects.filter(category__id="food")
        return Response({
            "status": "success",
            "data": {
                "interests": InterestSerializer(interests, many=True).data,
            }
        }, status=status.HTTP_200_OK)
class CityAreaView(APIView):
    def get(self, request):
        city_id = request.query_params.get("city_id")
        if not city_id:
            return Response(
                {"status": "error", "message": "Параметр city_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            city = City.objects.get(id=city_id)
        except City.DoesNotExist:
            return Response(
                {"status": "error", "message": f"Город {city_id} не найден"},
                status=status.HTTP_404_NOT_FOUND
            )

        areas = CityArea.objects.filter(city=city)

        data = {
            "city": {
                "id": city.id,
                "name": city.name,
            },
            "areas": [
                {
                    "name": area.name,
                    "description": area.description,
                    "image_url": area.image_url.url if area.image_url else None,
                }
                for area in areas
            ],
        }

        return Response({"status": "success", "data": data}, status=status.HTTP_200_OK)


def _normalize_city_name(name):
    return " ".join(name.strip().lower().split())


def _city_suggestions_queryset(user):
    user_votes = CitySuggestionVote.objects.filter(suggestion=OuterRef("pk"), user=user)
    return (
        CitySuggestion.objects
        .select_related("created_by")
        .annotate(votes_count=Count("votes", distinct=True))
        .annotate(has_voted=Exists(user_votes))
    )


class CitySuggestionListCreateView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        search = request.query_params.get("search")
        status_filter = request.query_params.get("status")
        limit = int(request.query_params.get("limit", 50))
        offset = int(request.query_params.get("offset", 0))

        qs = _city_suggestions_queryset(request.user)
        if status_filter:
            qs = qs.filter(status=status_filter)
        if search:
            qs = qs.filter(name__icontains=search.strip())

        qs = qs.order_by("-votes_count", "-created_at")
        total_count = qs.count()
        serializer = CitySuggestionSerializer(qs[offset:offset + limit], many=True)

        return Response(
            {"status": "success", "total_count": total_count, "data": serializer.data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        name = str(request.data.get("name", "")).strip()
        country = str(request.data.get("country", "")).strip() or None
        comment = str(request.data.get("comment", "")).strip() or None

        if not name:
            return Response(
                {"status": "error", "message": "name обязателен"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        existing_city = City.objects.filter(name__iexact=name).first()
        if existing_city:
            return Response(
                {
                    "status": "error",
                    "message": "Этот город уже доступен в приложении",
                    "data": CitySerializer(existing_city).data,
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        normalized_name = _normalize_city_name(name)
        with transaction.atomic():
            suggestion, created = CitySuggestion.objects.get_or_create(
                normalized_name=normalized_name,
                defaults={
                    "name": name,
                    "country": country,
                    "comment": comment,
                    "created_by": request.user,
                },
            )
            vote, voted_now = CitySuggestionVote.objects.get_or_create(
                suggestion=suggestion,
                user=request.user,
            )

        suggestion = _city_suggestions_queryset(request.user).get(id=suggestion.id)
        serializer = CitySuggestionSerializer(suggestion)

        return Response(
            {
                "status": "success",
                "created": created,
                "voted_now": voted_now,
                "data": serializer.data,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class CitySuggestionVoteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, suggestion_id):
        try:
            suggestion = CitySuggestion.objects.get(id=suggestion_id)
        except CitySuggestion.DoesNotExist:
            return Response(
                {"status": "error", "message": "Предложенный город не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        vote, voted_now = CitySuggestionVote.objects.get_or_create(
            suggestion=suggestion,
            user=request.user,
        )
        suggestion = _city_suggestions_queryset(request.user).get(id=suggestion.id)

        return Response(
            {
                "status": "success",
                "voted_now": voted_now,
                "data": CitySuggestionSerializer(suggestion).data,
            },
            status=status.HTTP_200_OK,
        )


def _route_author_payload(route):
    if not route.user:
        return None
    return {
        "id": route.user.id,
        "username": route.user.username,
        "email": route.user.email,
    }


def _route_main_point(route):
    points = list(route.points.all())
    if route.point_sequence:
        first_id = str(route.point_sequence[0])
        main_point = next((p for p in points if str(p.id) == first_id), None)
        if main_point:
            return main_point
    return points[0] if points else None


def _serialize_route_card(route, request_user=None):
    main_point = _route_main_point(route)
    is_owner = bool(request_user and request_user.is_authenticated and route.user_id == request_user.id)

    return {
        "route_id": route.id,
        "title": route.title,
        "description": route.description,
        "total_duration": route.total_duration,
        "total_cost": route.total_cost,
        "total_meters": route.total_meters,
        "status": route.status,
        "is_public": route.is_public,
        "is_owner": is_owner,
        "author": _route_author_payload(route),
        "public_uses_count": route.public_uses_count,
        "original_route_id": route.original_route_id,
        "created_at": route.created_at.isoformat(),
        "updated_at": getattr(route, "updated_at", None).isoformat() if hasattr(route, "updated_at") and route.updated_at else None,
        "city": route.city.name if route.city else None,
        "image": main_point.image_url if main_point else None,
        "tag": main_point.tags.first().name if main_point and main_point.tags.exists() else None,
        "interest": main_point.interests.first().label if main_point and main_point.interests.exists() else None,
        "best_visit_time": main_point.best_visit_time[0] if main_point and main_point.best_visit_time else None,
    }


def _serialize_route_detail(route, request_user=None):
    seq = route.point_sequence
    point_map = {str(p.id): p for p in route.points.all()}
    ordered_points = [point_map[pid] for pid in seq if pid in point_map]
    is_owner = bool(request_user and request_user.is_authenticated and route.user_id == request_user.id)

    return {
        "route_id": route.id,
        "user": _route_author_payload(route),
        "author": _route_author_payload(route),
        "is_owner": is_owner,
        "is_public": route.is_public,
        "public_uses_count": route.public_uses_count,
        "original_route_id": route.original_route_id,
        "title": route.title,
        "description": route.description,
        "total_duration": route.total_duration,
        "walk_time": route.walk_time,
        "visit_time": route.visit_time,
        "total_cost": route.total_cost,
        "total_meters": route.total_meters,
        "status": route.status,
        "point_sequence": route.point_sequence,
        "points": [
            {
                "id": p.id,
                "name": p.name,
                "description": p.description,
                "average_rating": float(p.average_rating),
                "reviews_count": p.reviews_count,
                "image_url": p.image_url,
                "coordinates": {
                    "lat": float(p.coordinates_lat),
                    "lng": float(p.coordinates_lng),
                },
                "working_hours": p.working_hours_json,
                "average_cost": p.average_cost,
                "city": p.city.name if p.city else None,
                "tags": [t.name for t in p.tags.all()],
                "interests": [i.label for i in p.interests.all()],
            }
            for p in ordered_points
        ],
        "created_at": route.created_at.isoformat(),
        "updated_at": getattr(route, "updated_at", None).isoformat() if hasattr(route, "updated_at") and route.updated_at else None,
    }


def _get_positive_int(value, default, max_value=100):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    if value < 0:
        return default
    return min(value, max_value)


def _build_user_route_profile(user):
    routes = (
        Route.objects
        .filter(user=user)
        .prefetch_related("points__interests", "points__moods", "points__tags")
        .order_by("-created_at")[:50]
    )
    profile = {
        "city_ids": set(),
        "interest_ids": set(),
        "mood_ids": set(),
        "tag_ids": set(),
        "point_ids": set(),
        "durations": [],
        "copied_source_ids": set(),
        "has_history": False,
    }

    for route in routes:
        profile["has_history"] = True
        if route.city_id:
            profile["city_ids"].add(route.city_id)
        if route.total_duration:
            profile["durations"].append(route.total_duration)
        if route.original_route_id:
            profile["copied_source_ids"].add(str(route.original_route_id))

        for point in route.points.all():
            profile["point_ids"].add(str(point.id))
            profile["interest_ids"].update(point.interests.values_list("id", flat=True))
            profile["mood_ids"].update(point.moods.values_list("id", flat=True))
            profile["tag_ids"].update(point.tags.values_list("id", flat=True))

    return profile


def _score_public_route_for_user(route, profile):
    score = 0
    reasons = []
    route_points = list(route.points.all())

    if route.public_uses_count:
        score += min(route.public_uses_count * 3, 30)
        reasons.append("popular")

    if route.city_id and route.city_id in profile["city_ids"]:
        score += 20
        reasons.append("same_city")

    route_interest_ids = set()
    route_mood_ids = set()
    route_tag_ids = set()
    route_point_ids = set()

    for point in route_points:
        route_point_ids.add(str(point.id))
        route_interest_ids.update(point.interests.values_list("id", flat=True))
        route_mood_ids.update(point.moods.values_list("id", flat=True))
        route_tag_ids.update(point.tags.values_list("id", flat=True))

    interest_matches = len(route_interest_ids & profile["interest_ids"])
    mood_matches = len(route_mood_ids & profile["mood_ids"])
    tag_matches = len(route_tag_ids & profile["tag_ids"])
    point_matches = len(route_point_ids & profile["point_ids"])

    if interest_matches:
        score += min(interest_matches * 6, 30)
        reasons.append("matching_interests")
    if mood_matches:
        score += min(mood_matches * 4, 20)
        reasons.append("matching_moods")
    if tag_matches:
        score += min(tag_matches * 2, 12)
        reasons.append("matching_tags")
    if point_matches:
        score += min(point_matches * 8, 24)
        reasons.append("familiar_places")

    if route.total_duration and profile["durations"]:
        avg_duration = sum(profile["durations"]) / len(profile["durations"])
        diff = abs(route.total_duration - avg_duration)
        if diff <= 30:
            score += 10
            reasons.append("similar_duration")
        elif diff <= 60:
            score += 5
            reasons.append("near_duration")

    if not reasons:
        reasons.append("new_public_route")

    return score, reasons


class GenerateRouteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data

        city_id = data.get("city_id")
        duration_minutes = data.get("duration_minutes")
        radius_km = data.get("radius_km")

        # базовая валидация
        if not city_id or not duration_minutes:
            return Response(
                {"status": "error", "message": "city_id и duration_minutes обязательны"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            duration_minutes = int(duration_minutes)
        except Exception:
            return Response(
                {"status": "error", "message": "duration_minutes должен быть числом"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            radius_km = float(radius_km) if radius_km else 2.0
        except Exception:
            return Response(
                {"status": "error", "message": "radius_km должен быть числом"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # 1) Получаем город и точки
            city = City.objects.get(id=city_id)
            BLOCKED_INTEREST_IDS = ["coffee", "fine_dining", "food", "sweet", "unusual_food"]
            pois_qs = (
                Point.objects
                .filter(city=city)
                .exclude(interests__id__in=BLOCKED_INTEREST_IDS)
                .distinct()
            )

            # 2) Запускаем пайплайн
            req_payload = {
                "city_id": city_id,
                "time_of_day": data.get("time_of_day"),
                "interests": data.get("interests", []),
                "mood": data.get("mood", []),
                "budget": data.get("budget"),
                "transport": data.get("transport"),
                "duration_minutes": duration_minutes,
                "description": data.get("description"),
                "start_point": data.get("start_point"),
                "start_area": data.get("start_area"),
            }
            pipeline = RoutePipeline(req_payload=req_payload,
                                     gpt_text=data.get("gpt_description"),
                                     radius_km=radius_km)
            try:
                final_result = pipeline.run_pipeline(pois_qs)
            except Exception as e:
                return Response(
                    {"status": "error", "message": "Ошибка пайплайна", "details": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            selected = final_result.get("points", [])
            if not selected:
                return Response(
                    {"status": "error", "message": "GPT вернул пустой список точек"},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )

            # 3) Создаём маршрут
            try:
                point_map = {str(p.id): p for p in Point.objects.filter(id__in=[s["id"] for s in selected])}
                ordered_points = [
                    point_map[str(item["id"])]
                    for item in sorted(selected, key=lambda x: x.get("order", 9999))
                    if str(item["id"]) in point_map
                ]
            except Exception as e:
                return Response(
                    {"status": "error", "message": "Ошибка при обработке точек", "details": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            try:
                total_cost = calculate_total_cost(ordered_points)
                total_meters = calculate_total_meters(ordered_points)
                name = final_result.get("name", "")
                lat0, lon0 = map(float, req_payload.get("start_point").split(","))
                route = Route.objects.create(
                    total_duration=final_result.get("total_time", 0),
                    total_cost=total_cost,
                    total_meters=total_meters,
                    walk_time=final_result.get("walk_time_minutes", 0),
                    visit_time=final_result.get("visit_time_minutes", 0),
                    city=city,
                    title=name,
                    description=final_result.get("description") or data.get("gpt_description") or name,
                    user=request.user,
                    point_sequence=[p.id for p in ordered_points],
                    status=Route.WalkStatus.GOING,
                    lat0=lat0,
                    lon0=lon0
                )
                for item in selected:
                    p = point_map.get(str(item["id"]))
                    if p:
                        route.points.add(p)
            except Exception as e:
                return Response(
                    {"status": "error", "message": "Ошибка при создании маршрута", "details": str(e)},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                )

            # 4) Обогащаем точки
            enriched_points = []
            for item in sorted(selected, key=lambda x: x.get("order", 9999)):
                p = point_map.get(str(item["id"]))
                if not p:
                    continue
                try:
                    enriched_points.append({
                        "id": str(p.id),
                        "name": p.name,
                        "description": p.description,
                        "reason": item.get("reason", ""),
                        "image_url": getattr(p, "image_url", None),
                        "visit_time": getattr(p, "visit_time", None) or "30 мин",
                        "tags": [t.name for t in p.tags.all()] if hasattr(p, "tags") else [],
                        "average_rating":p.average_rating,
                        "reviews_count":p.reviews_count,
                        "coordinates": {
                            "lat": float(p.coordinates_lat),
                            "lng": float(p.coordinates_lng),
                        },
                    })
                except Exception as e:
                    print(f"[WARN] enrich point failed: {e}")

            # 5) Ответ
            map_url = build_yandex_map_url([ep["coordinates"] for ep in enriched_points])
            response_data = {
                "route_id": str(route.id),
                "title": route.title,
                "route_name": route.title,
                "description": route.description,
                "total_duration": route.total_duration,
                "total_meters": route.total_meters,
                "total_cost": route.total_cost,
                "walk_time": route.walk_time,
                "visit_time": route.visit_time,
                "user_id": request.user.id,
                "is_public": route.is_public,
                "public_uses_count": route.public_uses_count,
                "map_url": map_url,
                "points": enriched_points,
            }
            return Response({"status": "success", "data": response_data}, status=status.HTTP_200_OK)

        except City.DoesNotExist:
            return Response(
                {"status": "error", "message": "Город не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": "Непредвиденная ошибка", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EditRouteStatusView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        route_id = request.data.get("route_id")
        new_status = request.data.get("status")

        if not route_id:
            return Response(
                {"status": "error", "message": "route_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if new_status not in Route.WalkStatus.values:
            return Response(
                {"status": "error", "message": f"Недопустимый статус: {new_status}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            route = Route.objects.get(id=route_id, user=request.user)
        except Route.DoesNotExist:
            return Response(
                {"status": "error", "message": "Маршрут не найден или не принадлежит пользователю"},
                status=status.HTTP_404_NOT_FOUND
            )

        route.status = new_status
        route.save(update_fields=["status"])

        return Response(
            {
                "status": "success",
                "data": {
                    "route_id": route.id,
                    "new_status": route.status,
                    "updated_at": timezone.now().isoformat()
                }
            },
            status=status.HTTP_200_OK
        )


class CancelRouteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        route_id = request.data.get("route_id")
        reason = request.data.get("reason")

        if not route_id:
            return Response(
                {"status": "error", "message": "route_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            route = Route.objects.get(id=route_id, user=request.user)
        except Route.DoesNotExist:
            return Response(
                {"status": "error", "message": "Маршрут не найден или не принадлежит пользователю"},
                status=status.HTTP_404_NOT_FOUND
            )

        route.status = Route.WalkStatus.CANCELLED
        Feedback.objects.create(
            route=route,
            user=request.user,
            comment=reason
        )

        return Response(
            {
                "status": "success",
                "data": {
                    "route_id": route.id,
                    "status": route.status,
                    "cancel_reason": reason,
                    "updated_at": timezone.now().isoformat()
                }
            },
            status=status.HTTP_200_OK
        )


class RouteDetailView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, id_route):
        try:
            route = (
                Route.objects
                .select_related("user", "city", "original_route")
                .prefetch_related("points__tags", "points__interests")
                .get(models.Q(user=request.user) | models.Q(is_public=True), id=id_route)
            )
        except Route.DoesNotExist:
            return Response(
                {"status": "error", "message": "Маршрут не найден или не принадлежит пользователю"},
                status=status.HTTP_404_NOT_FOUND
            )

        return Response(
            {"status": "success", "data": _serialize_route_detail(route, request.user)},
            status=status.HTTP_200_OK
        )

        data = {
            "route_id": route.id,
            "user": {
                "id": route.user.id,
                "username": route.user.username,
                "email": route.user.email,
            } if route.user else None,
            "title": f"Маршрут {route.id[:8]}",
            "description": route.description,
            "total_duration": route.total_duration,
            "walk_time": route.walk_time,
            "visit_time": route.visit_time,
            "total_cost": route.total_cost,
            "total_meters": route.total_meters,
            "status": route.status,
            "point_sequence": route.point_sequence,
            "points": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "average_rating": float(p.average_rating),
                    "reviews_count": p.reviews_count,
                    "image_url": p.image_url,
                    "coordinates": {
                        "lat": float(p.coordinates_lat),
                        "lng": float(p.coordinates_lng),
                    },
                    "working_hours": p.working_hours_json,
                    "average_cost": p.average_cost,
                    "city": p.city.name if p.city else None,
                    "tags": [t.name for t in p.tags.all()],
                    "interests": [i.label for i in p.interests.all()],
                }
                for p in ordered_points
            ],
            "created_at": route.created_at.isoformat(),
            "updated_at": route.updated_at.isoformat() if hasattr(route, "updated_at") and route.updated_at else None,
        }

        return Response({"status": "success", "data": data}, status=status.HTTP_200_OK)



class PublicRoutesListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        city_id = request.query_params.get("city_id")
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))

        qs = (
            Route.objects
            .filter(is_public=True)
            .select_related("user", "city", "original_route")
            .prefetch_related("points__tags", "points__interests")
            .order_by("-created_at")
        )
        if city_id:
            qs = qs.filter(city_id=city_id)

        total_count = qs.count()
        data = [_serialize_route_card(route, request.user) for route in qs[offset:offset + limit]]

        return Response(
            {"status": "success", "total_count": total_count, "data": data},
            status=status.HTTP_200_OK,
        )


class RecommendedPublicRoutesView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        city_id = request.query_params.get("city_id")
        limit = _get_positive_int(request.query_params.get("limit"), 20, max_value=50)
        offset = _get_positive_int(request.query_params.get("offset"), 0, max_value=1000)
        exclude_copied = str(request.query_params.get("exclude_copied", "true")).lower() not in ("false", "0")

        profile = _build_user_route_profile(request.user)
        qs = (
            Route.objects
            .filter(is_public=True)
            .exclude(user=request.user)
            .select_related("user", "city", "original_route")
            .prefetch_related("points__tags", "points__interests", "points__moods")
            .order_by("-public_uses_count", "-created_at")
        )
        if city_id:
            qs = qs.filter(city_id=city_id)
        if exclude_copied and profile["copied_source_ids"]:
            qs = qs.exclude(id__in=profile["copied_source_ids"])

        total_count = qs.count()
        candidate_pool_limit = max(300, offset + limit)
        scored_routes = []
        for route in qs[:candidate_pool_limit]:
            score, reasons = _score_public_route_for_user(route, profile)
            scored_routes.append((score, route.created_at, route, reasons))

        scored_routes.sort(key=lambda item: (item[0], item[1]), reverse=True)
        paginated = scored_routes[offset:offset + limit]

        data = []
        for score, created_at, route, reasons in paginated:
            route_data = _serialize_route_card(route, request.user)
            route_data.update({
                "recommendation_score": score,
                "recommendation_reasons": reasons,
                "can_copy": True,
            })
            data.append(route_data)

        return Response(
            {
                "status": "success",
                "total_count": total_count,
                "data": data,
            },
            status=status.HTTP_200_OK,
        )


class RouteVisibilityView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        route_id = request.data.get("route_id")
        if not route_id:
            return Response(
                {"status": "error", "message": "route_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_visibility = request.data.get("is_public", request.data.get("visibility"))
        if raw_visibility is None:
            return Response(
                {"status": "error", "message": "is_public обязателен"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if isinstance(raw_visibility, bool):
            is_public = raw_visibility
        elif str(raw_visibility).lower() in ("true", "1", "public"):
            is_public = True
        elif str(raw_visibility).lower() in ("false", "0", "private"):
            is_public = False
        else:
            return Response(
                {"status": "error", "message": "is_public должен быть boolean"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            route = Route.objects.get(id=route_id, user=request.user)
        except Route.DoesNotExist:
            return Response(
                {"status": "error", "message": "Маршрут не найден или не принадлежит пользователю"},
                status=status.HTTP_404_NOT_FOUND,
            )

        route.is_public = is_public
        route.save(update_fields=["is_public"])

        return Response(
            {"status": "success", "data": _serialize_route_card(route, request.user)},
            status=status.HTTP_200_OK,
        )


class CopyPublicRouteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        route_id = request.data.get("route_id")
        if not route_id:
            return Response(
                {"status": "error", "message": "route_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            with transaction.atomic():
                source = (
                    Route.objects
                    .select_for_update()
                    .select_related("user", "city")
                    .prefetch_related("points")
                    .get(id=route_id, is_public=True)
                )

                if source.user_id == request.user.id:
                    return Response(
                        {"status": "error", "message": "Нельзя скопировать собственный публичный маршрут"},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

                copied_route = Route.objects.create(
                    total_duration=source.total_duration,
                    walk_time=source.walk_time,
                    visit_time=source.visit_time,
                    total_cost=source.total_cost,
                    total_meters=source.total_meters,
                    city=source.city,
                    title=source.title,
                    description=source.description,
                    lat0=source.lat0,
                    lon0=source.lon0,
                    user=request.user,
                    point_sequence=list(source.point_sequence),
                    status=Route.WalkStatus.GOING,
                    is_public=False,
                    original_route=source,
                )
                copied_route.points.set(source.points.all())
                Route.objects.filter(id=source.id).update(public_uses_count=F("public_uses_count") + 1)
                source.refresh_from_db(fields=["public_uses_count"])
        except Route.DoesNotExist:
            return Response(
                {"status": "error", "message": "Публичный маршрут не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            {
                "status": "success",
                "data": {
                    "route": _serialize_route_detail(copied_route, request.user),
                    "source_route_id": source.id,
                    "source_public_uses_count": source.public_uses_count,
                },
            },
            status=status.HTTP_201_CREATED,
        )


class FeedbackView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        route_id = request.data.get("route_id")
        rating = request.data.get("rating")
        comment = request.data.get("comment")

        if not route_id:
            return Response(
                {"status": "error", "message": "route_id обязателен"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            route = Route.objects.get(id=route_id, user=request.user)
        except Route.DoesNotExist:
            return Response(
                {"status": "error", "message": "Маршрут не найден или не принадлежит пользователю"},
                status=status.HTTP_404_NOT_FOUND
            )

        if rating is not None and (int(rating) < 1 or int(rating) > 5):
            return Response(
                {"status": "error", "message": "rating должен быть от 1 до 5"},
                status=status.HTTP_400_BAD_REQUEST
            )

        feedback = Feedback.objects.create(
            route=route,
            user=request.user,
            rating=rating,
            comment=comment
        )

        return Response(
            {
                "status": "success",
                "data": {
                    "route_id": route.id,
                    "user_id": request.user.id,
                    "rating": feedback.rating,
                    "comment": feedback.comment,
                    "created_at": feedback.created_at.isoformat()
                }
            },
            status=status.HTTP_201_CREATED
        )


client = OpenAI(api_key=settings.OPENAI_API_KEY,
                base_url="https://api.proxyapi.ru/openai/v1")


class GenerateDescriptionView(APIView):
    """
    Ручка принимает параметры маршрута и возвращает описание от GPT.
    """

    def post(self, request):
        data = request.data

        # достаём имя района по ID
        start_area_id = data.get("start_area")
        start_area_name = None
        if start_area_id:
            try:
                area = CityArea.objects.get(id=start_area_id)
                start_area_name = area.name
            except CityArea.DoesNotExist:
                start_area_name = f"район {start_area_id}"  # fallback

        # Формируем промпт для GPT
        prompt = (
            "Ты — помощник по созданию маршрутов для прогулок и досуга.\n"
            "На основе данных пользователя составь компактное и человечное описание маршрута.\n\n"
            "Данные пользователя:\n"
            f"- Город: {data.get('city_id')}\n"
            f"- Время суток: {data.get('time_of_day')}\n"
            f"- Интересы: {', '.join(data.get('interests', []))}\n"
            f"- Настроения: {', '.join(data.get('mood', []))}\n"
            f"- Бюджет: {data.get('budget')}\n"
            f"- Транспорт: {data.get('transport')}\n"
            f"- Длительность: {data.get('duration_minutes')} минут\n"
            f"- Стартовая точка: рядом с районом {start_area_name} (координаты не упоминай)\n"
            f"- Дополнительное описание: {data.get('description')}\n\n"
            "Требования:\n"
            "- Обязательно упомяни все ключевые параметры в тексте.\n"
            "- Не используй сухие перечисления, пиши естественным языком.\n"
            "- Не упоминай точные координаты, только названия районов или ориентиры.\n"
            "- Сделай текст компактным и лёгким для чтения.\n"
            "- Добавь контекст и разнообразие: включи разные категории мест (например, парки, музеи, достопримечательности, кафе), "
            "но сохраняя основные категории из списка.\n"
            "- Сохрани факты из данных, но можешь расширить их ассоциациями (например, вечером → огни города, искусство → галерея, расслабление → уютная атмосфера)."
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300
            )

            gpt_text = response.choices[0].message.content.strip()

            return Response({"route_description": gpt_text}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@csrf_exempt
def pipeline_view(request):
    context = {}
    if request.method == "POST":
        form = request.POST.dict()
        req_payload = {
            "city_id": form.get("city_id"),
            "time_of_day": form.get("time_of_day"),
            "interests": [s.strip() for s in form.get("interests", "").split(",") if s.strip()],
            "mood": [s.strip() for s in form.get("mood", "").split(",") if s.strip()],
            "budget": form.get("budget"),
            "transport": form.get("transport"),
            "duration_minutes": int(form.get("duration_minutes") or 0),
            "description": form.get("description"),
            "start_point": form.get("start_point"),
            "start_area": form.get("start_area"),
        }
        gpt_text = form.get("gpt_description")

        try:
            city = City.objects.get(id=req_payload["city_id"])
            pois = Point.objects.filter(city=city)
            pipeline = RoutePipeline(req_payload=req_payload, gpt_text=gpt_text)
            result = pipeline.run_pipeline(pois)
            context["result"] = result
        except Exception as e:
            context["result"] = f"Ошибка: {e}"

        # сохраняем введённые значения, чтобы они остались в форме
        context.update(form)

    return render(request, "pipeline.html", context)


class AddFoodPointView(APIView):
    """
    Добавляет точку еды между двумя точками маршрута.
    """

    def post(self, request):
        try:
            between_index = int(request.data.get("between_index")) - 1
            interests_list = request.data.get("interests", [])
            note = request.data.get("note", "").strip()
            route_id = request.data.get("route_id")
            if not interests_list:
                return Response({"error": "interests is required"}, status=400)

            # 1. Получаем маршрут
            route = Route.objects.get(id=route_id)
            seq = route.point_sequence
            if between_index < 0 or between_index >= len(seq) - 1:
                return Response({"error": "Invalid between_index"}, status=400)

            # 2. Две точки маршрута
            point_a = Point.objects.get(id=seq[between_index])
            point_b = Point.objects.get(id=seq[between_index + 1])
            # 3. Все точки, у которых есть хотя бы один из интересов
            candidate_points = (
                Point.objects
                .filter(interests__id__in=interests_list)
                .exclude(id__in=seq)  # не вставлять уже существующие точки
                .distinct()
            )
            if not candidate_points.exists():
                return Response({"error": "No candidate points found"}, status=404)

            # 4. Формируем текст для эмбеддинга запроса
            interests_qs = Interest.objects.filter(id__in=interests_list)

            parts = []
            for intr in interests_qs:
                parts.append(intr.label)
                parts.append(intr.description)

            if note:
                parts.append(note)

            query_text = ". ".join(parts)
            query_embedding = generate_embedding(query_text)

            # 5. Фильтрация по окружности
            center_lat = (point_a.coordinates_lat + point_b.coordinates_lat) / 2
            center_lng = (point_a.coordinates_lng + point_b.coordinates_lng) / 2

            radius_m = haversine(
                point_a.coordinates_lat, point_a.coordinates_lng,
                point_b.coordinates_lat, point_b.coordinates_lng
            ) / 2
            radius_m += radius_m * 0.2

            filtered = []
            for p in candidate_points:
                dist = haversine(center_lat, center_lng, p.coordinates_lat, p.coordinates_lng)
                if dist <= radius_m:
                    filtered.append(p)
            if not filtered:
                return Response({"error": "No points found in radius"}, status=404)

            # 6. Подтягиваем эмбеддинги точек
            embeddings = {
                pe.point_id: pe.embedding
                for pe in PointEmbedding.objects.filter(point__in=filtered)
            }

            # 7. Косинусная близость
            def cosine(a, b):
                return dot(a, b) / (norm(a) * norm(b))

            best_point = None
            best_score = -1

            for p in filtered:
                emb = embeddings.get(p.id)
                if not emb:
                    continue
                score = cosine(query_embedding, emb)
                if score > best_score:
                    best_score = score
                    best_point = p

            if not best_point:
                return Response({"error": "No suitable point found"}, status=404)
            # 8. Вставляем точку в маршрут
            seq.insert(between_index + 1, best_point.id)
            route.point_sequence = seq
            route.points.add(best_point)
            route.save()
            # --- 9. Пересчёт времени, расстояния и стоимости маршрута ---

            # 9.1. Формат для расчёта времени
            points_for_time = [{"id": pid} for pid in seq]

            # 9.2. Формат для расчёта расстояния и стоимости
            # Гарантируем правильный порядок точек
            points_for_distance_and_cost = []
            point_filter = {p.id: p for p in Point.objects.filter(id__in=seq)}

            for pid in seq:
                p = point_filter.get(pid)
                if p:
                    points_for_distance_and_cost.append(p)

            # 9.3. Карта точек
            point_map = {p.id: p for p in points_for_distance_and_cost}

            # 9.5. Пересчитываем время маршрута
            lat0 = float(route.lat0)
            lon0 = float(route.lon0)
            time_calc = calculate_route_times(points_for_time, point_map, lat0, lon0)
            # 9.6. Пересчитываем расстояние
            total_meters = calculate_total_meters(points_for_distance_and_cost)
            # 9.7. Пересчитываем стоимость
            total_cost = calculate_total_cost(points_for_distance_and_cost)
            # 9.8. Сохраняем в маршрут
            route.total_duration = time_calc["total_time"]
            route.walk_time_minutes = time_calc["walk_time"]
            route.visit_time_minutes = time_calc["visit_time"]
            route.total_meters = total_meters
            route.total_cost = total_cost
            route.save()

            # --- 10. Формируем ответ в нужном формате ---

            # Берём точки как объекты Point
            points_for_response = points_for_distance_and_cost

            points_payload = []
            for p in points_for_response:
                points_payload.append({
                    "id": str(p.id),
                    "name": p.name,
                    "description": p.description,
                    "reason": p.description,  # временно reason = description
                    "image_url": p.image_url if hasattr(p, "image_url") else None,
                    "average_rating": p.average_rating,
                    "reviews_count": p.reviews_count,
                    "visit_time": f"{p.average_visit_duration or 30} мин",
                    "tags": [t.name for t in p.tags.all()] if hasattr(p, "tags") else [],
                    "coordinates": {
                        "lat": float(p.coordinates_lat),
                        "lng": float(p.coordinates_lng)
                    }
                })

            response_payload = {
                "status": "success",
                "data": {
                    "route_id": str(route.id),
                    "user_id": route.user_id,
                    "total_duration": route.total_duration,
                    "total_meters": route.total_meters,
                    "total_cost": route.total_cost,
                    "walk_time": route.walk_time_minutes,
                    "visit_time": route.visit_time_minutes,
                    "route_name": route.description,
                    "points": points_payload
                }
            }

            return Response(response_payload, status=200)


        except Route.DoesNotExist:
            return Response({"error": "Route not found"}, status=404)
        except Exception as e:
            return Response({"error": str(e)}, status=500)
