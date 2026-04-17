from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from apps.routes.models import Point


class Command(BaseCommand):
    help = 'Создаёт группы и права для фрилансеров и редакторов'

    def handle(self, *args, **options):
        # Группа фрилансеров
        freelancer_group, _ = Group.objects.get_or_create(name='Freelancer')
        # Группа редакторов (админы по проверке)
        editor_group, _ = Group.objects.get_or_create(name='Editor')
        # Право на проверку точек (можно добавить вручную)
        content_type = ContentType.objects.get_for_model(Point)
        can_review, _ = Permission.objects.get_or_create(
            codename='can_review_points',
            name='Can review points',
            content_type=content_type,
        )
        editor_group.permissions.add(can_review)
        self.stdout.write(self.style.SUCCESS('Группы и права созданы'))