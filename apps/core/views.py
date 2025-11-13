import json

from django.shortcuts import get_object_or_404
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction

from .services import generate_embedding,build_point_text
from apps.routes.models import Point, PointEmbedding



class EmbedMissingPointsView(APIView):


    def get(self, request):
        created = 0
        for point in Point.objects.all():
            if not hasattr(point, "pointembedding"):
                text = build_point_text(point)
                embedding = generate_embedding(text)
                PointEmbedding.objects.create(point=point, embedding=embedding)
                created += 1

        return Response(
            {"status": "success", "created_embeddings": created},
            status=status.HTTP_201_CREATED
        )


class EmbedRefreshPointsView(APIView):


    def get(self, request):
        refreshed = 0
        with transaction.atomic():
            for point in Point.objects.all():
                text = build_point_text(point)
                embedding = generate_embedding(text)
                PointEmbedding.objects.update_or_create(
                    point=point,
                    defaults={"embedding": embedding}
                )
                refreshed += 1

        return Response(
            {"status": "success", "refreshed_embeddings": refreshed},
            status=status.HTTP_200_OK
        )
class EmbedUpdatePointView(APIView):


    def get(self, request, point_id):
        point = get_object_or_404(Point, id=point_id)

        # собираем текст из description + tags + interests + moods
        text = build_point_text(point)

        # генерируем новый эмбеддинг
        embedding = generate_embedding(text)

        # обновляем или создаём запись
        with transaction.atomic():
            PointEmbedding.objects.update_or_create(
                point=point,
                defaults={"embedding": embedding}
            )

        return Response(
            {
                "status": "success",
                "point_id": point.id,
                "message": "Эмбеддинг обновлён"
            },
            status=status.HTTP_200_OK
        )


# views.py
from django.http import JsonResponse

# views.py
from django.shortcuts import render


def map_view(request):
    points = Point.objects.all().values("name", "coordinates_lat", "coordinates_lng")
    # преобразуем Decimal → float
    points_list = []
    for p in points:
        points_list.append({
            "name": p["name"],
            "coordinates_lat": float(p["coordinates_lat"]),
            "coordinates_lng": float(p["coordinates_lng"]),
        })
    return render(request, "map.html", {"points_json": json.dumps(points_list)})