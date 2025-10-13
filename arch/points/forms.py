# forms.py
from django import forms
from apps.core.models import City, CityArea

TOURIST_CATEGORY_CHOICES = [
    ("catering.cafe", "Кафе"),
    ("catering.bar", "Бары"),
    ("catering.restaurant", "Рестораны"),
    ("leisure.park", "Парки"),
    ("entertainment.museum", "Музеи"),
    ("heritage.sights", "Исторические места"),
    ("entertainment.culture", "Галереи / арт‑пространства"),
    ("entertainment.events", "Театры / культурные события"),
    ("tourism.sights", "Фото‑зоны / смотровые точки"),
    ("entertainment.zoo", "Зоопарки"),
    ("entertainment.theme_park", "Площади / тематические зоны"),
    ("tourism.attraction", "Интересные места"),
]


class PlaceSearchForm(forms.Form):
    city = forms.ModelChoiceField(queryset=City.objects.all(), label="Город")
    area = forms.ModelChoiceField(queryset=CityArea.objects.none(), required=False, label="Район")
    categories = forms.MultipleChoiceField(choices=TOURIST_CATEGORY_CHOICES, widget=forms.CheckboxSelectMultiple, label="Категории")
    limit = forms.IntegerField(min_value=1, max_value=100, initial=20, label="Лимит")
    lang = forms.ChoiceField(choices=[("ru", "Русский"), ("en", "English")], initial="ru", label="Язык")

    def __init__(self, *args, **kwargs):
        city_id = kwargs.pop("city_id", None)
        super().__init__(*args, **kwargs)
        if city_id:
            self.fields["area"].queryset = CityArea.objects.filter(city_id=city_id)
