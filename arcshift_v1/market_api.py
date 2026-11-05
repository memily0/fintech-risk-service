"""Published synthetic history only; no HTTP download/fit/write endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from .market import HistoryResponse, MarketStore, SeriesList


router = APIRouter(prefix="/api/v1/market", tags=["synthetic-market-history"])


def market(request: Request) -> MarketStore:
    return request.app.state.market_store


@router.get("/series", response_model=SeriesList)
def series(store: MarketStore = Depends(market)):
    return store.series()


@router.get("/series/{series_id}/history", response_model=HistoryResponse)
def history(series_id: str, start: date | None = None, end: date | None = None, include_revisions: bool = False, limit: Annotated[int, Query(ge=1, le=500)] = 100, offset: Annotated[int, Query(ge=0)] = 0, store: MarketStore = Depends(market)):
    if start is not None and end is not None and start > end:
        raise HTTPException(422, detail={"code": "invalid_date_range", "synthetic": True})
    try:
        return store.history(series_id, start, end, include_revisions, limit, offset)
    except KeyError:
        raise HTTPException(404, detail={"code": "series_not_found", "synthetic": True}) from None
