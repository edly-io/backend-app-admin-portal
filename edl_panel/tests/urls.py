"""Root URLconf for the standalone test suite.

Mounts the plugin at the same prefix the platform uses (``^edl-panel/``),
so tests exercise real, namespaced paths.
"""
from django.urls import include, path

urlpatterns = [
    path('edl-panel/', include('edl_panel.urls')),
]
