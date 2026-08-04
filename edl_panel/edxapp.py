"""Thin seam over edx-platform account/password APIs.

Every call into core lives here and imports lazily, so the plugin (and its
standalone test suite) imports cleanly without edx-platform present. Tests
patch these functions; in the LMS they delegate to the real platform helpers.

We deliberately *reuse* the platform's own account-creation, password and
email machinery rather than reimplementing any of it.
"""

try:  # AccountValidationError carries the structured duplicate-field info.
    from common.djangoapps.student.helpers import AccountValidationError
except Exception:  # pragma: no cover - standalone fallback (edx-platform absent)
    class AccountValidationError(Exception):
        """Standalone stand-in mirroring the platform exception's shape."""

        def __init__(self, message, field=None, error_code=None):
            super().__init__(message)
            self.field = field
            self.error_code = error_code


def account_creation_form(data):
    """Build the platform ``AccountCreationForm`` (terms not required for admin-created accounts)."""
    from openedx.core.djangoapps.user_authn.views.registration_form import AccountCreationForm
    return AccountCreationForm(data=data, tos_required=False)


def do_create_account(form):
    """Create User + UserProfile + Registration via the platform helper."""
    from common.djangoapps.student.helpers import do_create_account as _do_create_account
    return _do_create_account(form)


def generate_password(length=12):
    """Generate a validator-compliant random password (platform helper)."""
    from edx_django_utils.user import generate_password as _generate_password
    return _generate_password(length=length)


def send_set_password_email(user, request=None):
    """Email the user a single-use set-password link (activates on confirm)."""
    from openedx.core.djangoapps.user_authn.views.password_reset import (
        send_password_reset_email_for_user,
    )
    return send_password_reset_email_for_user(user, request)
