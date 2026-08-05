"""Top-level URL configuration for the admin_portal plugin.

Mounted by the platform at ``^admin-portal/`` (see ``apps.AdminPortalConfig``), so:

* ``/admin-portal/``            -> browser-facing panel landing (``PanelIndexView``)
* ``/admin-portal/api/v1/...``  -> REST API consumed by the panel
"""
from django.urls import include, path

from admin_portal import views

app_name = 'admin_portal'

urlpatterns = [
    path('', views.PanelIndexView.as_view(), name='index'),
    path('api/v1/', include('admin_portal.rest_api.v1.urls', namespace='v1')),
]
