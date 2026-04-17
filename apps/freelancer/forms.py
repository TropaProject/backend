from django import forms
from apps.routes.models import Point, Tag, Interest, Mood
from django.contrib.admin.widgets import FilteredSelectMultiple

class FreelancerPointEditForm(forms.ModelForm):
    # Разрешаем редактировать только определённые поля
    tags = forms.ModelMultipleChoiceField(
        queryset=Tag.objects.all(),
        widget=FilteredSelectMultiple("Теги", is_stacked=False),
        required=False
    )
    interests = forms.ModelMultipleChoiceField(
        queryset=Interest.objects.all(),
        widget=FilteredSelectMultiple("Интересы", is_stacked=False),
        required=False
    )
    moods = forms.ModelMultipleChoiceField(
        queryset=Mood.objects.all(),
        widget=FilteredSelectMultiple("Настроения", is_stacked=False),
        required=False
    )

    class Meta:
        model = Point
        fields = [
            'description',
            'tags',
            'interests',
            'moods',
            'keywords',
            'average_visit_duration',
            'average_cost',
            'best_visit_time',
            'working_hours_json',
            'is_seasonal',
            'seasonal_months',
            'image_url',
            'address',
        ]
        widgets = {
            'keywords': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Введите ключевые слова через запятую'}),
            'working_hours_json': forms.Textarea(attrs={'rows': 5, 'placeholder': 'JSON формат режима работы'}),
            'best_visit_time': forms.CheckboxSelectMultiple(choices=Point.BEST_TIME_CHOICES),
            'seasonal_months': forms.SelectMultiple(attrs={'size': 6}, choices=[(i, i) for i in range(1, 13)]),
            'description': forms.Textarea(attrs={'rows': 6}),
        }
        help_texts = {
            'keywords': 'Ключевые слова через запятую',
            'working_hours_json': 'Пример: {"monday": "09:00-18:00", "tuesday": "09:00-18:00"}',
        }