from django.utils import timezone

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .generator.generator import generate_route_stub
from .models import City, Interest, Mood, CityArea, Route, Feedback
from .serializers import CitySerializer, InterestSerializer, MoodSerializer

# Форма ввода
class FormDataView(APIView):
    def get(self, request):
        cities = City.objects.all()
        interests = Interest.objects.all()
        moods = Mood.objects.all()

        return Response({
            "status": "success",
            "data": {
                "cities": CitySerializer(cities, many=True).data,
                "interests": InterestSerializer(interests, many=True).data,
                "moods": MoodSerializer(moods, many=True).data,
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


class GenerateRouteView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        data = request.data

        city_id = data.get("city_id")
        time_of_day = data.get("time_of_day")
        interests = data.get("interests", [])
        mood = data.get("mood", [])
        budget = data.get("budget")
        transport = data.get("transport")
        duration_minutes = data.get("duration_minutes")
        description = data.get("description")

        if not city_id or not duration_minutes:
            return Response(
                {"status": "error", "message": "city_id и duration_minutes обязательны"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Вызов заглушки вместо ML
        route_data = generate_route_stub(
            city_id, time_of_day, interests, mood, budget, transport, duration_minutes, description, request.user
        )

        return Response({"status": "success", "data": route_data}, status=status.HTTP_200_OK)


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
            route = Route.objects.get(id=id_route, user=request.user)
        except Route.DoesNotExist:
            return Response(
                {"status": "error", "message": "Маршрут не найден или не принадлежит пользователю"},
                status=status.HTTP_404_NOT_FOUND
            )

        data = {
            "route_id": route.id,
            "user_id": route.user.id if route.user else None,
            "description": route.description,
            "total_duration": route.total_duration,
            "total_cost": route.total_cost,
            "status": route.status,
            "point_sequence": route.point_sequence,
            "points": [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "image_url": p.image_url,
                    "coordinates": {
                        "lat": float(p.coordinates_lat),
                        "lng": float(p.coordinates_lng),
                    },
                }
                for p in route.points.all()
            ],
            "created_at": route.created_at.isoformat(),
            "updated_at": route.updated_at.isoformat() if hasattr(route, "updated_at") else None,
        }

        return Response({"status": "success", "data": data}, status=status.HTTP_200_OK)


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