"""Security-hardening tests (EDL-19 security review)."""
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


def _login_admin(client):
    user = User.objects.create_user('admin', email='admin@e.com', password='pw')
    user.groups.add(Group.objects.get(name='edl_admin'))
    client.force_login(user)
    return user


class SecurityHardeningTests(APITestCase):
    def test_gated_responses_are_not_cacheable(self):
        _login_admin(self.client)
        response = self.client.get(reverse('admin_portal:v1:me'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response['Cache-Control'], 'no-store')

    def test_enroll_rejects_oversized_batch(self):
        _login_admin(self.client)
        payload = {
            'course_id': 'course-v1:X+Y+Z',
            'identifiers': [f'u{i}@e.com' for i in range(1001)],
        }
        response = self.client.post(reverse('admin_portal:v1:enroll'), payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('identifiers', response.data)
