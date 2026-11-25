"""Create the service account used for Studio requests."""
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations


def create_service_user(apps, schema_editor):
    app_label, model_name = settings.AUTH_USER_MODEL.split('.')
    User = apps.get_model(app_label, model_name)
    username = getattr(settings, 'ADMIN_PORTAL_SERVICE_USER', 'edl_portal_service')
    user, created = User.objects.get_or_create(
        username=username,
        defaults={
            # auth_user.email is unique in edx-platform, so a blank email would take the only blank slot.
            'email': f'{username}@service.invalid',
            'is_staff': True,
            'is_superuser': False,
            'is_active': True,
        },
    )
    if created:
        user.password = make_password(None)
        user.save(update_fields=['password'])
    elif not (user.is_active and user.is_staff):
        raise RuntimeError(
            f"The account '{username}' already exists but is not an active staff user. "
            'Make it active staff, or set ADMIN_PORTAL_SERVICE_USER to another username, then migrate again.'
        )


class Migration(migrations.Migration):
    dependencies = [
        ('admin_portal', '0003_resend_invite_action'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [migrations.RunPython(create_service_user, migrations.RunPython.noop)]
