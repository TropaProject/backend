from django.urls import path
from .views import EmbedMissingPointsView, EmbedRefreshPointsView, EmbedUpdatePointView, map_view

urlpatterns = [
    path("embed-missing/", EmbedMissingPointsView.as_view(), name="embed-missing-points"),
    path("embed-refresh/", EmbedRefreshPointsView.as_view(), name="embed-refresh-points"),
    path("embed-update/<str:point_id>/", EmbedUpdatePointView.as_view(), name="embed-update-point"),
    path("map/", map_view, name="map_view")
,
]
