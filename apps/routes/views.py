from django.conf import settings
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from openai import OpenAI

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, permissions

from .models import City, Interest, Mood, CityArea, Route, Feedback, Point
from .serializers import CitySerializer, InterestSerializer, MoodSerializer
from .services.generate_route import RoutePipeline, build_map_url
from .services.route_metrics import calculate_total_cost, calculate_total_duration, calculate_total_meters


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
        start_point=data.get("start_point")
        start_area=data.get("start_area")
        gpt_description=data.get("gpt_description")
        radius_km=data.get("radius_km")
        if not city_id or not duration_minutes:
            return Response(
                {"status": "error", "message": "city_id и duration_minutes обязательны"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Вызов ML
        try:
            # 1) Получаем город и точки
            city = City.objects.get(id=city_id)
            pois_qs = Point.objects.filter(city=city)

            # 2) Запускаем пайплайн
            req_payload = {
                "city_id": city_id,
                "time_of_day": time_of_day,
                "interests": interests,
                "mood": mood,
                "budget": budget,
                "transport": transport,
                "duration_minutes": int(duration_minutes),
                "description": description,
                "start_point": start_point,
                "start_area": start_area,
            }
            pipeline = RoutePipeline(req_payload=req_payload, gpt_text=gpt_description,radius_km=float(radius_km))
            final_result = pipeline.run_pipeline(pois_qs)
            # Ожидается: {"points": [{"id": "...", "order": 1, "reason": "..."} ...]}
            selected = final_result.get("points", [])
            if not selected:
                return Response(
                    {"status": "error", "message": "GPT вернул пустой список точек"},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
            print("Step 2 complete")
            # 3) Создаём маршрут в БД

            point_map = {str(p.id): p for p in Point.objects.filter(id__in=[s["id"] for s in selected])}
            ordered_points = [
                point_map[str(item["id"])]
                for item in sorted(selected, key=lambda x: x.get("order", 9999))
                if str(item["id"]) in point_map
            ]
            # Вызываем сервисные функции
            total_cost = calculate_total_cost(ordered_points)
            total_duration = final_result.get("total_time", 0)  # можно передать api_key при необходимости
            total_meters = calculate_total_meters(ordered_points)
            route = Route.objects.create(
                total_duration=total_duration,
                total_cost=total_cost,
                total_meters=total_meters,
                city=city,
                description=gpt_description or description or "",
                user=request.user,
                point_sequence=[p.id for p in ordered_points],
                status=Route.WalkStatus.GOING,
            )

            # ManyToMany связывание

            for item in selected:
                p = point_map.get(str(item["id"]))
                if p:
                    route.points.add(p)
            print("Step 3 complete")
            # 4) Обогащаем точки для ответа
            enriched_points = []
            for item in sorted(selected, key=lambda x: x.get("order", 9999)):
                p = point_map.get(str(item["id"]))
                if not p:
                    continue
                enriched_points.append({
                    "id": str(p.id),
                    "name": p.name,
                    "description": p.description,
                    "reason": item.get("reason", ""),
                    "image_url": getattr(p, "image_url", None),
                    "visit_time": getattr(p, "visit_time", None) or "30 мин",
                    "tags": [t.name for t in p.tags.all()] if hasattr(p, "tags") else [],
                    "coordinates": {
                         "lat": float(p.coordinates_lat),
                         "lng": float(p.coordinates_lng),
                    },
                })
            print("Step 4 complete")
            # 5) Формируем ответ
            response_data = {
                    "route_id": str(route.id),
                    "total_duration":route.total_duration,
                    "total_meters":route.total_meters,
                    "total_cost":route.total_cost,
                    "walk_time":final_result.get("walk_time_minutes", 0),
                    "visit_time":final_result.get("visit_time_minutes", 0),
                    "user_id": request.user.id,
                    "map_url": 'ffd',
                    "points": enriched_points,
                }
            print(response_data)
            return Response({"status": "success", "data": response_data}, status=status.HTTP_200_OK)
        except City.DoesNotExist:
            return Response(
                {"status": "error", "message": "Город не найден"},
                status=status.HTTP_404_NOT_FOUND,
            )
        except Exception as e:
            return Response(
                {"status": "error", "message": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


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


client = OpenAI(api_key=settings.OPENAI_API_KEY,
                base_url="https://api.proxyapi.ru/openai/v1")


class GenerateDescriptionView(APIView):
    """
    Ручка принимает параметры маршрута и возвращает описание от GPT.
    """

    def post(self, request):
        data = request.data

        # достаём имя района по ID
        start_area_id = data.get("start_area")
        start_area_name = None
        if start_area_id:
            try:
                area = CityArea.objects.get(id=start_area_id)
                start_area_name = area.name
            except CityArea.DoesNotExist:
                start_area_name = f"район {start_area_id}"  # fallback

        # Формируем промпт для GPT
        prompt = (
            "Ты — помощник по созданию маршрутов для прогулок и досуга.\n"
            "На основе данных пользователя составь компактное и человечное описание маршрута.\n\n"
            "Данные пользователя:\n"
            f"- Город: {data.get('city_id')}\n"
            f"- Время суток: {data.get('time_of_day')}\n"
            f"- Интересы: {', '.join(data.get('interests', []))}\n"
            f"- Настроения: {', '.join(data.get('mood', []))}\n"
            f"- Бюджет: {data.get('budget')}\n"
            f"- Транспорт: {data.get('transport')}\n"
            f"- Длительность: {data.get('duration_minutes')} минут\n"
            f"- Стартовая точка: рядом с районом {start_area_name} (координаты не упоминай)\n"
            f"- Дополнительное описание: {data.get('description')}\n\n"
            "Требования:\n"
            "- Обязательно упомяни все ключевые параметры в тексте.\n"
            "- Не используй сухие перечисления, пиши естественным языком.\n"
            "- Не упоминай точные координаты, только названия районов или ориентиры.\n"
            "- Сделай текст компактным и лёгким для чтения.\n"
            "- Добавь контекст и разнообразие: включи разные категории мест (например, парки, музеи, достопримечательности, кафе), "
            "но сохраняя основные категории из списка.\n"
            "- Сохрани факты из данных, но можешь расширить их ассоциациями (например, вечером → огни города, искусство → галерея, расслабление → уютная атмосфера)."
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4.1-mini",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300
            )

            gpt_text = response.choices[0].message.content.strip()

            return Response({"route_description": gpt_text}, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)



@csrf_exempt
def pipeline_view(request):
    context = {}
    if request.method == "POST":
        form = request.POST.dict()
        req_payload = {
            "city_id": form.get("city_id"),
            "time_of_day": form.get("time_of_day"),
            "interests": [s.strip() for s in form.get("interests","").split(",") if s.strip()],
            "mood": [s.strip() for s in form.get("mood","").split(",") if s.strip()],
            "budget": form.get("budget"),
            "transport": form.get("transport"),
            "duration_minutes": int(form.get("duration_minutes") or 0),
            "description": form.get("description"),
            "start_point": form.get("start_point"),
            "start_area": form.get("start_area"),
        }
        gpt_text = form.get("gpt_description")

        try:
            city = City.objects.get(id=req_payload["city_id"])
            pois = Point.objects.filter(city=city)
            pipeline = RoutePipeline(req_payload=req_payload, gpt_text=gpt_text)
            result = pipeline.run_pipeline(pois)
            context["result"] = result
        except Exception as e:
            context["result"] = f"Ошибка: {e}"

        # сохраняем введённые значения, чтобы они остались в форме
        context.update(form)

    return render(request, "pipeline.html", context)
