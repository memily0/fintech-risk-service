"""Workbench asset boundaries and browser security headers."""

import unittest

from fastapi.testclient import TestClient

from arcshift_v1.api import create_app
from arcshift_v1.settings import Settings


class WebTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(Settings(environment="test", storage_backend="memory")))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_application_and_local_assets_are_available_without_external_cdn(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn('lang="ru"', response.text)
        self.assertIn("Синтетические данные", response.text)
        self.assertNotIn("https://", response.text)
        for name, mime in (("app.js", "text/javascript"), ("app.css", "text/css"), ("lucide.min.js", "text/javascript")):
            response = self.client.get("/assets/" + name)
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.headers["content-type"].startswith(mime))

    def test_static_allowlist_does_not_expose_database_source_or_secrets(self):
        for path in ("/assets/fixtures.sqlite3", "/assets/auth.py", "/assets/.env", "/assets/LUCIDE-LICENSE", "/.arcshift-v1/fixtures.sqlite3", "/data/crisis_dataset.csv", "/models/model.pkl"):
            self.assertEqual(self.client.get(path).status_code, 404)

    def test_no_cache_no_frame_no_inline_scripts_for_pages_and_errors(self):
        for path in ("/", "/assets/app.js", "/api/v1/demo/scenarios", "/not-found"):
            headers = self.client.get(path).headers
            self.assertEqual(headers["cache-control"], "no-store")
            self.assertEqual(headers["x-frame-options"], "DENY")
            self.assertEqual(headers["referrer-policy"], "no-referrer")
            self.assertIn("frame-ancestors 'none'", headers["content-security-policy"])
            self.assertNotIn("unsafe-inline", headers["content-security-policy"])


if __name__ == "__main__":
    unittest.main()
