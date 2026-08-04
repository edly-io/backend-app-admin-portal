"""
Production settings for the edl_panel plugin.

Reads overrides from the LMS ``ENV_TOKENS`` (Tutor ``config.yml`` /
``*_CFG`` YAML), falling back to whatever ``common.plugin_settings`` set.
"""


def plugin_settings(settings):
    """Apply environment overrides for edl_panel."""
    env_tokens = getattr(settings, 'ENV_TOKENS', {})

    settings.EDL_PANEL_ADMIN_GROUP = env_tokens.get(
        'EDL_PANEL_ADMIN_GROUP', settings.EDL_PANEL_ADMIN_GROUP,
    )
    settings.EDL_PANEL_PASSWORD_MODE = env_tokens.get(
        'EDL_PANEL_PASSWORD_MODE', settings.EDL_PANEL_PASSWORD_MODE,
    )
