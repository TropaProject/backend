
from .models import City, CityArea, Interest, Mood, Point, PointEmbedding, Route, Feedback, InterestCategory, Tag,ReviewPoint, FavoritePoint
from django.contrib import admin


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "latitude", "longitude")
    search_fields = ("id", "name")
    list_filter = ("name",)


@admin.register(CityArea)
class CityAreaAdmin(admin.ModelAdmin):
    list_display = ('id',"name", "city", "latitude", "longitude")
    search_fields = ("name", "city__name")
    list_filter = ("city",)


@admin.register(InterestCategory)
class MoodAdmin(admin.ModelAdmin):
    list_display = ("id", "label")
    search_fields = ("id", "label")


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
    list_filter = ("city", "is_partner", "partner_tier",'interests')


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


@admin.register(Tag)
class InterestAdmin(admin.ModelAdmin):
    list_display = ('id',"name", "category")
    search_fields = ("name", "category")




@admin.register(ReviewPoint)
class ReviewPointAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "point", "rating", "created_at", "updated_at")
    list_filter = ("rating", "created_at", "updated_at")
    search_fields = ("user__username", "user__email", "point__name", "comment")
    ordering = ("-created_at",)
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        ("Основная информация", {
            "fields": ("user", "point", "rating", "comment")
        }),
        ("Служебные поля", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(FavoritePoint)
class FavoritePointAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "point", "note_short", "created_at")
    list_filter = ("created_at",)
    search_fields = ("user__username", "user__email", "point__name", "note")
    ordering = ("-created_at",)
    readonly_fields = ("created_at",)

    fieldsets = (
        ("Основная информация", {
            "fields": ("user", "point", "note")
        }),
        ("Служебные поля", {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )

    def note_short(self, obj):
        if not obj.note:
            return ""
        return obj.note[:40] + ("..." if len(obj.note) > 40 else "")
    note_short.short_description = "Заметка"
