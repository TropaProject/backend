from .views import *
from django.urls import path

urlpatterns = [
    path("<str:point_id>/create-review/", ReviewView.as_view(), name="create-review"),
    path("<str:point_id>/", PointDetailView.as_view(), name="point-detail"),
    path("<str:point_id>/reviews/", PointAllReviewsView.as_view(), name="point-reviews"),
]