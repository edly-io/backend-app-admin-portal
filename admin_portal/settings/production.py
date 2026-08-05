"""
Production settings for the admin_portal plugin.

Reads overrides from the LMS ``ENV_TOKENS`` (Tutor ``config.yml`` /
``*_CFG`` YAML), falling back to whatever ``common.plugin_settings`` set.
"""


def plugin_settings(settings):
    """Apply environment overrides for admin_portal."""
    env_tokens = getattr(settings, 'ENV_TOKENS', {})

    settings.ADMIN_PORTAL_ADMIN_GROUP = env_tokens.get(
        'ADMIN_PORTAL_ADMIN_GROUP', settings.ADMIN_PORTAL_ADMIN_GROUP,
    )
    settings.ADMIN_PORTAL_PASSWORD_MODE = env_tokens.get(
        'ADMIN_PORTAL_PASSWORD_MODE', settings.ADMIN_PORTAL_PASSWORD_MODE,
    )
    settings.ADMIN_PORTAL_SUPERUSER_BYPASS = env_tokens.get(
        'ADMIN_PORTAL_SUPERUSER_BYPASS', settings.ADMIN_PORTAL_SUPERUSER_BYPASS,
    )
