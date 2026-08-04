"""App configuration for edl_panel."""
from django.apps import AppConfig


class EdlPanelConfig(AppConfig):
    """
    edl-panel Open edX plugin application configuration.

    Registered under the ``lms.djangoapp`` entry point so the platform
    auto-discovers it, mounts its URLs at ``^edl-panel/`` and loads its
    plugin settings. See edx-django-utils Django App Plugins:
    https://github.com/openedx/edx-django-utils/tree/master/edx_django_utils/plugins
    """

    name = 'edl_panel'
    verbose_name = 'EDL Panel'

    plugin_app = {
        'url_config': {
            'lms.djangoapp': {
                'namespace': 'edl_panel',
                'regex': r'^edl-panel/',
                'relative_path': 'urls',
            },
        },
        'settings_config': {
            'lms.djangoapp': {
                'common': {'relative_path': 'settings.common'},
                'test': {'relative_path': 'settings.test'},
                'production': {'relative_path': 'settings.production'},
            },
        },
    }
