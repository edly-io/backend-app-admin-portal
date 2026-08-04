"""
Standalone Django settings for running the edl_panel test suite outside of
edx-platform (``pytest`` / ``tox``). Inside the LMS the plugin uses the
platform's settings plus ``common.plugin_settings``.
"""

SECRET_KEY = 'edl-panel-test-secret-key'

INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'rest_framework',
    'edl_panel',
]

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    },
}

ROOT_URLCONF = 'edl_panel.tests.urls'

USE_TZ = True
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Plugin defaults (mirrors common.plugin_settings for the standalone suite).
EDL_PANEL_ADMIN_GROUP = 'edl_admin'
EDL_PANEL_PASSWORD_MODE = 'link'
