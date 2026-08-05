"""Data models for the admin_portal plugin."""
from django.conf import settings
from django.db import models


class EdlAdminAuditLog(models.Model):
    """
    Append-only audit trail of admin actions performed through the panel.

    One row per create / deactivate / enroll / unenroll / role change, capturing
    actor, action, target and timestamp. Enrollment actions additionally leave
    the platform's own ``ManualEnrollmentAudit`` row; this table covers the
    actions that have no core audit equivalent and gives the panel a single,
    uniform trail.
    """

    class Action(models.TextChoices):
        CREATE_USER = 'create_user', 'Create user'
        DEACTIVATE_USER = 'deactivate_user', 'Deactivate user'
        REACTIVATE_USER = 'reactivate_user', 'Reactivate user'
        ENROLL = 'enroll', 'Enroll'
        UNENROLL = 'unenroll', 'Unenroll'
        ROLE_GRANT = 'role_grant', 'Grant course role'
        ROLE_REVOKE = 'role_revoke', 'Revoke course role'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='edl_admin_actions',
        help_text='Admin who performed the action (null if the actor was later removed).',
    )
    action = models.CharField(max_length=64, choices=Action.choices)
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='edl_admin_targeted',
        help_text='Affected user, when one exists.',
    )
    target_identifier = models.CharField(
        max_length=254, blank=True,
        help_text='Email/username when the target is not (yet) a user row (e.g. a pending enrollment).',
    )
    course_id = models.CharField(max_length=255, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    reason = models.TextField(blank=True)
    created = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = 'EDL admin audit entry'
        verbose_name_plural = 'EDL admin audit log'
        ordering = ('-created',)
        indexes = [
            models.Index(fields=['action', 'created']),
            models.Index(fields=['target_user', 'created']),
        ]

    @property
    def target_repr(self):
        """Human-readable target: username if known, else the raw identifier."""
        if self.target_user_id:
            return self.target_user.get_username()
        return self.target_identifier

    def __str__(self):
        actor = self.actor.get_username() if self.actor_id else 'system'
        return f'{self.created:%Y-%m-%d %H:%M} {actor} {self.action} {self.target_repr}'.strip()
