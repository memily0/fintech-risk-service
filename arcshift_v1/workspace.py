"""Owner-scoped synthetic reviews with immutable evidence and optimistic writes."""

from contextlib import closing
from typing import Annotated, Literal
import uuid

from pydantic import AwareDatetime, Field, field_validator

from .auth import AuthFailure, AuthService
from .database import connect
from .market import SERIES_BINDINGS, MarketStore
from .schemas import ContractModel, DemoScenario, ScenarioID, SyntheticModel
from .store import SQLiteScenarioStore


ReviewStatus = Literal["acknowledged", "in_review", "closed", "dismissed"]
WarningID = Annotated[str, Field(pattern=r"^synthetic-warning-[a-z0-9-]{1,64}$")]
SeriesID = Annotated[str, Field(pattern=r"^[a-z0-9_.]{1,96}$")]
WARNING_POLICY = "fixture-policy-1"
WARNING_EVENTS = (
    ("episode-001", "2026-11-05T06:10:00Z"),
    ("episode-002", "2026-11-05T06:15:00Z"),
)
TRANSITIONS = {
    "acknowledged": {"acknowledged", "in_review", "dismissed"},
    "in_review": {"in_review", "closed", "dismissed"},
    "closed": {"closed"},
    "dismissed": {"dismissed"},
}


class WorkspaceView(SyntheticModel):
    workspace_contract_version: Literal["v1-local-workspace.1"] = "v1-local-workspace.1"
    production_ready: Literal[False] = False


class WatchlistRequest(ContractModel):
    scenario_ids: Annotated[tuple[ScenarioID, ...], Field(max_length=6)]

    @field_validator("scenario_ids")
    @classmethod
    def distinct(cls, values):
        if len(values) != len(set(values)):
            raise ValueError("Duplicate scenario")
        return values


class WatchlistView(WorkspaceView):
    scenario_ids: tuple[ScenarioID, ...]


class SeriesWatchlistRequest(ContractModel):
    series_ids: Annotated[tuple[SeriesID, ...], Field(max_length=13)]

    @field_validator("series_ids")
    @classmethod
    def known_distinct_series(cls, values):
        if len(values) != len(set(values)) or any(value not in SERIES_BINDINGS for value in values):
            raise ValueError("Expected distinct supported market series IDs")
        return values


class SeriesWatchlistView(WorkspaceView):
    series_ids: tuple[SeriesID, ...]


class WarningReference(SyntheticModel):
    warning_id: WarningID
    event_key: str
    policy_version: str
    occurred_at: AwareDatetime
    fixture_snapshot_id: str
    data_snapshot_id: str
    validity_status: Literal["historical_demo"] = "historical_demo"


class WarningView(WarningReference):
    review_id: str | None
    review_status: ReviewStatus | Literal["new"]


class WarningQueue(WorkspaceView):
    warning_contract_version: Literal["v1-local-warnings.1"] = "v1-local-warnings.1"
    source_rights_status: Literal["not_admitted"] = "not_admitted"
    warnings: tuple[WarningView, ...]


class CreateReview(ContractModel):
    scenario_id: ScenarioID
    note: Annotated[str, Field(max_length=4000, strict=True)] = ""


class UpdateReview(ContractModel):
    expected_revision: Annotated[int, Field(ge=1, strict=True)]
    status: ReviewStatus
    note: Annotated[str, Field(max_length=4000, strict=True)]

    @field_validator("note")
    @classmethod
    def closure_requires_note(cls, value, info):
        if info.data.get("status") in {"closed", "dismissed"} and not value.strip():
            raise ValueError("Closing or dismissing requires an analyst note")
        return value


class ReviewView(WorkspaceView):
    review_id: str
    snapshot_id: str
    scenario: DemoScenario
    status: ReviewStatus
    note: str
    revision: int
    created_at: int
    updated_at: int
    warning: WarningReference | None = Field(default=None, exclude_if=lambda value: value is None)


class ReviewList(WorkspaceView):
    reviews: tuple[ReviewView, ...]
    limit: int
    offset: int


class ReviewEvent(ContractModel):
    status: ReviewStatus
    revision: int
    occurred_at: int


