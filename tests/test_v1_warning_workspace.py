"""Synthetic warning queue, private reviews and pinned reports through the API."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from pypdf import PdfReader

from arcshift_v1.api import create_app
from arcshift_v1.auth import CSRF_COOKIE, read_local_outbox
from arcshift_v1.database import connect
from arcshift_v1.market import canonical, fixture_state
from arcshift_v1.settings import Settings


BASE = "/api/v1/workspace"
WARNINGS = BASE + "/warnings"
WATCHLIST = BASE + "/series-watchlist"
ORIGIN = {"Origin": "http://testserver"}
USD = "ru.fx.cbr.usd_rub.official"
EUR = "ru.fx.cbr.eur_rub.official"


class WarningWorkspaceTests(unittest.TestCase):
    def setUp(self):
        directory = self.enterContext(TemporaryDirectory())
        self.path = Path(directory) / "warnings.sqlite3"
        self.settings = Settings(environment="test", database_path=self.path)
        self.client = self.enterContext(TestClient(create_app(self.settings)))
        self.credentials = self.sign_in(self.client, "first@example.test")

    def sign_in(self, client, email):
        credentials = {"email": email, "password": "Synthetic-warning-workspace-password"}
        self.assertEqual(client.post("/api/v1/auth/register", json=credentials, headers=ORIGIN).status_code, 202)
        token = read_local_outbox(self.path, email)[0]["token"]
        self.assertEqual(client.post("/api/v1/auth/verify-email", json={"token": token}, headers=ORIGIN).status_code, 204)
        self.assertEqual(client.post("/api/v1/auth/login", json=credentials, headers=ORIGIN).status_code, 204)
        return credentials

    @staticmethod
    def headers(client):
        return {**ORIGIN, "X-CSRF-Token": client.cookies.get(CSRF_COOKIE)}

    def queue(self, client):
        response = client.get(WARNINGS)
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["synthetic"])
        self.assertFalse(payload["production_ready"])
        self.assertEqual(payload["source_rights_status"], "not_admitted")
        return payload["warnings"]

    def acknowledge(self, client, warning):
        response = client.put(WARNINGS + "/" + warning["warning_id"] + "/review", headers=self.headers(client))
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def save_report(self, client, review, snapshot_id):
        return client.post(BASE + "/reports", headers=self.headers(client), json={
            "review_id": review["review_id"], "expected_revision": review["revision"],
            "expected_data_snapshot_id": snapshot_id, "series_ids": [USD],
        })

    def test_queue_to_review_and_report_with_two_private_accounts(self):
        initial = self.queue(self.client)
        self.assertEqual(len(initial), 2)
        self.assertEqual(len({item["warning_id"] for item in initial}), 2)
        self.assertTrue(all(item["validity_status"] == "historical_demo" and item["synthetic"] for item in initial))
        self.assertTrue(all(item["review_id"] is None and item["review_status"] == "new" for item in initial))
        before = self.path.read_bytes()
        self.assertEqual(self.queue(self.client), initial)
        self.assertEqual(self.path.read_bytes(), before)

        other = self.enterContext(TestClient(create_app(self.settings)))
        self.sign_in(other, "second@example.test")
        self.assertEqual(self.queue(other), initial)
        warning = initial[0]
        review = self.acknowledge(self.client, warning)
        self.assertEqual(self.acknowledge(self.client, warning), review)
        self.assertEqual(review["snapshot_id"], warning["fixture_snapshot_id"])
        self.assertEqual(review["warning"]["warning_id"], warning["warning_id"])
        self.assertEqual(self.queue(other), initial)
        other_review = self.acknowledge(other, warning)
        self.assertNotEqual(other_review["review_id"], review["review_id"])

        review_url = BASE + "/reviews/" + review["review_id"]
        note = "First account's private synthetic note"
        update = {"expected_revision": 1, "status": "in_review", "note": note}
        self.assertEqual(other.patch(review_url, json=update, headers=self.headers(other)).status_code, 404)
        changed = self.client.patch(review_url, json=update, headers=self.headers(self.client))
        self.assertEqual(changed.status_code, 200, changed.text)
        self.assertEqual(self.queue(self.client)[0]["review_status"], "in_review")
        self.assertEqual(self.queue(other)[0]["review_status"], "acknowledged")
        self.assertEqual(self.queue(self.client)[1], initial[1])
        self.assertNotIn(note, other.get(WARNINGS).text)
        self.assertEqual(self.acknowledge(self.client, warning), changed.json())

        response = self.save_report(self.client, changed.json(), warning["data_snapshot_id"])
        self.assertEqual(response.status_code, 201, response.text)
        report = response.json()
        self.assertEqual(report["review"]["review"]["note"], note)
        self.assertEqual(report["review"]["review"]["warning"]["warning_id"], warning["warning_id"])
        self.assertEqual(self.save_report(other, changed.json(), warning["data_snapshot_id"]).status_code, 404)
        report_url = BASE + "/reports/" + report["report_id"]
        for suffix in ("", "/export.json", "/export.csv", "/export.pdf"):
            with self.subTest(suffix=suffix):
                self.assertEqual(other.get(report_url + suffix).status_code, 404)
        pdf = self.client.get(report_url + "/export.pdf")
        self.assertEqual(pdf.status_code, 200)
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(pdf.content)).pages)
        self.assertIn(warning["warning_id"], text)
        self.assertNotIn("synthetic_uncalibrated_score", text)

    def test_warning_and_report_keep_the_old_market_values_after_active_snapshot_changes(self):
        warning = self.queue(self.client)[0]
        pinned_id = warning["data_snapshot_id"]
        raw = fixture_state()
        revised = next(row for row in raw["latest"].values() if row["observation"]["series_id"] == USD)
        old_value = revised["observation"]["value"]
        new_value = old_value + 1000
        revised["observation"]["value"] = new_value
        for row in raw["revisions"]:
            if (row["observation_identity"], row["revision_number"]) == (revised["observation_identity"], revised["revision_number"]):
                row["observation"]["value"] = new_value
        raw.pop("snapshot_id")
        raw["snapshot_id"] = hashlib.sha256(canonical(raw).encode()).hexdigest()
        active_id = self.client.app.state.market_store.publish(raw)
        self.assertNotEqual(active_id, pinned_id)
        self.assertEqual(self.queue(self.client)[0], warning)

        review = self.acknowledge(self.client, warning)
        response = self.save_report(self.client, review, active_id)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["detail"]["code"], "report_snapshot_conflict")
        self.assertEqual(self.client.get(BASE + "/reports").json()["reports"], [])
        response = self.save_report(self.client, review, pinned_id)
        self.assertEqual(response.status_code, 201, response.text)
        report = response.json()
        values = [row["observation"]["value"] for row in report["observations"]]
        self.assertEqual(report["data_snapshot_id"], pinned_id)
        self.assertIn(old_value, values)
        self.assertNotIn(new_value, values)

        restarted = self.enterContext(TestClient(create_app(self.settings)))
        self.assertEqual(restarted.post("/api/v1/auth/login", json=self.credentials, headers=ORIGIN).status_code, 204)
        self.assertEqual(restarted.get("/api/v1/market/series").json()["data_snapshot_id"], active_id)
        self.assertEqual(self.queue(restarted), self.queue(self.client))
        self.assertEqual(restarted.get(BASE + "/reports/" + report["report_id"] + "/export.json").json(), report)

    def test_concurrent_acknowledgement_does_not_duplicate_review_or_status_event(self):
        warning = self.queue(self.client)[0]
        with ThreadPoolExecutor(max_workers=2) as pool:
            reviews = list(pool.map(lambda _: self.acknowledge(self.client, warning), range(2)))
        self.assertEqual(reviews[0], reviews[1])
        with closing(connect(self.path, readonly=True)) as connection:
            self.assertEqual(connection.execute("SELECT count(*) FROM local_reviews").fetchone()[0], 1)
            self.assertEqual(connection.execute("SELECT count(*) FROM local_review_events").fetchone()[0], 1)

    def test_series_watchlist_is_private_validated_and_separate_from_scenario_bookmarks(self):
        other = self.enterContext(TestClient(create_app(self.settings)))
        self.sign_in(other, "second@example.test")
        for client, series in ((self.client, USD), (other, EUR)):
            self.assertEqual(client.get(WATCHLIST).json()["series_ids"], [])
            response = client.put(WATCHLIST, json={"series_ids": [series]}, headers=self.headers(client))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["series_ids"], [series])
            self.assertEqual(client.get(BASE + "/watchlist").json()["scenario_ids"], [])
        for payload in ({"series_ids": [USD, USD]}, {"series_ids": ["unknown"]}, {"series_ids": [], "user_id": "foreign"}):
            self.assertEqual(self.client.put(WATCHLIST, json=payload, headers=self.headers(self.client)).status_code, 422)
        self.assertEqual(self.client.get(WATCHLIST).json()["series_ids"], [USD])
        self.assertEqual(other.get(WATCHLIST).json()["series_ids"], [EUR])
        restarted = self.enterContext(TestClient(create_app(self.settings)))
        self.assertEqual(restarted.post("/api/v1/auth/login", json=self.credentials, headers=ORIGIN).status_code, 204)
        self.assertEqual(restarted.get(WATCHLIST).json()["series_ids"], [USD])
        self.assertEqual(restarted.put(WATCHLIST, json={"series_ids": []}, headers=self.headers(restarted)).json()["series_ids"], [])
        self.assertEqual(other.get(WATCHLIST).json()["series_ids"], [EUR])

    def test_private_routes_require_authentication_and_csrf(self):
        path = WARNINGS + "/" + self.queue(self.client)[0]["warning_id"] + "/review"
        self.assertEqual(self.client.put(path, headers=ORIGIN).status_code, 403)
        self.assertEqual(self.client.put(WATCHLIST, json={"series_ids": []}, headers=ORIGIN).status_code, 403)
        self.assertEqual(self.client.put(WARNINGS + "/synthetic-warning-unknown/review", headers=self.headers(self.client)).status_code, 404)
        self.client.cookies.clear()
        self.assertEqual(self.client.get(WARNINGS).status_code, 401)
        self.assertEqual(self.client.get(WATCHLIST).status_code, 401)
        self.assertEqual(self.client.put(path, headers=ORIGIN).status_code, 401)


if __name__ == "__main__":
    unittest.main()
