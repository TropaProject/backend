# yourapp/management/commands/load_moscow_areas.py
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.core.models import City, CityArea  # замените yourapp на имя вашего приложения


AREAS = [
    # name, (min_lon, min_lat, max_lon, max_lat), relation_id
    ("Центральный административный округ", (37.5139298, 55.710271, 37.7135246, 55.7971397), 364005),
    ("Арбат", (37.5720599, 55.7437121, 37.6122284, 55.758061), 1257484),
    ("Басманный район", (37.6279401, 55.7507488, 37.7135246, 55.7819563), 1257201),
    ("Замоскворечье", (37.6151325, 55.7202801, 37.6542108, 55.7491534), 1255942),
    ("Красносельский район", (37.6283861, 55.7597965, 37.6888037, 55.7929812), 1257218),
    ("Мещанский район", (37.6122228, 55.7591203, 37.6448957, 55.7971397), 364001),
    ("Пресненский район", (37.5139298, 55.7443963, 37.609757, 55.7756393), 1275551),
    ("Таганский район", (37.6321094, 55.7257985, 37.6997522, 55.7547685), 1275608),
    ("Тверской район", (37.5761735, 55.7467048, 37.635017, 55.792578), 1257786),
    ("Хамовники", (37.5411899, 55.710271, 37.6123162, 55.7503457), 1255987),
    ("Якиманка", (37.5776062, 55.7110252, 37.62644, 55.7490432), 1275627),
]


class Command(BaseCommand):
    help = "Создаёт/обновляет центральные и туристические районы Москвы в CityArea с bbox"

    def add_arguments(self, parser):
        parser.add_argument(
            "--city-id",
            dest="city_id",
            default="moscow",
            help='ID города (City.id), например "moscow". По умолчанию: moscow',
        )
        parser.add_argument(
            "--city-name",
            dest="city_name",
            default=None,
            help='Название города (City.name), например "Москва". Если указан, перекрывает --city-id',
        )

    def get_city(self, city_id: str, city_name: str | None):
        if city_name:
            city = City.objects.filter(name__iexact=city_name).first()
            if not city:
                raise CommandError(f'Город с name="{city_name}" не найден.')
            return city
        city = City.objects.filter(Q(id=city_id) | Q(name__iexact=city_id)).first()
        if not city:
            raise CommandError(f'Город с id/name="{city_id}" не найден.')
        return city

    @transaction.atomic
    def handle(self, *args, **options):
        city_id = options["city_id"]
        city_name = options["city_name"]
        city = self.get_city(city_id, city_name)

        created, updated = 0, 0

        for name, (min_lon, min_lat, max_lon, max_lat), relation_id in AREAS:
            bbox = {
                "min_lat": float(min_lat),
                "max_lat": float(max_lat),
                "min_lon": float(min_lon),
                "max_lon": float(max_lon),
            }
            # В поле osm_area_id сохраняем OSM relation id.
            # Для Overpass area используйте: area_id = 3600000000 + relation_id.
            obj, is_created = CityArea.objects.update_or_create(
                city=city,
                name=name,
                defaults={
                    "osm_area_id": int(relation_id),
                    "bbox": bbox,
                    "latitude": None,
                    "longitude": None,
                },
            )
            if is_created:
                created += 1
            else:
                updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Готово: создано {created}, обновлено {updated} для города {city.name}."
            )
        )
