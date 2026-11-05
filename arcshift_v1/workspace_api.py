"""Every private read is owner scoped; every write requires session-bound CSRF."""

import csv
from io import StringIO
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response

from .auth import SESSION_COOKIE, SessionIdentity
from .auth_api import peer, same_origin, service
from .workspace import CreateReview, ReviewList, ReviewReport, ReviewView, UpdateReview, WatchlistRequest, WatchlistView, WorkspaceService


router = APIRouter(prefix="/api/v1/workspace", tags=["local-private-workspace"])


def current_user(request: Request) -> SessionIdentity:
    return service(request).authenticate(request.cookies.get(SESSION_COOKIE))


def writing_user(request: Request) -> SessionIdentity:
    same_origin(request)
    auth = service(request)
    identity = auth.require_csrf(request.cookies.get(SESSION_COOKIE), request.headers.get("x-csrf-token"))
    auth.limit_write(identity, peer(request))
    return identity


def workspace(request: Request) -> WorkspaceService:
    return WorkspaceService(service(request), request.app.state.scenario_store)


@router.get("/watchlist", response_model=WatchlistView)
def watchlist(user: SessionIdentity = Depends(current_user), work: WorkspaceService = Depends(workspace)):
    return work.watchlist(user.user_id)


@router.put("/watchlist", response_model=WatchlistView)
def save_watchlist(data: WatchlistRequest, user: SessionIdentity = Depends(writing_user), work: WorkspaceService = Depends(workspace)):
    return work.save_watchlist(user.user_id, data)


@router.get("/reviews", response_model=ReviewList)
def reviews(limit: Annotated[int, Query(ge=1, le=100)] = 50, offset: Annotated[int, Query(ge=0)] = 0, user: SessionIdentity = Depends(current_user), work: WorkspaceService = Depends(workspace)):
    return work.list_reviews(user.user_id, limit, offset)


@router.post("/reviews", status_code=201, response_model=ReviewView)
def create_review(data: CreateReview, user: SessionIdentity = Depends(writing_user), work: WorkspaceService = Depends(workspace)):
    return work.create_review(user.user_id, data)


@router.get("/reviews/{review_id}", response_model=ReviewView)
def review(review_id: UUID, user: SessionIdentity = Depends(current_user), work: WorkspaceService = Depends(workspace)):
    return work.report(user.user_id, str(review_id)).review


@router.patch("/reviews/{review_id}", response_model=ReviewView)
def update_review(review_id: UUID, data: UpdateReview, user: SessionIdentity = Depends(writing_user), work: WorkspaceService = Depends(workspace)):
    return work.update_review(user.user_id, str(review_id), data)


@router.get("/reviews/{review_id}/report.json", response_model=ReviewReport)
def report_json(review_id: UUID, user: SessionIdentity = Depends(current_user), work: WorkspaceService = Depends(workspace)):
    return work.report(user.user_id, str(review_id))


def safe_csv(value):
    text = str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) or text.startswith(("\t", "\r", "\n")) else text


@router.get("/reviews/{review_id}/report.csv")
def report_csv(review_id: UUID, user: SessionIdentity = Depends(current_user), work: WorkspaceService = Depends(workspace)):
    report = work.report(user.user_id, str(review_id))
    review = report.review
    output = StringIO(newline="")
    writer = csv.writer(output)
    writer.writerow(("review_id", "snapshot_id", "scenario_id", "status", "revision", "note", "synthetic", "production_ready", "source_rights_status"))
    writer.writerow([safe_csv(value) for value in (review.review_id, review.snapshot_id, review.scenario.id, review.status, review.revision, review.note, "true", "false", "not_admitted")])
    return Response("\ufeff" + output.getvalue(), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": f'attachment; filename="arcshift-review-{review_id}.csv"'})
