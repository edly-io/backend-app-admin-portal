"""Authenticated requests to the Studio course creator endpoint."""
import time
from urllib.parse import quote

import requests
from django.conf import settings

from admin_portal import edxapp

_sleep = time.sleep


class StudioError(Exception):
    """A Studio request failed or may have been applied."""

    def __init__(self, kind, status=None, code=None, detail=None):
        super().__init__(detail or kind)
        self.kind, self.status, self.code, self.detail = kind, status, code, detail


def _request(method, username, payload=None):
    base = settings.ADMIN_PORTAL_STUDIO_URL or 'https://' + settings.CMS_BASE
    url = f"{base.rstrip('/')}/api/edl/v1/course-creator/{quote(username, safe='')}/"
    headers = {'Authorization': 'JWT ' + edxapp.mint_service_jwt(edxapp.get_service_user())}
    uncertain = False
    attempts = settings.ADMIN_PORTAL_STUDIO_MAX_ATTEMPTS
    for attempt in range(attempts):
        try:
            response = requests.request(method, url, headers=headers, json=payload, timeout=settings.ADMIN_PORTAL_STUDIO_TIMEOUT)
        except (requests.ConnectionError, requests.Timeout):
            uncertain = True
        else:
            if 200 <= response.status_code < 300:
                return response.json()
            if response.status_code in (502, 504):
                uncertain = True
            elif response.status_code != 503:
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                raise StudioError('rejected', response.status_code, body.get('code'), body.get('detail'))
        if attempt + 1 < attempts:
            backoff = settings.ADMIN_PORTAL_STUDIO_BACKOFF
            _sleep(backoff[min(attempt, len(backoff) - 1)] if backoff else 0)
    raise StudioError('uncertain' if uncertain else 'unavailable')


def get_state(username):
    """Read the current creator state."""
    return _request('GET', username)


def set_state(username, org_admin, organizations, acting_admin, confirm_downgrade=False):
    """Set the creator state."""
    return _request('POST', username, {
        'org_admin': org_admin, 'organizations': organizations, 'acting_admin': acting_admin,
        'confirm_downgrade': confirm_downgrade,
    })


def restore_state(username, snapshot_token, acting_admin):
    """Restore the signed snapshot from the start of this request."""
    return _request('POST', username, {'restore_token': snapshot_token, 'acting_admin': acting_admin})
