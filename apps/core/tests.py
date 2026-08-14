from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import UserProfile


class LogAccessTests(TestCase):
    def setUp(self):
        self.User = get_user_model()

    def _make_user(self, username, role):
        user = self.User.objects.create_user(username=username, password='pass12345')
        profile = user.profile
        profile.role = role
        profile.save(update_fields=['role'])
        return user

    def test_admin_can_open_logs(self):
        admin = self._make_user('admin-user', UserProfile.Role.ADMIN)
        self.client.force_login(admin)

        response = self.client.get(reverse('core:logs'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Activity Log')

    def test_regular_user_cannot_open_logs(self):
        user = self._make_user('regular-user', UserProfile.Role.USER)
        self.client.force_login(user)

        response = self.client.get(reverse('core:logs'))

        self.assertEqual(response.status_code, 403)

    def test_admin_search_includes_logs(self):
        admin = self._make_user('search-admin', UserProfile.Role.ADMIN)
        self.client.force_login(admin)

        response = self.client.get(reverse('core:search'), {'q': ''})
        payload = response.json()

        pages = payload['groups'][0]['items']
        self.assertTrue(any(item['title'] == 'Logs' for item in pages))