class ReviewReport(WorkspaceView):
    review: ReviewView
    events: tuple[ReviewEvent, ...]
    source_rights_status: Literal["not_admitted"] = "not_admitted"
    limitation: Literal["Synthetic workflow evidence only; not a current risk estimate or model validation"] = "Synthetic workflow evidence only; not a current risk estimate or model validation"


def warning_reference(row):
    return WarningReference(**{key: row[key] for key in (
        "warning_id", "event_key", "policy_version", "occurred_at", "fixture_snapshot_id", "data_snapshot_id",
    )})


REVIEW_SELECT = """SELECT r.*, w.event_key, w.policy_version, w.occurred_at,
                          w.fixture_snapshot_id, w.data_snapshot_id
                   FROM local_reviews r LEFT JOIN local_warnings w ON w.warning_id=r.warning_id"""


class WorkspaceService:
    def __init__(self, auth: AuthService, store: SQLiteScenarioStore):
        self.auth, self.store = auth, store

    @staticmethod
    def view(row):
        return ReviewView(
            review_id=row["review_id"], snapshot_id=row["snapshot_id"],
            scenario=DemoScenario.model_validate_json(row["scenario_json"]), status=row["status"], note=row["note"],
            revision=row["revision"], created_at=row["created_at"], updated_at=row["updated_at"],
            warning=warning_reference(row) if row["warning_id"] is not None else None,
        )

    @staticmethod
    def owned(connection, user_id, review_id):
        row = connection.execute(REVIEW_SELECT + " WHERE r.user_id=? AND r.review_id=?", (user_id, review_id)).fetchone()
        if row is None:
            raise AuthFailure("review_not_found", 404)
        return row

    def watchlist(self, user_id):
        with closing(connect(self.auth.path, readonly=True)) as connection:
            rows = connection.execute("SELECT scenario_id FROM local_watchlist WHERE user_id=? ORDER BY scenario_id", (user_id,)).fetchall()
        return WatchlistView(scenario_ids=tuple(row[0] for row in rows))

    def save_watchlist(self, user_id, data: WatchlistRequest):
        with self.auth.transaction() as connection:
            connection.execute("DELETE FROM local_watchlist WHERE user_id=?", (user_id,))
            connection.executemany("INSERT INTO local_watchlist VALUES (?, ?, ?)", [(user_id, value, int(self.auth.clock())) for value in data.scenario_ids])
        return self.watchlist(user_id)

    def series_watchlist(self, user_id):
        with closing(connect(self.auth.path, readonly=True)) as connection:
            rows = connection.execute("SELECT series_id FROM local_series_watchlist WHERE user_id=? ORDER BY series_id", (user_id,)).fetchall()
        return SeriesWatchlistView(series_ids=tuple(row[0] for row in rows))

    def save_series_watchlist(self, user_id, data: SeriesWatchlistRequest):
        with self.auth.transaction() as connection:
            connection.execute("DELETE FROM local_series_watchlist WHERE user_id=?", (user_id,))
            connection.executemany("INSERT INTO local_series_watchlist VALUES (?, ?)", [(user_id, series_id) for series_id in data.series_ids])
        return SeriesWatchlistView(series_ids=tuple(sorted(data.series_ids)))

    def seed_warnings(self, market: MarketStore):
        with self.auth.transaction() as connection:
            existing = {row[0] for row in connection.execute("SELECT event_key FROM local_warnings WHERE policy_version=?", (WARNING_POLICY,))}
            pending = [(key, occurred_at) for key, occurred_at in WARNING_EVENTS if key not in existing]
            if not pending:
                return
            fixture_snapshot_id, _ = self.store.snapshot_scenario("historical_demo")
            data_snapshot_id = "market-" + market.read().snapshot_id
            connection.executemany(
                "INSERT INTO local_warnings VALUES (?, ?, ?, ?, ?, ?)",
                [(f"synthetic-warning-{WARNING_POLICY}-{key}", key, WARNING_POLICY, occurred_at, fixture_snapshot_id, data_snapshot_id) for key, occurred_at in pending],
            )

    def warnings(self, user_id):
        with closing(connect(self.auth.path, readonly=True)) as connection:
            rows = connection.execute(
                """SELECT w.*, r.review_id, r.status FROM local_warnings w
                   LEFT JOIN local_reviews r ON w.warning_id=r.warning_id AND r.user_id=?
                   ORDER BY w.occurred_at DESC, w.warning_id""", (user_id,),
            ).fetchall()
        return WarningQueue(warnings=tuple(
            WarningView(**warning_reference(row).model_dump(), review_id=row["review_id"], review_status=row["status"] or "new")
            for row in rows
        ))

    def acknowledge_warning(self, user_id, warning_id):
        with self.auth.transaction() as connection:
            warning = connection.execute("SELECT * FROM local_warnings WHERE warning_id=?", (warning_id,)).fetchone()
            if warning is None:
                raise AuthFailure("warning_not_found", 404)
            existing = connection.execute("SELECT review_id FROM local_reviews WHERE user_id=? AND warning_id=?", (user_id, warning_id)).fetchone()
            if existing is not None:
                return self.view(self.owned(connection, user_id, existing["review_id"]))
            snapshot_id, scenario = self.store.snapshot_scenario("historical_demo", snapshot_id=warning["fixture_snapshot_id"])
            return self._insert_review(connection, user_id, snapshot_id, scenario, note="", warning_id=warning_id)

    def list_reviews(self, user_id, limit, offset):
        with closing(connect(self.auth.path, readonly=True)) as connection:
            rows = connection.execute(REVIEW_SELECT + " WHERE r.user_id=? ORDER BY r.created_at DESC, r.review_id DESC LIMIT ? OFFSET ?", (user_id, limit, offset)).fetchall()
        return ReviewList(reviews=tuple(self.view(row) for row in rows), limit=limit, offset=offset)

    def create_review(self, user_id, data: CreateReview):
        snapshot_id, scenario = self.store.snapshot_scenario(data.scenario_id)
        with self.auth.transaction() as connection:
            return self._insert_review(connection, user_id, snapshot_id, scenario, note=data.note)

    def _insert_review(self, connection, user_id, snapshot_id, scenario, *, note, warning_id=None):
        review_id = str(uuid.uuid4())
        now = int(self.auth.clock())
        connection.execute(
            """INSERT INTO local_reviews
               (review_id, user_id, snapshot_id, scenario_json, status, note, revision, created_at, updated_at, warning_id)
               VALUES (?, ?, ?, ?, 'acknowledged', ?, 1, ?, ?, ?)""",
            (review_id, user_id, snapshot_id, scenario.model_dump_json(), note, now, now, warning_id),
        )
        connection.execute("INSERT INTO local_review_events VALUES (?, ?, ?, 'acknowledged', 1, ?)", (str(uuid.uuid4()), review_id, user_id, now))
        return self.view(self.owned(connection, user_id, review_id))

    def update_review(self, user_id, review_id, data: UpdateReview):
        now = int(self.auth.clock())
        with self.auth.transaction() as connection:
            row = self.owned(connection, user_id, review_id)
            if row["revision"] != data.expected_revision:
                raise AuthFailure("review_revision_conflict", 409)
            if data.status not in TRANSITIONS[row["status"]]:
                raise AuthFailure("invalid_review_transition", 409)
            connection.execute("UPDATE local_reviews SET status=?, note=?, revision=revision+1, updated_at=? WHERE review_id=? AND user_id=?", (data.status, data.note, now, review_id, user_id))
            connection.execute("INSERT INTO local_review_events VALUES (?, ?, ?, ?, ?, ?)", (str(uuid.uuid4()), review_id, user_id, data.status, row["revision"] + 1, now))
            return self.view(self.owned(connection, user_id, review_id))

    def report(self, user_id, review_id):
        with closing(connect(self.auth.path, readonly=True)) as connection:
            connection.execute("BEGIN")
            row = self.owned(connection, user_id, review_id)
            events = connection.execute("SELECT status, revision, occurred_at FROM local_review_events WHERE user_id=? AND review_id=? ORDER BY revision", (user_id, review_id)).fetchall()
            return ReviewReport(review=self.view(row), events=tuple(ReviewEvent(**dict(event)) for event in events))
