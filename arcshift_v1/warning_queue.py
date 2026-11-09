"""Versioned indicator watchlist and explicitly synthetic immutable warnings."""

from contextlib import closing
import hashlib
from typing import Annotated, Literal
from uuid import UUID, NAMESPACE_URL, uuid4, uuid5

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field, field_validator

from .auth import AuthFailure, SessionIdentity
from .database import connect
from .market import SERIES_BINDINGS
from .schemas import ContractModel, DemoScenario
from .workspace import ReviewView, WorkspaceService, WorkspaceView
from .workspace_api import current_user, writing_user, workspace


class IndicatorWatchlistRequest(ContractModel):
    series_ids: Annotated[tuple[str, ...], Field(max_length=13)]

    @field_validator("series_ids")
    @classmethod
    def supported_distinct_series(cls, values):
        if len(set(values)) != len(values) or not set(values) <= set(SERIES_BINDINGS):
            raise ValueError("Unknown or duplicate series ID")
        return values


class IndicatorWatchlist(WorkspaceView):
    indicator_contract_version: Literal["v1-local-indicators.1"] = "v1-local-indicators.1"
    series_ids: tuple[str, ...]


class WarningView(WorkspaceView):
    queue_contract_version: Literal["v1-local-queue.1"] = "v1-local-queue.1"
    warning_id: UUID
    signal_id: str
    policy_id: str
    snapshot_id: str
    data_snapshot_id: str
    title: str
    scenario: DemoScenario
    created_at: int
    review: ReviewView | None = None


class WarningList(WorkspaceView):
    queue_contract_version: Literal["v1-local-queue.1"] = "v1-local-queue.1"
    warnings: tuple[WarningView, ...]
    limit: int
    offset: int


class QueueService:
    def __init__(self, work: WorkspaceService, market):
        self.work, self.market = work, market
        self.auth = work.auth

    def publish_examples(self):
        """Explicit startup publication. HTTP reads never create warnings."""
        fixture_id, scenario = self.work.store.snapshot_scenario("historical_demo")
        market_id = "market-" + self.market.read().snapshot_id
        policy = "synthetic-queue-policy.1"
        with self.auth.transaction() as connection:
            for example in ("A", "B"):
                digest = hashlib.sha256(f"{fixture_id}/{market_id}/{example}".encode()).hexdigest()
                signal_id = "synthetic-signal-" + digest
                warning_id = str(uuid5(NAMESPACE_URL, signal_id + "/" + policy))
                connection.execute(
                    "INSERT OR IGNORE INTO local_warnings VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (warning_id, signal_id, policy, fixture_id, market_id,
                     "Исторический synthetic-пример " + example, scenario.model_dump_json(), int(self.auth.clock())),
                )

    def indicators(self, user_id):
        with closing(connect(self.auth.path, readonly=True)) as connection:
            rows = connection.execute("SELECT series_id FROM local_indicator_watchlist WHERE user_id=? ORDER BY series_id", (user_id,)).fetchall()
        return IndicatorWatchlist(series_ids=tuple(row[0] for row in rows))

    def save_indicators(self, user_id, data):
        with self.auth.transaction() as connection:
            connection.execute("DELETE FROM local_indicator_watchlist WHERE user_id=?", (user_id,))
            connection.executemany("INSERT INTO local_indicator_watchlist VALUES (?, ?, ?)",
                                   [(user_id, series, int(self.auth.clock())) for series in data.series_ids])
        return self.indicators(user_id)

    def list(self, user_id, limit, offset):
        with closing(connect(self.auth.path, readonly=True)) as connection:
            connection.execute("BEGIN")
            rows = connection.execute(
                "SELECT w.*, link.review_id FROM local_warnings w LEFT JOIN local_warning_reviews link "
                "ON link.warning_id=w.warning_id AND link.user_id=? ORDER BY w.created_at DESC, w.warning_id LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
            warnings = []
            for row in rows:
                review = self.work.view(self.work.owned(connection, user_id, row["review_id"])) if row["review_id"] else None
                warnings.append(WarningView(
                    warning_id=row["warning_id"], signal_id=row["signal_id"], policy_id=row["policy_id"],
                    snapshot_id=row["snapshot_id"], data_snapshot_id=row["data_snapshot_id"],
                    title=row["title"], created_at=row["created_at"],
                    scenario=DemoScenario.model_validate_json(row["scenario_json"]), review=review,
                ))
        return WarningList(warnings=tuple(warnings), limit=limit, offset=offset)

    def begin_review(self, user_id, warning_id):
        with self.auth.transaction() as connection:
            row = connection.execute("SELECT * FROM local_warnings WHERE warning_id=?", (str(warning_id),)).fetchone()
            if row is None:
                raise AuthFailure("warning_not_found", 404)
            existing = connection.execute("SELECT review_id FROM local_warning_reviews WHERE user_id=? AND warning_id=?",
                                          (user_id, str(warning_id))).fetchone()
            if existing:
                return self.work.view(self.work.owned(connection, user_id, existing[0]))
            review_id, now = str(uuid4()), int(self.auth.clock())
            connection.execute("INSERT INTO local_reviews VALUES (?, ?, ?, ?, 'acknowledged', '', 1, ?, ?)",
                               (review_id, user_id, row["snapshot_id"], row["scenario_json"], now, now))
            connection.execute("INSERT INTO local_review_events VALUES (?, ?, ?, 'acknowledged', 1, ?)",
                               (str(uuid4()), review_id, user_id, now))
            connection.execute("INSERT INTO local_warning_reviews VALUES (?, ?, ?)", (user_id, str(warning_id), review_id))
            return self.work.view(self.work.owned(connection, user_id, review_id))


router = APIRouter(prefix="/api/v1/workspace", tags=["synthetic-queue-indicators"])


def queue(request: Request, work: WorkspaceService = Depends(workspace)):
    return QueueService(work, request.app.state.market_store)


@router.get("/indicator-watchlist", response_model=IndicatorWatchlist)
def indicators(user: SessionIdentity = Depends(current_user), service: QueueService = Depends(queue)):
    return service.indicators(user.user_id)


@router.put("/indicator-watchlist", response_model=IndicatorWatchlist)
def save_indicators(data: IndicatorWatchlistRequest, user: SessionIdentity = Depends(writing_user), service: QueueService = Depends(queue)):
    return service.save_indicators(user.user_id, data)


@router.get("/warnings", response_model=WarningList)
def warnings(limit: Annotated[int, Query(ge=1, le=100)] = 50, offset: Annotated[int, Query(ge=0)] = 0,
             user: SessionIdentity = Depends(current_user), service: QueueService = Depends(queue)):
    return service.list(user.user_id, limit, offset)


@router.post("/warnings/{warning_id}/review", response_model=ReviewView)
def begin_review(warning_id: UUID, user: SessionIdentity = Depends(writing_user), service: QueueService = Depends(queue)):
    return service.begin_review(user.user_id, warning_id)
