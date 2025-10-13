from django.contrib import admin

from .models import Partner


@admin.register(Partner)
class PartnerAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'tier', 'status', 'monthly_fee',
        'total_impressions', 'impressions_this_month',
        'conversion_rate', 'last_impression_date'
    ]
    list_filter = ['tier', 'status', 'created_at']
    search_fields = ['name', 'email', 'phone']
    readonly_fields = [
        'total_impressions', 'impressions_this_month',
        'last_impression_date', 'created_at', 'conversion_rate'
    ]
    fieldsets = (
        ('Основная информация', {
            'fields': ('name', 'email', 'phone')
        }),
        ('Тариф и статус', {
            'fields': ('tier', 'monthly_fee', 'status')
        }),
        ('Статистика', {
            'fields': (
                'total_impressions', 'impressions_this_month',
                'last_impression_date', 'conversion_rate', 'created_at'
            ),
            'classes': ('collapse',)
        })
    )

    actions = ['activate_partners', 'pause_partners', 'reset_monthly_stats']

    def conversion_rate(self, obj):
        # TODO: Реализовать расчет конверсии на основе Feedback
        return "N/A"

    conversion_rate.short_description = 'Конверсия'

    def activate_partners(self, request, queryset):
        updated = queryset.update(status='active')
        self.message_user(request, f'Активировано {updated} партнеров')

    activate_partners.short_description = 'Активировать выбранных партнеров'

    def pause_partners(self, request, queryset):
        updated = queryset.update(status='paused')
        self.message_user(request, f'Приостановлено {updated} партнеров')

    pause_partners.short_description = 'Приостановить выбранных партнеров'

    def reset_monthly_stats(self, request, queryset):
        updated = queryset.update(impressions_this_month=0)
        self.message_user(request, f'Сброшена месячная статистика для {updated} партнеров')

    reset_monthly_stats.short_description = 'Сбросить месячную статистику'