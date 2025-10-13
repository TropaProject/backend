from django.db import models


class Article(models.Model):
    id = models.AutoField(primary_key=True)
    title = models.CharField(max_length=255, help_text="Заголовок статьи")
    slug = models.SlugField(unique=True, help_text="URL-идентификатор")

    # Основной контент
    content = models.TextField(help_text="Текст статьи")
    cover = models.ImageField(
        upload_to="articles/covers/",
        null=True, blank=True,
        help_text="Обложка статьи"
    )

    # SEO-поля
    seo_title = models.CharField(
        max_length=255, null=True, blank=True,
        help_text="SEO title (если пусто — берётся title)"
    )
    seo_description = models.TextField(
        null=True, blank=True,
        help_text="Meta description для поисковиков"
    )
    seo_keywords = models.CharField(
        max_length=500, null=True, blank=True,
        help_text="Ключевые слова через запятую"
    )

    # Служебные поля
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    is_published = models.BooleanField(default=False)

    class Meta:
        db_table = "articles"
        verbose_name = "Статья"
        verbose_name_plural = "Статьи"
        indexes = [
            models.Index(fields=["slug"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["is_published"]),
        ]

    def __str__(self):
        return self.title

    def get_seo_title(self):
        return self.seo_title or self.title
