"""Read boundary for Nastya's parser/revision output; synthetic fixtures only."""

from contextlib import closing
from datetime import date
import hashlib
import json
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import time
from typing import Annotated, Literal

from arcshift_data import JsonObservationStore, load_source_registry, parse_cbr_currency_xml, parse_cbr_curve_html, parse_rosstat_cpi_json
from arcshift_data.parsers import CURRENCY_SERIES, CURVE_SERIES
from pydantic import AwareDatetime, Field, ValidationError, field_validator, model_validator

from .database import check_schema, connect
from .schemas import ContractModel, SyntheticModel
from .store import StoreUnavailableError


FIXTURES = Path(__file__).resolve().parent / "fixtures/market"
REGISTRY = FIXTURES / "source_registry.json"
HEX = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
POSITIVE = Annotated[int, Field(ge=1, strict=True)]
SERIES_BINDINGS = {row["series_id"]: (row["resource_id"], row["units"]) for row in CURRENCY_SERIES.values()}
SERIES_BINDINGS.update({row[0]: (row[1], "percent_per_annum") for row in CURVE_SERIES.values()})
SERIES_BINDINGS["ru.prices.rosstat.cpi_yoy"] = ("rosstat:11521100300010200001:selection_pending", "percent_YoY")


class Observation(ContractModel):
    schema_version: Literal["candidate.1"]
    series_id: str
    definition_version: Literal["candidate.1"]
    resource_id: str
    units: str
    value: float
    quality: Literal["observed"]
    reference_start: date
    reference_end: date
    effective_date: date | None
    published_at: AwareDatetime | None
    publication_status: Literal["unknown", "known"]
    received_at: AwareDatetime
    source_timezone: Literal["Europe/Moscow"]
    snapshot_id: str
    receipt_sha256: HEX
    dimensions: dict[str, str | int]
    is_synthetic: Literal[True]

    @field_validator("value", mode="before")
    @classmethod
    def numeric_only(cls, value):
        if type(value) not in (int, float):
            raise ValueError("Value must be numeric")
        return value

    @field_validator("is_synthetic", mode="before")
    @classmethod
    def synthetic_only(cls, value):
        if value is not True:
            raise ValueError("Real observations are not admitted")
        return value

    @model_validator(mode="after")
    def consistent_metadata(self):
        if self.reference_start > self.reference_end:
            raise ValueError("Reference range reversed")
        if (self.published_at is None) != (self.publication_status == "unknown"):
            raise ValueError("Publication status is inconsistent")
        if self.published_at is not None and self.published_at > self.received_at:
            raise ValueError("Publication follows receipt")
        return self


class Revision(ContractModel):
    observation_identity: str
    revision_number: POSITIVE
    ingested_at: AwareDatetime
    observation: Observation


class MarketState(ContractModel):
    schema_version: Literal["candidate.1"]
    revisions: Annotated[tuple[Revision, ...], Field(min_length=1, max_length=10000)]
    latest: dict[str, Revision]
    published_at: AwareDatetime
    snapshot_id: HEX


class MarketEnvelope(SyntheticModel):
    market_contract_version: Literal["v1-local-market.1"] = "v1-local-market.1"
    data_mode: Literal["synthetic"] = "synthetic"
    production_ready: Literal[False] = False
    source_rights_status: Literal["not_admitted"] = "not_admitted"
    validity_status: Literal["historical_demo"] = "historical_demo"
    data_snapshot_id: str


class SeriesView(ContractModel):
    series_id: str
    resource_id: str
    source_id: str
    units: str
    latest_reference_end: date
    received_at: AwareDatetime
    publication_status: Literal["unknown", "known"]
    published_at: AwareDatetime | None
    observation_count: int
    revision_count: int


class SeriesList(MarketEnvelope):
    series: tuple[SeriesView, ...]


class HistoryRow(Revision):
    is_latest: bool


class HistoryResponse(MarketEnvelope):
    series_id: str
    observations: tuple[HistoryRow, ...]
    total: int
    limit: int
    offset: int


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)


def validate_state(raw):
    without_id = dict(raw)
    claimed = without_id.pop("snapshot_id", None)
    if claimed != hashlib.sha256(canonical(without_id).encode()).hexdigest():
        raise ValueError("Market state content hash mismatch")
    state = MarketState.model_validate(raw)
    latest, sequences, seen = {}, {}, set()
    resources = {resource: source for source in load_source_registry(REGISTRY)["sources"] for resource in source["series"]}
    for revision in state.revisions:
        row = revision.observation
        if row.received_at > revision.ingested_at or revision.ingested_at > state.published_at:
            raise ValueError("Receipt ingestion and publication order is invalid")
        identity = "|".join((row.series_id, row.reference_start.isoformat(), row.reference_end.isoformat()))
        if revision.observation_identity != identity:
            raise ValueError("Observation identity mismatch")
        source = resources.get(row.resource_id)
        if source is None or SERIES_BINDINGS.get(row.series_id) != (row.resource_id, row.units):
            raise ValueError("Unknown or mismatched series resource or units")
        key = (identity, row.receipt_sha256)
        if key in seen or revision.revision_number != sequences.get(identity, 0) + 1:
            raise ValueError("Duplicate or non-contiguous revision")
        seen.add(key); sequences[identity] = revision.revision_number
        if identity not in latest or row.received_at >= latest[identity].observation.received_at:
            latest[identity] = revision
    if state.latest != latest:
        raise ValueError("Latest map differs from the revision history")
    return state


