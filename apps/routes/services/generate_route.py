import json
from collections import defaultdict
import numpy as np
import math
from typing import Dict, Any, List
from openai import OpenAI
from django.conf import settings

from apps.routes.models import Point, PointEmbedding


def build_yandex_map_url(points):
    """
    Формирует ссылку на маршрут в Яндекс.Картах (режим пешком).
    points: список словарей [{"lat": 55.751244, "lng": 37.618423}, ...]
    """
    if not points:
        return None
    coords_str = "~".join([f"{p['lat']},{p['lng']}" for p in points])
    return f"https://yandex.ru/maps/?rtext={coords_str}&rtt=walk"


def haversine(lat1, lon1, lat2, lon2):
    """
    Возвращает расстояние в метрах между двумя координатами по формуле Хаверсина.
    """
    R = 6371000  # радиус Земли в метрах
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


client = OpenAI(api_key=settings.OPENAI_API_KEY,
                base_url="https://api.proxyapi.ru/openai/v1")


class RoutePipeline:
    def __init__(self, req_payload: Dict[str, Any], gpt_text: str, a: float = 0.7, b: float = 0.3,
                 radius_km: float = 2.0):
        """
        Инициализация пайплайна.
        req_payload — запрос пользователя (JSON).
        gpt_text — заранее полученный текст от GPT (описание маршрута).
        a, b — веса для комбинирования эмбеддингов GPT и структурных данных.
        """
        self.req_payload = req_payload
        self.gpt_text = gpt_text
        self.a = a
        self.b = b
        self.E_gpt = None
        self.E_struct = None
        self.E_final = None
        self.filtered_points = None
        self.final_points = None
        self.radius_km = radius_km

    # --- Шаг 1: эмбеддинг текста GPT ---
    def embed_gpt_text(self):
        """
        Считаем эмбеддинг текста, заранее полученного от GPT.
        """
        self.E_gpt = np.array(
            client.embeddings.create(model="text-embedding-3-small", input=self.gpt_text).data[0].embedding
        )
        return self.E_gpt

    # --- Шаг 2: эмбеддинг структурных данных ---
    def embed_struct_data(self):
        """
        Формируем краткий текст из полей запроса и считаем его эмбеддинг.
        """
        struct_text = (
            f"{self.req_payload.get('city_id')}, {self.req_payload.get('time_of_day')}, "
            f"интересы: {', '.join(self.req_payload.get('interests', []))}, "
            f"настроение: {', '.join(self.req_payload.get('mood', []))}, "
            f"бюджет: {self.req_payload.get('budget')}, "
            f"транспорт: {self.req_payload.get('transport')}, "
            f"{self.req_payload.get('duration_minutes')} минут, "
            f"район: {self.req_payload.get('start_area')}, "
            f"старт: {self.req_payload.get('start_point')}"
        )
        self.E_struct = np.array(
            client.embeddings.create(model="text-embedding-3-small", input=struct_text).data[0].embedding
        )
        return self.E_struct

    # --- Шаг 3: комбинирование эмбеддингов ---
    def combine_embeddings(self):
        """
        Комбинируем эмбеддинг GPT-текста и структурных данных.
        """
        if self.E_gpt is None:
            self.embed_gpt_text()
        if self.E_struct is None:
            self.embed_struct_data()
        self.E_final = self.a * self.E_gpt + self.b * self.E_struct
        self.E_final = self.E_final / (np.linalg.norm(self.E_final) + 1e-9)
        return self.E_final.tolist()

    # --- Шаг 4: фильтр по старту ---
    def filter_by_start_point(self, pois: List[Dict[str, Any]], radius_km: float) -> List[Dict[str, Any]]:
        """
        Фильтруем точки по радиусу от стартовой точки.
        radius_km: радиус в километрах (например, 0.5, 1, 3).
        Возвращает список точек в пределах указанного радиуса.
        """
        # стартовая точка пользователя
        lat0, lon0 = map(float, self.req_payload.get("start_point").split(","))

        def haversine_filter(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
            """
            Возвращает расстояние между двумя координатами в километрах.
            """
            R = 6371.0  # радиус Земли в км
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            phi1 = math.radians(lat1)
            phi2 = math.radians(lat2)

            a = math.sin(dlat / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlon / 2) ** 2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            return R * c  # расстояние в км

        # фильтрация точек
        self.filtered_points = [
            p for p in pois
            if haversine_filter(lat0, lon0, float(p['coordinates_lat']), float(p['coordinates_lng'])) <= radius_km
        ]

        return self.filtered_points

    # --- Шаг 5: поиск по эмбеддингам ---
    def search_by_embeddings(self, pois: List[Dict[str, Any]], top_n: int = 50) -> List[Dict[str, Any]]:
        """
        Считаем косинусное сходство между E_final и эмбеддингами точек.
        Берём top_n ближайших.
        """

        def cosine_similarity(vec1, vec2):
            v1 = np.array(vec1)
            v2 = np.array(vec2)
            return float(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2) + 1e-9))

        results = []
        for p in pois:
            sim = cosine_similarity(self.E_final, p['embedding'])
            results.append({**p, "similarity": sim})

        results.sort(key=lambda x: x["similarity"], reverse=True)
        return results[:top_n]

    # --- Шаг 6: стохастический отбор ---
    def stochastic_selection(self, pois: List[Dict[str, Any]], k: int = 30) -> List[Dict[str, Any]]:
        """
        Из top-N выбираем k точек случайным образом, но с весами по similarity.
        """
        sims = np.array([p["similarity"] for p in pois])
        weights = sims / sims.sum()
        chosen_idx = np.random.choice(len(pois), size=min(k, len(pois)), replace=False, p=weights)
        chosen = [pois[i] for i in chosen_idx]
        chosen_sorted = sorted(chosen, key=lambda p: p["similarity"], reverse=True)
        return chosen_sorted

    # --- Шаг 7: финальный выбор точек GPT ---
    def final_selection_gpt(self, candidate_points: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Отправляем список 30 точек в GPT с инструкцией:
        «Выбери 5–7 точек для маршрута, учитывая интересы, настроение, бюджет и логистику».
        GPT должен вернуть строго JSON-словарь с выбранными точками в порядке движения.
        """

        points_text = "\n".join([
            f"- id: {p['id']}, name: {p['name']}, desc: {p['description']}, "
            f"coords: [{p['coordinates_lat']}, {p['coordinates_lng']}]"
            for p in candidate_points
        ])
        prompt = (
            f"Исходный запрос пользователя:\n{self.req_payload}\n\n"
            f"Описание маршрута от GPT:\n{self.gpt_text}\n\n"
            f"Список доступных точек (30):\n{points_text}\n\n"
            f"Задача: выбери 7-10 точек для маршрута, учитывая интересы, настроение, бюджет и логистику.\n"
            f"Важные требования:\n"
            f"- Верни строго JSON-словарь.\n"
            f"- Формат: {{\"points\": [{{\"id\": \"...\", \"order\": 1, \"reason\": \"...\"}}, ...]}}.\n"
            f"- Используй только id из списка.\n"
            f"- Список точек отсортирован по приоритету (начало списка важнее).\n"
            f"- Выбирай преимущественно из первых точек, но допускается брать более дальние, если они лучше подходят для маршрута.\n"
            f"- Расположи точки в порядке движения по координатам (от стартовой точки).\n"
            f"- Избегай точек, которые находятся на противоположных концах радиуса,\n"
            f"- Формируй логичный маршрут а не разбросанные места\n"
            f"- Не добавляй лишнего текста, только JSON.\n"
            f"- Верни только JSON без форматирования, без ```json и других обёрток."
        )

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = response.choices[0].message.content.strip()
        # Попробуем распарсить JSON
        try:
            result_json = json.loads(result_text)
        except Exception:
            result_json = {"points": []}

        # --- Жадный алгоритм ближайшего соседа ---
        if result_json.get("points"):
            # словарь для быстрого доступа к координатам
            point_map = {str(p["id"]): p for p in candidate_points}

            # стартовая точка
            lat0, lon0 = map(float, self.req_payload.get("start_point").split(","))
            ordered = []
            remaining = result_json["points"]

            current_lat, current_lon = lat0, lon0
            order = 1

            while remaining:
                # ищем ближайшую точку
                next_point = min(
                    remaining,
                    key=lambda p: haversine(
                        current_lat, current_lon,
                        float(point_map[p["id"]]["coordinates_lat"]),
                        float(point_map[p["id"]]["coordinates_lng"])
                    )
                )
                # добавляем в маршрут
                next_point["order"] = order
                ordered.append(next_point)
                order += 1

                # обновляем текущие координаты
                current_lat = float(point_map[next_point["id"]]["coordinates_lat"])
                current_lon = float(point_map[next_point["id"]]["coordinates_lng"])

                # убираем точку из списка
                remaining.remove(next_point)

            result_json["points"] = ordered
            # --- Расчёт времени маршрута ---
            user_time_limit = int(self.req_payload.get("duration_minutes", 180))  # время от пользователя
            max_time = user_time_limit * 1.4  # +20% буфер
            walk_speed_m_per_min = 70  # средняя скорость ходьбы

            total_time = 0.0
            walk_time = 0.0
            visit_time = 0.0
            total_distance = 0.0

            final_points = []
            prev_lat, prev_lon = lat0, lon0

            for p in ordered:
                # координаты точки
                lat = float(point_map[p["id"]]["coordinates_lat"])
                lon = float(point_map[p["id"]]["coordinates_lng"])

                # расстояние и время ходьбы до этой точки
                dist = haversine(prev_lat, prev_lon, lat, lon)
                walk_time_inc = dist / walk_speed_m_per_min

                # время посещения из модели
                visit_time_inc = int(point_map[p["id"]].get("average_visit_duration", 30))

                # проверка лимита
                if (total_time + walk_time_inc + visit_time_inc) <= max_time:
                    total_time += walk_time_inc + visit_time_inc
                    walk_time += walk_time_inc
                    visit_time += visit_time_inc
                    total_distance += dist

                    final_points.append(p)
                    prev_lat, prev_lon = lat, lon
                else:
                    break  # дальше уже не влезаем по времени

            result_json["points"] = final_points
            result_json["total_time"] = int(round(total_time))
            result_json["walk_time_minutes"] = int(round(walk_time))
            result_json["visit_time_minutes"] = int(round(visit_time))
        self.final_points = result_json
        return result_json

    # --- Адаптер для моделей Django ---
    @staticmethod
    def adapt_points(points: List[Point]) -> List[Dict[str, Any]]:
        """
        Превращаем список объектов Point + PointEmbedding в словари,
        удобные для работы пайплайна.
        """
        adapted = []
        embeddings = PointEmbedding.objects.filter(point__in=points).select_related("point")
        for pe in embeddings:
            adapted.append({
                "id": pe.point.id,
                "name": pe.point.name,
                "description": pe.point.description,
                "coordinates_lat": float(pe.point.coordinates_lat),
                "coordinates_lng": float(pe.point.coordinates_lng),
                "embedding": pe.embedding,
            })
        return adapted

    def compute_top_n(self, filtered_count: int, radius_km: float) -> int:
        """
        Адаптивный выбор количества точек для семантического отбора.
        """
        if filtered_count < 20:
            return filtered_count

        # коэффициент охвата по радиусу
        if radius_km <= 1:
            coverage = 1.0
        elif radius_km <= 2:
            coverage = 0.4
        else:
            coverage = 0.3

        min_floor = 20  # минимум точек для семантики
        max_cap = 70  # максимум точек для семантики

        top_n = int(round(filtered_count * coverage))
        top_n = max(min_floor, top_n)
        top_n = min(max_cap, top_n, filtered_count)
        return top_n
    def run_pipeline(self, pois: List[Point]) -> Dict[str, Any]:
        """
        Запускаем весь пайплайн:
        1. Комбинирование эмбеддингов
        2. Фильтр по радиусу
        3. Поиск по эмбеддингам (top-50)
        4. Стохастический отбор (30 точек)
        5. Финальный выбор GPT (5–7 точек)
        """
        # шаг 1: итоговый эмбеддинг
        # шаг 1: итоговый эмбеддинг
        self.combine_embeddings()

        # шаг 2: адаптируем точки из БД в словари
        pois_dicts = self.adapt_points(pois)
        print(f"[LOG] Всего точек в городе: {len(pois_dicts)}")

        # шаг 3: фильтр по радиусу
        filtered = self.filter_by_start_point(pois_dicts, radius_km=self.radius_km)
        print(f"[LOG] После фильтра по радиусу осталось: {len(filtered)} точек")

        # шаг 4: поиск по эмбеддингам
        top_n = self.compute_top_n(len(filtered), self.radius_km)
        top_points = self.search_by_embeddings(filtered, top_n=top_n)
        print(f"[LOG] Топ-{top_n} точек по сходству выбрано")

        # шаг 5: стохастический отбор (условный)
        if top_n > 40:
            selected = self.stochastic_selection(top_points, k=min(35, top_n))
            print(f"[LOG] Стохастически выбрано: {len(selected)} точек")
        else:
            selected = top_points
            print(f"[LOG] Стохастика пропущена, выбраны все {len(selected)} точек")

        # шаг 6: финальный выбор GPT
        final_result = self.final_selection_gpt(selected)
        print(f"[LOG] Финальный маршрут сформирован")

        return final_result


def build_map_url(points):
    """
    Генерируем простой URL для карты (пример для Яндекс.Карт).
    Можно заменить на свой генератор маршрутов.
    """
    if not points:
        return None
    coords = "~".join([f"{p['coordinates']['lat']},{p['coordinates']['lng']}" for p in points])
    return f"https://yandex.ru/maps/?pt={coords}"
