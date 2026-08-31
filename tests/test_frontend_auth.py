
"""Frontend must be behind HTTP Basic Auth so the browser prompts.

If GET / is public, the SPA loads without a prompt, fetch() to /api/* returns
401 without a login dialog, and the dashboard looks dead.
"""
import base64
import unittest

import httpx

from config import settings
from main import app


def _client():
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url='http://test')


def _basic_header(username: str, password: str) -> str:
    token = base64.b64encode(f'{username}:{password}'.encode('utf-8')).decode('ascii')
    return f'Basic {token}'


class FrontendAuthTests(unittest.IsolatedAsyncioTestCase):
    async def test_root_without_auth_challenges_browser(self):
        async with _client() as client:
            response = await client.get('/')
        self.assertEqual(response.status_code, 401)
        self.assertIn('www-authenticate', {k.lower() for k in response.headers.keys()})
        self.assertTrue(response.headers.get('www-authenticate', '').lower().startswith('basic'))

    async def test_root_with_valid_basic_auth_serves_spa(self):
        headers = {
            'Authorization': _basic_header(settings.auth_username, settings.auth_password),
        }
        async with _client() as client:
            response = await client.get('/', headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/html', response.headers.get('content-type', ''))
        self.assertIn('id="root"', response.text)

    async def test_api_without_auth_is_unauthorized(self):
        async with _client() as client:
            response = await client.get('/api/stats')
        self.assertEqual(response.status_code, 401)

    async def test_health_is_reachable_without_auth_for_probes(self):
        async with _client() as client:
            response = await client.get('/api/health')
        self.assertNotEqual(response.status_code, 401)


if __name__ == '__main__':
    unittest.main()
