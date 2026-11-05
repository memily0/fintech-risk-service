"""Owner-scoped synthetic reviews with immutable evidence and optimistic writes."""

from contextlib import closing
from typing import Annotated, Literal
import uuid

from pydantic import Field, field_validator

from .auth import AuthFailure, AuthService
from .database import connect
from .schemas import ContractModel, DemoScenario, ScenarioID, SyntheticModel
from .store import SQLiteScenarioStore


ReviewStatus = Literal["acknowledged", "in_review", "closed", "dismissed"]
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


class CreateReview(ContractModel):
    scenario_id: ScenarioID
    note: Annotated[str, Field(max_length=4000, strict=True)] = ""


class UpdateReview(ContractModel):
    expected_revision: Annotated[int, Field(ge=1, strict=True)]
    status: ReviewStatus
    note: Annotated[str, Field(max_length=4000, strict=True)]


class ReviewView(WorkspaceView):
    review_id: str
    snapshot_id: str
    scenario: DemoScenario
    status: ReviewStatus
    note: str
    revision: int
    created_at: int
    updated_at: int


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


class WorkspaceService:
    def __init__(self, auth: AuthService, store: SQLiteScenarioStore):
        self.auth, self.store = auth, store

    @staticmethod
    def view(row):
        return ReviewView(
            review_id=row["review_id"], snapshot_id=row["snapshot_id"],
            scenario=DemoScenario.model_validate_json(row["scenario_json"]), status=row["status"], note=row["note"],
            revision=row["revision"], created_at=row["created_at"], updated_at=row["updated_at"],
        )

    @staticmethod
    def owned(connection, user_id, review_id):
        row = connection.execute("SELECT * FROM local_reviews WHERE user_id=? AND review_id=?", (user_id, review_id)).fetchone()
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

    def list_reviews(self, user_id, limit, offset):
        with closing(connect(self.auth.path, readonly=True)) as connection:
            rows = connection.execute("SELECT * FROM local_reviews WHERE user_id=? ORDER BY created_at DESC, review_id DESC LIMIT ? OFFSET ?", (user_id, limit, offset)).fetchall()
        return ReviewList(reviews=tuple(self.view(row) for row in rows), limit=limit, offset=offset)

    def create_review(self, user_id, data: CreateReview):
        snapshot_id, scenario = self.store.snapshot_scenario(data.scenario_id)
        review_id = str(uuid.uuid4())
        now = int(self.auth.clock())
        with self.auth.transaction() as connection:
            connection.execute("INSERT INTO local_reviews VALUES (?, ?, ?, ?, 'acknowledged', ?, 1, ?, ?)", (review_id, user_id, snapshot_id, scenario.model_dump_json(), data.note, now, now))
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
