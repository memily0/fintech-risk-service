"""Local read API for shared synthetic scenarios, never a live-risk endpoint."""

from contextlib import asynccontextmanager
import sqlite3
from typing import Callable

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import __version__
from .auth import AuthFailure, AuthService
from .auth_api import router as auth_router
from .workspace_api import router as workspace_router
from .web import router as web_router
from .market import MarketStore
from .market_api import router as market_router
from .model_api import router as model_router
from .database import SchemaError
from .schemas import CapabilitiesResponse, HealthResponse, ScenarioListResponse, ScenarioResponse
from .settings import Settings
from .store import FixtureStore, ScenarioStore, SQLiteScenarioStore, StoreUnavailableError


def get_store(request: Request) -> ScenarioStore:
    store = getattr(request.app.state, "scenario_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail={"code": "fixture_store_unavailable", "synthetic": True})
    return store


def create_app(settings: Settings | None = None, store_factory: Callable[[], ScenarioStore] | None = None) -> FastAPI:
    config = Settings.from_env() if settings is None else settings
    if store_factory is not None:
        factory = store_factory
    elif config.storage_backend == "sqlite":
        factory = lambda: SQLiteScenarioStore.open(config.database_path)
    else:
        factory = FixtureStore.from_file

    @asynccontextmanager
    async def lifespan(app):
        app.state.scenario_store = factory()
        app.state.auth_service = AuthService(config.database_path) if config.storage_backend == "sqlite" and store_factory is None else None
        app.state.market_store = MarketStore.open(config.database_path if app.state.auth_service is not None else None)
        try:
            yield
        finally:
            del app.state.scenario_store
            del app.state.auth_service
            del app.state.market_store

    app = FastAPI(
        title="ArcShift V1 Local Fixture API",
        version=__version__,
        description="Synthetic market fixtures and local .test accounts only; no accepted model, real email or production access.",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])
    app.include_router(auth_router)
    app.include_router(workspace_router)
    app.include_router(web_router)
    app.include_router(market_router)
    app.include_router(model_router)

    @app.exception_handler(AuthFailure)
    async def authentication_failure(request, exc):
        headers = {"Retry-After": "60"} if exc.status == 429 else None
        return JSONResponse(status_code=exc.status, content={"detail": {"code": exc.code, "synthetic": True}}, headers=headers)

    @app.exception_handler(sqlite3.Error)
    @app.exception_handler(SchemaError)
    async def unavailable_auth_storage(request, exc):
        return JSONResponse(status_code=503, content={"detail": {"code": "local_storage_unavailable", "synthetic": True}})

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, exc):
        return JSONResponse(status_code=422, content={"detail": {"code": "invalid_request", "synthetic": True}})

    @app.exception_handler(StoreUnavailableError)
    async def unavailable_store(request, exc):
        return JSONResponse(status_code=503, content={"detail": {"code": "fixture_store_unavailable", "synthetic": True}})

    @app.middleware("http")
    async def label_fixture_responses(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-ArcShift-Data-Mode"] = "synthetic"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; font-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.get("/healthz", response_model=HealthResponse)
    async def health():
        return HealthResponse(environment=config.environment)

    @app.get("/readyz", response_model=HealthResponse)
    async def ready(store: ScenarioStore = Depends(get_store)):
        store.check_ready()
        if app.state.auth_service is not None:
            app.state.auth_service.check_ready()
        app.state.market_store.check_ready()
        return HealthResponse(environment=config.environment)

    @app.get("/api/v1/capabilities", response_model=CapabilitiesResponse)
    async def capabilities():
        return CapabilitiesResponse()

    @app.get("/api/v1/demo/scenarios", response_model=ScenarioListResponse)
    async def scenarios(store: ScenarioStore = Depends(get_store)):
        return ScenarioListResponse(scenarios=store.list_scenarios())

    @app.get("/api/v1/demo/scenarios/{scenario_id}", response_model=ScenarioResponse)
    async def scenario(scenario_id: str, store: ScenarioStore = Depends(get_store)):
        try:
            row = store.get_scenario(scenario_id)
        except KeyError:
            raise HTTPException(status_code=404, detail={"code": "scenario_not_found", "synthetic": True}) from None
        return ScenarioResponse(scenario=row)

    return app
