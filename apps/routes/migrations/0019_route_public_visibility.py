from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("routes", "0018_pointearning_point_assigned_at_point_edit_status_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="route",
            name="is_public",
            field=models.BooleanField(default=False, help_text="Route is visible to other users"),
        ),
        migrations.AddField(
            model_name="route",
            name="public_uses_count",
            field=models.PositiveIntegerField(default=0, help_text="How many times other users copied this route"),
        ),
        migrations.AddField(
            model_name="route",
            name="original_route",
            field=models.ForeignKey(
                blank=True,
                help_text="Public route this route was copied from",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="copied_routes",
                to="routes.route",
            ),
        ),
        migrations.AddIndex(
            model_name="route",
            index=models.Index(fields=["is_public", "created_at"], name="routes_is_publ_675143_idx"),
        ),
        migrations.AddIndex(
            model_name="route",
            index=models.Index(fields=["original_route"], name="routes_origina_1db873_idx"),
        ),
    ]
