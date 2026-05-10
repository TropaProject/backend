from django.db import migrations, models


def copy_description_to_title(apps, schema_editor):
    Route = apps.get_model("routes", "Route")
    for route in Route.objects.filter(title__isnull=True).exclude(description__isnull=True):
        route.title = route.description[:255]
        route.save(update_fields=["title"])


class Migration(migrations.Migration):

    dependencies = [
        ("routes", "0019_route_public_visibility"),
    ]

    operations = [
        migrations.AddField(
            model_name="route",
            name="title",
            field=models.CharField(blank=True, help_text="Название маршрута", max_length=255, null=True),
        ),
        migrations.RunPython(copy_description_to_title, migrations.RunPython.noop),
    ]
