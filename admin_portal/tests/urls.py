"""Root URLconf for the standalone test suite.

Mounts the plugin at the same prefix the platform uses (``^admin-portal/``),
so tests exercise real, namespaced paths.
"""
from django.urls import include, path

urlpatterns = [
    path('admin-portal/', include('admin_portal.urls')),
]
