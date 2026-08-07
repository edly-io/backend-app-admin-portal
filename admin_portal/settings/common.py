"""
Common settings for the admin_portal plugin.

``plugin_settings`` is called by the Open edX plugin machinery against the
LMS settings object at startup (for every settings variant). Keep defaults
here; environment-specific overrides go in ``production.py``.
"""


def plugin_settings(settings):
    """Inject admin_portal defaults into the LMS settings object."""
    # Django group whose members are treated as EDL admins. The permission
    # gate (EDL-2) checks membership of this group.
    settings.ADMIN_PORTAL_ADMIN_GROUP = 'edl_admin'

    # When True, Django superusers bypass the EDL-admin group check.
    settings.ADMIN_PORTAL_SUPERUSER_BYPASS = True

    # Password provisioning mode for admin-created accounts (EDL-4/EDL-5):
    #   'link'  -> create with an unusable password and email a set-password link
    #   'copy'  -> generate a password and surface it once to the admin
    settings.ADMIN_PORTAL_PASSWORD_MODE = 'link'

    # Absolute URL of the Admin Portal MFE. The LMS-host landing page
    # (``/admin-portal/``) redirects admins here. Leave empty to derive
    # ``<scheme>://apps.<lms-host>/admin-portal/`` from the request (the tutor
    # MFE-host convention); set explicitly if the MFE lives elsewhere.
    settings.ADMIN_PORTAL_MFE_URL = ''
