"""Django admin registration for the edl_panel audit log (read-only)."""
from django.contrib import admin

from edl_panel.models import EdlAdminAuditLog


@admin.register(EdlAdminAuditLog)
class EdlAdminAuditLogAdmin(admin.ModelAdmin):
    """Read-only view of the audit log; entries are never editable."""

    list_display = ('created', 'actor', 'action', 'target_repr', 'course_id')
    list_filter = ('action', 'created')
    search_fields = ('actor__username', 'target_user__username', 'target_identifier', 'course_id')
    readonly_fields = (
        'actor', 'action', 'target_user', 'target_identifier',
        'course_id', 'detail', 'reason', 'created',
    )
    date_hierarchy = 'created'

    @admin.display(description='Target')
    def target_repr(self, obj):
        return obj.target_repr

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
