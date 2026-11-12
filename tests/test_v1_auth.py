"""Local .test account flows only; no real identity, email delivery or public deployment."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import json
from pathlib import Path
import stat
from tempfile import TemporaryDirectory
from threading import Event
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from arcshift_v1.api import create_app
from arcshift_v1.auth import AuthFailure, AuthPolicy, AuthService, CSRF_COOKIE, SESSION_COOKIE, digest, password_hasher, read_local_outbox
from arcshift_v1.database import connect
from arcshift_v1.settings import Settings


EMAIL = "analyst@example.test"
PASSWORD = "Synthetic-only-password-for-local-tests"
NEW_PASSWORD = "Updated-synthetic-only-password"
ORIGIN = {"Origin": "http://testserver"}
BASE = "/api/v1/auth"


class LocalAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "local.sqlite3"
        self.settings = Settings(environment="test", database_path=self.path)
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.now = 1800000000
        self.auth = AuthService(self.path, clock=lambda: self.now)
        self.app.state.auth_service = self.auth

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def post(self, suffix, payload=None, **kwargs):
        return self.client.post(BASE + suffix, json=payload, headers={**ORIGIN, **kwargs})

    def credentials(self, email=EMAIL, password=PASSWORD):
        return {"email": email, "password": password}

    def register(self, email=EMAIL):
        response = self.post("/register", self.credentials(email))
        self.assertEqual(response.status_code, 202)
        return response

    def token(self, email=EMAIL):
        return read_local_outbox(self.path, email, now=self.now)[0]["token"]

    def verified(self, email=EMAIL):
        self.register(email)
        self.assertEqual(self.post("/verify-email", {"token": self.token(email)}).status_code, 204)

    def login(self, email=EMAIL):
        response = self.post("/login", self.credentials(email))
        self.assertEqual(response.status_code, 204)
        return response

    def query(self, sql):
        with closing(connect(self.path, readonly=True)) as connection:
            return [dict(row) for row in connection.execute(sql)]

    def test_registration_duplicate_is_generic_and_no_password_or_token_in_response(self):
        first = self.register()
        second = self.register()
        self.assertEqual(first.json(), second.json())
        self.assertNotIn(PASSWORD, first.text)
        self.assertNotIn(self.token(), first.text)
        self.assertEqual(len(self.query("SELECT * FROM local_users")), 1)
        self.assertEqual(len(self.query("SELECT * FROM local_dev_outbox")), 1)

    def test_password_is_argon2_hash_with_different_salts(self):
        self.register()
        self.register("other@example.test")
        rows = self.query("SELECT password_hash FROM local_users")
        self.assertTrue(all(row["password_hash"].startswith("$argon2id$") for row in rows))
        self.assertNotEqual(rows[0]["password_hash"], rows[1]["password_hash"])
        self.assertNotIn(PASSWORD, str(rows))

    def test_real_email_and_weak_password_rejected_without_echoing_input(self):
        for data in (self.credentials("person@example.com"), self.credentials(password="too-short"), {**self.credentials(), "role": "admin"}):
            response = self.post("/register", data)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn(data["password"], response.text)
        self.assertEqual(self.query("SELECT count(*) AS n FROM local_users")[0]["n"], 0)

    def test_email_identity_is_case_insensitive(self):
        self.register("Analyst@Example.test")
        self.register(EMAIL)
        self.assertEqual(len(self.query("SELECT * FROM local_users")), 1)
        self.assertEqual(len(read_local_outbox(self.path, EMAIL, now=self.now)), 1)

    def test_login_requires_verification_and_matches_unknown_wrong_password_response(self):
        self.register()
        unverified = self.post("/login", self.credentials())
        unknown = self.post("/login", self.credentials("unknown@example.test"))
        self.assertEqual(unverified.status_code, 401)
        self.assertEqual(unverified.json(), unknown.json())
        self.post("/verify-email", {"token": self.token()})
        wrong = self.post("/login", self.credentials(password=PASSWORD + "-wrong"))
        self.assertEqual(wrong.json(), unknown.json())

    def test_verification_is_single_use_and_removes_local_message(self):
        self.register()
        token = self.token()
        self.assertEqual(self.post("/verify-email", {"token": token}).status_code, 204)
        self.assertEqual(read_local_outbox(self.path, EMAIL, now=self.now), [])
        self.assertEqual(self.post("/verify-email", {"token": token}).status_code, 400)

    def test_verification_expiry_boundary_and_random_token(self):
        self.register()
        token = self.token()
        self.now += self.auth.policy.verification_seconds
        self.assertEqual(self.post("/verify-email", {"token": token}).status_code, 400)
        self.assertEqual(self.post("/verify-email", {"token": "x" * 43}).status_code, 400)

    def test_login_sets_host_only_http_only_session_and_strict_samesite(self):
        self.verified()
        response = self.login()
        cookies = response.headers.get_list("set-cookie")
        session = next(value for value in cookies if value.startswith(SESSION_COOKIE + "="))
        csrf = next(value for value in cookies if value.startswith(CSRF_COOKIE + "="))
        self.assertIn("HttpOnly", session)
        self.assertIn("SameSite=strict", session)
        self.assertNotIn("Domain=", session)
        self.assertNotIn("HttpOnly", csrf)
        self.assertEqual(response.text, "")

    def test_session_and_csrf_are_stored_only_as_hashes(self):
        self.verified()
        self.login()
        token = self.client.cookies.get(SESSION_COOKIE)
        csrf = self.client.cookies.get(CSRF_COOKIE)
        row = self.query("SELECT * FROM local_sessions")[0]
        self.assertEqual(row["session_hash"], digest(token))
        self.assertEqual(row["csrf_hash"], digest(csrf))
        self.assertNotIn(token, str(row))
        self.assertNotIn(csrf, str(row))

    def test_me_requires_session_and_never_returns_hash_or_token(self):
        self.assertEqual(self.client.get(BASE + "/me").status_code, 401)
        self.verified()
        self.login()
        response = self.client.get(BASE + "/me")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["email"], EMAIL)
        self.assertTrue(response.json()["synthetic"])
        for secret in (PASSWORD, self.client.cookies.get(SESSION_COOKIE), self.client.cookies.get(CSRF_COOKIE), "password_hash", "csrf_hash"):
            self.assertNotIn(secret, response.text)

    def test_session_expiry_and_tampered_token_are_rejected(self):
        self.verified()
        self.login()
        token = self.client.cookies.get(SESSION_COOKIE)
        with self.assertRaises(AuthFailure):
            self.auth.authenticate(("y" if token[0] == "x" else "x") + token[1:])
        self.now += self.auth.policy.session_seconds
        self.assertEqual(self.client.get(BASE + "/me").status_code, 401)

    def test_relogin_rotates_and_revokes_previous_browser_session(self):
        self.verified()
        self.login()
        old = self.client.cookies.get(SESSION_COOKIE)
        self.login()
        self.assertNotEqual(old, self.client.cookies.get(SESSION_COOKIE))
        with self.assertRaises(AuthFailure):
            self.auth.authenticate(old)

    def test_state_changing_requests_require_exact_origin(self):
        for headers in ({}, {"Origin": "https://attacker.example"}, {"Origin": "null"}, {"Origin": "http://testserver.attacker.example"}):
            response = self.client.post(BASE + "/register", json=self.credentials(), headers=headers)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.query("SELECT count(*) AS n FROM local_users")[0]["n"], 0)

    def test_logout_requires_session_bound_csrf_and_revokes_server_session(self):
        self.verified()
        self.login()
        session = self.client.cookies.get(SESSION_COOKIE)
        csrf = self.client.cookies.get(CSRF_COOKIE)
        self.assertEqual(self.post("/logout").status_code, 403)
        self.assertEqual(self.post("/logout", **{"X-CSRF-Token": "wrong" * 10}).status_code, 403)
        self.assertEqual(self.client.get(BASE + "/me").status_code, 200)
        self.assertEqual(self.post("/logout", **{"X-CSRF-Token": csrf}).status_code, 204)
        self.assertEqual(self.client.get(BASE + "/me").status_code, 401)
        self.assertIsNone(self.client.cookies.get(SESSION_COOKIE))
        with self.assertRaises(AuthFailure):
            self.auth.authenticate(session)

    def test_two_users_receive_only_own_identity_and_csrf_is_not_transferable(self):
        self.verified()
        self.login()
        first = self.client.get(BASE + "/me").json()
        first_csrf = self.client.cookies.get(CSRF_COOKIE)
        other_email = "other@example.test"
        self.auth.register(other_email, PASSWORD, "second-peer")
        self.auth.verify_email(self.token(other_email), "second-peer")
        with TestClient(create_app(self.settings)) as other:
            other.app.state.auth_service.clock = lambda: self.now
            self.assertEqual(other.post(BASE + "/login", json=self.credentials(other_email), headers=ORIGIN).status_code, 204)
            second = other.get(BASE + "/me").json()
            self.assertNotEqual(second["user_id"], first["user_id"])
            self.assertEqual(self.client.get(BASE + "/me", params={"user_id": second["user_id"]}).json()["user_id"], first["user_id"])
            self.assertEqual(other.post(BASE + "/logout", headers={**ORIGIN, "X-CSRF-Token": first_csrf}).status_code, 403)
            self.assertEqual(other.get(BASE + "/me").status_code, 200)

    def test_login_rate_limit_persists_and_forwarded_for_does_not_bypass(self):
        self.app.state.auth_service = AuthService(self.path, AuthPolicy(rate_limit=2), lambda: self.now)
        for i in range(2):
            self.assertEqual(self.post("/login", self.credentials("missing@example.test"), **{"X-Forwarded-For": str(i)}).status_code, 401)
        response = self.post("/login", self.credentials("missing@example.test"), **{"X-Forwarded-For": "new-address"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response.headers["retry-after"], "60")
        self.app.state.auth_service = AuthService(self.path, AuthPolicy(rate_limit=2), lambda: self.now)
        self.assertEqual(self.post("/login", self.credentials("missing@example.test")).status_code, 429)
        self.now += 60
        self.assertEqual(self.post("/login", self.credentials("missing@example.test")).status_code, 401)

    def test_verification_rate_limited_before_token_lookup(self):
        self.app.state.auth_service = AuthService(self.path, AuthPolicy(rate_limit=1), lambda: self.now)
        self.assertEqual(self.post("/verify-email", {"token": "x" * 43}).status_code, 400)
        self.assertEqual(self.post("/verify-email", {"token": "y" * 43}).status_code, 429)

    def test_registration_rate_limit_does_not_create_more_users(self):
        self.app.state.auth_service = AuthService(self.path, AuthPolicy(rate_limit=1), lambda: self.now)
        self.register()
        self.assertEqual(self.post("/register", self.credentials("other@example.test")).status_code, 429)
        self.assertEqual(len(self.query("SELECT * FROM local_users")), 1)

    def test_memory_mode_does_not_silently_create_accounts(self):
        with TestClient(create_app(Settings(environment="test", storage_backend="memory"))) as client:
            self.assertEqual(client.post(BASE + "/register", json=self.credentials(), headers=ORIGIN).status_code, 503)

    def test_session_survives_api_restart(self):
        self.verified()
        self.login()
        session = self.client.cookies.get(SESSION_COOKIE)
        identity = self.client.get(BASE + "/me").json()
        self.client.__exit__(None, None, None)
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.app.state.auth_service.clock = lambda: self.now
        self.client.cookies.set(SESSION_COOKIE, session)
        self.assertEqual(self.client.get(BASE + "/me").json(), identity)

    def test_no_outbox_http_or_public_claim(self):
        for suffix in ("/outbox", "/users", "/password-reset"):
            self.assertEqual(self.client.get(BASE + suffix).status_code, 404)
        capabilities = self.client.get(BASE + "/capabilities").json()
        self.assertFalse(capabilities["real_mail_delivery"])
        self.assertTrue(capabilities["password_recovery_implemented"])
        self.assertFalse(capabilities["verification_resend_implemented"])
        self.assertFalse(capabilities["production_ready"])
        self.assertFalse(self.client.get("/api/v1/capabilities").json()["public_registration_implemented"])

    def test_reset_request_is_generic_and_only_verified_test_accounts_get_a_code(self):
        self.verified()
        pending = "pending@example.test"
        self.register(pending)
        for email in (EMAIL, pending, "absent@example.test"):
            response = self.post("/password-reset/request", {"email": email})
            self.assertEqual(response.status_code, 202)
            self.assertEqual(response.json(), {"synthetic": True, "auth_contract_version": "v1-local-auth.1", "production_ready": False, "status": "accepted", "delivery_mode": "local_outbox_only"})
        self.assertEqual(read_local_outbox(self.path, pending, now=self.now)[0]["purpose"], "verify_email")
        self.assertEqual(read_local_outbox(self.path, "absent@example.test", now=self.now), [])
        message, = read_local_outbox(self.path, EMAIL, now=self.now)
        self.assertEqual(message["purpose"], "reset_password")
        self.assertEqual(self.query("SELECT token_hash FROM local_password_resets"), [{"token_hash": digest(message["token"])}])
        self.assertEqual(self.post("/password-reset/request", {"email": "real@example.com"}).status_code, 422)
        self.assertEqual(self.post("/password-reset/request", {"email": EMAIL}, Origin="http://other.test").status_code, 403)

    def test_reset_revokes_all_sessions_of_owner_and_preserves_other_accounts(self):
        self.verified()
        other = "other@example.test"
        self.verified(other)
        first, _ = self.auth.login(EMAIL, PASSWORD, "a")
        second, _ = self.auth.login(EMAIL, PASSWORD, "b")
        unrelated, _ = self.auth.login(other, PASSWORD, "c")
        self.assertEqual(self.post("/password-reset/request", {"email": EMAIL}).status_code, 202)
        token = self.token()
        payload = {"token": token, "password": NEW_PASSWORD}
        self.assertEqual(self.post("/password-reset/confirm", payload, Origin="http://other.test").status_code, 403)
        self.assertEqual(self.post("/password-reset/confirm", {**payload, "password": "short"}).status_code, 422)
        self.assertEqual(self.post("/password-reset/confirm", payload).status_code, 204)
        self.assertEqual(read_local_outbox(self.path, EMAIL, now=self.now), [])
        self.assertEqual(self.post("/password-reset/confirm", payload).status_code, 400)
        for session in (first, second):
            self.client.cookies.set(SESSION_COOKIE, session)
            self.assertEqual(self.client.get(BASE + "/me").status_code, 401)
        self.assertEqual(self.auth.authenticate(unrelated).email, other)
        self.assertEqual(self.post("/login", self.credentials()).status_code, 401)
        self.assertEqual(self.post("/login", self.credentials(password=NEW_PASSWORD)).status_code, 204)

    def test_reset_code_is_replaced_expires_and_cannot_verify_email(self):
        self.verified()
        self.post("/password-reset/request", {"email": EMAIL})
        first = self.token()
        self.post("/password-reset/request", {"email": EMAIL})
        second = self.token()
        self.assertNotEqual(first, second)
        self.assertEqual(len(self.query("SELECT * FROM local_password_reset_outbox")), 1)
        self.assertEqual(self.post("/password-reset/confirm", {"token": first, "password": NEW_PASSWORD}).status_code, 400)
        self.assertEqual(self.post("/verify-email", {"token": second}).status_code, 400)
        self.now += self.auth.policy.password_reset_seconds
        self.assertEqual(read_local_outbox(self.path, EMAIL, now=self.now), [])
        self.assertEqual(self.post("/password-reset/confirm", {"token": second, "password": NEW_PASSWORD}).status_code, 400)
        self.login()

    def test_reset_rate_limits_are_applied_before_account_or_token_lookup(self):
        self.app.state.auth_service = AuthService(self.path, AuthPolicy(rate_limit=1), lambda: self.now)
        for path, payload, status in (
            ("/password-reset/request", {"email": "absent@example.test"}, 202),
            ("/password-reset/confirm", {"token": "a" * 43, "password": NEW_PASSWORD}, 400),
        ):
            self.assertEqual(self.post(path, payload).status_code, status)
            self.assertEqual(self.post(path, payload).status_code, 429)

    def test_concurrent_reset_confirmation_consumes_code_once(self):
        self.verified()
        self.auth.request_password_reset(EMAIL, "recovery")
        token = self.token()

        def confirm(peer):
            try:
                self.auth.reset_password(token, NEW_PASSWORD, peer)
                return "accepted"
            except AuthFailure as error:
                return error.code

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(pool.map(confirm, ("first", "second")), ["accepted", "invalid_password_reset"])
        self.assertEqual(read_local_outbox(self.path, EMAIL, now=self.now), [])

    def test_login_started_before_reset_cannot_create_a_post_reset_session(self):
        self.verified()
        self.auth.request_password_reset(EMAIL, "recovery")
        ready, release = Event(), Event()
        hasher = password_hasher()

        class DelayedVerification:
            hash = staticmethod(hasher.hash)

            @staticmethod
            def verify(password, encoded):
                verified = hasher.verify(password, encoded)
                ready.set()
                if not release.wait(5):
                    raise RuntimeError("Password verification test timed out")
                return verified

        with patch("arcshift_v1.auth.password_hasher", return_value=DelayedVerification()), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.auth.login, EMAIL, PASSWORD, "old-login")
            try:
                self.assertTrue(ready.wait(5))
                self.auth.reset_password(self.token(), NEW_PASSWORD, "recovery")
            finally:
                release.set()
            with self.assertRaises(AuthFailure) as rejected:
                future.result(timeout=5)
            self.assertEqual(rejected.exception.code, "invalid_credentials")
        self.assertEqual(self.query("SELECT * FROM local_sessions"), [])

    def test_database_restricted_permissions_and_event_log_has_no_credentials(self):
        self.verified()
        self.login()
        events = self.query("SELECT * FROM local_auth_events")
        self.assertEqual([row["event"] for row in events], ["registered", "verified", "login"])
        self.assertNotIn(PASSWORD, str(events))
        self.assertNotIn(EMAIL, str(events))
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)

    def test_deleted_auth_database_returns_503_without_recreation(self):
        self.verified()
        self.login()
        self.path.unlink()
        response = self.client.get(BASE + "/me")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.path), response.text)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
