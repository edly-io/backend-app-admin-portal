"""
ACE message types for the admin portal.

Imports platform modules at module level, so import it lazily (see
``edxapp.send_set_password_email``) to keep the standalone test suite importable.
"""
from email.utils import formataddr, parseaddr

from django.conf import settings

from openedx.core.djangoapps.ace_common.message import BaseMessageType
from openedx.core.djangoapps.site_configuration import helpers as configuration_helpers


class AccountInvite(BaseMessageType):
    """
    Welcome email with a set-password link for accounts created in the admin portal.
    """
    APP_LABEL = 'admin_portal'
    NAME = 'accountinvite'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # pylint: disable=unsupported-assignment-operation
        # Link-mode accounts have an unusable password; without this ACE drops the mail.
        self.options['skip_disable_user_policy'] = True
        self.options['transactional'] = True

        # The django_email channel ignores from_name.txt, so the display name goes into the address.
        platform_name = configuration_helpers.get_value('PLATFORM_NAME', settings.PLATFORM_NAME)
        address = parseaddr(self.options.get('from_address') or settings.DEFAULT_FROM_EMAIL)[1]
        self.options['from_address'] = formataddr((platform_name, address))
