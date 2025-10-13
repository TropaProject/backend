from django.contrib import admin
from .models import Article
@admin.register(Article)
class FeedbackAdmin(admin.ModelAdmin):
    list_display = ("id", "title")

