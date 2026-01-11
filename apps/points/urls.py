from .views import *
from django.urls import path

urlpatterns = [
    path("<str:point_id>/create-review/", ReviewView.as_view(), name="create-review"),
    path("<str:point_id>/detail/", PointDetailView.as_view(), name="point-detail"),
    path("<str:point_id>/reviews/", PointAllReviewsView.as_view(), name="point-reviews"),
    path("<str:point_id>/favorite/", ToggleFavoritePointView.as_view(), name="toggle-favorite"),
    path("<str:point_id>/favorite/note/", UpdateFavoriteNoteView.as_view(), name="favorite-note"),
    path("favorites/", UserFavoritePointsView.as_view(), name="user-favorites"),
]