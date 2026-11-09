"""A missing/unapproved model never becomes a probability or low-risk result."""

from contextlib import closing
import hashlib
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
        self.assertEqual(body["approved_horizons_days"], [30])
        self.assertEqual(body["primary_horizon_days"], 30)
        self.assertEqual(body["task_scope_status"], "user_confirmed")
        self.assertEqual(body["horizon_approval_scope"], "business_task_not_model_admission")
        self.assertEqual(body["target_measurement_status"], "design_frozen_not_validated")
        self.assertEqual(body["model_contract_version"], "v1-model-readiness.3")
        self.assertEqual(body["candidate_horizons_scope"], "legacy_inventory_not_serving_approval")
        self.assertEqual(body["source_commit_scope"], "imported_temporal_core_only")
        self.assertEqual(body["candidate_horizons_days"], [7, 30, 90])
        self.assertEqual(body["calibration_status"], "not_established")
        self.assertEqual(body["source_commit"], "eb54d6ed10e8337afc6c0221419936be07f6dadc")

    def test_raw_coverage_reports_imoex_not_vix_without_feature_claim(self):
        body = self.client.get("/api/v1/models/status").json()
        self.assertEqual(body["missing_input_series"], ["ru.equity.imoex.close"])
        self.assertEqual([row["component"] for row in body["input_coverage"]], ["fx", "equity", "rates"])
        self.assertTrue(all(row["feature_ready"] is False for row in body["input_coverage"]))
        self.assertEqual(body["coverage_scope"], "raw_target_inputs_only_not_feature_readiness")

    def test_model_and_history_share_the_published_snapshot(self):
        status = self.client.get("/api/v1/models/status").json()
        market = self.client.get("/api/v1/market/series").json()
        signal = self.client.get("/api/v1/signals/current").json()
        self.assertEqual(status["data_snapshot_id"], market["data_snapshot_id"])
        self.assertEqual(status["data_snapshot_id"], signal["data_snapshot_id"])

    def test_approved_task_is_unavailable_not_an_approved_model_or_zero_score(self):
        body = self.client.get("/api/v1/signals/current", params={"horizon_days": 30}).json()
        self.assertEqual(body["state"], "unavailable")
        self.assertIsNone(body["signal"])
        self.assertIn("accepted_artifact_missing", body["reasons"])
        self.assertIn("measurement_not_validated", body["reasons"])
        self.assertIn("source_calendars_not_verified", body["reasons"])
        self.assertNotIn("task_and_horizons_not_approved", body["reasons"])
        self.assertNotIn("score", body)
        self.assertFalse(body["production_ready"])

    def test_other_countries_are_not_forecast_coverage(self):
        for geography in ("KZ", "US"):
            body = self.client.get("/api/v1/signals/current", params={"geography": geography}).json()
            self.assertEqual(body["state"], "unsupported")
            self.assertIsNone(body["signal"])
            self.assertIn("geography_not_supported", body["reasons"])

    def test_unknown_task_or_horizon_is_explicitly_unsupported(self):
        cases = [({"task_id": task}, "task_not_supported") for task in ("bank_pd", "ru_composite_stress_event_candidate_v1")]
        cases += [({"horizon_days": horizon}, "horizon_not_approved") for horizon in (7, 90, 365)]
        for params, reason in cases:
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
        for path in ("/api/v1/models/task", "/api/v1/models/measurement", "/api/v1/models/status", "/api/v1/signals/current"):
            self.assertEqual(self.client.get(path).headers["cache-control"], "no-store")
            self.assertEqual(self.client.post(path).status_code, 405)

    def test_task_contract_separates_business_approval_frozen_design_and_model_admission(self):
        body = self.client.get("/api/v1/models/task").json()
        self.assertEqual(body["task_contract_version"], "v1-task.2")
        self.assertEqual(body["task_id"], self.client.get("/api/v1/models/status").json()["task_id"])
        self.assertEqual(body["business_scope_status"], "user_confirmed")
        self.assertEqual(body["approved_on"], "2026-11-06")
        self.assertEqual(body["geography"], "RU")
        self.assertEqual(body["approved_horizons_days"], [30])
        self.assertEqual(body["horizon_unit"], "calendar_days")
        self.assertEqual(body["future_window"], "(t, t + 30 days]")
        self.assertEqual(body["onset_risk_set"], "current_stress_known_absent")
        self.assertEqual(body["already_in_stress"], "monitor_current_state_do_not_score_onset")
        self.assertEqual(body["unknown_policy"], "unavailable_never_zero")
        self.assertEqual(body["measurement_status"], "design_frozen_not_validated")
        self.assertEqual(body["model_validation_status"], "not_run")
        for field in ("decision_impact_validated", "horizon_optimality_established", "production_ready"):
            self.assertIs(body[field], False)

    def test_business_contract_does_not_depend_on_market_data_availability(self):
        with closing(connect(self.path, create=False)) as connection:
            connection.execute("DELETE FROM local_market_active")
        self.assertEqual(self.client.get("/api/v1/models/task").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/models/measurement").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/signals/current").status_code, 503)

    def test_server_startup_and_model_status_do_not_import_ml_runtime(self):
        code = "from fastapi.testclient import TestClient; from arcshift_v1.api import create_app; from arcshift_v1.settings import Settings; import sys; c=TestClient(create_app(Settings(environment='test',storage_backend='memory'))); c.__enter__(); assert c.get('/api/v1/models/status').status_code==200; assert c.get('/api/v1/models/measurement').status_code==200; assert c.get('/api/v1/signals/current').json()['signal'] is None; assert not {'pandas','numpy','sklearn','joblib','arcshift_model'} & set(sys.modules); c.__exit__(None,None,None)"
        result = subprocess.run([sys.executable, "-c", code], env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"), capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_measurement_contract_digest_bindings_and_admission_boundary(self):
        body = self.client.get("/api/v1/models/measurement").json()
        definition = body["definition"]
        task = self.client.get("/api/v1/models/task").json()
        status = self.client.get("/api/v1/models/status").json()
        digest = hashlib.sha256(json.dumps(definition, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")).hexdigest()
        for response in (body, task, status):
            self.assertEqual(response["measurement_sha256"], digest)
        self.assertEqual(definition["target_definition_id"], task["target_definition_id"])
        self.assertEqual(definition["target_definition_id"], status["target_definition_id"])
        self.assertEqual(definition["forecast_horizon_calendar_days"], 30)
        self.assertEqual(definition["segment_threshold"], .9)
        self.assertEqual(definition["required_segments"], 2)
        self.assertEqual(definition["cutoff_hour"], 9)
        for key in ("empirical_validity_established", "source_admission_complete", "global_context_in_event", "production_ready"):
            self.assertIs(definition[key], False)


if __name__ == "__main__":
    unittest.main()
