import json

from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions
from django.db import transaction

from .services import generate_embedding,build_point_text
from apps.routes.models import Point, PointEmbedding, Mood, Tag, Interest


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
from django.http import JsonResponse, HttpResponse

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


def check_points_page(request):
    """
    Страница с формой загрузки и результатами проверки.
    """
    context = {}
    cleaned_json = None

    if request.method == "POST":
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            context["error"] = "Файл не передан"
        else:
            try:
                data = json.load(uploaded_file)
                missing_interests, missing_tags, missing_moods = set(), set(), set()
                cleaned_data = []

                for obj in data:
                    fields = obj.get("fields", {})

                    # фильтруем interests
                    interests = [
                        iid for iid in fields.get("interests", [])
                        if Interest.objects.filter(pk=iid).exists()
                    ]
                    for iid in fields.get("interests", []):
                        if not Interest.objects.filter(pk=iid).exists():
                            missing_interests.add(iid)

                    # фильтруем tags
                    tags = [
                        tid for tid in fields.get("tags", [])
                        if Tag.objects.filter(pk=tid).exists()
                    ]
                    for tid in fields.get("tags", []):
                        if not Tag.objects.filter(pk=tid).exists():
                            missing_tags.add(tid)

                    # фильтруем moods
                    moods = [
                        mid for mid in fields.get("moods", [])
                        if Mood.objects.filter(pk=mid).exists()
                    ]
                    for mid in fields.get("moods", []):
                        if not Mood.objects.filter(pk=mid).exists():
                            missing_moods.add(mid)

                    # обновляем объект
                    fields["interests"] = interests
                    fields["tags"] = tags
                    fields["moods"] = moods
                    obj["fields"] = fields
                    cleaned_data.append(obj)

                context["missing_interests"] = list(missing_interests)
                context["missing_tags"] = list(missing_tags)
                context["missing_moods"] = list(missing_moods)
                context["status"] = "ok" if not (missing_interests or missing_tags or missing_moods) else "errors"

                # сохраняем очищенный JSON в строку
                cleaned_json = json.dumps(cleaned_data, ensure_ascii=False, indent=2)
                request.session["cleaned_json"] = cleaned_json  # кладём в сессию для скачивания

            except Exception as e:
                context["error"] = f"Ошибка парсинга JSON: {e}"

    return render(request, "check_points.html", context)


def download_cleaned_json(request):
    """
    Отдаёт очищенный JSON для скачивания.
    """
    cleaned_json = request.session.get("cleaned_json")
    if not cleaned_json:
        return JsonResponse({"error": "Нет данных для скачивания"}, status=400)

    response = HttpResponse(cleaned_json, content_type="application/json")
    response["Content-Disposition"] = 'attachment; filename="history_5.json"'
    return response


