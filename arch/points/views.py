# views.py
import json
import logging
import requests
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.core.cache import cache
from apps.core.models import City, CityArea
from .api.ChatGPT import process_api_feature
from .forms import PlaceSearchForm, TOURIST_CATEGORY_CHOICES
from .utils import build_rect_from_bbox
from .api.wikidata import get_wikidata_description_and_image
from django.views.decorators.http import require_POST
from django.db import transaction
from apps.core.models import City, Interest, Mood,Point
import uuid

logger = logging.getLogger(__name__)

ALLOWED_CATEGORIES = set(k for k, _ in TOURIST_CATEGORY_CHOICES)

@ensure_csrf_cookie
def place_search_page(request):
    city_id = request.GET.get("city")
    form = PlaceSearchForm(city_id=city_id)
    return render(request, "points/place_search.html", {"form": form})

@require_GET
def api_city_areas(request):
    city_id = request.GET.get("city_id")
    if not city_id:
        return JsonResponse({"error": "city_id is required"}, status=400)
    areas = CityArea.objects.filter(city_id=city_id).values("id", "name")
    return JsonResponse({"areas": list(areas)})

@require_POST
def api_places(request):
    """
    Принимает JSON:
    {
      "city_id": "moscow",
      "area_id": 123,
      "categories": ["leisure.park","tourism.museum"],
      "limit": 20,
      "lang": "ru"
    }
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return HttpResponseBadRequest("Invalid JSON")

    city_id = payload.get("city_id")
    area_id = payload.get("area_id")
    categories = payload.get("categories") or []
    limit = int(payload.get("limit") or 20)
    lang = payload.get("lang") or "ru"

    if not city_id:
        return JsonResponse({"error": "city_id is required"}, status=400)
    if not categories:
        return JsonResponse({"error": "at least one category is required"}, status=400)

    # Валидация категорий, лимита, языка
    categories = [c for c in categories if c in ALLOWED_CATEGORIES]
    if not categories:
        return JsonResponse({"error": "no valid categories"}, status=400)
    limit = max(1, min(100, limit))
    lang = "ru" if lang not in ("ru", "en") else lang

    # Достаём bbox: приоритет у района
    try:
        city = City.objects.get(pk=city_id)
    except City.DoesNotExist:
        return JsonResponse({"error": "city not found"}, status=404)

    bbox = None
    if area_id:
        try:
            area = CityArea.objects.get(pk=area_id, city=city)
            bbox = area.bbox
        except CityArea.DoesNotExist:
            return JsonResponse({"error": "area not found for this city"}, status=404)

    if bbox is None:
        bbox = city.bbox

    if not bbox:
        return JsonResponse({"error": "no bbox available for selection"}, status=400)

    rect = build_rect_from_bbox(bbox)
    categories_param = ",".join(categories)

    # Ключ кеша (10 минут): параметры запроса
    cache_key = f"geoapify:{rect}:{categories_param}:{limit}:{lang}"
    cached = cache.get(cache_key)
    if cached:
        return JsonResponse(cached, safe=False)

    api_key = getattr(settings, "GEOAPIFY_API_KEY", None)
    if not api_key:
        return JsonResponse({"error": "api key is not configured"}, status=500)

    url = "https://api.geoapify.com/v2/places"
    params = {
        "categories": categories_param,
        "filter": f"rect:{rect}",
        "limit": limit,
        "lang": lang,
        "apiKey": api_key,
    }

    try:
        # Максимально лёгкий запрос: без лишних параметров, с таймаутом
        resp = requests.get(url, params=params, timeout=8)
    except requests.RequestException as e:
        logger.exception("Geoapify request failed")
        return JsonResponse({"error": "geoapify request failed"}, status=502)

    if resp.status_code != 200:
        return JsonResponse({"error": "geoapify error", "status": resp.status_code, "body": resp.text[:500]}, status=resp.status_code)

    data = resp.json()
    for idx, feature in enumerate(data.get("features", [])):
        props = feature.get("properties", {})
        wiki_id = props.get("wiki_and_media", {}).get("wikidata")
        if wiki_id:
            desc, img = get_wikidata_description_and_image(wiki_id, lang=lang)
            if desc:
                props["description_wiki"] = desc
            if img:
                props["image_url_wiki"] = img

        # Новый шаг — обогащение через GPT
        try:
            enriched = process_api_feature(feature)
            # перезапишем feature.properties и добавим новые поля
            data["features"][idx]["properties"].update({
                "description": enriched.get("description"),
                "interests": enriched.get("interests", []),
                "moods": enriched.get("moods", []),
                "tags": enriched.get("tags", []),
                "raw_tags": enriched.get("raw_tags", []),
                "all_tags": enriched.get("all_tags", []),
            })
        except Exception as e:
            logger.exception("GPT enrichment failed")
            # Можно просто пропустить или проставить пустые поля
            data["features"][idx]["properties"].update({
                "description": None,
                "interests": [],
                "moods": [],
                "tags": [],
                "raw_tags": props.get("categories", []),
                "all_tags": props.get("categories", []),
            })

    # Кешируем уже обогащённый ответ
    cache.set(cache_key, data, timeout=60 * 10)
    return JsonResponse(data, safe=False)



@require_POST
def api_save_points(request):
    """
    Принимает JSON: { "city_id": "moscow", "points": [ {данные точки}, ... ] }
    """
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    city_id = payload.get("city_id")
    points_data = payload.get("points", [])

    if not city_id or not points_data:
        return JsonResponse({"error": "city_id and points are required"}, status=400)

    try:
        city = City.objects.get(pk=city_id)
    except City.DoesNotExist:
        return JsonResponse({"error": "City not found"}, status=404)

    created_points = []
    skipped_points = []

    with transaction.atomic():
        for p in points_data:
            # Чистим и нормализуем имя
            raw_name = p.get("name") or "(без названия)"
            name = raw_name.strip()

            # Проверка на дубль по городу и имени (без учёта регистра)
            if Point.objects.filter(city=city, name__iexact=name).exists():
                skipped_points.append(name)
                continue

            point = Point.objects.create(
                id=str(uuid.uuid4()),
                name=name[:1000],
                description=p.get("description") or "",
                tags=[t[:600] for t in (p.get("tags") or [])],  # защита от слишком длинных тегов
                image_url=p.get("image_url"),
                city=city,
                coordinates_lat=p.get("coordinates_lat") or p.get("lat"),
                coordinates_lng=p.get("coordinates_lng") or p.get("lon"),
                average_visit_duration=p.get("average_visit_duration") or 60,
                average_cost=p.get("average_cost"),
                is_partner=False,
                best_visit_time=[bt[:20] for bt in p.get("best_visit_time", ["any"])],
                working_hours_json=p.get("working_hours_json"),
                is_seasonal=p.get("is_seasonal", False),
                seasonal_months=p.get("seasonal_months"),
            )

            # M2M: интересы
            for interest_id in p.get("interests", []):
                try:
                    interest = Interest.objects.get(pk=interest_id)
                    point.interests.add(interest)
                except Interest.DoesNotExist:
                    pass

            # M2M: настроения
            for mood_id in p.get("moods", []):
                try:
                    mood = Mood.objects.get(pk=mood_id)
                    point.moods.add(mood)
                except Mood.DoesNotExist:
                    pass

            created_points.append(point.id)
    return JsonResponse({"status": "ok", "created_count": len(created_points), "ids": created_points})