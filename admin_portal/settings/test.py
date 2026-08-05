"""
Standalone Django settings for running the admin_portal test suite outside of
edx-platform (``pytest`` / ``tox``). Inside the LMS the plugin uses the
platform's settings plus ``common.plugin_settings``.
"""

SECRET_KEY = 'admin-portal-test-secret-key'

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'rest_framework',
    'admin_portal',
]

MIDDLEWARE = [
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

ROOT_URLCONF = 'admin_portal.tests.urls'

USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Plugin defaults (mirrors common.plugin_settings for the standalone suite).
ADMIN_PORTAL_ADMIN_GROUP = 'edl_admin'
ADMIN_PORTAL_PASSWORD_MODE = 'link'
ADMIN_PORTAL_SUPERUSER_BYPASS = True
