"""Tests for the invite email templates, ``AccountInvite`` and ``send_set_password_email``.

``body.html`` and ``head.html`` extend platform templates, so they are covered by
manual verification in a real LMS.
"""
import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth.tokens import default_token_generator
from django.template.loader import render_to_string

from admin_portal import edxapp

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = 'admin_portal/edx_ace/accountinvite/email'
TEMPLATE_FILES = ['subject.txt', 'body.txt', 'body.html', 'head.html', 'from_name.txt']
RESET_LINK = 'https://lms.example.com/password/reset/abc/def/?track=pwreset'


def _render(name, **extra):
    context = {'platform_name': 'Visible Skills', 'reset_link': RESET_LINK}
    context.update(extra)
    return render_to_string(f'{TEMPLATE_DIR}/{name}', context)


@pytest.mark.parametrize('name', TEMPLATE_FILES)
def test_invite_template_file_exists(name):
    assert (PACKAGE_ROOT / 'templates' / TEMPLATE_DIR / name).is_file()


def test_subject_renders_welcome_with_platform_name():
    assert _render('subject.txt').strip() == 'Welcome to Visible Skills! Create your password.'


def test_body_txt_contains_reset_link_and_welcome_copy():
    body = _render('body.txt')
    assert RESET_LINK in body
    assert 'Welcome to Visible Skills!' in body
    assert 'Create your password to access your account and get started.' in body
    assert "If you weren't expecting this invitation, you can disregard this email." in body


def test_body_txt_does_not_mention_password_reset():
    assert 'password reset' not in _render('body.txt').lower()


def test_body_txt_does_not_html_escape_link():
    link = 'https://lms.example.com/password/reset/a/b/?track=pwreset&x=1'
    assert link in _render('body.txt', reset_link=link)


def test_from_name_renders_platform_name():
    assert _render('from_name.txt').strip() == 'Visible Skills'


def test_manifest_packages_html_and_txt_templates():
    manifest = (PACKAGE_ROOT.parent / 'MANIFEST.in').read_text().splitlines()
    lines = [line for line in manifest if line.startswith('recursive-include admin_portal')]
    assert any('*.html' in line and '*.txt' in line for line in lines)


def _fake_module(name, **attrs):
    module = ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    return module


@pytest.fixture
def platform_fakes():
    """Stub the lazily imported platform modules; returns the recorded fakes."""
    ace = mock.Mock()
    invite_cls = mock.Mock()
    get_params = mock.Mock(return_value=({'base': 1}, 'es'))
    helpers = SimpleNamespace(get_value=mock.Mock(side_effect=lambda key, default=None: {
        'PLATFORM_NAME': 'Visible Skills'}.get(key, default)))
    fakes = {
        'edx_ace': _fake_module('edx_ace', ace=ace),
        'edx_ace.recipient': _fake_module('edx_ace.recipient', Recipient=lambda uid, email: (uid, email)),
        'openedx': _fake_module('openedx'),
        'openedx.core': _fake_module('openedx.core'),
        'openedx.core.djangoapps': _fake_module('openedx.core.djangoapps'),
        'openedx.core.djangoapps.site_configuration': _fake_module(
            'openedx.core.djangoapps.site_configuration', helpers=helpers),
        'openedx.core.djangoapps.site_configuration.helpers': helpers,
        'openedx.core.djangoapps.user_authn': _fake_module('openedx.core.djangoapps.user_authn'),
        'openedx.core.djangoapps.user_authn.toggles': _fake_module(
            'openedx.core.djangoapps.user_authn.toggles', should_redirect_to_authn_microfrontend=lambda: False),
        'openedx.core.djangoapps.user_authn.views': _fake_module('openedx.core.djangoapps.user_authn.views'),
        'openedx.core.djangoapps.user_authn.views.password_reset': _fake_module(
            'openedx.core.djangoapps.user_authn.views.password_reset', get_user_default_email_params=get_params),
        'admin_portal.message_types': _fake_module('admin_portal.message_types', AccountInvite=invite_cls),
    }
    with mock.patch.dict(sys.modules, fakes):
        yield SimpleNamespace(ace=ace, invite_cls=invite_cls)


