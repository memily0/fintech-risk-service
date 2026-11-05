"""Persistent synthetic snapshots, migration integrity and restart tests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient
from pydantic import ValidationError

from arcshift_v1.api import create_app
from arcshift_v1.database import APPLICATION_ID, MIGRATIONS, SchemaError, check_schema, connect, load_migrations, migrate
from arcshift_v1.schemas import FixtureDataset
from arcshift_v1.settings import PROJECT_ROOT, Settings
from arcshift_v1.store import FIXTURE_PATH, SQLiteScenarioStore, StoreUnavailableError

SCHEMA_VERSION = len(load_migrations())


class DatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.path = self.directory / "fixture.sqlite3"

    def tearDown(self):
        self.temp.cleanup()

    def query(self, sql):
        with closing(connect(self.path, readonly=True)) as connection:
            return [tuple(row) for row in connection.execute(sql)]

    def execute(self, sql):
        with closing(connect(self.path)) as connection:
            connection.execute(sql)

    def copy_migrations(self):
        target = self.directory / "migrations"
        target.mkdir()
        for path in MIGRATIONS.glob("*.sql"):
            (target / path.name).write_bytes(path.read_bytes())
        return target


class MigrationTests(DatabaseTestCase):
    def test_initial_schema_and_checksum_ledger(self):
        self.assertEqual(migrate(self.path), SCHEMA_VERSION)
        self.assertEqual(check_schema(self.path), SCHEMA_VERSION)
        self.assertEqual(self.query("PRAGMA application_id"), [(APPLICATION_ID,)])
        ledger = self.query("SELECT version, name, checksum FROM schema_migrations")
        self.assertEqual(ledger[0][:2], (1, "001_fixture_snapshots.sql"))
        self.assertEqual(ledger[0][2], hashlib.sha256((MIGRATIONS / ledger[0][1]).read_bytes()).hexdigest())

    def test_repeat_migration_is_idempotent(self):
        migrate(self.path)
        before = self.query("SELECT * FROM schema_migrations")
        migrate(self.path)
        self.assertEqual(before, self.query("SELECT * FROM schema_migrations"))

    def test_upgrade_from_fixture_only_schema_preserves_snapshot(self):
        directory = self.directory / "original-migrations"
        directory.mkdir()
        source = MIGRATIONS / "001_fixture_snapshots.sql"
        (directory / source.name).write_bytes(source.read_bytes())
        self.assertEqual(migrate(self.path, directory), 1)
        with closing(connect(self.path)) as connection:
            connection.execute("INSERT INTO fixture_snapshots(snapshot_id, fixture_version, payload_sha256, payload_json, synthetic, imported_at) VALUES ('old', 'original', ?, '{}', 1, 'original-time')", (hashlib.sha256(b"{}").hexdigest(),))
        before = self.query("SELECT * FROM fixture_snapshots")
        self.assertEqual(migrate(self.path), SCHEMA_VERSION)
        self.assertEqual(before, self.query("SELECT * FROM fixture_snapshots"))
        self.assertEqual(self.query("SELECT count(*) FROM local_users"), [(0,)])

    def test_modified_applied_migration_is_rejected(self):
        directory = self.copy_migrations()
        migrate(self.path, directory)
        with (directory / "001_fixture_snapshots.sql").open("a") as stream:
            stream.write("\n-- changed after application\n")
        with self.assertRaisesRegex(SchemaError, "modified"):
            migrate(self.path, directory)

    def test_unknown_future_schema_is_rejected(self):
        migrate(self.path)
        future = SCHEMA_VERSION + 1
        self.execute(f"INSERT INTO schema_migrations VALUES ({future}, 'future.sql', 'future', 'synthetic')")
        self.execute(f"PRAGMA user_version = {future}")
        with self.assertRaises(SchemaError):
            migrate(self.path)

    def test_gap_in_migration_files_is_rejected_before_creating_db(self):
        directory = self.copy_migrations()
        (directory / f"{SCHEMA_VERSION + 2:03d}_gap.sql").write_text("CREATE TABLE wrong (id INTEGER);\n")
        with self.assertRaises(SchemaError):
            migrate(self.path, directory)
        self.assertFalse(self.path.exists())

    def test_failing_migration_rolls_back_ddl_and_ledger(self):
        directory = self.copy_migrations()
        migrate(self.path, directory)
        ledger = self.query("SELECT * FROM schema_migrations")
        (directory / f"{SCHEMA_VERSION + 1:03d}_broken.sql").write_text("CREATE TABLE should_rollback (id INTEGER);\nINSERT INTO missing_table VALUES (1);\n")
        with self.assertRaises(sqlite3.Error):
            migrate(self.path, directory)
        self.assertEqual(ledger, self.query("SELECT * FROM schema_migrations"))
        self.assertEqual(self.query("PRAGMA user_version"), [(SCHEMA_VERSION,)])
        self.assertEqual(self.query("SELECT name FROM sqlite_master WHERE name='should_rollback'"), [])

    def test_first_migration_failure_leaves_no_partial_schema(self):
        directory = self.copy_migrations()
        (directory / "001_fixture_snapshots.sql").write_text("CREATE TABLE partial (id INTEGER);\nINVALID SQL;\n")
        with self.assertRaises(sqlite3.Error):
            migrate(self.path, directory)
        self.assertEqual(self.query("SELECT name FROM sqlite_master WHERE type='table'"), [])
        self.assertEqual(self.query("PRAGMA application_id"), [(0,)])

    def test_foreign_database_refused_without_data_changes(self):
        self.execute("CREATE TABLE unrelated (value TEXT)")
        self.execute("INSERT INTO unrelated VALUES ('keep-me')")
        before = self.path.read_bytes()
        with self.assertRaisesRegex(SchemaError, "not owned"):
            migrate(self.path)
        self.assertEqual(before, self.path.read_bytes())

    def test_readonly_check_does_not_create_missing_database(self):
        with self.assertRaises(sqlite3.Error):
            check_schema(self.path)
        self.assertFalse(self.path.exists())

    def test_schema_version_mismatch_is_rejected(self):
        migrate(self.path)
        self.execute("PRAGMA user_version = 0")
        with self.assertRaisesRegex(SchemaError, "disagree"):
            check_schema(self.path)

    def test_two_migrators_do_not_apply_same_step_twice(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: migrate(self.path), range(2)))
        self.assertEqual(results, [SCHEMA_VERSION, SCHEMA_VERSION])
        self.assertEqual(self.query("SELECT count(*) FROM schema_migrations"), [(SCHEMA_VERSION,)])

    def test_new_migration_preserves_existing_snapshot_and_old_code_refuses_future_schema(self):
        SQLiteScenarioStore.open(self.path)
        before = self.query("SELECT * FROM fixture_snapshots")
        directory = self.copy_migrations()
        (directory / f"{SCHEMA_VERSION + 1:03d}_extra.sql").write_text("CREATE TABLE additional_fixture_state (id INTEGER PRIMARY KEY);\n")
        with self.assertRaisesRegex(SchemaError, "pending"):
            check_schema(self.path, directory)
        self.assertEqual(migrate(self.path, directory), SCHEMA_VERSION + 1)
        self.assertEqual(check_schema(self.path, directory), SCHEMA_VERSION + 1)
        self.assertEqual(before, self.query("SELECT * FROM fixture_snapshots"))
        with self.assertRaises(SchemaError):
            check_schema(self.path)

    def test_migration_cli_and_readonly_check(self):
        env = dict(os.environ, ARCSHIFT_ENVIRONMENT="test", ARCSHIFT_DATA_MODE="synthetic", ARCSHIFT_STORAGE_BACKEND="sqlite", ARCSHIFT_DB_PATH=str(self.path))
        command = [sys.executable, "-m", "arcshift_v1.database"]
        result = subprocess.run(command, cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(json.loads(result.stdout)["schema_version"], SCHEMA_VERSION)
        self.assertEqual(self.query("SELECT count(*) FROM fixture_snapshots"), [(0,)])
        check = subprocess.run([*command, "--check"], cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=10, check=True)
        self.assertEqual(json.loads(check.stdout)["data_mode"], "synthetic")


class PersistentStoreTests(DatabaseTestCase):
    def test_seed_reopen_and_import_are_idempotent(self):
        first = SQLiteScenarioStore.open(self.path)
        before = self.query("SELECT * FROM fixture_snapshots")
        second = SQLiteScenarioStore.open(self.path)
        self.assertEqual(first.list_scenarios(), second.list_scenarios())
        self.assertEqual(before, self.query("SELECT * FROM fixture_snapshots"))
        self.assertEqual(self.query("SELECT count(*) FROM fixture_snapshots"), [(1,)])

    def test_same_fixture_version_with_changed_content_is_not_overwritten(self):
        store = SQLiteScenarioStore.open(self.path)
        data = json.loads(FIXTURE_PATH.read_text())
        data["scenarios"][0]["message"] = "Different synthetic content"
        with self.assertRaisesRegex(StoreUnavailableError, "overwrite"):
            store.import_fixture(FixtureDataset.model_validate(data))
        self.assertNotEqual(store.get_scenario("loading").message, "Different synthetic content")

    def test_invalid_fixture_does_not_create_database(self):
        path = self.directory / "invalid.json"
        path.write_text('{"synthetic": false}')
        with self.assertRaises(ValidationError):
            SQLiteScenarioStore.open(self.path, path)
        self.assertFalse(self.path.exists())

    def test_tampered_snapshot_fails_integrity_check(self):
        store = SQLiteScenarioStore.open(self.path)
        self.execute("UPDATE fixture_snapshots SET payload_json = '{}'")
        with self.assertRaises(StoreUnavailableError):
            store.list_scenarios()

    def test_bad_version_metadata_is_not_accepted(self):
        store = SQLiteScenarioStore.open(self.path)
        self.execute("UPDATE fixture_snapshots SET fixture_version = 'wrong'")
        with self.assertRaises(StoreUnavailableError):
            store.check_ready()

    def test_blob_payload_is_unavailable_not_unhandled_error(self):
        store = SQLiteScenarioStore.open(self.path)
        self.execute("UPDATE fixture_snapshots SET payload_json=X'7B7D'")
        with self.assertRaises(StoreUnavailableError):
            store.list_scenarios()
        self.execute("ALTER TABLE fixture_snapshots RENAME COLUMN payload_json TO incompatible_field")
        with self.assertRaises(StoreUnavailableError):
            store.check_ready()

    def test_bypassed_model_validation_cannot_publish_nonsynthetic_data(self):
        store = SQLiteScenarioStore.open(self.path)
        dataset = FixtureDataset.model_validate_json(FIXTURE_PATH.read_text())
        unvalidated = dataset.model_copy(update={"synthetic": False})
        before = self.query("SELECT * FROM fixture_snapshots")
        with self.assertRaises(ValidationError):
            store.import_fixture(unvalidated)
        self.assertEqual(before, self.query("SELECT * FROM fixture_snapshots"))

    def test_deleted_database_is_not_silently_recreated_by_reads(self):
        store = SQLiteScenarioStore.open(self.path)
        self.path.unlink()
        with self.assertRaises(StoreUnavailableError):
            store.list_scenarios()
        self.assertFalse(self.path.exists())

    def test_missing_active_snapshot_is_not_low_risk(self):
        store = SQLiteScenarioStore.open(self.path)
        self.execute("DELETE FROM fixture_active_snapshot")
        with self.assertRaises(StoreUnavailableError):
            store.get_scenario("historical_demo")

    def test_foreign_keys_prevent_invalid_active_pointer(self):
        SQLiteScenarioStore.open(self.path)
        with self.assertRaises(sqlite3.IntegrityError):
            self.execute("UPDATE fixture_active_snapshot SET snapshot_id='not-a-snapshot'")

    def test_parallel_import_is_single_snapshot(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            stores = list(executor.map(lambda _: SQLiteScenarioStore.open(self.path), range(2)))
        self.assertEqual(self.query("SELECT count(*) FROM fixture_snapshots"), [(1,)])
        self.assertEqual(stores[0].list_scenarios(), stores[1].list_scenarios())

    def test_untrusted_scenario_id_is_not_sql(self):
        store = SQLiteScenarioStore.open(self.path)
        with self.assertRaises(KeyError):
            store.get_scenario("'; DROP TABLE fixture_snapshots;--")
        store.check_ready()


class PersistentAPITests(DatabaseTestCase):
    def settings(self):
        return Settings(environment="test", storage_backend="sqlite", database_path=self.path)

    def test_restart_preserves_snapshot_and_api_contract(self):
        with TestClient(create_app(self.settings())) as client:
            before = client.get("/api/v1/demo/scenarios").json()
        snapshot = self.query("SELECT * FROM fixture_snapshots")
        with TestClient(create_app(self.settings())) as client:
            self.assertEqual(client.get("/api/v1/demo/scenarios").json(), before)
            self.assertFalse(client.get("/readyz").json()["production_ready"])
        self.assertEqual(snapshot, self.query("SELECT * FROM fixture_snapshots"))

    def test_corruption_returns_generic_503_and_health_is_separate(self):
        with TestClient(create_app(self.settings())) as client:
            self.execute("UPDATE fixture_snapshots SET payload_json='corrupt-private-details'")
            for path in ("/readyz", "/api/v1/demo/scenarios", "/api/v1/demo/scenarios/empty"):
                response = client.get(path)
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.json()["detail"]["code"], "fixture_store_unavailable")
                self.assertNotIn(str(self.path), response.text)
                self.assertNotIn("corrupt-private-details", response.text)
                self.assertEqual(response.headers["x-arcshift-data-mode"], "synthetic")
            self.assertEqual(client.get("/healthz").status_code, 200)

    def test_get_requests_do_not_modify_database_or_migrate(self):
        with TestClient(create_app(self.settings())) as client:
            before = self.path.read_bytes()
            for _ in range(3):
                self.assertEqual(client.get("/api/v1/demo/scenarios/empty").status_code, 200)
                self.assertEqual(client.get("/readyz").status_code, 200)
            self.assertEqual(before, self.path.read_bytes())

    def test_memory_mode_does_not_create_database(self):
        settings = Settings(environment="test", storage_backend="memory", database_path=self.path)
        with TestClient(create_app(settings)) as client:
            self.assertEqual(client.get("/readyz").status_code, 200)
        self.assertFalse(self.path.exists())

    def test_storage_settings_reject_unknown_backend_or_empty_path(self):
        self.assertEqual(Settings.from_env({}).storage_backend, "sqlite")
        settings = Settings.from_env({"ARCSHIFT_DB_PATH": "relative-fixture.db"})
        self.assertEqual(settings.database_path, PROJECT_ROOT / "relative-fixture.db")
        for env in ({"ARCSHIFT_STORAGE_BACKEND": "production-cloud"}, {"ARCSHIFT_DB_PATH": ""}, {"ARCSHIFT_DB_PATH": ":memory:"}):
            with self.subTest(env=env), self.assertRaises(ValueError):
                Settings.from_env(env)


if __name__ == "__main__":
    unittest.main()
