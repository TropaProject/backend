
from apps.routes.models import Point, PointEmbedding
from openai import OpenAI
from django.conf import settings


client = OpenAI(api_key=settings.OPENAI_API_KEY)


def generate_embedding(text: str) -> list[float]:
    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )
    return response.data[0].embedding


def build_point_text(point: Point) -> str:
    # description
    parts = [point.description or ""]

    # tags (ArrayField)
    if point.tags:
        parts.append("Теги: " + ", ".join(point.tags))

    # interests (ManyToMany)
    interests = point.interests.values_list("name", flat=True)
    if interests:
        parts.append("Интересы: " + ", ".join(interests))

    # moods (ManyToMany)
    moods = point.moods.values_list("name", flat=True)
    if moods:
        parts.append("Настроения: " + ", ".join(moods))

    return "\n".join(parts)
