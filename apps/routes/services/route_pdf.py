from io import BytesIO
from pathlib import Path
from textwrap import shorten

import requests
from django.conf import settings
from PIL import Image, ImageDraw, ImageFont, ImageOps


PAGE_WIDTH = 1240
PAGE_HEIGHT = 1754
MARGIN = 88
GAP = 24
INK = (36, 38, 44)
MUTED = (102, 112, 128)
LINE = (224, 229, 236)
SOFT = (247, 249, 252)
ACCENT = (38, 132, 255)
PARTNER = (23, 143, 92)


def build_route_pdf(route):
    renderer = _RoutePdfRenderer(route)
    return renderer.render()


class _RoutePdfRenderer:
    def __init__(self, route):
        self.route = route
        self.pages = []
        self.page = None
        self.draw = None
        self.y = MARGIN
        self.fonts = _load_fonts()
        self.ordered_points = self._get_ordered_points()

    def render(self):
        self._new_page()
        self._draw_cover()

        for index, point in enumerate(self.ordered_points, start=1):
            self._draw_point(index, point)

        output = BytesIO()
        first, *rest = self.pages
        first.save(output, format="PDF", save_all=True, append_images=rest, resolution=150.0)
        output.seek(0)
        return output.getvalue()

    def _new_page(self):
        self.page = Image.new("RGB", (PAGE_WIDTH, PAGE_HEIGHT), "white")
        self.draw = ImageDraw.Draw(self.page)
        self.pages.append(self.page)
        self.y = MARGIN

    def _ensure_space(self, height):
        if self.y + height > PAGE_HEIGHT - MARGIN:
            self._draw_footer()
            self._new_page()

    def _draw_cover(self):
        title = self.route.title or f"Маршрут {str(self.route.id)[:8]}"
        city = self.route.city.name if self.route.city else None
        author = self.route.user.username if self.route.user else None

        self._text(title, MARGIN, self.y, self.fonts["title"], INK, max_width=PAGE_WIDTH - MARGIN * 2)
        self.y += self._text_block_height(title, self.fonts["title"], PAGE_WIDTH - MARGIN * 2) + 24

        meta = " • ".join([part for part in [city, f"Автор: {author}" if author else None] if part])
        if meta:
            self._text(meta, MARGIN, self.y, self.fonts["small"], MUTED, max_width=PAGE_WIDTH - MARGIN * 2)
            self.y += 46

        stats = [
            ("Время", _minutes(self.route.total_duration)),
            ("Пешком", _minutes(getattr(self.route, "walk_time", None))),
            ("Точки", str(len(self.ordered_points))),
            ("Дистанция", _meters(self.route.total_meters)),
            ("Бюджет", _money(self.route.total_cost)),
        ]
        self._draw_stats(stats)

        if self.route.description:
            self.y += 26
            self._section_title("Описание")
            self._paragraph(self.route.description, self.fonts["body"], INK, PAGE_WIDTH - MARGIN * 2)

        self.y += 30
        self._section_title("Последовательность точек")

    def _draw_stats(self, stats):
        card_width = (PAGE_WIDTH - MARGIN * 2 - GAP * 2) // 3
        card_height = 112
        x = MARGIN
        start_y = self.y

        for i, (label, value) in enumerate(stats):
            if i and i % 3 == 0:
                x = MARGIN
                start_y += card_height + GAP
            self.draw.rounded_rectangle(
                (x, start_y, x + card_width, start_y + card_height),
                radius=18,
                fill=SOFT,
                outline=LINE,
                width=2,
            )
            self.draw.text((x + 22, start_y + 20), label, font=self.fonts["small"], fill=MUTED)
            self.draw.text((x + 22, start_y + 56), value, font=self.fonts["stat"], fill=INK)
            x += card_width + GAP

        rows = (len(stats) + 2) // 3
        self.y = start_y + rows * card_height + (rows - 1) * GAP

    def _draw_point(self, index, point):
        image_w = 320
        image_h = 220
        text_w = PAGE_WIDTH - MARGIN * 2 - image_w - 34
        desc = point.description or ""
        tags = ", ".join([tag.name for tag in point.tags.all()])
        interests = ", ".join([interest.label for interest in point.interests.all()])

        desc_height = self._text_block_height(desc, self.fonts["body"], text_w, max_lines=8)
        detail_lines = [
            point.address,
            f"Рейтинг: {point.average_rating} ({point.reviews_count} отзывов)" if point.reviews_count else None,
            f"Среднее время: {_minutes(point.average_visit_duration)}" if point.average_visit_duration else None,
            f"Средний чек: {_money(point.average_cost)}" if point.average_cost else None,
            f"Теги: {tags}" if tags else None,
            f"Интересы: {interests}" if interests else None,
        ]
        detail_text = "\n".join([line for line in detail_lines if line])
        detail_height = self._text_block_height(detail_text, self.fonts["small"], text_w, max_lines=6)
        card_height = max(image_h, 72 + desc_height + detail_height) + 54

        self._ensure_space(card_height + GAP)
        top = self.y
        self.draw.rounded_rectangle(
            (MARGIN, top, PAGE_WIDTH - MARGIN, top + card_height),
            radius=20,
            fill="white",
            outline=LINE,
            width=2,
        )

        self._draw_point_image(point, MARGIN + 24, top + 24, image_w, image_h)

        x = MARGIN + 24 + image_w + 34
        y = top + 26
        marker = f"{index}."
        self.draw.text((x, y), marker, font=self.fonts["h2"], fill=ACCENT)
        self._text(point.name, x + 58, y, self.fonts["h2"], INK, max_width=text_w - 58, max_lines=2)
        y += self._text_block_height(point.name, self.fonts["h2"], text_w - 58, max_lines=2) + 16

        if point.is_partner:
            badge = "Партнерская точка"
            badge_w = self.draw.textbbox((0, 0), badge, font=self.fonts["small_bold"])[2] + 28
            self.draw.rounded_rectangle((x, y, x + badge_w, y + 34), radius=17, fill=(229, 247, 239))
            self.draw.text((x + 14, y + 7), badge, font=self.fonts["small_bold"], fill=PARTNER)
            y += 48

        if desc:
            self._text(shorten(desc, width=520, placeholder="..."), x, y, self.fonts["body"], INK, max_width=text_w, max_lines=8)
            y += desc_height + 14

        if detail_text:
            self._text(detail_text, x, y, self.fonts["small"], MUTED, max_width=text_w, max_lines=6)

        self.y = top + card_height + GAP

    def _draw_point_image(self, point, x, y, width, height):
        image = _load_point_image(point.image_url, width, height)
        if image:
            self.page.paste(image, (x, y))
            return

        self.draw.rounded_rectangle((x, y, x + width, y + height), radius=18, fill=SOFT, outline=LINE, width=2)
        label = "Фото недоступно"
        label_w = self.draw.textbbox((0, 0), label, font=self.fonts["small"])[2]
        self.draw.text((x + (width - label_w) // 2, y + height // 2 - 12), label, font=self.fonts["small"], fill=MUTED)

    def _section_title(self, text):
        self._text(text, MARGIN, self.y, self.fonts["h1"], INK, max_width=PAGE_WIDTH - MARGIN * 2)
        self.y += 54

    def _paragraph(self, text, font, fill, max_width):
        lines = _wrap_text(self.draw, text, font, max_width)
        for line in lines:
            self.draw.text((MARGIN, self.y), line, font=font, fill=fill)
            self.y += font.size + 12

    def _text(self, text, x, y, font, fill, max_width, max_lines=None):
        lines = _wrap_text(self.draw, str(text or ""), font, max_width)
        if max_lines:
            lines = lines[:max_lines]
        for line in lines:
            self.draw.text((x, y), line, font=font, fill=fill)
            y += font.size + 10

    def _text_block_height(self, text, font, max_width, max_lines=None):
        lines = _wrap_text(self.draw, str(text or ""), font, max_width)
        if max_lines:
            lines = lines[:max_lines]
        return max(1, len(lines)) * (font.size + 10)

    def _draw_footer(self):
        page_number = len(self.pages)
        label = f"Страница {page_number}"
        self.draw.line((MARGIN, PAGE_HEIGHT - 70, PAGE_WIDTH - MARGIN, PAGE_HEIGHT - 70), fill=LINE, width=2)
        self.draw.text((MARGIN, PAGE_HEIGHT - 50), label, font=self.fonts["small"], fill=MUTED)

    def _get_ordered_points(self):
        point_map = {str(point.id): point for point in self.route.points.all()}
        return [point_map[str(point_id)] for point_id in self.route.point_sequence if str(point_id) in point_map]


def _load_fonts():
    regular = _find_font(["arial.ttf", "DejaVuSans.ttf"])
    bold = _find_font(["arialbd.ttf", "DejaVuSans-Bold.ttf"])
    return {
        "title": ImageFont.truetype(bold or regular, 58) if regular or bold else ImageFont.load_default(),
        "h1": ImageFont.truetype(bold or regular, 36) if regular or bold else ImageFont.load_default(),
        "h2": ImageFont.truetype(bold or regular, 28) if regular or bold else ImageFont.load_default(),
        "stat": ImageFont.truetype(bold or regular, 30) if regular or bold else ImageFont.load_default(),
        "body": ImageFont.truetype(regular or bold, 24) if regular or bold else ImageFont.load_default(),
        "small": ImageFont.truetype(regular or bold, 20) if regular or bold else ImageFont.load_default(),
        "small_bold": ImageFont.truetype(bold or regular, 20) if regular or bold else ImageFont.load_default(),
    }


def _find_font(names):
    candidates = [
        Path("C:/Windows/Fonts"),
        Path("/usr/share/fonts/truetype/dejavu"),
        Path("/usr/local/share/fonts"),
    ]
    for base in candidates:
        for name in names:
            path = base / name
            if path.exists():
                return str(path)
    return None


def _load_point_image(image_url, width, height):
    if not image_url:
        return None

    try:
        if str(image_url).startswith("/"):
            path = Path(settings.BASE_DIR) / str(image_url).lstrip("/")
            image = Image.open(path)
        else:
            response = requests.get(image_url, timeout=4)
            response.raise_for_status()
            image = Image.open(BytesIO(response.content))

        image = ImageOps.exif_transpose(image).convert("RGB")
        image.thumbnail((width, height), Image.LANCZOS)
        canvas = Image.new("RGB", (width, height), SOFT)
        canvas.paste(image, ((width - image.width) // 2, (height - image.height) // 2))
        return canvas
    except Exception:
        return None


def _wrap_text(draw, text, font, max_width):
    lines = []
    for paragraph in str(text or "").splitlines() or [""]:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if draw.textlength(candidate, font=font) <= max_width:
                current = candidate
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def _minutes(value):
    if value in (None, ""):
        return "—"
    return f"{value} мин"


def _meters(value):
    if value in (None, ""):
        return "—"
    if value >= 1000:
        return f"{round(value / 1000, 1)} км"
    return f"{value} м"


def _money(value):
    if value in (None, ""):
        return "—"
    return f"{value} ₽"
