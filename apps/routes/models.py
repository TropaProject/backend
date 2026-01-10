from django.db import models
from django.contrib.postgres.fields import ArrayField
import uuid
from apps.partners.models import Partner
from django.conf import settings


class City(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Идентификатор города, например "moscow"')
    name = models.CharField(max_length=100, help_text='Название города, например "Москва"')
    image_url = models.URLField(null=True, blank=True, help_text='Ссылка на фото города')
    description = models.TextField(help_text='Краткое описание города')
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    bbox = models.JSONField(null=True, blank=True)  # {"min_lat": ..., "max_lat": ..., "min_lon": ..., "max_lon": ...}
    class Meta:
        db_table = 'cities'
        verbose_name = 'Город'
        verbose_name_plural = 'Города'

    def __str__(self):
        return self.name

class CityArea(models.Model):
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name="areas")
    name = models.CharField(max_length=255)
    bbox = models.JSONField(null=True, blank=True)  # {"min_lat": ..., "max_lat": ..., "min_lon": ..., "max_lon": ...}
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)
    description=models.TextField(null=True, blank=True)
    image_url=models.ImageField(null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.city.name})"


class InterestCategory(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Идентификатор категории')
    label = models.CharField(max_length=100, help_text='Название категории')

    class Meta:
        db_table = 'interest_categories'
        verbose_name = 'Категория интереса'
        verbose_name_plural = 'Категории интересов'

    def __str__(self):
        return self.label


class Interest(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Идентификатор интереса, например "parks"')
    label = models.CharField(max_length=100, help_text='Название интереса, например "Парки"')
    description = models.TextField(help_text='Описание интереса для показа пользователю')
    category = models.ForeignKey(
        InterestCategory,
        on_delete=models.CASCADE,
        related_name="interests",
        help_text='Категория интереса',
        null=True, blank=True,
    )
    is_seasonal=models.BooleanField(default=False)
    is_view = models.BooleanField(default=True)
    class Meta:
        db_table = 'interests'
        verbose_name = 'Интерес'
        verbose_name_plural = 'Интересы'
    def __str__(self):
        return f'{self.label} Категория: {self.category}'


class Mood(models.Model):
    id = models.CharField(max_length=50, primary_key=True, help_text='Идентификатор настроения, например "explore"')
    label = models.CharField(max_length=100, help_text='Название настроения, например "Исследовать"')
    description = models.TextField(help_text='Описание настроения для помощи в выборе')

    class Meta:
        db_table = 'moods'
        verbose_name = 'Настроение'
        verbose_name_plural = 'Настроения'

    def __str__(self):
        return f"{self.label}"

class Tag(models.Model):
    name = models.CharField(max_length=100, unique=True, help_text="Название тега (например, 'romantic')")
    description = models.TextField(null=True, blank=True, help_text="Описание тега для эмбеддингов")
    category = models.CharField(
        max_length=50,
        choices=[
            ('interest', 'Интерес'),
            ('mood', 'Настроение'),
            ('type', 'Тип места'),
            ('feature', 'Особенность'),
        ],
        help_text="Категория тега"
    )

    def __str__(self):
        return self.name
class Point(models.Model):
    id = models.CharField(max_length=400, primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=1000, help_text='Название точки')
    description = models.TextField(help_text='Описание точки')
    tags = models.ManyToManyField(Tag, blank=True, related_name="points")
    keywords = ArrayField(
        models.CharField(max_length=100),
        null=True,
        blank=True,
        help_text="Ключевые слова для улучшения эмбеддинга и поиска"
    )
    image_url = models.URLField(null=True, blank=True, help_text='URL фотографии точки')
    city = models.ForeignKey(City, on_delete=models.CASCADE, help_text='Город, к которому относится точка')
    area=models.ForeignKey(CityArea,on_delete=models.CASCADE,help_text='Район точки', null=True, blank=True)
    interests = models.ManyToManyField(Interest, blank=True)
    moods = models.ManyToManyField(Mood,blank=True)
    coordinates_lat = models.DecimalField(max_digits=9, decimal_places=6, help_text='Широта')
    coordinates_lng = models.DecimalField(max_digits=9, decimal_places=6, help_text='Долгота')
    address=models.CharField(max_length=300, null=True, blank=True)
    average_visit_duration = models.IntegerField(help_text='Среднее время посещения в минутах')
    average_cost = models.IntegerField(null=True, blank=True, help_text='Средняя стоимость посещения')
    is_partner = models.BooleanField(default=False, help_text='Является ли точка партнерской')
    partner_tier = models.CharField(max_length=10, null=True, blank=True, choices=Partner.TIER_CHOICES)
    partner = models.ForeignKey(Partner, on_delete=models.SET_NULL, null=True, blank=True)
    BEST_TIME_CHOICES = [
        ('morning', 'Утром (6:00-12:00)'),
        ('afternoon', 'Днём (12:00-18:00)'),
        ('evening', 'Вечером (18:00-23:00)'),
        ('night', 'Ночью (23:00-6:00)'),
        ('any', 'В любое время'),
    ]
    working_hours_json = models.JSONField(
        null=True,
        blank=True,
        help_text='Детальный режим работы по дням недели в формате JSON'
    )
    # Оптимальное время для посещения
    best_visit_time = ArrayField(
        models.CharField(max_length=20, choices=BEST_TIME_CHOICES),
        help_text='Оптимальное время для посещения (может быть несколько вариантов)',
        default=list
    )
    is_seasonal = models.BooleanField(
        default=False,
        help_text='Сезонное место (например, летние веранды, катки)'
    )
    seasonal_months = ArrayField(
        models.IntegerField(),
        null=True,
        blank=True,
        help_text='Месяцы работы для сезонных мест (1-12)'
    )
    # Дополнительные поля для аналитики
    view_count = models.IntegerField(default=0)
    success_rate = models.DecimalField(max_digits=3, decimal_places=2, default=0.0)
    last_viewed_at = models.DateTimeField(null=True, blank=True)
    class Meta:
        db_table = 'points'
        verbose_name = 'Точка интереса'
        verbose_name_plural = 'Точки интереса'
        indexes = [
            models.Index(fields=['city', 'coordinates_lat', 'coordinates_lng']),
            models.Index(fields=['is_partner']),
        ]

    def __str__(self):
        return f"{self.name} ({self.city.name})"


class PointEmbedding(models.Model):
    point = models.OneToOneField(Point, on_delete=models.CASCADE, primary_key=True)
    embedding = ArrayField(models.FloatField(), size=1536, help_text='Векторное представление описания точки')
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'point_embeddings'



class Route(models.Model):
    class WalkStatus(models.TextChoices):
        GOING = "going", "Иду гулять"
        DONE = "done", "Прошел"
        CANCELLED = "cancelled", "Не иду"
    id = models.CharField(max_length=50, primary_key=True, default=uuid.uuid4)
    created_at = models.DateTimeField(auto_now_add=True)
    total_duration = models.IntegerField(help_text='Общее время прогулки в минутах')
    walk_time = models.IntegerField(help_text='время пешком в минутах',default=0)
    visit_time = models.IntegerField(help_text='время посещения в минутах',default=0)
    total_cost = models.IntegerField(null=True, blank=True, help_text='Общий бюджет маршрута')
    total_meters=models.IntegerField(null=True, blank=True, help_text='Общее расстояние маршрута')
    city = models.ForeignKey("City", on_delete=models.CASCADE, related_name="routes",null=True, blank=True)
    description = models.TextField(null=True, blank=True, help_text='Текстовый гид или описание маршрута')
    lat0=models.DecimalField(max_digits=9, decimal_places=6, help_text='Широта',default=55.766157)
    lon0=models.DecimalField(max_digits=9, decimal_places=6, help_text='Долгота',default=37.617797)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="routes",
        help_text="Пользователь, которому принадлежит маршрут",
        null=True, blank=True
    )
    point_sequence = ArrayField(
        models.CharField(max_length=50),
        help_text='ID точек в порядке прохождения маршрута'
    )

    points = models.ManyToManyField("Point")
    status = models.CharField(
        max_length=20,
        choices=WalkStatus.choices,
        default=WalkStatus.GOING,
        help_text="Статус прогулки"
    )
    class Meta:
        db_table = 'routes'
        verbose_name = 'Маршрут'
        verbose_name_plural = 'Маршруты'
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"Маршрут {self.id[:8]} ({self.total_duration} мин)"


class Feedback(models.Model):
    id = models.CharField(max_length=50, primary_key=True, default=uuid.uuid4)
    route = models.ForeignKey(Route, on_delete=models.CASCADE, related_name="feedbacks")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="feedbacks",null=True, blank=True)
    rating = models.PositiveSmallIntegerField(help_text="Оценка маршрута (1–5)", null=True, blank=True)
    comment = models.TextField(null=True, blank=True, help_text="Текстовый отзыв")
    going = models.BooleanField(help_text="Планирует ли пользователь идти по маршруту", default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "feedback"
        verbose_name = "Отзыв"
        verbose_name_plural = "Отзывы"
        indexes = [
            models.Index(fields=["going", "created_at"]),
        ]

    def __str__(self):
        return f"Feedback {self.id} for Route {self.route.id}"