"""Account deactivation/reactivation service for the admin_portal plugin (EDL-7).

Disabling is *not* retirement: it blocks login and course access (via the
platform's ``UserStandingMiddleware``) while keeping enrollments, submissions
and grades intact, and it is fully reversible.
"""
from django.contrib.auth import get_user_model

from admin_portal import edxapp

User = get_user_model()


class UserNotFound(Exception):
    """Raised when the target username does not exist."""


def set_account_disabled(*, actor, username, disabled):
    """
    Disable or re-enable an account by username.

    Returns the affected user. Raises :class:`UserNotFound` if no such user.
    """
    user = User.objects.filter(username=username).first()
    if user is None:
        raise UserNotFound(username)
    edxapp.set_user_standing(user, disabled=disabled, changed_by=actor)
    return user
