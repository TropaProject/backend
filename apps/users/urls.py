from django.urls import path
from .views import RegisterView, LoginView, RefreshView, UserView, UserRoutesListView, UserStatisticsView

urlpatterns = [
    path("auth/register", RegisterView.as_view(), name="register"),
    path("auth/login", LoginView.as_view(), name="login"),
    path("auth/refresh", RefreshView.as_view(), name="token_refresh"),
    path("user", UserView.as_view(), name="user_info"),
    path("user/list/", UserRoutesListView.as_view(), name="user-routes-list"),
    path("user/statistic/", UserStatisticsView.as_view(), name="user-statistic"),
]