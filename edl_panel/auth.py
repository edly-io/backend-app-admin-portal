"""Authentication wiring for the edl_panel REST API.

In the LMS we authenticate with JWT (the standard for Open edX MFE→API calls)
plus session auth as a fallback. When the plugin is imported standalone (its
own test suite), ``edx_rest_framework_extensions`` is not installed, so we fall
back to session auth only.
"""
from rest_framework.authentication import SessionAuthentication


def get_authentication_classes():
    """Return the auth classes available in the current environment."""
    classes = []
    try:  # pragma: no cover - exercised in-platform, not in standalone tests
        from edx_rest_framework_extensions.auth.jwt.authentication import JwtAuthentication
        classes.append(JwtAuthentication)
    except ImportError:
        pass
    classes.append(SessionAuthentication)
    return classes
