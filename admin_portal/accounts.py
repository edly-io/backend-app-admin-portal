"""Account-creation service for the admin_portal plugin (EDL-5).

Wraps the platform's ``do_create_account`` with the panel's rules:

* one user at a time, created atomically (no partial account on failure);
* duplicate email/username surface as inline field errors (HTTP 409);
* password provisioning follows ``ADMIN_PORTAL_PASSWORD_MODE``:
    - ``link`` (default): create with an unusable password and email a
      set-password link; the account activates when the link is confirmed.
    - ``copy``: set a generated password, activate immediately, and return it
      once so the admin can copy it.
"""
import logging

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction

from admin_portal import edxapp

log = logging.getLogger(__name__)

_DUPLICATE_HINTS = ('already', 'exists', 'taken', 'in use')


class CreateUserError(Exception):
    """Validation/conflict error carrying inline field errors and a status code."""

    def __init__(self, field_errors, status_code=400):
        super().__init__(str(field_errors))
        self.field_errors = field_errors
        self.status_code = status_code


def _looks_like_conflict(messages):
    joined = ' '.join(messages).lower()
    return any(hint in joined for hint in _DUPLICATE_HINTS)


def create_learner(*, actor, request, username, email, name, password_mode='link'):
    """
    Create a single account and provision its password per ``password_mode``.

    Returns:
        (user, password) — ``password`` is the plaintext to surface in
        ``copy`` mode, or ``None`` in ``link`` mode.

    Raises:
        CreateUserError: on duplicate (409) or other validation failure (400),
        with nothing persisted.
    """
    password = edxapp.generate_password()
    form = edxapp.account_creation_form({
        'username': username,
        'email': email,
        'name': name,
        'password': password,
    })

    try:
        with transaction.atomic():
            user, _profile, registration = edxapp.do_create_account(form)
            if password_mode == 'copy':
                # Activate so the copied password works immediately.
                registration.activate()
                result_password = password
            else:
                # Wipe the generated password; the set-password link activates
                # the account and lets the learner choose their own.
                user.set_unusable_password()
                user.save(update_fields=['password'])
                result_password = None
    except edxapp.AccountValidationError as exc:
        field = getattr(exc, 'field', None) or 'non_field_errors'
        code = getattr(exc, 'error_code', '') or ''
        status_code = 409 if 'duplicate' in code or _looks_like_conflict([str(exc)]) else 400
        raise CreateUserError({field: [str(exc)]}, status_code) from exc
    except DjangoValidationError as exc:
        field_errors = getattr(exc, 'message_dict', None) or {
            'non_field_errors': list(getattr(exc, 'messages', [str(exc)])),
        }
        flat = [msg for msgs in field_errors.values() for msg in msgs]
        status_code = 409 if _looks_like_conflict(flat) else 400
        raise CreateUserError(field_errors, status_code) from exc

    if password_mode != 'copy':
        # Send after commit so we never email about an account that rolled back.
        edxapp.send_set_password_email(user, getattr(request, '_request', request))

    return user, result_password
