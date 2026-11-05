"""Private synthetic workflow: ownership, atomic writes, evidence and exports."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from arcshift_v1.api import create_app
from arcshift_v1.auth import AuthFailure, SESSION_COOKIE, CSRF_COOKIE, read_local_outbox
from arcshift_v1.database import connect
from arcshift_v1.settings import Settings
from arcshift_v1.workspace import UpdateReview, WorkspaceService


ORIGIN = {"Origin": "http://testserver"}
BASE = "/api/v1/workspace"


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "local.sqlite3"
        self.settings = Settings(environment="test", database_path=self.path)
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()
        self.sign_in(self.client, "first@example.test")

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def sign_in(self, client, email):
        credentials = {"email": email, "password": "Synthetic-only-workspace-password"}
        self.assertEqual(client.post("/api/v1/auth/register", json=credentials, headers=ORIGIN).status_code, 202)
        token = read_local_outbox(self.path, email)[0]["token"]
        self.assertEqual(client.post("/api/v1/auth/verify-email", json={"token": token}, headers=ORIGIN).status_code, 204)
        self.assertEqual(client.post("/api/v1/auth/login", json=credentials, headers=ORIGIN).status_code, 204)

    def headers(self, client=None):
        return {**ORIGIN, "X-CSRF-Token": (self.client if client is None else client).cookies.get(CSRF_COOKIE)}

    def create(self, note="Тестовый разбор", scenario="historical_demo"):
        response = self.client.post(BASE + "/reviews", json={"scenario_id": scenario, "note": note}, headers=self.headers())
        self.assertEqual(response.status_code, 201)
        return response.json()

    def patch(self, review, status="in_review", note="Продолжение"):
        return self.client.patch(BASE + "/reviews/" + review["review_id"], json={"expected_revision": review["revision"], "status": status, "note": note}, headers=self.headers())

    def test_anonymous_requests_cannot_read_or_write_private_state(self):
        self.client.cookies.clear()
        for method, path in (("get", "/watchlist"), ("get", "/reviews"), ("put", "/watchlist"), ("post", "/reviews")):
            kwargs = {"headers": ORIGIN}
            if method in {"put", "post"}:
                kwargs["json"] = {"scenario_ids": []} if path == "/watchlist" else {"scenario_id": "stale"}
            self.assertEqual(getattr(self.client, method)(BASE + path, **kwargs).status_code, 401)

    def test_writes_require_origin_and_session_bound_csrf(self):
        for headers in (ORIGIN, {"X-CSRF-Token": self.client.cookies.get(CSRF_COOKIE)}, {**ORIGIN, "X-CSRF-Token": "wrong" * 10}):
            response = self.client.post(BASE + "/reviews", json={"scenario_id": "stale"}, headers=headers)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get(BASE + "/reviews").json()["reviews"], [])

    def test_review_freezes_evidence_and_has_explicit_synthetic_labels(self):
        review = self.create()
        self.assertTrue(review["synthetic"])
        self.assertFalse(review["production_ready"])
        self.assertEqual(review["revision"], 1)
        self.assertEqual(review["status"], "acknowledged")
        self.assertTrue(review["snapshot_id"].startswith("fixture-"))
        self.assertEqual(review["scenario"]["signal"]["model_version"], "synthetic-no-fitted-model")
        updated = self.patch(review).json()
        self.assertEqual(updated["scenario"], review["scenario"])
        self.assertEqual(updated["snapshot_id"], review["snapshot_id"])

    def test_no_signal_states_remain_no_signal_in_reports(self):
        review = self.create(scenario="stale")
        report = self.client.get(BASE + "/reviews/" + review["review_id"] + "/report.json").json()
        self.assertIsNone(report["review"]["scenario"]["signal"])
        self.assertEqual(report["source_rights_status"], "not_admitted")

    def test_revision_conflict_does_not_overwrite_newer_note(self):
        review = self.create()
        self.assertEqual(self.patch(review, note="Новый вывод").status_code, 200)
        self.assertEqual(self.patch(review, note="Устаревший вывод").status_code, 409)
        current = self.client.get(BASE + "/reviews/" + review["review_id"]).json()
        self.assertEqual(current["note"], "Новый вывод")
        self.assertEqual(current["revision"], 2)

    def test_state_machine_records_all_revisions_without_reopening_closed_case(self):
        review = self.create()
        self.assertEqual(self.patch(review, "closed").status_code, 409)
        review = self.patch(review).json()
        review = self.patch(review, "closed").json()
        self.assertEqual(self.patch(review, "in_review").status_code, 409)
        report = self.client.get(BASE + "/reviews/" + review["review_id"] + "/report.json").json()
        self.assertEqual([event["status"] for event in report["events"]], ["acknowledged", "in_review", "closed"])
        self.assertEqual(report["events"][-1]["revision"], report["review"]["revision"])

    def test_closed_and_dismissed_require_nonempty_note_per_team_contract(self):
        review = self.create()
        review = self.patch(review).json()
        for status in ("closed", "dismissed"):
            self.assertEqual(self.patch(review, status, "   ").status_code, 422)
        self.assertEqual(self.client.get(BASE + "/reviews/" + review["review_id"]).json()["revision"], 2)

    def test_two_users_cannot_access_each_others_reviews_in_any_export(self):
        review = self.create()
        root = BASE + "/reviews/" + review["review_id"]
        with TestClient(create_app(self.settings)) as other:
            self.sign_in(other, "other@example.test")
            self.assertEqual(other.get(BASE + "/reviews").json()["reviews"], [])
            for suffix in ("", "/report.json", "/report.csv"):
                response = other.get(root + suffix)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(review["note"], response.text)
            self.assertEqual(other.patch(root, json={"expected_revision": 1, "status": "in_review", "note": "foreign"}, headers=self.headers(other)).status_code, 404)
        self.assertEqual(self.client.get(root).json()["revision"], 1)

    def test_watchlist_is_owner_scoped_and_persistent(self):
        response = self.client.put(BASE + "/watchlist", json={"scenario_ids": ["historical_demo", "stale"]}, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        with TestClient(create_app(self.settings)) as other:
            self.sign_in(other, "other@example.test")
            self.assertEqual(other.get(BASE + "/watchlist").json()["scenario_ids"], [])
        self.assertEqual(set(self.client.get(BASE + "/watchlist").json()["scenario_ids"]), {"historical_demo", "stale"})

    def test_invalid_or_duplicate_watchlist_does_not_replace_previous_value(self):
        self.client.put(BASE + "/watchlist", json={"scenario_ids": ["stale"]}, headers=self.headers())
        for values in (["stale", "stale"], ["unknown"]):
            self.assertEqual(self.client.put(BASE + "/watchlist", json={"scenario_ids": values}, headers=self.headers()).status_code, 422)
        self.assertEqual(self.client.get(BASE + "/watchlist").json()["scenario_ids"], ["stale"])

    def test_untrusted_owner_snapshot_and_revision_fields_are_rejected(self):
        for extra in ({"user_id": "foreign"}, {"snapshot_id": "other"}, {"status": "closed"}, {"note": "x" * 4001}):
            self.assertEqual(self.client.post(BASE + "/reviews", json={"scenario_id": "stale", **extra}, headers=self.headers()).status_code, 422)

    def test_csv_export_preserves_cyrillic_and_neutralizes_formula(self):
        review = self.create(note="=HYPERLINK(\"http://example.test\",\"Вывод\")")
        response = self.client.get(BASE + "/reviews/" + review["review_id"] + "/report.csv")
        self.assertEqual(response.status_code, 200)
        row = next(csv.DictReader(StringIO(response.text.lstrip("\ufeff"))))
        self.assertTrue(row["note"].startswith("'="))
        self.assertIn("Вывод", row["note"])
        self.assertEqual(row["synthetic"], "true")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_pagination_is_bounded_and_does_not_accept_file_paths(self):
        self.create()
        for query in ("?limit=101", "?limit=0", "?offset=-1"):
            self.assertEqual(self.client.get(BASE + "/reviews" + query).status_code, 422)
        self.assertEqual(self.client.get(BASE + "/reviews?offset=1").json()["reviews"], [])
        self.assertEqual(self.client.get(BASE + "/reviews/not-a-uuid/report.json").status_code, 422)

    def test_parallel_updates_have_one_winner_and_one_conflict(self):
        review = self.create()
        identity = self.client.get("/api/v1/auth/me").json()
        auth = self.client.app.state.auth_service
        work = WorkspaceService(auth, self.client.app.state.scenario_store)

        def update(note):
            try:
                work.update_review(identity["user_id"], review["review_id"], UpdateReview(expected_revision=1, status="in_review", note=note))
                return 200
            except AuthFailure as error:
                return error.status

        with ThreadPoolExecutor(max_workers=2) as executor:
            self.assertEqual(sorted(executor.map(update, ("one", "two"))), [200, 409])
        self.assertEqual(len(work.report(identity["user_id"], review["review_id"]).events), 2)

    def test_logout_blocks_private_reports_and_old_session_cannot_be_reused(self):
        review = self.create()
        session = self.client.cookies.get(SESSION_COOKIE)
        self.assertEqual(self.client.post("/api/v1/auth/logout", headers=self.headers()).status_code, 204)
        self.client.cookies.set(SESSION_COOKIE, session)
        self.assertEqual(self.client.get(BASE + "/reviews/" + review["review_id"] + "/report.json").status_code, 401)

    def test_audit_events_do_not_duplicate_private_notes(self):
        self.create(note="Private synthetic note")
        with closing(connect(self.path, readonly=True)) as connection:
            rows = [dict(row) for row in connection.execute("SELECT * FROM local_review_events")]
        self.assertNotIn("Private synthetic note", str(rows))


if __name__ == "__main__":
    unittest.main()
