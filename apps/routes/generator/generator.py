
import uuid

# Заглушка для ML-логики
def generate_route_stub(city_id, time_of_day, interests, mood, budget, transport, duration_minutes, description, user):
    """
    В будущем здесь будет вызов ML-модуля.
    Пока возвращаем фиктивный маршрут.
    """
    return {
        "route_id": str(uuid.uuid4())[:8],
        "user_id": user.id,
        "map_url": "https://yandex.ru/maps/?text=" + city_id,
        "points": [
            {
                "id": "1",
                "name": "Парк Горького",
                "description": "Один из самых популярных парков города — идеально для прогулки вечером.",
                "image_url": "https://example.com/gorky.jpg",
                "visit_time": "30 мин",
                "tags": ["🌳", "💸 0 ₽", "🚶 10 мин"],
                "coordinates": {"lat": 55.792, "lng": 37.586},
            },
            {
                "id": "2",
                "name": "ВкусОчка",
                "description": "Элитный ресторан Москвы",
                "image_url": "https://example.com/gorky.jpg",
                "visit_time": "30 мин",
                "tags": ["🌳", "💸 1 ₽", "🚶 10 мин"],
                "coordinates": {"lat": 55.792, "lng": 37.586},
            }
        ],
    }