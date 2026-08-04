"""v1 URL routes for the edl_panel plugin."""
from django.urls import path

from edl_panel.rest_api.v1 import views

app_name = 'v1'

urlpatterns = [
    path('health/', views.HealthView.as_view(), name='health'),
    path('me/', views.MeView.as_view(), name='me'),
    path('users/', views.UsersView.as_view(), name='users'),
]
