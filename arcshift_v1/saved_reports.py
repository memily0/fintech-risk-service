"""Freeze an owner-scoped review and selected synthetic observations together."""

from contextlib import closing
import hashlib
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import Field, ValidationError, field_validator

from .auth import AuthFailure
from .database import connect
from .market import HistoryRow
from .schemas import ContractModel
from .store import StoreUnavailableError
from .workspace import ReviewEvent, ReviewReport, WorkspaceView


class CreateSavedReport(ContractModel):
    review_id: UUID
    expected_revision: Annotated[int, Field(ge=1, strict=True)]
    expected_data_snapshot_id: Annotated[str, Field(pattern=r"^market-[0-9a-f]{64}$")]
    series_ids: Annotated[tuple[str, ...] | None, Field(max_length=13)] = None

    @field_validator("series_ids")
    @classmethod
    def unique_series(cls, values):
        if values is not None and len(values) != len(set(values)):
            raise ValueError("Duplicate series")
        return values


class SavedReport(WorkspaceView):
    report_id: UUID
    created_at: int
    data_snapshot_id: str
    review: ReviewReport
    observations: Annotated[tuple[HistoryRow, ...], Field(max_length=2000)]
    source_rights_status: Literal["not_admitted"] = "not_admitted"


class ReportSummary(WorkspaceView):
    report_id: UUID
    review_id: str
    review_revision: int
    created_at: int
    data_snapshot_id: str
    observation_count: int


class SavedReportList(WorkspaceView):
    reports: tuple[ReportSummary, ...]
    limit: int
    offset: int


class SavedReportService:
    def __init__(self, workspace, market):
        self.workspace, self.market = workspace, market
        self.auth = workspace.auth

    def create(self, user_id, data: CreateSavedReport):
        review = self.workspace.report(user_id, str(data.review_id)).review
        snapshot = self.market.read(review.data_snapshot_id)
        snapshot_id = "market-" + snapshot.snapshot_id
        if data.expected_data_snapshot_id != snapshot_id:
            raise AuthFailure("report_snapshot_conflict", 409)
        known = {row.observation.series_id for row in snapshot.revisions}
        selected = known if data.series_ids is None else set(data.series_ids)
        if not selected <= known:
            raise AuthFailure("report_series_not_supported", 422)
        observations = tuple(HistoryRow(**row.model_dump(), is_latest=snapshot.latest[row.observation_identity] == row) for row in snapshot.revisions if row.observation.series_id in selected)
        if len(observations) > 2000:
            raise AuthFailure("report_too_large", 413)
        now = int(self.auth.clock())
        with self.auth.transaction() as connection:
            row = self.workspace.owned(connection, user_id, str(data.review_id))
            if row["revision"] != data.expected_revision:
                raise AuthFailure("review_revision_conflict", 409)
            events = connection.execute("SELECT status, revision, occurred_at FROM local_review_events WHERE user_id=? AND review_id=? ORDER BY revision", (user_id, str(data.review_id))).fetchall()
            report = SavedReport(report_id=uuid4(), created_at=now, data_snapshot_id=snapshot_id, review=ReviewReport(review=self.workspace.view(row), events=tuple(ReviewEvent(**dict(event)) for event in events)), observations=observations)
            payload = report.model_dump_json()
            connection.execute("INSERT INTO local_saved_reports VALUES (?, ?, ?, ?, ?, ?, ?)", (str(report.report_id), user_id, str(data.review_id), snapshot_id, payload, hashlib.sha256(payload.encode()).hexdigest(), now))
        return report

    @staticmethod
    def decode(row):
        try:
            if type(row["payload_json"]) is not str or hashlib.sha256(row["payload_json"].encode()).hexdigest() != row["payload_sha256"]:
                raise ValueError("Report payload hash mismatch")
            report = SavedReport.model_validate_json(row["payload_json"])
            if str(report.report_id) != row["report_id"] or report.created_at != row["created_at"] or report.data_snapshot_id != row["data_snapshot_id"] or report.review.review.review_id != row["review_id"]:
                raise ValueError("Report metadata mismatch")
            if report.review.review.data_snapshot_id not in (None, report.data_snapshot_id):
                raise ValueError("Warning and report snapshots differ")
            return report
        except (ValidationError, ValueError, TypeError, KeyError, IndexError) as error:
            raise StoreUnavailableError("Saved report unavailable") from error

    def get(self, user_id, report_id):
        with closing(connect(self.auth.path, readonly=True)) as connection:
            row = connection.execute("SELECT * FROM local_saved_reports WHERE user_id=? AND report_id=?", (user_id, str(report_id))).fetchone()
        if row is None:
            raise AuthFailure("report_not_found", 404)
        return self.decode(row)

    def list(self, user_id, limit, offset):
        with closing(connect(self.auth.path, readonly=True)) as connection:
            rows = connection.execute("SELECT * FROM local_saved_reports WHERE user_id=? ORDER BY created_at DESC, report_id DESC LIMIT ? OFFSET ?", (user_id, limit, offset)).fetchall()
        reports = []
        for row in rows:
            report = self.decode(row)
            reports.append(ReportSummary(report_id=report.report_id, review_id=report.review.review.review_id, review_revision=report.review.review.revision, created_at=report.created_at, data_snapshot_id=report.data_snapshot_id, observation_count=len(report.observations)))
        return SavedReportList(reports=tuple(reports), limit=limit, offset=offset)
