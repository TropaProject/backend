import requests

def get_wikidata_description_and_image(wikidata_id: str, lang: str = "ru", fallback_lang: str = "en", timeout: int = 6):
    """
    Возвращает (description, image_url) по Wikidata ID.
    - description: краткое описание на языке lang, затем fallback_lang, затем любой доступный.
    - image_url: прямая ссылка на изображение из свойства P18 (если есть).

    :param wikidata_id: например, "Q1394233"
    :param lang: предпочтительный язык описания
    :param fallback_lang: запасной язык описания
    :param timeout: таймаут HTTP-запросов в секундах
    :return: tuple(description or None, image_url or None)
    """
    if not wikidata_id:
        return None, None

    wid = wikidata_id.strip()
    if wid[0].lower() == "q":
        wid = "Q" + wid[1:]

    description, image_url = None, None

    try:
        # 1) Забираем сущность из Wikidata
        wd_url = f"https://www.wikidata.org/wiki/Special:EntityData/{wid}.json"
        wd_resp = requests.get(wd_url, timeout=timeout)
        wd_resp.raise_for_status()
        data = wd_resp.json()
        entity = data["entities"][wid]

        # 2) Описание (descriptions)
        descriptions = entity.get("descriptions", {})
        if lang in descriptions:
            description = descriptions[lang]["value"]
        elif fallback_lang in descriptions:
            description = descriptions[fallback_lang]["value"]
        elif descriptions:
            # любой доступный, если предпочитаемых нет
            description = next(iter(descriptions.values()))["value"]

        # 3) Изображение (claims.P18 -> имя файла -> Commons api -> URL)
        claims = entity.get("claims", {})
        p18 = claims.get("P18")
        if p18 and len(p18) > 0:
            file_name = p18[0]["mainsnak"]["datavalue"]["value"]  # например: "Moscow Paveletsky rail terminal.jpg"
            title = f"File:{file_name.replace(' ', '_')}"
            commons_params = {
                "action": "query",
                "titles": title,
                "prop": "imageinfo",
                "iiprop": "url",
                "format": "json"
            }
            commons_resp = requests.get("https://commons.wikimedia.org/w/api.php", params=commons_params, timeout=timeout)
            commons_resp.raise_for_status()
            commons_data = commons_resp.json()
            pages = commons_data.get("query", {}).get("pages", {})
            if pages:
                page = next(iter(pages.values()))
                info = page.get("imageinfo")
                if info and len(info) > 0:
                    image_url = info[0].get("url")

    except Exception:
        # Тихо гасим ошибки: вернём то, что удалось достать (или None, None)
        pass

    return description, image_url
