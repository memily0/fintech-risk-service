"""A missing/unapproved model never becomes a probability or low-risk result."""

from contextlib import closing
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from arcshift_v1.api import create_app
from arcshift_v1.database import connect
from arcshift_v1.settings import Settings


class ModelAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "local.sqlite3"
        self.client = TestClient(create_app(Settings(environment="test", database_path=self.path)))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def test_status_distinguishes_temporal_code_from_model_admission(self):
        body = self.client.get("/api/v1/models/status").json()
        self.assertEqual(body["status"], "not_admitted")
        self.assertFalse(body["accepted_artifact_available"])
        self.assertEqual(body["approved_horizons_days"], [])
        self.assertEqual(body["candidate_horizons_days"], [7, 30, 90])
        self.assertEqual(body["calibration_status"], "not_established")
        self.assertEqual(body["source_commit"], "eb54d6ed10e8337afc6c0221419936be07f6dadc")

    def test_raw_coverage_includes_vix_and_imoex_without_feature_claim(self):
        body = self.client.get("/api/v1/models/status").json()
        self.assertEqual(body["missing_input_series"], [])
        self.assertEqual(len(body["input_coverage"]), 5)
        self.assertTrue(all(row["present_in_synthetic_snapshot"] for row in body["input_coverage"]))
        self.assertTrue(all(row["feature_ready"] is False for row in body["input_coverage"]))
        self.assertEqual(body["coverage_scope"], "raw_target_inputs_only_not_feature_readiness")
        self.assertNotIn("mandatory_stress_inputs_incomplete", body["blockers"])

    def test_model_and_history_share_the_published_snapshot(self):
        status = self.client.get("/api/v1/models/status").json()
        market = self.client.get("/api/v1/market/series").json()
        signal = self.client.get("/api/v1/signals/current").json()
        self.assertEqual(status["data_snapshot_id"], market["data_snapshot_id"])
        self.assertEqual(status["data_snapshot_id"], signal["data_snapshot_id"])

    def test_every_candidate_horizon_is_unavailable_not_a_zero_score(self):
        for horizon in (7, 30, 90):
            body = self.client.get("/api/v1/signals/current", params={"horizon_days": horizon}).json()
            self.assertEqual(body["state"], "unavailable")
            self.assertIsNone(body["signal"])
            self.assertIn("accepted_artifact_missing", body["reasons"])
            self.assertIn("task_and_horizons_not_approved", body["reasons"])
            self.assertNotIn("score", body)
            self.assertFalse(body["production_ready"])

    def test_other_countries_are_not_forecast_coverage(self):
        for geography in ("KZ", "US"):
            body = self.client.get("/api/v1/signals/current", params={"geography": geography}).json()
            self.assertEqual(body["state"], "unsupported")
            self.assertIsNone(body["signal"])
            self.assertIn("geography_not_supported", body["reasons"])

    def test_unknown_task_or_horizon_is_explicitly_unsupported(self):
        for params, reason in (({"task_id": "bank_pd"}, "task_not_supported"), ({"horizon_days": 365}, "horizon_not_supported")):
            response = self.client.get("/api/v1/signals/current", params=params)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["state"], "unsupported")
            self.assertIn(reason, response.json()["reasons"])
            self.assertIsNone(response.json()["signal"])

    def test_invalid_parameters_are_bounded(self):
        for params in ({"horizon_days": 0}, {"horizon_days": 3651}, {"horizon_days": "true"}, {"geography": "Russia"}, {"task_id": "x" * 129}):
            self.assertEqual(self.client.get("/api/v1/signals/current", params=params).status_code, 422)

    def test_fixture_score_remains_separate_from_current_signal(self):
        demo = self.client.get("/api/v1/demo/scenarios/historical_demo").json()["scenario"]["signal"]
        live = self.client.get("/api/v1/signals/current").json()
        self.assertEqual(demo["score"], 0.35)
        self.assertIsNone(live["signal"])
        self.assertEqual(live["source_rights_status"], "not_admitted")

    def test_query_parameters_cannot_enable_legacy_artifact_loading(self):
        response = self.client.get("/api/v1/signals/current", params={"artifact_path": "models/artifacts/crisis_logreg_30d.joblib", "production_ready": "true"})
        self.assertEqual(response.json()["state"], "unavailable")
        self.assertIsNone(response.json()["signal"])
        self.assertNotIn("joblib", response.text)
        self.assertFalse(response.json()["production_ready"])

    def test_corrupt_data_is_503_not_a_model_prediction(self):
        with closing(connect(self.path, create=False)) as connection:
            connection.execute("DELETE FROM local_market_active")
        for path in ("/api/v1/models/status", "/api/v1/signals/current"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 503)
            self.assertNotIn(str(self.path), response.text)

    def test_status_and_signal_are_read_only_and_not_cached(self):
        for path in ("/api/v1/models/status", "/api/v1/signals/current"):
            self.assertEqual(self.client.get(path).headers["cache-control"], "no-store")
            self.assertEqual(self.client.post(path).status_code, 405)

    def test_server_startup_and_model_status_do_not_import_ml_runtime(self):
        code = "from fastapi.testclient import TestClient; from arcshift_v1.api import create_app; from arcshift_v1.settings import Settings; import sys; c=TestClient(create_app(Settings(environment='test',storage_backend='memory'))); c.__enter__(); assert c.get('/api/v1/models/status').status_code==200; assert c.get('/api/v1/signals/current').json()['signal'] is None; assert not {'pandas','numpy','sklearn','joblib','arcshift_model'} & set(sys.modules); c.__exit__(None,None,None)"
        result = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
