
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

    # Название
    if point.name:
        parts.append(f"Название: {point.name.strip()}")

    # Описание
    if point.description:
        parts.append(f"Описание: {point.description.strip()}")

    # Лучшее время для посещения
    if point.best_visit_time:
        best_times = ", ".join([t.strip() for t in point.best_visit_time if t])
        if best_times:
            parts.append(f"Лучшее время для посещения: {best_times}")

    # Теги
    tag_texts = []
    if hasattr(point, "tags"):
        for tag in point.tags.all():
            tag_texts.append(
                f"{tag.name.strip()} | Категория: {getattr(tag, 'category', '')} | {tag.description.strip() if tag.description else ''}"
            )
    if tag_texts:
        parts.append("Теги: " + "; ".join(tag_texts))

    # Интересы
    interest_texts = []
    for interest in point.interests.all():
        interest_texts.append(
            f"{interest.label.strip()} | {interest.description.strip() if interest.description else ''} | Категория: {interest.category.label if interest.category else ''}"
        )
    if interest_texts:
        parts.append("Интересы: " + "; ".join(interest_texts))

    # Настроения
    mood_texts = []
    for mood in point.moods.all():
        mood_texts.append(f"{mood.label.strip()} | {mood.description.strip() if mood.description else ''}")
    if mood_texts:
        parts.append("Настроения: " + "; ".join(mood_texts))
    if hasattr(point, "keywords") and point.keywords:
        keywords_text = ", ".join([kw.strip() for kw in point.keywords if kw])
        if keywords_text:
            parts.append(f"Ключевые слова: {keywords_text}")
    # Нормализация: убираем пустые строки и лишние пробелы
    normalized_parts = [p.strip() for p in parts if p and p.strip()]

    return " ; ".join(normalized_parts)


