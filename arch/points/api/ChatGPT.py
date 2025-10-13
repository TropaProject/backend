# utils.py
import os
import json
import requests
from apps.core.models import Interest, Mood  # поправь под свой путь к моделям

OPENAI_API_KEY = 'sk-2T8KSdH5HiStual2sYQAjp1KVHvRKpcu'
OPENAI_API_URL = "https://api.proxyapi.ru/openai/v1/chat/completions"


def get_interest_ids():
    """Получаем список id интересов из БД"""
    return list(Interest.objects.values_list("id", flat=True))


def get_mood_ids():
    """Получаем список id настроений из БД"""
    return list(Mood.objects.values_list("id", flat=True))


def prepare_place_data(feature: dict) -> dict:
    props = feature.get("properties", {})
    return {
        "name": props.get("name"),
        "city": props.get("city"),
        "country": props.get("country"),
        "street": props.get("street"),
        "housenumber": props.get("housenumber"),
        "lat": props.get("lat"),
        "lon": props.get("lon"),
        "categories": props.get("categories", []),
        "raw_tags": props.get("categories", []),
        "wiki_description": props.get("description_wiki"),
        "image_url": props.get("image_url_wiki") or props.get("image"),
        "website": props.get("website"),
        "opening_hours": props.get("opening_hours"),
    }


def enrich_point_with_gpt(place_data: dict) -> dict:
    interest_ids = get_interest_ids()
    mood_ids = get_mood_ids()

    prompt = f"""
Ты — travel-копирайтер туристического сервиса.

Дано:
{json.dumps(place_data, ensure_ascii=False, indent=2)}

Нужно:
1. Напиши привлекательное, живое и информативное описание места для туриста (4–6 предложений).
2. Подбери список "interests" — только id из: {", ".join(interest_ids)}.
3. Подбери список "moods" — только id из: {", ".join(mood_ids)}.
4. Придумай до 6 тегов (латиницей, lower_case, без пробелов).
5. Верни строго JSON:
{{
  "description": "...",
  "interests": ["id1", "id2"],
  "moods": ["id1", "id2"],
  "tags": ["tag1", "tag2"]
}}
"""

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "Ты пишешь тексты для туристического приложения."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.8
    }

    resp = requests.post(OPENAI_API_URL, headers=headers, json=payload)
    resp.raise_for_status()
    raw_content = resp.json()["choices"][0]["message"]["content"]

    try:
        return json.loads(raw_content)
    except json.JSONDecodeError:
        raise ValueError(f"Ответ модели не JSON: {raw_content}")


def process_api_feature(feature: dict) -> dict:
    clean_data = prepare_place_data(feature)
    gpt_result = enrich_point_with_gpt(clean_data)
    return {
        **clean_data,
        **gpt_result,
        "all_tags": list(set(clean_data.get("raw_tags", []) + gpt_result.get("tags", [])))
    }
