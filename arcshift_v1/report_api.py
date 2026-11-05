"""Private immutable reports; no public file URL or demo actor identity."""

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from .auth import AuthFailure, SessionIdentity
from .auth_api import peer, service
from .report_rendering import csv_bytes, pdf_bytes
from .saved_reports import CreateSavedReport, SavedReport, SavedReportList, SavedReportService
from .workspace import WorkspaceService
from .workspace_api import current_user, workspace, writing_user


router = APIRouter(prefix="/api/v1/workspace/reports", tags=["private-saved-reports"])


def reports(request: Request, work: WorkspaceService = Depends(workspace)):
    return SavedReportService(work, request.app.state.market_store)


@router.post("", status_code=201, response_model=SavedReport)
def create(data: CreateSavedReport, user: SessionIdentity = Depends(writing_user), store: SavedReportService = Depends(reports)):
    return store.create(user.user_id, data)


@router.get("", response_model=SavedReportList)
def listing(limit: Annotated[int, Query(ge=1, le=100)] = 50, offset: Annotated[int, Query(ge=0)] = 0, user: SessionIdentity = Depends(current_user), store: SavedReportService = Depends(reports)):
    return store.list(user.user_id, limit, offset)


@router.get("/{report_id}", response_model=SavedReport)
def detail(report_id: UUID, user: SessionIdentity = Depends(current_user), store: SavedReportService = Depends(reports)):
    return store.get(user.user_id, report_id)


@router.get("/{report_id}/export.{format}")
def export(report_id: UUID, format: Literal["json", "csv", "pdf"], request: Request, user: SessionIdentity = Depends(current_user), store: SavedReportService = Depends(reports)):
    report = store.get(user.user_id, report_id)
    service(request).limit_export(user, peer(request))
    try:
        payload = report.model_dump_json() if format == "json" else csv_bytes(report) if format == "csv" else pdf_bytes(report)
    except (OSError, ValueError):
        raise AuthFailure("report_render_unavailable", 503) from None
    media_type = {"json": "application/json", "csv": "text/csv; charset=utf-8", "pdf": "application/pdf"}[format]
    return Response(payload, media_type=media_type, headers={"Content-Disposition": f'attachment; filename="arcshift-report-{report_id}.{format}"'})
