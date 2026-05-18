from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer
from ..routes.models import Route,Point
from django.db.models import Sum, Count, Max
from django.contrib.auth import get_user_model

User = get_user_model()


def _route_main_point(route):
    points = list(route.points.all())
    if route.point_sequence:
        first_id = str(route.point_sequence[0])
        main_point = next((p for p in points if str(p.id) == first_id), None)
        if main_point:
            return main_point
    return points[0] if points else None


def _serialize_public_route_card(route, request_user=None):
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
        "author": {
            "id": route.user.id,
            "username": route.user.username,
            "email": route.user.email,
        } if route.user else None,
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


def _build_routes_statistics(routes_qs):
    total_routes = routes_qs.count()
    completed_routes = routes_qs.filter(status="done").count()
    active_routes = routes_qs.filter(status="going").count()
    total_duration = routes_qs.aggregate(Sum("total_duration"))["total_duration__sum"] or 0
    total_cost = routes_qs.aggregate(Sum("total_cost"))["total_cost__sum"] or 0
    total_distance_m = routes_qs.aggregate(Sum("total_meters"))["total_meters__sum"] or 0
    last_activity = routes_qs.aggregate(Max("created_at"))["created_at__max"]
    unique_places = Point.objects.filter(route__in=routes_qs).values("id").distinct().count()
    favourite_city = (
        routes_qs.values("city__name")
        .annotate(cnt=Count("id"))
        .order_by("-cnt")
        .first()
    )

    return {
        "total_routes": total_routes,
        "completed_routes": completed_routes,
        "active_routes": active_routes,
        "total_duration_minutes": total_duration,
        "total_distance_km": total_distance_m // 1000,
        "total_cost": total_cost,
        "unique_places": unique_places,
        "favourite_city": favourite_city["city__name"] if favourite_city else None,
        "last_activity": last_activity.isoformat() if last_activity else None,
    }


def _get_positive_int(value, default, max_value=100):
    try:
        value = int(value)
    except (TypeError, ValueError):
        return default
    if value < 0:
        return default
    return min(value, max_value)


class RegisterView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response(serializer.to_representation(user), status=status.HTTP_200_OK)
        return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(
            {"status": "error", "errors": serializer.errors},
            status=status.HTTP_400_BAD_REQUEST
        )

class RefreshView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        refresh_token = request.data.get("refresh")
        if not refresh_token:
            return Response(
                {"status": "error", "errors": {"refresh": ["This field is required."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            refresh = RefreshToken(refresh_token)
            new_access = str(refresh.access_token)
            return Response(
                {
                    "access": new_access,
                    "refresh": str(refresh)  # добавляем refresh для совместимости
                },
                status=status.HTTP_200_OK,
            )
        except TokenError:
            return Response(
                {"status": "error", "errors": {"refresh": ["Invalid or expired token."]}},
                status=status.HTTP_400_BAD_REQUEST,
            )


class UserView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(
            {"status": "success", "data": serializer.data},
            status=status.HTTP_200_OK
        )


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, user_id):
        routes_limit = _get_positive_int(request.query_params.get("routes_limit"), 20)
        routes_offset = _get_positive_int(request.query_params.get("routes_offset"), 0, max_value=1000)

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return Response(
                {"status": "error", "message": "User not found"},
                status=status.HTTP_404_NOT_FOUND
            )

        serializer = UserSerializer(user, context={"request": request})
        public_routes_qs = (
            Route.objects
            .filter(user=user, is_public=True)
            .select_related("user", "city", "original_route")
            .prefetch_related("points__tags", "points__interests")
            .order_by("-created_at")
        )
        public_routes_total_count = public_routes_qs.count()
        public_routes = public_routes_qs[routes_offset:routes_offset + routes_limit]
        all_routes_qs = Route.objects.filter(user=user)

        data = dict(serializer.data)
        data["statistics"] = _build_routes_statistics(all_routes_qs)
        data["public_routes_total_count"] = public_routes_total_count
        data["public_routes"] = [
            _serialize_public_route_card(route, request.user)
            for route in public_routes
        ]

        return Response(
            {"status": "success", "data": data},
            status=status.HTTP_200_OK
        )


from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import permissions, status

class UserRoutesListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        status_filter = request.query_params.get("status")
        public_only = str(request.query_params.get("public_only", "")).lower() == "true"
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))

        qs = Route.objects.filter(user=request.user).order_by("-created_at")

        if status_filter:
            qs = qs.filter(status=status_filter)
        if public_only:
            qs = qs.filter(is_public=True)

        total_count = qs.count()  # ← для пагинации
        routes = qs[offset:offset+limit]

        data = []
        for r in routes:
            points = list(r.points.all())
            main_point = None

            # основная точка = первая из point_sequence
            if r.point_sequence:
                first_id = r.point_sequence[0]
                main_point = next((p for p in points if str(p.id) == first_id), None)

            # fallback: если sequence пустой или точка не найдена
            if not main_point and points:
                main_point = points[0]

            data.append({
                "route_id": r.id,
                "title": r.title,
                "description": r.description,
                "total_duration": r.total_duration,
                "total_cost": r.total_cost,
                "status": r.status,
                "is_public": r.is_public,
                "public_uses_count": r.public_uses_count,
                "original_route_id": r.original_route_id,
                "created_at": r.created_at.isoformat(),
                "updated_at": getattr(r, "updated_at", None).isoformat() if hasattr(r, "updated_at") and r.updated_at else None,
                "city": r.city.name if r.city else None,
                "image": main_point.image_url if main_point else None,
                "tag": main_point.tags.first().name if main_point and main_point.tags.exists() else None,
                "interest": main_point.interests.first().label if main_point and main_point.interests.exists() else None,
                "best_visit_time": main_point.best_visit_time[0] if main_point and main_point.best_visit_time else None,
            })

        return Response(
            {"status": "success", "total_count": total_count, "data": data},
            status=status.HTTP_200_OK
        )



class UserStatisticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = Route.objects.filter(user=request.user)

        total_routes = qs.count()
        completed_routes = qs.filter(status="done").count()
        active_routes = qs.filter(status="going").count()

        total_duration = qs.aggregate(Sum("total_duration"))["total_duration__sum"] or 0
        total_cost = qs.aggregate(Sum("total_cost"))["total_cost__sum"] or 0
        last_activity = qs.aggregate(Max("created_at"))["created_at__max"]

        # Уникальные места (по id точек)
        unique_places = Point.objects.filter(route__user=request.user).values("id").distinct().count()

        # Протяжённость маршрутов (если в модели Point есть координаты lat/lng)
        # Здесь можно вставить функцию расчёта расстояния по координатам
        total_distance_m = qs.aggregate(Sum("total_meters"))["total_meters__sum"] or 0
        total_distance_km = total_distance_m//1000
        # Любимый город (где больше всего маршрутов)
        favourite_city = (
            qs.values("city__name")
              .annotate(cnt=Count("id"))
              .order_by("-cnt")
              .first()
        )
        favourite_city_name = favourite_city["city__name"] if favourite_city else None

        data = {
            "total_routes": total_routes,
            "completed_routes": completed_routes,
            "active_routes": active_routes,
            "total_duration_minutes": total_duration,
            "total_distance_km": total_distance_km,
            "total_cost": total_cost,
            "unique_places": unique_places,
            "favourite_city": favourite_city_name,
            "last_activity": last_activity.isoformat() if last_activity else None,
        }

        return Response({"status": "success", "data": data}, status=status.HTTP_200_OK)
