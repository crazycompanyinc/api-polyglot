"""
Tests for API Polyglot - no external deps, uses stdlib only.
Run with: python3 -m pytest tests/ -v
"""

import os
import sys
import json
import unittest

# Ensure we import from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src import Polyglot, ask, get
from src.core import Intent, APIProfile, save_profile, find_profile_by_name, list_profiles
from src.discovery import discover_from_name, list_known_apis, KNOWN_APIS
from src.auth import negotiate_auth, AuthResult
from src.execute import execute, get_json, clear_cache


class TestIntent(unittest.TestCase):
    def test_detect_search(self):
        i = Intent("buscá issues de github")
        self.assertEqual(i.action, "search")

    def test_detect_list(self):
        i = Intent("listá los últimos posts")
        self.assertEqual(i.action, "list")

    def test_detect_post(self):
        i = Intent("creá un nuevo issue")
        self.assertEqual(i.action, "post")

    def test_detect_monitor(self):
        i = Intent("avisame cuando haya un terremoto")
        self.assertEqual(i.action, "monitor")

    def test_default_action(self):
        i = Intent("bitcoin price")
        self.assertEqual(i.action, "get")


class TestDiscovery(unittest.TestCase):
    def test_known_apis_list(self):
        apis = list_known_apis()
        self.assertTrue(len(apis) > 0)
        names = [a["name"] for a in apis]
        self.assertIn("GitHub", names)
        self.assertIn("CoinGecko", names)

    def test_discover_github(self):
        profile = discover_from_name("GitHub")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "GitHub")
        self.assertTrue(len(profile.endpoints) > 0)

    def test_discover_coingecko(self):
        profile = discover_from_name("coingecko")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.auth_type, "none")

    def test_discover_usgs(self):
        profile = discover_from_name("earthquake")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.auth_type, "none")

    def test_unknown_api(self):
        profile = discover_from_name("totally_fake_api_xyz")
        self.assertIsNone(profile)


class TestAPIProfileStore(unittest.TestCase):
    def test_save_and_load(self):
        p = APIProfile(
            name="Test API",
            base_url="https://api.test.com",
            description="Test",
            auth_type="none",
            endpoints=[{"method": "GET", "path": "/test", "desc": "test endpoint"}],
        )
        save_profile(p)
        loaded = find_profile_by_name("Test API")
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.name, "Test API")
        self.assertEqual(loaded.base_url, "https://api.test.com")

    def test_profile_id(self):
        p = APIProfile(name="Test", base_url="https://test.com", description="")
        self.assertTrue(len(p.id) > 0)


class TestExecute(unittest.TestCase):
    def test_get_jsonplaceholder(self):
        resp = get_json("https://jsonplaceholder.typicode.com/posts/1")
        self.assertEqual(resp.status_code, 200)
        self.assertIsNotNone(resp.data)
        self.assertIsNone(resp.error)
        if isinstance(resp.data, dict):
            self.assertIn("id", resp.data)

    def test_get_coingecko_ping(self):
        resp = get_json("https://api.coingecko.com/api/v3/ping")
        self.assertIn(resp.status_code, [200, 429])  # 429 if rate limited
        if resp.status_code == 200:
            self.assertIsNotNone(resp.data)

    def test_not_found(self):
        resp = get_json("https://jsonplaceholder.typicode.com/nonexistent_xyz")
        self.assertEqual(resp.status_code, 404)

    def test_clear_cache(self):
        clear_cache()  # Should not raise


class TestPolyglot(unittest.TestCase):
    def test_discover_via_ask(self):
        poly = Polyglot()
        profile = poly.discover("coingecko")
        self.assertIsNotNone(profile)
        self.assertEqual(profile.name, "CoinGecko")

    def test_ask_coingecko_ping(self):
        poly = Polyglot()
        resp = poly.ask("ping coingecko api")
        # Should either succeed or fail with rate limit, not crash
        self.assertIsNotNone(resp)

    def test_last_profile(self):
        poly = Polyglot()
        poly.discover("usgs earthquake")
        profile = poly.last_profile()
        self.assertIsNotNone(profile)


class TestAuthNegotiation(unittest.TestCase):
    def test_no_auth(self):
        profile = APIProfile(name="Test", base_url="https://test.com", description="", auth_type="none")
        result = negotiate_auth(profile, "test")
        self.assertTrue(result.success)

    def test_bearer_missing(self):
        profile = APIProfile(name="Test", base_url="https://test.com", description="", auth_type="bearer",
                              auth_config={"env_var": "NONEXISTENT_TOKEN_VAR_XYZ"})
        env_backup = os.environ.pop("NONEXISTENT_TOKEN_VAR_XYZ", None)
        try:
            result = negotiate_auth(profile, "test_service_bearer_missing")
            self.assertFalse(result.success)
            self.assertIn("AUTH_REQUIRED", result.error)
        finally:
            if env_backup:
                os.environ["NONEXISTENT_TOKEN_VAR_XYZ"] = env_backup

    def test_api_key_missing(self):
        profile = APIProfile(name="Test", base_url="https://test.com", description="", auth_type="api_key",
                              auth_config={"env_var": "NONEXISTENT_API_KEY_VAR_XYZ"})
        env_backup = os.environ.pop("NONEXISTENT_API_KEY_VAR_XYZ", None)
        try:
            result = negotiate_auth(profile, "test_service_key_missing")
            self.assertFalse(result.success)
            self.assertIn("AUTH_REQUIRED", result.error)
        finally:
            if env_backup:
                os.environ["NONEXISTENT_API_KEY_VAR_XYZ"] = env_backup


if __name__ == "__main__":
    unittest.main()
