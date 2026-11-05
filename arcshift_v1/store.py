"""Memory and persistent synthetic stores; no provider or model access."""

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Protocol

from pydantic import ValidationError

from .database import check_schema, connect, migrate
from .schemas import DemoScenario, FixtureDataset


FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures/ui_scenarios.json"


class StoreUnavailableError(RuntimeError):
    pass


class ScenarioStore(Protocol):
    def check_ready(self) -> None: ...

    def list_scenarios(self) -> tuple[DemoScenario, ...]: ...

    def get_scenario(self, scenario_id: str) -> DemoScenario: ...


class FixtureStore:
    def __init__(self, dataset: FixtureDataset):
        self._dataset = dataset.model_copy(deep=True)

    @classmethod
    def from_file(cls, path: Path = FIXTURE_PATH):
        return cls(FixtureDataset.model_validate_json(path.read_text(encoding="utf-8")))

    def list_scenarios(self) -> tuple[DemoScenario, ...]:
        return tuple(row.model_copy(deep=True) for row in self._dataset.scenarios)

    def get_scenario(self, scenario_id: str) -> DemoScenario:
        for row in self._dataset.scenarios:
            if row.id == scenario_id:
                return row.model_copy(deep=True)
        raise KeyError(scenario_id)

    def check_ready(self) -> None:
        return None


def canonical_payload(dataset: FixtureDataset) -> str:
    validated = FixtureDataset.model_validate_json(dataset.model_dump_json())
    return json.dumps(validated.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class SQLiteScenarioStore:
    def __init__(self, path: Path):
        self.path = path.resolve()

    @classmethod
    def open(cls, path: Path, fixture_path: Path = FIXTURE_PATH):
        dataset = FixtureDataset.model_validate_json(fixture_path.read_text(encoding="utf-8"))
        migrate(path)
        store = cls(path)
        store.import_fixture(dataset)
        store.check_ready()
        return store

    def import_fixture(self, dataset: FixtureDataset) -> str:
        payload = canonical_payload(dataset)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        snapshot_id = "fixture-" + digest
        check_schema(self.path)
        with closing(connect(self.path, create=False)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute("SELECT snapshot_id, payload_sha256, payload_json, synthetic FROM fixture_snapshots WHERE fixture_version = ?", (dataset.fixture_version,)).fetchone()
                if existing is not None:
                    if tuple(existing) != (snapshot_id, digest, payload, 1):
                        raise StoreUnavailableError("Fixture version was modified; refusing to overwrite history")
                else:
                    connection.execute(
                        "INSERT INTO fixture_snapshots VALUES (?, ?, ?, ?, 1, ?)",
                        (snapshot_id, dataset.fixture_version, digest, payload, datetime.now(timezone.utc).isoformat()),
                    )
                connection.execute("INSERT INTO fixture_active_snapshot(slot, snapshot_id) VALUES (1, ?) ON CONFLICT(slot) DO NOTHING", (snapshot_id,))
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        return snapshot_id

    def _snapshot(self) -> tuple[str, FixtureDataset]:
        try:
            check_schema(self.path)
            with closing(connect(self.path, readonly=True)) as connection:
                row = connection.execute(
                    "SELECT s.* FROM fixture_snapshots s JOIN fixture_active_snapshot a ON a.snapshot_id = s.snapshot_id WHERE a.slot = 1"
                ).fetchone()
            if row is None:
                raise StoreUnavailableError("No active fixture snapshot")
            if any(type(row[key]) is not str for key in ("snapshot_id", "fixture_version", "payload_sha256", "payload_json")):
                raise StoreUnavailableError("Invalid fixture metadata types")
            digest = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
            if row["payload_sha256"] != digest or row["snapshot_id"] != "fixture-" + digest or row["synthetic"] != 1:
                raise StoreUnavailableError("Fixture snapshot integrity check failed")
            dataset = FixtureDataset.model_validate_json(row["payload_json"])
            if dataset.fixture_version != row["fixture_version"]:
                raise StoreUnavailableError("Fixture version metadata mismatch")
            return row["snapshot_id"], dataset
        except (sqlite3.Error, ValidationError, OSError, ValueError, RuntimeError, IndexError, TypeError) as exc:
            raise StoreUnavailableError("Persistent fixture store unavailable") from exc

    def _dataset(self) -> FixtureDataset:
        return self._snapshot()[1]

    def snapshot_scenario(self, scenario_id: str) -> tuple[str, DemoScenario]:
        snapshot_id, dataset = self._snapshot()
        for row in dataset.scenarios:
            if row.id == scenario_id:
                return snapshot_id, row
        raise KeyError(scenario_id)

    def check_ready(self) -> None:
        self._dataset()

    def list_scenarios(self) -> tuple[DemoScenario, ...]:
        return self._dataset().scenarios

    def get_scenario(self, scenario_id: str) -> DemoScenario:
        for row in self._dataset().scenarios:
            if row.id == scenario_id:
                return row
        raise KeyError(scenario_id)
