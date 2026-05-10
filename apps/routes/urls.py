from .views import *
from django.urls import path

urlpatterns = [
    path("feedback/", FeedbackView.as_view(), name="route-feedback"),
    path('form/', FormDataView.as_view(), name='form-data-view'),
    path('food-form/', FormFoodView.as_view(), name='form-food-view'),
    path("area/", CityAreaView.as_view(), name="city-areas"),
    path("city-suggestions/", CitySuggestionListCreateView.as_view(), name="city-suggestions"),
    path("city-suggestions/<uuid:suggestion_id>/vote/", CitySuggestionVoteView.as_view(), name="city-suggestion-vote"),
    path("generate/", GenerateRouteView.as_view(), name="generate-route"),
    path("edit-status/", EditRouteStatusView.as_view(), name="edit-route-status"),
    path("visibility/", RouteVisibilityView.as_view(), name="route-visibility"),
    path("public/", PublicRoutesListView.as_view(), name="public-routes-list"),
    path("recommended/", RecommendedPublicRoutesView.as_view(), name="recommended-public-routes"),
    path("copy-public/", CopyPublicRouteView.as_view(), name="copy-public-route"),
    path("cancel/", CancelRouteView.as_view(), name="cancel-route"),
    path("show/<str:id_route>/", RouteDetailView.as_view(), name="route-detail"),
    path("gen-description/", GenerateDescriptionView.as_view(), name="generate-description"),
    path("pipeline/", pipeline_view, name="pipeline"),
    path("add_food_point/", AddFoodPointView.as_view()),
]
