import time
import requests
import json

# список зеркал Overpass API
OVERPASS_URLS = [
    "https://overpass-api.de/api/interpreter",
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter"
]

def get_osm_points(lat, lon, radius, categories, retries=3):
    """
    categories может быть строкой (один тег) или списком (несколько тегов).
    retries — количество попыток при ошибке.
    """
    if isinstance(categories, str):
        categories = [categories]

    parts = []
    for cat in categories:
        key, value = cat.split("=")
        parts.append(f'node["{key}"="{value}"](around:{radius},{lat},{lon});')
        parts.append(f'way["{key}"="{value}"](around:{radius},{lat},{lon});')
        parts.append(f'relation["{key}"="{value}"](around:{radius},{lat},{lon});')

    query = f"""
    [out:json][timeout:25];
    (
      {"".join(parts)}
    );
    out tags center;
    """

    for attempt in range(retries):
        for url in OVERPASS_URLS:
            try:
                response = requests.post(url, data={"data": query}, timeout=60)
                if response.status_code != 200:
                    print(f"Ошибка {response.status_code} на {url}, попытка {attempt+1}")
                    continue

                try:
                    data = response.json()
                except Exception as e:
                    print(f"Ошибка парсинга JSON с {url}: {e}")
                    print("Ответ сервера:", response.text[:200])
                    continue

                points = []
                for element in data.get("elements", []):
                    tags = element.get("tags", {})
                    name = tags.get("name", "")
                    if not name:
                        continue
                    point = {
                        "id": element.get("id"),
                        "name": name,
                        "categories": categories,
                        "coordinates_lat": element.get("lat") or element.get("center", {}).get("lat"),
                        "coordinates_lng": element.get("lon") or element.get("center", {}).get("lon"),
                        "address": f"{tags.get('addr:city', '')} {tags.get('addr:street', '')} {tags.get('addr:housenumber', '')}".strip(),
                        "opening_hours": tags.get("opening_hours", ""),
                        "average_cost": tags.get("fee") or tags.get("charge", ""),
                        "phone": tags.get("phone", ""),
                        "website": tags.get("website", ""),
                        "email": tags.get("email", ""),
                        "wheelchair": tags.get("wheelchair", ""),
                        "image_url": tags.get("image") or tags.get("wikimedia_commons", ""),
                        "wikidata": tags.get("wikidata", ""),
                        "wikipedia": tags.get("wikipedia", ""),
                        "description": tags.get("description", "")
                    }
                    points.append(point)
                return points

            except Exception as e:
                print(f"Ошибка запроса к {url}: {e}")
                continue

        print("Повтор через 5 секунд...")
        time.sleep(5)

    return []


def collect_points(circles, categories, output_file="points.json"):
    all_points = {}
    results = []

    for lat, lon, radius in circles:
        print(f"Поиск {categories} вокруг ({lat}, {lon}) радиус {radius}м...")
        points = get_osm_points(lat, lon, radius, categories)
        print(f"Найдено: {len(points)} точек")
        for p in points:
            if p["id"] not in all_points:
                all_points[p["id"]] = p
                results.append(p)
        time.sleep(2)  # пауза между запросами

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"Сохранено {len(results)} уникальных точек в {output_file}")


# 🔎 Пример использования
circles = [
    (55.753673, 37.619881, 790),
    (55.762541, 37.612308, 500),
    (55.770314, 37.607332, 700),
    (55.766157, 37.617797, 190)
]

# один тег
category = "amenity=cafe"
# несколько тегов (ИЛИ)
categories = ["tourism=museum", "amenity=theatre", "amenity=arts_centre", "gallery=yes"]

collect_points(circles, categories, "museum.json")
