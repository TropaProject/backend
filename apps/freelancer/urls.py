from django.contrib.auth.views import LogoutView
from django.urls import path, include

from apps.freelancer.views import *

urlpatterns = [
    path('freelancer/', include([
        path('dashboard/', freelancer_dashboard, name='freelancer_dashboard'),
        path('edit/<uuid:point_id>/', edit_point, name='freelancer_edit_point'),
        path('submit/<uuid:point_id>/', submit_point, name='submit_point'),
    ])),
    path('admin-panel/', include([
        path('assign/', assign_points, name='assign_points'),
        path('review/', review_points, name='review_points'),
        path('compare/<uuid:point_id>/', compare_point, name='compare_point'),
    ])),

]
