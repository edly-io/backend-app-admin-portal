"""Top-level URL configuration for the edl_panel plugin.

Mounted by the platform at ``^edl-panel/`` (see ``apps.EdlPanelConfig``), so:

* ``/edl-panel/``            -> browser-facing panel landing (``PanelIndexView``)
* ``/edl-panel/api/v1/...``  -> REST API consumed by the panel
"""
from django.urls import include, path

from edl_panel import views

app_name = 'edl_panel'

urlpatterns = [
    path('', views.PanelIndexView.as_view(), name='index'),
    path('api/v1/', include('edl_panel.rest_api.v1.urls', namespace='v1')),
]
