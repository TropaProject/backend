from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework import status, permissions
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken, TokenError
from .serializers import RegisterSerializer, LoginSerializer, UserSerializer
from ..routes.models import Route,Point
from django.db.models import Sum, Count, Max

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
                {"status": "success", "data": {"access": new_access}},
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
        serializer = UserSerializer(request.user)
        return Response(
            {"status": "success", "data": serializer.data},
            status=status.HTTP_200_OK
        )


class UserRoutesListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        status_filter = request.query_params.get("status")
        limit = int(request.query_params.get("limit", 20))
        offset = int(request.query_params.get("offset", 0))

        qs = Route.objects.filter(user=request.user).order_by("-created_at")

        if status_filter:
            qs = qs.filter(status=status_filter)

        routes = qs[offset:offset+limit]

        data = [
            {
                "route_id": r.id,
                "description": r.description,
                "total_duration": r.total_duration,
                "total_cost": r.total_cost,
                "status": r.status,
                "created_at": r.created_at.isoformat(),
                "updated_at": r.updated_at.isoformat() if hasattr(r, "updated_at") else None,
            }
            for r in routes
        ]

        return Response({"status": "success", "data": data}, status=status.HTTP_200_OK)


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
        total_distance_km = 0.0  # пока заглушка

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