def test_send_set_password_email_sends_invite_with_context(platform_fakes, settings):
    settings.SITE_NAME = 'lms.example.com'
    settings.PLATFORM_NAME = 'Fallback'
    user = SimpleNamespace(id=7, email='learner@example.com')
    request = SimpleNamespace(is_secure=lambda: True)

    with mock.patch('django.urls.reverse', return_value='/password/reset/7/tok/'), \
            mock.patch.object(default_token_generator, 'make_token', return_value='tok'):
        edxapp.send_set_password_email(user, request)

    kwargs = platform_fakes.invite_cls.return_value.personalize.call_args.kwargs
    assert kwargs['recipient'] == (7, 'learner@example.com')
    assert kwargs['language'] == 'es'
    context = kwargs['user_context']
    assert context['base'] == 1
    assert context['platform_name'] == 'Visible Skills'
    assert context['reset_link'] == 'https://lms.example.com/password/reset/7/tok/?track=pwreset'
    platform_fakes.ace.send.assert_called_once_with(platform_fakes.invite_cls.return_value.personalize.return_value)


def test_send_set_password_email_without_request_uses_http(platform_fakes, settings):
    settings.SITE_NAME = 'lms.example.com'
    settings.PLATFORM_NAME = 'Fallback'
    user = SimpleNamespace(id=7, email='learner@example.com')

    with mock.patch('django.urls.reverse', return_value='/password/reset/7/tok/'), \
            mock.patch.object(default_token_generator, 'make_token', return_value='tok'):
        edxapp.send_set_password_email(user)

    context = platform_fakes.invite_cls.return_value.personalize.call_args.kwargs['user_context']
    assert context['reset_link'].startswith('http://lms.example.com/')


def _load_account_invite(site_from_address):
    """
    Load ``AccountInvite`` against a fake ``BaseMessageType`` without registering the module.

    ``site_from_address`` mimics the platform base class, which copies the site
    configuration ``email_from_address`` into ``options['from_address']`` when set.
    """
    class FakeBaseMessageType:  # pylint: disable=too-few-public-methods
        """Stand-in for the platform ``BaseMessageType``."""
        def __init__(self):
            self.options = {'from_address': site_from_address} if site_from_address else {}

    helpers = SimpleNamespace(get_value=lambda key, default=None: {
        'PLATFORM_NAME': 'Visible Skills'}.get(key, default))
    fakes = {
        'openedx': _fake_module('openedx'),
        'openedx.core': _fake_module('openedx.core'),
        'openedx.core.djangoapps': _fake_module('openedx.core.djangoapps'),
        'openedx.core.djangoapps.ace_common': _fake_module('openedx.core.djangoapps.ace_common'),
        'openedx.core.djangoapps.ace_common.message': _fake_module(
            'openedx.core.djangoapps.ace_common.message', BaseMessageType=FakeBaseMessageType),
        'openedx.core.djangoapps.site_configuration': _fake_module(
            'openedx.core.djangoapps.site_configuration', helpers=helpers),
        'openedx.core.djangoapps.site_configuration.helpers': helpers,
    }
    spec = importlib.util.spec_from_file_location(
        'account_invite_under_test', PACKAGE_ROOT / 'message_types.py')
    module = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, fakes):
        spec.loader.exec_module(module)
    return module.AccountInvite


@pytest.fixture
def platform_settings(settings):
    settings.PLATFORM_NAME = 'Fallback'
    return settings


@pytest.mark.usefixtures('platform_settings')
def test_account_invite_skips_disable_user_policy_and_is_transactional():
    options = _load_account_invite('contact@example.com')().options
    assert options['skip_disable_user_policy'] is True
    assert options['transactional'] is True


@pytest.mark.usefixtures('platform_settings')
def test_account_invite_names_site_from_address_after_platform():
    options = _load_account_invite('contact@example.com')().options
    assert options['from_address'] == 'Visible Skills <contact@example.com>'


def test_account_invite_falls_back_to_default_from_email(platform_settings):
    platform_settings.DEFAULT_FROM_EMAIL = 'Old Name <noreply@example.com>'
    options = _load_account_invite(None)().options
    assert options['from_address'] == 'Visible Skills <noreply@example.com>'