def fixture_state():
    received = "2026-11-05T09:00:00+03:00"
    source_snapshot = "synthetic-parser-receipt-001"
    observations = []
    for filename, currency in (("usd.xml", "R01235"), ("eur.xml", "R01239")):
        observations.extend(parse_cbr_currency_xml((FIXTURES / filename).read_bytes(), currency, received, source_snapshot, True))
    observations.extend(parse_cbr_curve_html((FIXTURES / "curve.html").read_bytes(), received, source_snapshot, True))
    observations.extend(parse_rosstat_cpi_json((FIXTURES / "cpi.json").read_bytes(), {"territory": "SYNTHETIC_RU", "coverage": "SYNTHETIC_ALL_ITEMS", "comparison": "SYNTHETIC_YEAR_AGO", "frequency": "SYNTHETIC_MONTHLY"}, received, source_snapshot, True))
    # Exercise the contributor's real revision store before publishing a read snapshot.
    with TemporaryDirectory(prefix="arcshift-parser-fixture-") as directory:
        producer = JsonObservationStore(Path(directory) / "observations.json")
        producer.publish(observations, "2026-11-05T09:01:00+03:00")
        revised = parse_cbr_currency_xml((FIXTURES / "usd_revision.xml").read_bytes(), "R01235", "2026-11-05T09:05:00+03:00", "synthetic-parser-receipt-002", True)
        producer.publish(revised, "2026-11-05T09:06:00+03:00")
        return producer.read()


class MarketStore:
    def __init__(self, raw, path: Path | None = None):
        self.path = path
        self.raw = json.loads(canonical(raw))
        validate_state(self.raw)

    @classmethod
    def open(cls, path: Path | None = None):
        store = cls(fixture_state(), path)
        if path is not None:
            store.publish(store.raw, replace_active=False)
        return store

    def publish(self, raw, *, replace_active=True):
        state = validate_state(raw)
        if self.path is None:
            raise ValueError("Memory store is read-only")
        check_schema(self.path)
        payload = canonical(raw)
        payload_hash = hashlib.sha256(payload.encode()).hexdigest()
        identifier = "market-" + state.snapshot_id
        with closing(connect(self.path, create=False)) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute("SELECT payload_json, payload_sha256 FROM local_market_snapshots WHERE snapshot_id=?", (identifier,)).fetchone()
                if row is not None and tuple(row) != (payload, payload_hash):
                    raise StoreUnavailableError("Refusing changed immutable market snapshot")
                connection.execute("INSERT OR IGNORE INTO local_market_snapshots VALUES (?, ?, ?, 1, ?)", (identifier, payload, payload_hash, int(time.time())))
                if replace_active:
                    connection.execute("INSERT INTO local_market_active VALUES (1, ?) ON CONFLICT(slot) DO UPDATE SET snapshot_id=excluded.snapshot_id", (identifier,))
                else:
                    connection.execute("INSERT INTO local_market_active VALUES (1, ?) ON CONFLICT(slot) DO NOTHING", (identifier,))
                connection.execute("COMMIT")
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise
        return identifier

    def read(self):
        try:
            if self.path is None:
                return validate_state(self.raw)
            check_schema(self.path)
            with closing(connect(self.path, readonly=True)) as connection:
                row = connection.execute("SELECT s.* FROM local_market_snapshots s JOIN local_market_active a ON a.snapshot_id=s.snapshot_id WHERE a.slot=1").fetchone()
            if row is None or type(row["payload_json"]) is not str or row["synthetic"] != 1:
                raise ValueError("No valid active market snapshot")
            if hashlib.sha256(row["payload_json"].encode()).hexdigest() != row["payload_sha256"]:
                raise ValueError("Market payload hash mismatch")
            state = validate_state(json.loads(row["payload_json"]))
            if row["snapshot_id"] != "market-" + state.snapshot_id:
                raise ValueError("Market snapshot identity mismatch")
            return state
        except (sqlite3.Error, ValidationError, OSError, ValueError, TypeError, KeyError, IndexError, RuntimeError) as error:
            raise StoreUnavailableError("Market snapshot unavailable") from error

    def check_ready(self):
        self.read()

    def series(self):
        state = self.read()
        resources = {resource: source["source_id"] for source in load_source_registry(REGISTRY)["sources"] for resource in source["series"]}
        result = []
        for series_id in sorted({revision.observation.series_id for revision in state.revisions}):
            current = [revision.observation for revision in state.latest.values() if revision.observation.series_id == series_id]
            row = max(current, key=lambda item: (item.reference_end, item.received_at))
            result.append(SeriesView(series_id=series_id, resource_id=row.resource_id, source_id=resources[row.resource_id], units=row.units, latest_reference_end=row.reference_end, received_at=row.received_at, publication_status=row.publication_status, published_at=row.published_at, observation_count=len(current), revision_count=sum(item.observation.series_id == series_id for item in state.revisions)))
        return SeriesList(data_snapshot_id="market-" + state.snapshot_id, series=tuple(result))

    def history(self, series_id, start, end, include_revisions, limit, offset):
        state = self.read()
        if not any(item.observation.series_id == series_id for item in state.revisions):
            raise KeyError(series_id)
        rows = state.revisions if include_revisions else tuple(state.latest.values())
        selected = [row for row in rows if row.observation.series_id == series_id and (start is None or row.observation.reference_end >= start) and (end is None or row.observation.reference_start <= end)]
        selected.sort(key=lambda row: (row.observation.reference_start, row.revision_number))
        return HistoryResponse(data_snapshot_id="market-" + state.snapshot_id, series_id=series_id, observations=tuple(HistoryRow(**row.model_dump(), is_latest=state.latest[row.observation_identity] == row) for row in selected[offset:offset + limit]), total=len(selected), limit=limit, offset=offset)
