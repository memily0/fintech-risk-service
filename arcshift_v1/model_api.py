"""Read-only model status; query parameters cannot select an artifact to load."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from .market import MarketStore
from .market_api import market
from .model_status import CurrentSignal, ModelStatus, TASK, current_signal, model_status


router = APIRouter(tags=["model-readiness"])


@router.get("/api/v1/models/status", response_model=ModelStatus)
def status(store: MarketStore = Depends(market)):
    return model_status(store)


@router.get("/api/v1/signals/current", response_model=CurrentSignal)
def signal(geography: Annotated[str, Query(min_length=2, max_length=2)] = "RU", horizon_days: Annotated[int, Query(ge=1, le=3650)] = 30, task_id: Annotated[str, Query(min_length=1, max_length=128)] = TASK, store: MarketStore = Depends(market)):
    return current_signal(store, geography=geography, horizon_days=horizon_days, task_id=task_id)
