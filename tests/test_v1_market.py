"""D01-D03 -> local snapshot -> API, without providers or model fitting."""

from contextlib import closing
import copy
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from arcshift_v1.api import create_app
from arcshift_v1.data_worker import DataWorker, SourceJob
from arcshift_v1.database import connect
from arcshift_v1.market import FIXTURES, MarketStore, canonical, fixture_state, validate_state
from arcshift_v1.settings import Settings, PROJECT_ROOT
from arcshift_v1.store import StoreUnavailableError
from arcshift_data import merge_observation_state, parse_moex_imoex_json


USD = "ru.fx.cbr.usd_rub.official"


def rehash(raw):
    content = dict(raw)
    content.pop("snapshot_id", None)
    raw["snapshot_id"] = hashlib.sha256(canonical(content).encode()).hexdigest()
    return raw


class MarketTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.path = Path(self.temp.name) / "local.sqlite3"
        self.settings = Settings(environment="test", database_path=self.path)
        self.client = TestClient(create_app(self.settings))
        self.client.__enter__()
        self.store = self.client.app.state.market_store

    def tearDown(self):
        self.client.__exit__(None, None, None)
        self.temp.cleanup()

    def history(self, **params):
        return self.client.get("/api/v1/market/series/" + USD + "/history", params=params)

    def query(self, sql):
        with closing(connect(self.path, readonly=True)) as connection:
            return [tuple(row) for row in connection.execute(sql)]

    def test_registry_fixture_matches_contributor_config(self):
        self.assertEqual((FIXTURES / "source_registry.json").read_bytes(), (PROJECT_ROOT / "config/arcshift_source_registry.json").read_bytes())

    def test_actual_parsers_and_revision_store_include_imoex_vix_and_key_rate(self):
        response = self.client.get("/api/v1/market/series")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["series"]), 10)
        self.assertEqual(sum(row["observation_count"] for row in body["series"]), 14)
        self.assertEqual(sum(row["revision_count"] for row in body["series"]), 15)
        self.assertTrue(body["synthetic"])
        self.assertEqual(body["source_rights_status"], "not_admitted")
        self.assertEqual(body["validity_status"], "historical_demo")
        self.assertFalse(body["production_ready"])

    def test_latest_values_and_revision_history_are_distinct(self):
        latest = self.history().json()
        full = self.history(include_revisions=True).json()
        self.assertEqual(latest["total"], 3)
        self.assertEqual(full["total"], 4)
        self.assertEqual(latest["observations"][-1]["observation"]["value"], 81.2)
        self.assertEqual([row["is_latest"] for row in full["observations"]], [True, True, False, True])
        self.assertEqual(full["data_snapshot_id"], latest["data_snapshot_id"])

    def test_unknown_publication_is_not_replaced_by_receipt(self):
        row = self.history().json()["observations"][0]["observation"]
        self.assertIsNone(row["published_at"])
        self.assertEqual(row["publication_status"], "unknown")
        self.assertIn("+03:00", row["received_at"])
        self.assertTrue(row["is_synthetic"])

    def test_date_range_pagination_and_empty_history(self):
        response = self.history(start="2026-11-04", end="2026-11-05", limit=1, offset=1)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total"], 2)
        self.assertEqual(len(body["observations"]), 1)
        self.assertEqual(body["observations"][0]["observation"]["reference_start"], "2026-11-05")
        self.assertEqual(self.history(start="2026-12-01").json()["observations"], [])

    def test_invalid_range_limits_and_unknown_ids(self):
        for params in ({"start": "2026-11-05", "end": "2026-11-04"}, {"start": "not-a-date"}, {"limit": 501}, {"limit": 0}, {"offset": -1}):
            self.assertEqual(self.history(**params).status_code, 422)
        self.assertEqual(self.client.get("/api/v1/market/series/not-known/history").status_code, 404)
        self.assertEqual(self.client.post("/api/v1/market/series").status_code, 405)

    def test_synthetic_cpi_index_is_converted_to_yoy_percent(self):
        body = self.client.get("/api/v1/market/series/ru.prices.rosstat.cpi_yoy/history").json()
        row = body["observations"][0]["observation"]
        self.assertEqual(row["value"], 5.5)
        self.assertEqual(row["units"], "percent_YoY")
        self.assertEqual(row["reference_start"], "2026-09-01")
        self.assertEqual(row["reference_end"], "2026-09-30")

    def test_startup_does_not_duplicate_or_retimestamp_published_snapshot(self):
        before = self.query("SELECT * FROM local_market_snapshots")
        with TestClient(create_app(self.settings)) as second:
            self.assertEqual(second.get("/readyz").status_code, 200)
        self.assertEqual(before, self.query("SELECT * FROM local_market_snapshots"))

    def test_restarting_does_not_rollback_newer_active_snapshot(self):
        raw = fixture_state()
        raw["published_at"] = "2026-11-05T09:07:00+03:00"
        identifier = self.store.publish(rehash(raw))
        with TestClient(create_app(self.settings)) as second:
            self.assertEqual(second.get("/api/v1/market/series").json()["data_snapshot_id"], identifier)
        self.assertEqual(len(self.query("SELECT * FROM local_market_snapshots")), 2)

    def test_worker_retries_then_publishes_to_the_same_database(self):
        attempts = []
        waits = []
        payload = b'{"history":{"columns":["SECID","TRADEDATE","CLOSE"],"data":[["IMOEX","2026-11-05",2550.0]]}}'

        def fetch():
            attempts.append(1)
            if len(attempts) == 1:
                raise TimeoutError("synthetic timeout")
            return payload

        job = SourceJob(
            name="imoex",
            fetch_payload=fetch,
            parse_payload=lambda raw: parse_moex_imoex_json(
                raw, "2026-11-05T09:10:00+03:00", "worker-receipt-1", True
            ),
            maximum_attempts=2,
            wait_seconds=(0,),
        )
        worker = DataWorker(self.store, sleep_function=waits.append)
        result = worker.run([job], "2026-11-05T09:11:00+03:00")

        self.assertEqual(result.added_count, 1)
        self.assertEqual(waits, [0])
        self.assertEqual(len(self.query("SELECT * FROM local_market_snapshots")), 2)
        self.assertEqual(self.store.path.resolve(), self.path.resolve())
        history = self.client.get(
            "/api/v1/market/series/ru.equity.imoex.close/history",
            params={"include_revisions": True},
        ).json()
        self.assertEqual(history["total"], 2)
        self.assertEqual(history["observations"][-1]["observation"]["value"], 2550.0)

    def test_market_validator_keeps_a_new_acquisition_of_an_old_value(self):
        raw = fixture_state()
        usd_revisions = [
            revision
            for revision in raw["revisions"]
            if revision["observation_identity"].endswith("|2026-11-05|2026-11-05")
            and revision["observation"]["series_id"] == USD
        ]
        returned = copy.deepcopy(usd_revisions[0]["observation"])
        returned["snapshot_id"] = "synthetic-parser-receipt-003"
        returned["received_at"] = "2026-11-05T09:07:00+03:00"

        revised, result = merge_observation_state(
            raw, [returned], "2026-11-05T09:08:00+03:00"
        )
        state = validate_state(revised)
        identity = usd_revisions[0]["observation_identity"]
        self.assertEqual(result["added_count"], 1)
        self.assertEqual(state.latest[identity].revision_number, 3)
        self.assertEqual(state.latest[identity].observation.value, returned["value"])

        replayed, replay_result = merge_observation_state(
            revised, [returned], "2026-11-05T09:09:00+03:00"
        )
        self.assertEqual(replay_result["added_count"], 0)
        self.assertEqual(replayed["snapshot_id"], revised["snapshot_id"])

    def test_worker_recovers_after_failure_before_shared_publish(self):
        payload = b'{"history":{"columns":["SECID","TRADEDATE","CLOSE"],"data":[["IMOEX","2026-11-05",2551.0]]}}'
        job = SourceJob(
            name="imoex",
            fetch_payload=lambda: payload,
            parse_payload=lambda raw: parse_moex_imoex_json(
                raw, "2026-11-05T09:12:00+03:00", "worker-receipt-2", True
            ),
            maximum_attempts=1,
            wait_seconds=(),
        )

        class CrashBeforePublish:
            path = self.path

            def read(inner_self):
                return self.store.read()

            def publish(inner_self, raw):
                raise RuntimeError("synthetic worker crash")

        crash_worker = DataWorker(CrashBeforePublish())
        lock_path = crash_worker.lock_path
        with self.assertRaisesRegex(RuntimeError, "worker crash"):
            crash_worker.run([job], "2026-11-05T09:13:00+03:00")
        self.assertEqual(len(self.query("SELECT * FROM local_market_snapshots")), 1)
        self.assertFalse(lock_path.exists())

        result = DataWorker(self.store).run(
            [job], "2026-11-05T09:13:00+03:00"
        )
        self.assertEqual(result.added_count, 1)
        self.assertEqual(len(self.query("SELECT * FROM local_market_snapshots")), 2)

    def test_database_recovers_uncommitted_snapshot_after_worker_process_crash(self):
        active_before = self.query("SELECT * FROM local_market_active")
        code = (
            "import hashlib, os; from pathlib import Path; "
            "from arcshift_v1.database import connect; "
            f"db=Path({str(self.path)!r}); c=connect(db, create=False); "
            "c.execute('BEGIN IMMEDIATE'); payload='{}'; "
            "c.execute('INSERT INTO local_market_snapshots VALUES (?, ?, ?, 1, 1)', "
            "('market-'+'f'*64, payload, hashlib.sha256(payload.encode()).hexdigest())); "
            "os._exit(24)"
        )
        result = subprocess.run([sys.executable, "-c", code], env=dict(os.environ), timeout=10)
        self.assertEqual(result.returncode, 24)
        self.assertEqual(len(self.query("SELECT * FROM local_market_snapshots")), 1)
        self.assertEqual(self.query("SELECT * FROM local_market_active"), active_before)
        with TestClient(create_app(self.settings)) as restarted:
            self.assertEqual(restarted.get("/readyz").status_code, 200)
            self.assertEqual(
                restarted.get("/api/v1/market/series").json()["data_snapshot_id"],
                active_before[0][1],
            )

    def test_invalid_real_observation_cannot_be_published(self):
        raw = fixture_state()
        raw["revisions"][0]["observation"]["is_synthetic"] = False
        with self.assertRaises(ValueError):
            self.store.publish(rehash(raw))
        self.assertEqual(len(self.query("SELECT * FROM local_market_snapshots")), 1)

    def test_content_hash_detects_tampering(self):
        raw = fixture_state()
        raw["revisions"][0]["observation"]["value"] += 10
        with self.assertRaisesRegex(ValueError, "hash"):
            validate_state(raw)

    def test_latest_map_cannot_hide_or_invent_a_revision(self):
        raw = fixture_state()
        raw["latest"].pop(next(iter(raw["latest"])))
        with self.assertRaisesRegex(ValueError, "Latest"):
            validate_state(rehash(raw))

    def test_receipt_after_ingestion_is_rejected(self):
        raw = fixture_state()
        raw["revisions"][0]["observation"]["received_at"] = "2026-11-06T09:00:00+03:00"
        with self.assertRaisesRegex(ValueError, "order"):
            validate_state(rehash(raw))

    def test_series_resource_and_units_cannot_be_mixed(self):
        raw = fixture_state()
        raw["revisions"][0]["observation"]["resource_id"] = "cbr_xml:R01239"
        with self.assertRaisesRegex(ValueError, "mismatched"):
            validate_state(rehash(raw))

    def test_mutated_sqlite_payload_returns_generic_503(self):
        with closing(connect(self.path, create=False)) as connection:
            connection.execute("UPDATE local_market_snapshots SET payload_json='{}'")
        response = self.client.get("/api/v1/market/series")
        self.assertEqual(response.status_code, 503)
        self.assertNotIn(str(self.path), response.text)
        self.assertEqual(self.client.get("/healthz").status_code, 200)
        self.assertEqual(self.client.get("/readyz").status_code, 503)

    def test_deleted_market_database_is_not_recreated_by_reads(self):
        self.path.unlink()
        self.assertEqual(self.history().status_code, 503)
        self.assertFalse(self.path.exists())

    def test_memory_profile_also_returns_only_labeled_synthetic_history(self):
        with TestClient(create_app(Settings(environment="test", storage_backend="memory"))) as memory:
            body = memory.get("/api/v1/market/series").json()
            self.assertTrue(body["synthetic"])
            self.assertFalse(body["production_ready"])

    def test_response_does_not_expose_runtime_paths_or_private_accounts(self):
        response = self.history(include_revisions=True)
        self.assertEqual(response.headers["cache-control"], "no-store")
        for banned in (str(self.path), "password_hash", "local_dev_outbox", "@example.test"):
            self.assertNotIn(banned, response.text)


if __name__ == "__main__":
    unittest.main()
