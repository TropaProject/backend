from django.urls import path
from . import views
urlpatterns = [
    path("places/", views.place_search_page, name="place_search_page"),
    path("api/areas", views.api_city_areas, name="api_city_areas"),
    path("api/places", views.api_places, name="api_places"),
    path("api/save_points", views.api_save_points, name="api_save_points"),
]