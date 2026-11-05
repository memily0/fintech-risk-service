"""Fixture API integration and contract tests; no market data or model fitting."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from pydantic import ValidationError

from arcshift_v1.api import create_app
from arcshift_v1.schemas import API_CONTRACT_VERSION, FixtureDataset, SCENARIO_IDS
from arcshift_v1.settings import Settings
from arcshift_v1.store import FIXTURE_PATH, FixtureStore


def fixture_data():
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


class SettingsTests(unittest.TestCase):
    def test_default_environment_is_local_and_synthetic(self):
        settings = Settings.from_env({})
        self.assertEqual((settings.environment, settings.data_mode, settings.host, settings.port), ("local", "synthetic", "127.0.0.1", 8765))

    def test_environment_overrides_and_immutable_settings(self):
        settings = Settings.from_env({"ARCSHIFT_ENVIRONMENT": "test", "ARCSHIFT_PORT": "8766"})
        self.assertEqual(settings.port, 8766)
        with self.assertRaises(FrozenInstanceError):
            settings.data_mode = "live"

    def test_live_mode_and_public_environments_refused(self):
        for kwargs in ({"data_mode": "live"}, {"environment": "production"}, {"environment": "staging"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Settings(**kwargs)

    def test_public_bind_and_invalid_ports_refused(self):
        for kwargs in ({"host": "0.0.0.0"}, {"host": "example.com"}, {"port": 80}, {"port": 65536}, {"port": True}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                Settings(**kwargs)
        with self.assertRaises(ValueError):
            Settings.from_env({"ARCSHIFT_PORT": "invalid"})


class FixtureTests(unittest.TestCase):
    def test_all_six_shared_scenarios_parse(self):
        store = FixtureStore.from_file()
        self.assertEqual(tuple(row.id for row in store.list_scenarios()), SCENARIO_IDS)

    def test_false_missing_or_coerced_synthetic_labels_refused(self):
        for value in (False, 1, "true", None):
            for location in ("dataset", "scenario"):
                with self.subTest(value=value, location=location), self.assertRaises(ValidationError):
                    data = fixture_data()
                    target = data if location == "dataset" else data["scenarios"][0]
                    target["synthetic"] = value
                    FixtureDataset.model_validate(data)
        data = fixture_data()
        del data["scenarios"][0]["synthetic"]
        with self.assertRaises(ValidationError):
            FixtureDataset.model_validate(data)

    def test_duplicate_missing_or_wrong_version_refused(self):
        for change in ("duplicate", "missing", "version"):
            data = fixture_data()
            if change == "duplicate":
                data["scenarios"][1] = deepcopy(data["scenarios"][0])
            elif change == "missing":
                data["scenarios"].pop()
            else:
                data["fixture_version"] = "unreviewed-version"
            with self.subTest(change=change), self.assertRaises(ValidationError):
                FixtureDataset.model_validate(data)

    def test_non_demo_states_cannot_have_signal(self):
        data = fixture_data()
        data["scenarios"][2]["signal"] = deepcopy(data["scenarios"][-1]["signal"])
        with self.assertRaises(ValidationError):
            FixtureDataset.model_validate(data)

    def test_demo_needs_signal_and_matching_state(self):
        data = fixture_data()
        data["scenarios"][-1]["signal"] = None
        with self.assertRaises(ValidationError):
            FixtureDataset.model_validate(data)
        data = fixture_data()
        data["scenarios"][0]["state"] = "empty"
        with self.assertRaises(ValidationError):
            FixtureDataset.model_validate(data)

    def test_demo_score_has_bounds_and_cannot_be_nan_boolean_or_string(self):
        for value in (-1, 1.1, float("nan"), float("inf"), True, "0.35"):
            data = fixture_data()
            data["scenarios"][-1]["signal"]["score"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                FixtureDataset.model_validate(data)

    def test_demo_cannot_claim_live_or_calibrated_model(self):
        for key, value in (("validity_status", "valid"), ("calibration_status", "calibrated"), ("score_kind", "probability"), ("model_version", "crisis_logreg_30d")):
            data = fixture_data()
            data["scenarios"][-1]["signal"][key] = value
            with self.subTest(key=key), self.assertRaises(ValidationError):
                FixtureDataset.model_validate(data)

    def test_demo_rejects_naive_time_or_information_after_origin(self):
        for value in ("2026-11-05T08:00:00", "2026-11-05T10:00:00+03:00"):
            data = fixture_data()
            data["scenarios"][-1]["signal"]["information_as_of"] = value
            with self.subTest(value=value), self.assertRaises(ValidationError):
                FixtureDataset.model_validate(data)

    def test_unreviewed_extra_fields_and_drivers_rejected(self):
        data = fixture_data()
        data["scenarios"][-1]["signal"]["confidence"] = 99
        with self.assertRaises(ValidationError):
            FixtureDataset.model_validate(data)
        data = fixture_data()
        data["scenarios"][-1]["signal"]["drivers"] = [{"causal_effect": 1}]
        with self.assertRaises(ValidationError):
            FixtureDataset.model_validate(data)

    def test_store_is_portable_and_unknown_id_is_not_a_file_path(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text(FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")
            store = FixtureStore.from_file(path)
            self.assertEqual(store.get_scenario("empty").state, "empty")
            for unknown in ("not-found", "../../data/final_dataset.csv"):
                with self.assertRaises(KeyError):
                    store.get_scenario(unknown)

    def test_corrupt_fixture_prevents_startup(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "fixture.json"
            path.write_text("{broken", encoding="utf-8")
            with self.assertRaises(ValidationError):
                with TestClient(create_app(Settings(environment="test", storage_backend="memory"), lambda: FixtureStore.from_file(path))):
                    pass


class APITests(unittest.TestCase):
    def setUp(self):
        self.app = create_app(Settings(environment="test", storage_backend="memory"))
        self.client = TestClient(self.app)
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_health_and_readiness_are_fixture_only(self):
        for path in ("/healthz", "/readyz"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
            data = response.json()
            self.assertEqual(data["readiness_scope"], "fixture_development_only")
            self.assertFalse(data["production_ready"])
            self.assertEqual(data["environment"], "test")

    def test_capabilities_do_not_claim_unimplemented_features(self):
        data = self.client.get("/api/v1/capabilities").json()
        for field in ("public_registration_implemented", "live_ingest_implemented", "accepted_model_available", "private_state_implemented"):
            self.assertIs(data[field], False)

    def test_list_scenarios_and_provenance_labels(self):
        response = self.client.get("/api/v1/demo/scenarios")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["scenarios"]), 6)
        self.assertTrue(data["synthetic"])
        self.assertTrue(all(row["synthetic"] for row in data["scenarios"]))
        self.assertEqual(data["source_rights_status"], "not_admitted")
        self.assertEqual(data["api_contract_version"], API_CONTRACT_VERSION)

    def test_each_state_is_accessible_and_stale_has_no_score(self):
        for scenario_id in SCENARIO_IDS:
            response = self.client.get(f"/api/v1/demo/scenarios/{scenario_id}")
            self.assertEqual(response.status_code, 200)
            scenario = response.json()["scenario"]
            self.assertEqual(scenario["state"], scenario_id)
            if scenario_id != "historical_demo":
                self.assertIsNone(scenario["signal"])
            else:
                self.assertEqual(scenario["signal"]["score_kind"], "synthetic_uncalibrated_score")

    def test_unknown_scenario_and_traversal_do_not_expose_files(self):
        response = self.client.get("/api/v1/demo/scenarios/not-found")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"]["code"], "scenario_not_found")
        self.assertEqual(self.client.get("/api/v1/demo/scenarios/../../data/final_dataset.csv").status_code, 404)

    def test_no_write_upload_or_private_resource_routes(self):
        for method in ("post", "put", "patch", "delete"):
            response = getattr(self.client, method)("/api/v1/demo/scenarios/empty")
            self.assertEqual(response.status_code, 405)
        for path in ("/data/final_dataset.csv", "/models/artifacts/crisis_logreg_30d.joblib", "/api/v1/users", "/api/v1/reviews"):
            self.assertEqual(self.client.get(path).status_code, 404)
        current = self.client.get("/api/v1/signals/current")
        self.assertEqual(current.status_code, 200)
        self.assertIsNone(current.json()["signal"])
        self.assertEqual(current.json()["state"], "unavailable")

    def test_responses_are_noncacheable_and_synthetic(self):
        for path in ("/healthz", "/api/v1/demo/scenarios", "/not-found"):
            response = self.client.get(path)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["x-arcshift-data-mode"], "synthetic")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")

    def test_host_validation_and_no_wildcard_cors(self):
        self.assertEqual(self.client.get("/healthz", headers={"Host": "attacker.example"}).status_code, 400)
        response = self.client.get("/healthz", headers={"Origin": "https://attacker.example"})
        self.assertNotIn("access-control-allow-origin", response.headers)

    def test_openapi_is_local_and_has_response_contracts(self):
        response = self.client.get("/openapi.json")
        self.assertEqual(response.status_code, 200)
        paths = response.json()["paths"]
        self.assertIn("/api/v1/demo/scenarios/{scenario_id}", paths)
        self.assertEqual(self.client.get("/docs").status_code, 404)

    def test_store_loaded_once_and_requests_do_not_fetch_or_fit(self):
        factory = FixtureStore.from_file
        with patch("socket.create_connection", side_effect=AssertionError("No external socket")), patch("urllib.request.urlopen", side_effect=AssertionError("No provider requests")), patch("arcshift_v1.api.FixtureStore.from_file", wraps=factory) as load:
            with TestClient(create_app(Settings(environment="test", storage_backend="memory"))) as client:
                for _ in range(3):
                    self.assertEqual(client.get("/api/v1/demo/scenarios").status_code, 200)
            self.assertEqual(load.call_count, 1)
        for name in ("joblib", "sklearn", "yfinance", "scripts.train_crisis_model", "scripts.build_final_dataset"):
            self.assertNotIn(name, sys.modules)

    def test_store_removed_after_shutdown(self):
        app = create_app(Settings(environment="test", storage_backend="memory"))
        with TestClient(app):
            self.assertIsNotNone(app.state.scenario_store)
        self.assertFalse(hasattr(app.state, "scenario_store"))


if __name__ == "__main__":
    unittest.main()
