"""v1 URL routes for the edl_panel plugin."""
from django.urls import path

from edl_panel.rest_api.v1 import views

app_name = 'v1'

urlpatterns = [
    path('health/', views.HealthView.as_view(), name='health'),
    path('me/', views.MeView.as_view(), name='me'),
    path('users/', views.UsersView.as_view(), name='users'),
    path('users/<str:username>/deactivate/', views.DeactivateUserView.as_view(), name='user-deactivate'),
    path('users/<str:username>/reactivate/', views.ReactivateUserView.as_view(), name='user-reactivate'),
    path('enrollments/enroll/', views.EnrollView.as_view(), name='enroll'),
    path('enrollments/unenroll/', views.UnenrollView.as_view(), name='unenroll'),
    path('roles/', views.RolesView.as_view(), name='roles'),
]
