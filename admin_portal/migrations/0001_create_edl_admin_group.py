"""Create the EDL-admin Django group that gates the panel (EDL-2)."""
from django.conf import settings
from django.db import migrations

DEFAULT_GROUP = 'edl_admin'


def _group_name():
    return getattr(settings, 'ADMIN_PORTAL_ADMIN_GROUP', DEFAULT_GROUP)


def create_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.get_or_create(name=_group_name())


def delete_group(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    Group.objects.filter(name=_group_name()).delete()


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('auth', '__first__'),
    ]

    operations = [
        migrations.RunPython(create_group, delete_group),
    ]
