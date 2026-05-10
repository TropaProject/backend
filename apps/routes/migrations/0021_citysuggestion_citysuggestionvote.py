from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("routes", "0020_route_title"),
    ]

    operations = [
        migrations.CreateModel(
            name="CitySuggestion",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=100)),
                ("normalized_name", models.CharField(max_length=100, unique=True)),
                ("country", models.CharField(blank=True, max_length=100, null=True)),
                ("comment", models.TextField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[("pending", "На рассмотрении"), ("approved", "Одобрен"), ("rejected", "Отклонен")],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="city_suggestions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "city_suggestions",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="CitySuggestionVote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "suggestion",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="votes",
                        to="routes.citysuggestion",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="city_suggestion_votes",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "city_suggestion_votes",
                "unique_together": {("suggestion", "user")},
            },
        ),
        migrations.AddField(
            model_name="citysuggestion",
            name="voters",
            field=models.ManyToManyField(
                blank=True,
                related_name="voted_city_suggestions",
                through="routes.CitySuggestionVote",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddIndex(
            model_name="citysuggestion",
            index=models.Index(fields=["status", "created_at"], name="city_sugges_status_9d1fd9_idx"),
        ),
        migrations.AddIndex(
            model_name="citysuggestion",
            index=models.Index(fields=["normalized_name"], name="city_sugges_normali_6100f9_idx"),
        ),
        migrations.AddIndex(
            model_name="citysuggestionvote",
            index=models.Index(fields=["suggestion", "created_at"], name="city_sugges_suggest_1ccdef_idx"),
        ),
        migrations.AddIndex(
            model_name="citysuggestionvote",
            index=models.Index(fields=["user", "created_at"], name="city_sugges_user_id_14c8a6_idx"),
        ),
    ]
