"""Synthetic queue identity, owner isolation, and snapshot continuity."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from arcshift_v1.api import create_app
from arcshift_v1.auth import CSRF_COOKIE, read_local_outbox
from arcshift_v1.database import connect
from arcshift_v1.market import canonical, fixture_state
from arcshift_v1.settings import Settings
from arcshift_v1.warning_queue import QueueService
from arcshift_v1.workspace import WorkspaceService


BASE = "/api/v1/workspace"
ORIGIN = {"Origin": "http://testserver"}


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "synthetic.sqlite3"
        self.settings = Settings(environment="test", database_path=self.path)
        self.app = create_app(self.settings)
        self.client = TestClient(self.app)
        self.client.__enter__()
        self.login(self.client, "queue-a@example.test")

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def login(self, client, email):
        credentials = {"email": email, "password": "Synthetic-only-queue-password"}
        self.assertEqual(client.post("/api/v1/auth/register", json=credentials, headers=ORIGIN).status_code, 202)
        token = read_local_outbox(self.path, email)[0]["token"]
        self.assertEqual(client.post("/api/v1/auth/verify-email", json={"token": token}, headers=ORIGIN).status_code, 204)
        self.assertEqual(client.post("/api/v1/auth/login", json=credentials, headers=ORIGIN).status_code, 204)

    def headers(self, client=None):
        return {**ORIGIN, "X-CSRF-Token": (client or self.client).cookies.get(CSRF_COOKIE)}

    def warnings(self, client=None):
        response = (client or self.client).get(BASE + "/warnings")
        self.assertEqual(response.status_code, 200)
        return response.json()["warnings"]

    def begin(self, warning):
        response = self.client.post(BASE + "/warnings/" + warning["warning_id"] + "/review", headers=self.headers())
        self.assertEqual(response.status_code, 200)
        return response.json()

    def test_two_stable_warnings_and_concurrent_review_dedup(self):
        warnings = self.warnings()
        self.assertEqual(len({row["warning_id"] for row in warnings}), 2)
        self.assertEqual(warnings, self.warnings())
        self.assertEqual(warnings, self.warnings())
        self.assertTrue(all(row["review"] is None and row["synthetic"] for row in warnings))
        work = WorkspaceService(self.app.state.auth_service, self.app.state.scenario_store)
        queue = QueueService(work, self.app.state.market_store)
        user = self.client.get("/api/v1/auth/me").json()["user_id"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            reviews = list(pool.map(lambda _: queue.begin_review(user, warnings[0]["warning_id"]), range(2)))
        self.assertEqual(reviews[0].review_id, reviews[1].review_id)
        self.assertEqual(len(self.client.get(BASE + "/reviews").json()["reviews"]), 1)
        self.assertNotEqual(self.begin(warnings[1])["review_id"], reviews[0].review_id)

    def test_actor_and_warning_reviews_are_independent(self):
        warnings = self.warnings()
        first, second = self.begin(warnings[0]), self.begin(warnings[1])
        response = self.client.patch(BASE + "/reviews/" + first["review_id"],
            json={"expected_revision": 1, "status": "in_review", "note": "Вымышленная проверка A"}, headers=self.headers())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(BASE + "/reviews/" + second["review_id"]).json()["note"], "")
        with TestClient(create_app(self.settings)) as bob:
            self.login(bob, "queue-b@example.test")
            self.assertTrue(all(row["review"] is None for row in self.warnings(bob)))
            for suffix in ("", "/report.json", "/report.csv"):
                self.assertEqual(bob.get(BASE + "/reviews/" + first["review_id"] + suffix).status_code, 404)
            self.assertEqual(bob.patch(BASE + "/reviews/" + first["review_id"],
                json={"expected_revision": 2, "status": "closed", "note": "Чужое"}, headers=self.headers(bob)).status_code, 404)

    def test_indicator_contract_keeps_legacy_watchlist_and_rejects_unknown_ids(self):
        old = self.client.put(BASE + "/watchlist", json={"scenario_ids": ["stale"]}, headers=self.headers())
        self.assertEqual(old.status_code, 200)
        series = "ru.fx.cbr.usd_rub.official"
        saved = self.client.put(BASE + "/indicator-watchlist", json={"series_ids": [series]}, headers=self.headers())
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["indicator_contract_version"], "v1-local-indicators.1")
        self.assertEqual(self.client.get(BASE + "/watchlist").json()["scenario_ids"], ["stale"])
        for ids in (["stale"], [series, series]):
            self.assertEqual(self.client.put(BASE + "/indicator-watchlist", json={"series_ids": ids}, headers=self.headers()).status_code, 422)
        self.assertEqual(self.client.get(BASE + "/indicator-watchlist").json()["series_ids"], [series])
        with TestClient(create_app(self.settings)) as bob:
            self.login(bob, "watchlist-b@example.test")
            self.assertEqual(bob.get(BASE + "/indicator-watchlist").json()["series_ids"], [])
            self.assertEqual(bob.put(BASE + "/indicator-watchlist",
                json={"series_ids": ["ru.fx.cbr.eur_rub.official"]}, headers=self.headers(bob)).status_code, 200)
        self.assertEqual(self.client.get(BASE + "/indicator-watchlist").json()["series_ids"], [series])
        self.assertEqual(self.client.put(BASE + "/indicator-watchlist", json={"series_ids": []}, headers=ORIGIN).status_code, 403)
        self.client.cookies.clear()
        for path in ("/indicator-watchlist", "/warnings"):
            self.assertEqual(self.client.get(BASE + path).status_code, 401)

    def test_warning_and_report_keep_original_snapshot_after_active_switch(self):
        original = self.warnings()
        review = self.begin(original[0])
        raw = fixture_state()
        raw["published_at"] = "2026-11-06T12:00:00+03:00"
        raw.pop("snapshot_id")
        raw["snapshot_id"] = hashlib.sha256(canonical(raw).encode()).hexdigest()
        new_id = self.app.state.market_store.publish(raw)
        self.assertNotEqual(new_id, review["data_snapshot_id"])
        response = self.client.post(BASE + "/reports", json={
            "review_id": review["review_id"], "expected_revision": 1,
            "expected_data_snapshot_id": review["data_snapshot_id"],
        }, headers=self.headers())
        self.assertEqual(response.status_code, 201)
        report = response.json()
        self.assertEqual(report["data_snapshot_id"], original[0]["data_snapshot_id"])
        self.assertEqual(report["review"]["review"]["warning_id"], original[0]["warning_id"])
        self.assertEqual(report["review"]["review"]["policy_id"], original[0]["policy_id"])
        self.assertEqual(report["review"]["review"]["signal_id"], original[0]["signal_id"])
        queue = QueueService(WorkspaceService(self.app.state.auth_service, self.app.state.scenario_store), self.app.state.market_store)
        queue.publish_examples()
        queue.publish_examples()
        rows = self.warnings()
        self.assertEqual(len(rows), 4)
        for warning in original:
            saved = next(row for row in rows if row["warning_id"] == warning["warning_id"])
            self.assertEqual(saved["scenario"], warning["scenario"])
            self.assertEqual(saved["data_snapshot_id"], warning["data_snapshot_id"])
        for extension in ("pdf", "csv", "json"):
            self.assertEqual(self.client.get(BASE + "/reports/" + report["report_id"] + "/export." + extension).status_code, 200)
        self.assertEqual(self.client.get(BASE + "/reports/" + report["report_id"]).json(), report)

    def test_saved_report_from_previous_contract_remains_readable(self):
        review = self.client.post(BASE + "/reviews", json={"scenario_id": "historical_demo"}, headers=self.headers()).json()
        snapshot = self.client.get("/api/v1/market/series").json()["data_snapshot_id"]
        report = self.client.post(BASE + "/reports", json={"review_id": review["review_id"],
            "expected_revision": 1, "expected_data_snapshot_id": snapshot}, headers=self.headers()).json()
        with closing(connect(self.path)) as connection:
            raw = json.loads(connection.execute("SELECT payload_json FROM local_saved_reports WHERE report_id=?",
                (report["report_id"],)).fetchone()[0])
            for field in ("warning_id", "signal_id", "policy_id", "data_snapshot_id"):
                raw["review"]["review"].pop(field)
            payload = json.dumps(raw)
            connection.execute("UPDATE local_saved_reports SET payload_json=?, payload_sha256=? WHERE report_id=?",
                (payload, hashlib.sha256(payload.encode()).hexdigest(), report["report_id"]))
        restored = self.client.get(BASE + "/reports/" + report["report_id"])
        self.assertEqual(restored.status_code, 200)
        self.assertEqual(restored.json()["data_snapshot_id"], snapshot)
        self.assertIsNone(restored.json()["review"]["review"]["warning_id"])


if __name__ == "__main__":
    unittest.main()
