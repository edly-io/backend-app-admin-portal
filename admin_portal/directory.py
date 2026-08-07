"""User directory (list / search / filter) for the admin_portal plugin (EDL-6).

This is the one genuinely new piece of query logic: the platform's account API
only does exact-match lookups, so partial email/name search and status
filtering are built here.

Status vocabulary:
    * ``disabled`` — ``UserStanding.account_status == 'disabled'`` (login and
      course access blocked; enrollments/grades retained).
    * ``pending``  — not yet activated (``is_active`` False) and not disabled;
      e.g. an invited learner who hasn't set their password.
    * ``active``   — ``is_active`` True and not disabled.

Name (``UserProfile.name``) and standing (``UserStanding``) live in platform
models. We engage them via ``hasattr`` capability checks so the same code runs
standalone (username/email search + is_active status) and in the LMS (adds
name search + disabled status).
"""
from django.contrib.auth import get_user_model
from django.db.models import Q

User = get_user_model()

# Mirrors common.djangoapps.student.models.UserStanding.ACCOUNT_DISABLED.
ACCOUNT_DISABLED = 'disabled'

STATUS_PENDING = 'pending'
STATUS_ACTIVE = 'active'
STATUS_DISABLED = 'disabled'
STATUS_CHOICES = (STATUS_PENDING, STATUS_ACTIVE, STATUS_DISABLED)

_HAS_PROFILE = hasattr(User, 'profile')
_HAS_STANDING = hasattr(User, 'standing')


def derive_status(is_active, standing_status):
    """Map (is_active, standing) to the panel's status vocabulary."""
    if standing_status == ACCOUNT_DISABLED:
        return STATUS_DISABLED
    return STATUS_ACTIVE if is_active else STATUS_PENDING


def get_profile_name(user):
    """Return the user's full name, or '' when unavailable."""
    if not _HAS_PROFILE:
        return ''
    try:
        return user.profile.name or ''
    except Exception:  # noqa: BLE001 - no profile row yet
        return ''


def get_standing_status(user):
    """Return the user's account-standing status, or None when unavailable."""
    if not _HAS_STANDING:
        return None
    try:
        return user.standing.account_status
    except Exception:  # noqa: BLE001 - no standing row yet
        return None


def _search_q(term):
    q = Q(username__icontains=term) | Q(email__icontains=term)
    if _HAS_PROFILE:
        q |= Q(profile__name__icontains=term)
    return q


def _apply_status(queryset, status):
    if status == STATUS_DISABLED:
        if _HAS_STANDING:
            return queryset.filter(standing__account_status=ACCOUNT_DISABLED)
        return queryset.none()
    if status == STATUS_ACTIVE:
        queryset = queryset.filter(is_active=True)
        if _HAS_STANDING:
            queryset = queryset.exclude(standing__account_status=ACCOUNT_DISABLED)
        return queryset
    if status == STATUS_PENDING:
        queryset = queryset.filter(is_active=False)
        if _HAS_STANDING:
            queryset = queryset.exclude(standing__account_status=ACCOUNT_DISABLED)
        return queryset
    return queryset


def list_users(*, search='', status=None):
    """Return an ordered User queryset filtered by search term and status."""
    queryset = User.objects.all().order_by('id')
    if _HAS_PROFILE:
        queryset = queryset.select_related('profile')
    if _HAS_STANDING:
        queryset = queryset.select_related('standing')
    if search:
        queryset = queryset.filter(_search_q(search))
    return _apply_status(queryset, status)


def derive_lms_role(user):
    """Coarse platform role for the directory column: admin > staff > learner.

    Mirrors the Django/Open edX global flags — ``is_superuser`` (full admin),
    ``is_staff`` (global course staff) — and defaults everyone else to
    ``learner``. This is a platform-wide role, distinct from the course-scoped
    roles granted on the Staff & roles screen.
    """
    if getattr(user, 'is_superuser', False):
        return 'admin'
    if getattr(user, 'is_staff', False):
        return 'staff'
    return 'learner'


def serialize_user(user):
    """Serialize a user row for the directory list."""
    return {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'name': get_profile_name(user),
        'is_active': user.is_active,
        'status': derive_status(user.is_active, get_standing_status(user)),
        'lms_role': derive_lms_role(user),
    }
