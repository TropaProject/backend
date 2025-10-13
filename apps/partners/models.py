import uuid

from django.db import models


class Partner(models.Model):
    TIER_CHOICES = [
        ('basic', 'Basic'),
        ('premium', 'Premium'),
        ('vip', 'VIP'),
    ]

    STATUS_CHOICES = [
        ('active', 'Активный'),
        ('paused', 'Приостановлен'),
        ('suspended', 'Заблокирован'),
    ]

    id = models.CharField(max_length=50, primary_key=True, default=uuid.uuid4)
    name = models.CharField(max_length=200, help_text='Название партнера, например "Кофейня на Арбате"')
    email = models.EmailField(null=True, blank=True, help_text='Email для связи')
    phone = models.CharField(max_length=20, null=True, blank=True, help_text='Телефон для связи')
    tier = models.CharField(max_length=10, choices=TIER_CHOICES, help_text='Тариф партнера')
    monthly_fee = models.DecimalField(max_digits=8, decimal_places=2, help_text='Ежемесячная плата в рублях')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='active')

    # Простая аналитика
    total_impressions = models.IntegerField(default=0, help_text='Общее количество показов точек партнера в маршрутах')
    impressions_this_month = models.IntegerField(default=0, help_text='Показы за текущий месяц')
    last_impression_date = models.DateTimeField(null=True, blank=True, help_text='Дата последнего показа')

    created_at = models.DateTimeField(auto_now_add=True, help_text='Дата регистрации партнера')

    class Meta:
        db_table = 'partners'
        verbose_name = 'Партнер'
        verbose_name_plural = 'Партнеры'

    def __str__(self):
        return f"{self.name} ({self.tier})"