from django.contrib import admin
from .models import City, CityArea, Interest, Mood, Point, PointEmbedding, Route, Feedback


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "latitude", "longitude")
    search_fields = ("id", "name")
    list_filter = ("name",)


@admin.register(CityArea)
class CityAreaAdmin(admin.ModelAdmin):
    list_display = ("name", "city", "latitude", "longitude")
    search_fields = ("name", "city__name")
    list_filter = ("city",)


@admin.register(Interest)
class InterestAdmin(admin.ModelAdmin):
    list_display = ("id", "label")
    search_fields = ("id", "label")


@admin.register(Mood)
class MoodAdmin(admin.ModelAdmin):
    list_display = ("id", "label")
    search_fields = ("id", "label")


@admin.register(Point)
class PointAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "city", "average_visit_duration", "average_cost", "is_partner")
    search_fields = ("id", "name", "city__name")
    list_filter = ("city", "is_partner", "partner_tier")
    filter_horizontal = ("interests", "moods")


@admin.register(PointEmbedding)
class PointEmbeddingAdmin(admin.ModelAdmin):
    list_display = ("point", "updated_at")
    search_fields = ("point__name",)


@admin.register(Route)
class RouteAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "created_at", "total_duration", "total_cost", "status")
    search_fields = ("id", "user__username")
    list_filter = ("status", "created_at", "user")
    filter_horizontal = ("points",)


@admin.register(Feedback)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "route", "going", "created_at")
    search_fields = ("id", "route__id")
    list_filter = ("going", "created_at")
