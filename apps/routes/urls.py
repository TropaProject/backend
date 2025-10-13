from .views import *
from django.urls import path

urlpatterns = [
    path("feedback/", FeedbackView.as_view(), name="route-feedback"),
    path('form/', FormDataView.as_view(), name='form-data-view'),
    path("area/", CityAreaView.as_view(), name="city-areas"),
    path("generate/", GenerateRouteView.as_view(), name="generate-route"),
    path("edit-status/", EditRouteStatusView.as_view(), name="edit-route-status"),
    path("cancel/", CancelRouteView.as_view(), name="cancel-route"),
    path("show/<str:id_route>/", RouteDetailView.as_view(), name="route-detail"),

]