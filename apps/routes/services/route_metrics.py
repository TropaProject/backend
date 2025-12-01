import math
import requests

api = "eyJvcmciOiI1YjNjZTM1OTc4NTExMTAwMDFjZjYyNDgiLCJpZCI6IjEwZTQyNDQyMjA2NTRhYTQ4YTViOGY0ZTMyZDg4NzhhIiwiaCI6Im11cm11cjY0In0="

# --- Вспомогательная функция для расчёта расстояния по прямой (fallback) ---
def haversine(lat1, lon1, lat2, lon2):
    R = 6371000  # радиус Земли в метрах
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlambda/2)**2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# --- 1. Расчёт общей стоимости маршрута ---
def calculate_total_cost(points):
    total_cost = sum([p.average_cost for p in points if getattr(p, "average_cost", None)])
    print(f"[INFO] Общая стоимость маршрута: {total_cost}")
    return int(total_cost)


# --- 2. Расчёт общей длительности маршрута ---
def calculate_total_duration(points, api_key=api):
    if api_key and len(points) >= 2:
        coords = [[float(p.coordinates_lng), float(p.coordinates_lat)] for p in points]
        url = "https://api.openrouteservice.org/v2/directions/foot-walking"
        headers = {"Authorization": api_key, "Content-Type": "application/json"}
        body = {"coordinates": coords}

        try:
            resp = requests.post(url, json=body, headers=headers).json()
            print("[DEBUG] Ответ ORS (duration):")
            if "routes" in resp:
                duration_sec = resp["routes"][0]["summary"]["duration"]
                duration_min = int(round(duration_sec / 60))
                print(f"[INFO] Успешно рассчитана длительность: {duration_min} мин")
                return duration_min
        except Exception as e:
            print("[ERROR] Ошибка при запросе ORS (duration):", e)

    duration_fallback = sum([getattr(p, "visit_time", 30) for p in points])
    print(f"[WARN] Fallback длительность: {duration_fallback} мин")
    return int(duration_fallback)


def calculate_total_meters(points, api_key=api):
    if api_key and len(points) >= 2:
        coords = [[float(p.coordinates_lng), float(p.coordinates_lat)] for p in points]
        url = "https://api.openrouteservice.org/v2/directions/foot-walking"
        headers = {"Authorization": api_key, "Content-Type": "application/json"}
        body = {"coordinates": coords}

        try:
            resp = requests.post(url, json=body, headers=headers).json()
            print("[DEBUG] Ответ ORS (distance):")
            if "routes" in resp:
                distance_m = resp["routes"][0]["summary"]["distance"]
                distance_int = int(round(distance_m))
                print(f"[INFO] Успешно рассчитана длина: {distance_int} м")
                return distance_int
        except Exception as e:
            print("[ERROR] Ошибка при запросе ORS (distance):", e)

    total = 0
    for i in range(len(points) - 1):
        p1, p2 = points[i], points[i+1]
        total += haversine(
            float(p1.coordinates_lat), float(p1.coordinates_lng),
            float(p2.coordinates_lat), float(p2.coordinates_lng)
        )
    print(f"[WARN] Fallback длина: {int(total)} м")
    return int(total)
