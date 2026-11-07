"""Nikita report workflow on real server-owned local identities and snapshots."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import csv
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pypdf import PdfReader

from arcshift_v1.api import create_app
from arcshift_v1.auth import AuthPolicy, AuthService, CSRF_COOKIE, read_local_outbox
from arcshift_v1.database import connect
from arcshift_v1.settings import Settings


ORIGIN = {"Origin": "http://testserver"}
BASE = "/api/v1/workspace"
NOTE = "Синтетический вывод <b>с разметкой</b>. Проверка выполнена."


class SavedReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "local.sqlite3"
        self.settings = Settings(environment="test", database_path=self.path)
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()
        self.sign_in(self.client, "first@example.test")
        self.snapshot = self.client.get("/api/v1/market/series").json()["data_snapshot_id"]
        self.review = self.client.post(BASE + "/reviews", json={"scenario_id": "historical_demo", "note": NOTE}, headers=self.headers()).json()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def sign_in(self, client, email):
        credentials = {"email": email, "password": "Synthetic-report-test-password"}
        self.assertEqual(client.post("/api/v1/auth/register", json=credentials, headers=ORIGIN).status_code, 202)
        token = read_local_outbox(self.path, email)[0]["token"]
        self.assertEqual(client.post("/api/v1/auth/verify-email", json={"token": token}, headers=ORIGIN).status_code, 204)
        self.assertEqual(client.post("/api/v1/auth/login", json=credentials, headers=ORIGIN).status_code, 204)

    def headers(self, client=None):
        return {**ORIGIN, "X-CSRF-Token": (client or self.client).cookies.get(CSRF_COOKIE)}

    def payload(self, **overrides):
        return {"review_id": self.review["review_id"], "expected_revision": self.review["revision"], "expected_data_snapshot_id": self.snapshot, **overrides}

    def create(self, **overrides):
        response = self.client.post(BASE + "/reports", json=self.payload(**overrides), headers=self.headers())
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()

    def export(self, report, format):
        return self.client.get(BASE + "/reports/" + report["report_id"] + "/export." + format)

    def test_saved_report_contains_frozen_versions_and_only_synthetic_observations(self):
        report = self.create()
        self.assertEqual(report["review"]["review"]["note"], NOTE)
        self.assertEqual(report["data_snapshot_id"], self.snapshot)
        self.assertEqual(len(report["observations"]), 15)
        self.assertTrue(all(row["observation"]["is_synthetic"] for row in report["observations"]))
        self.assertTrue(all(row["observation"]["published_at"] is None for row in report["observations"]))
        self.assertFalse(report["production_ready"])
        self.assertEqual(report["source_rights_status"], "not_admitted")

    def test_editing_review_does_not_rewrite_saved_report(self):
        report = self.create()
        changed = self.client.patch(BASE + "/reviews/" + self.review["review_id"], json={"expected_revision": 1, "status": "in_review", "note": "Новый вывод"}, headers=self.headers())
        self.assertEqual(changed.status_code, 200)
        saved = self.client.get(BASE + "/reports/" + report["report_id"]).json()
        self.assertEqual(saved, report)
        self.assertEqual(saved["review"]["review"]["revision"], 1)

    def test_stale_review_or_snapshot_is_rejected_without_saving(self):
        for overrides in ({"expected_revision": 2}, {"expected_data_snapshot_id": "market-" + "0" * 64}):
            response = self.client.post(BASE + "/reports", json=self.payload(**overrides), headers=self.headers())
            self.assertEqual(response.status_code, 409)
        self.assertEqual(self.client.get(BASE + "/reports").json()["reports"], [])

    def test_creation_requires_same_origin_and_csrf(self):
        self.assertEqual(self.client.post(BASE + "/reports", json=self.payload(), headers=ORIGIN).status_code, 403)
        self.assertEqual(self.client.post(BASE + "/reports", json=self.payload(), headers={"X-CSRF-Token": self.client.cookies.get(CSRF_COOKIE)}).status_code, 403)

    def test_anonymous_reads_and_exports_are_blocked(self):
        report = self.create()
        self.client.cookies.clear()
        for suffix in ("", "/" + report["report_id"], "/" + report["report_id"] + "/export.pdf", "/" + report["report_id"] + "/export.json"):
            self.assertEqual(self.client.get(BASE + "/reports" + suffix).status_code, 401)

    def test_other_user_cannot_read_or_export_or_capture_foreign_review(self):
        report = self.create()
        with TestClient(create_app(self.settings)) as other:
            self.sign_in(other, "second@example.test")
            self.assertEqual(other.get(BASE + "/reports").json()["reports"], [])
            for suffix in ("", "/export.json", "/export.csv", "/export.pdf"):
                response = other.get(BASE + "/reports/" + report["report_id"] + suffix)
                self.assertEqual(response.status_code, 404)
                self.assertNotIn(NOTE, response.text)
            self.assertEqual(other.post(BASE + "/reports", json=self.payload(), headers=self.headers(other)).status_code, 404)

    def test_pdf_contains_cyrillic_and_escaped_note_and_same_report_identity(self):
        report = self.create()
        response = self.export(report, "pdf")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b"%PDF"))
        reader = PdfReader(BytesIO(response.content))
        text = "\n".join(page.extract_text() for page in reader.pages)
        for value in ("СИНТЕТИЧЕСКИЕ ДАННЫЕ", "Отчёт о разборе", "Синтетический вывод", "<b>с разметкой</b>", report["report_id"], "Неизвестно"):
            self.assertIn(value, text)
        self.assertEqual(response.headers["content-type"], "application/pdf")
        self.assertEqual(response.headers["cache-control"], "no-store")

    def test_json_export_matches_saved_snapshot(self):
        report = self.create()
        self.assertEqual(self.export(report, "json").json(), report)

    def test_csv_contains_same_observations_and_unknown_publication(self):
        report = self.create()
        response = self.export(report, "csv")
        rows = list(csv.DictReader(StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), len(report["observations"]))
        self.assertEqual({row["report_id"] for row in rows}, {report["report_id"]})
        self.assertTrue(all(row["published_at"] == "unknown" for row in rows))
        self.assertTrue(all(row["synthetic"] == "true" for row in rows))

    def test_csv_keeps_negative_numbers_but_defangs_untrusted_text(self):
        from arcshift_v1.report_rendering import safe_csv
        self.assertEqual(safe_csv(-5.2), -5.2)
        self.assertEqual(safe_csv("=formula"), "'=formula")

    def test_empty_observation_report_keeps_csv_headers_and_valid_pdf(self):
        report = self.create(series_ids=[])
        reader = csv.DictReader(StringIO(self.export(report, "csv").content.decode("utf-8-sig")))
        self.assertIn("series_id", reader.fieldnames)
        self.assertEqual(list(reader), [])
        self.assertEqual(self.export(report, "pdf").status_code, 200)

    def test_explicit_series_selection_is_respected_in_all_formats(self):
        report = self.create(series_ids=["ru.fx.cbr.usd_rub.official"])
        self.assertEqual(len(report["observations"]), 4)
        self.assertTrue(all(row["observation"]["series_id"] == "ru.fx.cbr.usd_rub.official" for row in report["observations"]))
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(self.export(report, "pdf").content)).pages)
        self.assertNotIn("ru.prices.rosstat.cpi_yoy", text)

    def test_unknown_duplicate_or_owner_fields_are_rejected(self):
        for overrides in ({"series_ids": ["unknown"]}, {"series_ids": ["x", "x"]}, {"user_id": "someone-else"}):
            response = self.client.post(BASE + "/reports", json=self.payload(**overrides), headers=self.headers())
            self.assertEqual(response.status_code, 422)

    def test_saved_reports_survive_restart(self):
        report = self.create()
        auth = self.client.app.state.auth_service
        actor = auth.authenticate(self.client.cookies.get("arcshift_dev_session"))
        with TestClient(create_app(self.settings)) as restarted:
            from arcshift_v1.saved_reports import SavedReportService
            from arcshift_v1.workspace import WorkspaceService
            service = SavedReportService(WorkspaceService(restarted.app.state.auth_service, restarted.app.state.scenario_store), restarted.app.state.market_store)
            self.assertEqual(service.get(actor.user_id, report["report_id"]).model_dump(mode="json"), report)

    def test_tampered_payload_is_503_without_note_or_path(self):
        report = self.create()
        with closing(connect(self.path, create=False)) as connection:
            connection.execute("UPDATE local_saved_reports SET payload_json='{}'")
        response = self.client.get(BASE + "/reports/" + report["report_id"])
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(NOTE, response.text)
        self.assertNotIn(str(self.path), response.text)

    def test_export_is_separately_rate_limited(self):
        report = self.create()
        self.client.app.state.auth_service = AuthService(self.path, AuthPolicy(rate_limit=1))
        self.assertEqual(self.export(report, "json").status_code, 200)
        self.assertEqual(self.export(report, "pdf").status_code, 429)

    def test_font_or_renderer_error_returns_generic_503(self):
        report = self.create()
        with patch("arcshift_v1.report_api.pdf_bytes", side_effect=OSError("private/font/path")):
            response = self.export(report, "pdf")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private/font/path", response.text)

    def test_parallel_pdf_downloads_remain_valid(self):
        report = self.create()
        with ThreadPoolExecutor(max_workers=2) as executor:
            responses = list(executor.map(lambda _: self.export(report, "pdf"), range(2)))
        self.assertTrue(all(response.status_code == 200 for response in responses))
        self.assertTrue(all(report["report_id"] in "".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages) for response in responses))

    def test_pagination_format_and_immutable_endpoints_are_bounded(self):
        report = self.create()
        self.assertEqual(self.client.get(BASE + "/reports?limit=101").status_code, 422)
        self.assertEqual(self.client.get(BASE + "/reports/" + report["report_id"] + "/export.exe").status_code, 422)
        self.assertEqual(self.client.patch(BASE + "/reports/" + report["report_id"]).status_code, 405)


if __name__ == "__main__":
    unittest.main()
