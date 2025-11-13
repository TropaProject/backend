
from apps.routes.models import Point, PointEmbedding
from openai import OpenAI
from django.conf import settings


client = OpenAI(api_key=settings.OPENAI_API_KEY,
                base_url="https://api.proxyapi.ru/openai/v1")


def generate_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


def build_point_text(point: Point) -> str:
    parts = []
    if point.name:
        parts.append(f"Название: {point.name}")
    # Основное описание точки
    if point.description:
        parts.append(point.description)
    if point.best_visit_time:
        best_times = ", ".join(point.best_visit_time)
        parts.append(f"Лучшее время для посещения: {best_times}")
    if hasattr(point, "tags"):
        tag_texts = []
        for tag in point.tags.all():
            tag_texts.append(f"{tag.name} | {tag.category} | {tag.description or ''}")
        if tag_texts:
            parts.append("Теги: " + "; ".join(tag_texts))

    # Интересы (ManyToMany Interest)
    interests = point.interests.all()
    if interests:
        interest_texts = []
        for interest in interests:
            interest_texts.append(
                f"{interest.label} | {interest.description or ''} | Категория: {interest.category.label if interest.category else ''}"
            )
        parts.append("Интересы: " + "; ".join(interest_texts))

    # Настроения (ManyToMany Mood)
    moods = point.moods.all()
    if moods:
        mood_texts = []
        for mood in moods:
            mood_texts.append(f"{mood.label} | {mood.description or ''}")
        parts.append("Настроения: " + "; ".join(mood_texts))

    return "\n".join(parts)

