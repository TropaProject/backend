import json
import re
from collections import defaultdict
import numpy as np
import math
from typing import Dict, Any, List
from openai import OpenAI
from django.conf import settings

from apps.routes.models import Point, PointEmbedding
from apps.routes.services.route_metrics import calculate_route_times

client = OpenAI(api_key=settings.OPENAI_API_KEY,
                base_url="https://api.proxyapi.ru/openai/v1")


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
    try:
        # Приведение к float
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)

        R = 6371000.0  # радиус Земли в метрах
        phi1, phi2 = math.radians(lat1), math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)

        a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
        # защита от округления
        a = min(1.0, max(0.0, a))

        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    except Exception as e:
        print(f"[WARN] haversine failed: {e}")
        return float("inf")  # безопасный fallback




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
        text = self.gpt_text or ""
        try:
            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=text
            )
            data = response.data if hasattr(response, "data") else []
            if data and hasattr(data[0], "embedding"):
                emb = np.array(data[0].embedding, dtype=float)
            else:
                print("[WARN] GPT embedding response empty or malformed.")
                emb = np.zeros(1536, dtype=float)  # размер зависит от модели
        except Exception as e:
            print(f"[WARN] GPT embedding failed: {e}")
            emb = np.zeros(1536, dtype=float)

        self.E_gpt = emb
        return self.E_gpt

    # --- Шаг 2: эмбеддинг структурных данных ---
    def embed_struct_data(self):
        """
        Формируем краткий текст из полей запроса и считаем его эмбеддинг.
        """
        try:
            interests = self.req_payload.get('interests') or []
            if not isinstance(interests, list):
                interests = [str(interests)]
            mood = self.req_payload.get('mood') or []
            if not isinstance(mood, list):
                mood = [str(mood)]

            struct_text = (
                f"{self.req_payload.get('city_id', '')}, {self.req_payload.get('time_of_day', '')}, "
                f"интересы: {', '.join(map(str, interests))}, "
                f"настроение: {', '.join(map(str, mood))}, "
                f"бюджет: {str(self.req_payload.get('budget', ''))}, "
                f"транспорт: {str(self.req_payload.get('transport', ''))}, "
                f"{str(self.req_payload.get('duration_minutes', ''))} минут, "
                f"район: {str(self.req_payload.get('start_area', ''))}, "
                f"старт: {str(self.req_payload.get('start_point', ''))}"
            )

            response = client.embeddings.create(
                model="text-embedding-3-small",
                input=struct_text or "empty"
            )
            data = getattr(response, "data", [])
            if data and hasattr(data[0], "embedding"):
                emb = np.array(data[0].embedding, dtype=float)
            else:
                print("[WARN] Struct embedding response empty or malformed.")
                emb = np.zeros(1536, dtype=float)  # размер зависит от модели
        except Exception as e:
            print(f"[WARN] Struct embedding failed: {e}")
            emb = np.zeros(1536, dtype=float)

        self.E_struct = emb
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

        def safe_cosine_similarity(vec1, vec2):
            try:
                v1 = np.array(vec1, dtype=float)
                v2 = np.array(vec2, dtype=float)
                n1, n2 = np.linalg.norm(v1), np.linalg.norm(v2)
                if n1 == 0 or n2 == 0 or np.isnan(n1) or np.isnan(n2):
                    return 0.0
                return float(np.dot(v1, v2) / (n1 * n2))
            except Exception as e:
                print(f"[WARN] cosine_similarity failed: {e}")
                return 0.0

        if not pois or not isinstance(pois, list):
            print("[WARN] pois is empty or not a list")
            return []

        results = []
        for p in pois:
            emb = p.get("embedding")
            if emb is None or self.E_final is None:
                sim = 0.0
            else:
                sim = safe_cosine_similarity(self.E_final, emb)
            results.append({**p, "similarity": sim})

        results.sort(key=lambda x: x.get("similarity", 0.0), reverse=True)
        return results[:min(top_n, len(results))]

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

    def sanitize_str(self, value: any, allow_symbols: str = r"A-Za-z0-9\-_") -> str:
        """
        Универсальная очистка строковых данных.
        - Приводит значение к строке
        - Убирает внешние кавычки и пробелы
        - Если value — список или dict, сериализует в JSON
        - Фильтрует недопустимые символы (по allow_symbols), если задано
        """
        if value is None:
            return ""

        # если список или словарь — превращаем в строку
        if isinstance(value, (list, dict)):
            value = json.dumps(value, ensure_ascii=False)

        s = str(value).strip()
        # убираем внешние кавычки
        s = s.strip("'").strip('"').strip()

        # если задан фильтр допустимых символов — применяем
        if allow_symbols:
            s = re.sub(fr"[^{allow_symbols}]", "", s)

        return s

    def final_selection_gpt(self, candidate_points: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Отправляем список точек в GPT и формируем финальный маршрут.
        """

        # безопасное формирование списка точек для промпта
        def short_desc(s):
            s = str(s or "")
            return s[:300]

        points_text = "\n".join([
            f"- id: {self.sanitize_str(value=p.get('id'))}, "
            f"name: {self.sanitize_str(value=p.get('name'), allow_symbols='')}, "
            f"desc: {self.sanitize_str(value=p.get('description'), allow_symbols='')}, "
            f"coords: [{p.get('coordinates_lat')}, {p.get('coordinates_lng')}]"
            for p in candidate_points
            if self.sanitize_str(value=p.get("id")) and p.get("coordinates_lat") and p.get("coordinates_lng")
        ])

        # полный промпт без сокращений
        prompt = (
            f"Исходный запрос пользователя:\n{self.req_payload}\n\n"
            f"Описание маршрута:\n{self.gpt_text}\n\n"
            f"Список доступных точек:\n{points_text}\n\n"
            f"Задача: выбери 5-8 точек для маршрута, учитывая интересы, настроение, бюджет и логистику.\n"
            f"Важные требования:\n"
            f"- Верни строго JSON-словарь.\n"
            f"- Формат: {{\"points\": [{{\"id\": \"...\", \"order\": 1}}, ...]}}.\n"
            f"- Используй только id из списка.\n"
            f"- Список точек отсортирован по приоритету (начало списка важнее).\n"
            f"- Выбирай преимущественно из первых точек, но допускается брать более дальние, если они лучше подходят для маршрута.\n"
            f"- Расположи точки в порядке движения по координатам (от стартовой точки).\n"
            f"- Избегай точек, которые находятся на противоположных концах радиуса.\n"
            f"- Формируй логичный маршрут, а не разбросанные места.\n"
            f"- Не добавляй лишнего текста, только JSON.\n"
            f"- Верни только JSON без форматирования, без ```json и других обёрток."
        )

        # вызов GPT
        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
            )
            result_text = (response.choices[0].message.content or "").strip()
        except Exception as e:
            print(f"[WARN] GPT call failed: {e}")
            result_text = '{"points": []}'

        # парсинг JSON
        try:
            result_json = json.loads(result_text)
        except Exception as e:
            print(f"[WARN] JSON parse failed: {e}")
            result_json = {"points": []}

        if not isinstance(result_json.get("points"), list):
            result_json["points"] = []

        # словарь для быстрого доступа к координатам
        point_map = {
            self.sanitize_str(value=p.get("id")): {
                **p,
                "id": self.sanitize_str(value=p.get("id")),
                "name": self.sanitize_str(value=p.get("name"), allow_symbols=""),
                "description": self.sanitize_str(value=p.get("description"), allow_symbols="")
            }
            for p in candidate_points if self.sanitize_str(value=p.get("id"))
        }

        # стартовая точка
        try:
            lat0_str, lon0_str = str(self.req_payload.get("start_point", "0,0")).split(",")
            lat0, lon0 = float(lat0_str.strip()), float(lon0_str.strip())
        except Exception:
            print("[WARN] Bad start_point format, using (0,0)")
            lat0, lon0 = 0.0, 0.0

        # очищаем точки из ответа GPT
        cleaned_points = []
        for p in result_json.get("points", []):
            sid = self.sanitize_str(value=p.get("id"))
            if sid and sid in point_map:
                try:
                    order_val = int(p.get("order") or 0)
                except Exception:
                    order_val = 0
                cleaned_points.append({
                    "id": sid,
                    "order": order_val,
                })

        # жадный алгоритм ближайшего соседа
        ordered = []
        remaining = cleaned_points[:]
        current_lat, current_lon = lat0, lon0
        order = 1

        while remaining:
            try:
                next_point = min(
                    remaining,
                    key=lambda pt: haversine(
                        current_lat, current_lon,
                        float(point_map[pt["id"]].get("coordinates_lat", 0.0)),
                        float(point_map[pt["id"]].get("coordinates_lng", 0.0))
                    )
                )
            except Exception as e:
                print(f"[WARN] nearest point selection failed: {e}")
                break

            next_point["order"] = order
            ordered.append(next_point)
            order += 1

            obj = point_map.get(next_point["id"])
            if not obj:
                remaining.remove(next_point)
                continue

            try:
                current_lat = float(obj.get("coordinates_lat", 0.0))
                current_lon = float(obj.get("coordinates_lng", 0.0))
            except Exception:
                current_lat, current_lon = 0.0, 0.0

            remaining.remove(next_point)

        try:
            user_time_limit = int(self.req_payload.get("duration_minutes", 180))
        except Exception:
            user_time_limit = 180

        max_time = user_time_limit * 1.2
        walk_speed_m_per_min = 70

        accumulated_time = 0.0
        final_points = []
        prev_lat, prev_lon = lat0, lon0

        for p in ordered:
            obj = point_map.get(p["id"])
            if not obj:
                continue

            try:
                lat = float(obj.get("coordinates_lat"))
                lon = float(obj.get("coordinates_lng"))
            except Exception:
                continue

            dist_m = haversine(prev_lat, prev_lon, lat, lon)
            walk_time_inc = dist_m / walk_speed_m_per_min

            try:
                visit_time_inc = int(obj.get("average_visit_duration", 30))
            except Exception:
                visit_time_inc = 30

            # фильтрация по лимиту времени
            if (accumulated_time + walk_time_inc + visit_time_inc) <= max_time:
                accumulated_time += walk_time_inc + visit_time_inc
                final_points.append(p)
                prev_lat, prev_lon = lat, lon
            else:
                break

        points_text = "\n".join([
            f"- id: {p['id']}, name: {point_map[p['id']]['name']}, "
            f"desc: {point_map[p['id']].get('description', '')}, "
            f"coords: [{point_map[p['id']]['coordinates_lat']}, {point_map[p['id']]['coordinates_lng']}]"
            for p in final_points
        ])

        prompt_reason = (
            f"Исходный запрос пользователя:\n{self.req_payload}\n\n"
            f"Описание маршрута:\n{self.gpt_text}\n\n"
            f"Финальный маршрут из {len(final_points)} точек:\n{points_text}\n\n"
            f"Задача: для каждой точки напиши поле reason в формате рассказа, "
            f"как будто ты идёшь вместе с другом-гидом и интересно описываешь маршрут.\n"
            f"Соблюдай order 1-первая точка и тд.\n"
            f"Формат ответа строго JSON:\n"
            f"{{\"points\": [{{\"id\": \"...\", \"order\": 1, \"reason\": \"...\"}}, ...]}}\n"
            f"- Используй только id из списка.\n"
            f"- reason должен быть живым, дружеским, с атмосферой путешествия.\n"
            f"- Для первой точки: «Начинаем мы в ... тут ...».\n"
            f"- Для второй: «Далее мы видим ...».\n"
            f"- Для третьей: «Следующая остановка ...» и так далее.\n"
            f"- Также сгенерируй короткое название всего маршрута (поле name). "
            f"- Название должно быть максимально коротким, в одном предложении, атмосферным и отражать суть маршрута.\n"
            f"- Формат ответа строго JSON:\n"
            f"{{\"name\": \"...\", \"points\": [{{\"id\": \"...\", \"order\": 1, \"reason\": \"...\"}}, ...]}}.\n"
            f"- Не добавляй лишнего текста, только JSON.\n"
            f"- Верни только JSON без ```json и других обёрток."
        )
        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[{"role": "user", "content": prompt_reason}],
        )
        raw_content = response.choices[0].message.content.strip()
        try:
            reasons_result = json.loads(raw_content)
        except json.JSONDecodeError:
            with open("failed_reasons.txt", "w", encoding="utf-8") as f:
                f.write(raw_content)
            reasons_result = {"points": []}

        # создаём словарь id -> reason
        reason_map = {p["id"]: p.get("reason", "") for p in reasons_result.get("points", [])}

        # добавляем reason в final_points
        for p in final_points:
            p["reason"] = reason_map.get(p["id"], "")
        cal = calculate_route_times(final_points, point_map, lat0, lon0)
        total_time = cal["total_time"]
        walk_time = cal["walk_time"]
        visit_time = cal["visit_time"]
        result_json["name"] = reasons_result.get("name", "")
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
