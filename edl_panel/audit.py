"""Audit helper for the edl_panel plugin.

Call :func:`record_action` from every mutating panel operation. It writes an
:class:`~edl_panel.models.EdlAdminAuditLog` row and emits a matching
``eventtracking`` event for the analytics pipeline. The event emit is
best-effort and never blocks the audited action.
"""
import logging

from edl_panel.models import EdlAdminAuditLog

log = logging.getLogger(__name__)


def _actor_or_none(actor):
    """Return a persisted user or None (anonymous/system actors are stored null)."""
    if actor is not None and getattr(actor, 'is_authenticated', False):
        return actor
    return None


def record_action(actor, action, *, target_user=None, target_identifier='',
                   course_id='', detail=None, reason=''):
    """
    Write an audit entry and emit a tracking event.

    Args:
        actor: the acting user (AnonymousUser/None is stored as null).
        action: an :class:`EdlAdminAuditLog.Action` value.
        target_user: the affected user, if one exists.
        target_identifier: email/username when there is no user row yet.
        course_id: course key string, for enrollment/role actions.
        detail: JSON-serialisable dict of extra context.
        reason: free-text reason.

    Returns:
        The created :class:`EdlAdminAuditLog` instance.
    """
    entry = EdlAdminAuditLog.objects.create(
        actor=_actor_or_none(actor),
        action=action,
        target_user=target_user,
        target_identifier=target_identifier or '',
        course_id=str(course_id) if course_id else '',
        detail=detail or {},
        reason=reason or '',
    )
    _emit_event(entry)
    return entry


def _emit_event(entry):
    """Emit an eventtracking event; no-op if eventtracking is unavailable."""
    try:  # pragma: no cover - eventtracking is platform-provided
        from eventtracking import tracker
    except ImportError:
        return
    try:
        tracker.emit(f'edl_panel.{entry.action}', {
            'actor_id': entry.actor_id,
            'target_user_id': entry.target_user_id,
            'target_identifier': entry.target_identifier,
            'course_id': entry.course_id,
            'detail': entry.detail,
        })
    except Exception:  # pragma: no cover - never let analytics break the action
        log.exception('edl_panel: failed to emit tracking event for audit %s', entry.pk)
