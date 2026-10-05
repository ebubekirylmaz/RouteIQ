import os
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query

from routeiq.cascade import route
from routeiq.config import ROOT, load_config
from routeiq.delivery import deliver
from routeiq.integrations import build_target
from routeiq.integrations import mock_erp as mock_erp_module
from routeiq.models.registry import build_tiers
from routeiq.schemas import (
    ErrorResponse, HealthResponse, ReviewDecision, ReviewItem, ReviewResolved,
    RetryResult, RouteRequest, RouteResponse, StatsResponse, ConfigResponse
)
from routeiq.store import Store
from routeiq.views import describe_config

def create_app(tiers=None, labels=None, db_path=None, mock_erp=False, target=None):
    config = None
    if tiers is None:
        config = load_config(os.getenv("ROUTEIQ_CONFIG", str(ROOT / "configs" / "clinc150.yaml")))
        mock_erp = mock_erp or (config.get("target") or {}).get("type") == "mock_erp"

    @asynccontextmanager
    async def lifespan(app):
        if config is not None:
            app.state.tiers = build_tiers(config)
            app.state.labels = config["labels"]
            app.state.target = build_target(config)
            app.state.config_view = describe_config(config=config)
        else:
            app.state.tiers = tiers
            app.state.labels = labels
            app.state.target = target
            app.state.config_view = describe_config(labels=labels, tiers=tiers)
        app.state.store = Store(db_path or os.getenv("ROUTEIQ_DB", str(ROOT / "routeiq.db")))
        yield

    app = FastAPI(
        title="RouteIQ",
        lifespan=lifespan,
        # operationId = function name, so generated TypeScript clients get clean names
        generate_unique_id_function=lambda route: route.name,
    )
    if mock_erp:
        app.state.erp = mock_erp_module.MockErpStore()
        app.include_router(mock_erp_module.router)

    @app.get("/health", response_model=HealthResponse)
    def health():
        return {"status": "ok"}
    
    @app.get("/config", response_model=ConfigResponse)
    def get_config():
        return app.state.config_view

    @app.post("/route", response_model=RouteResponse)
    def route_request(req: RouteRequest, background: BackgroundTasks):
        result = route(req.text, app.state.labels, app.state.tiers)
        payload = asdict(result)
        payload["degraded"] = payload.pop("error") is not None
        request_id = app.state.store.log(req.text, result)
        payload["request_id"] = request_id
        if result.action == "accepted" and app.state.target is not None:
            app.state.store.mark_delivery(request_id, "pending")
            background.add_task(deliver, app.state.store, app.state.target, request_id)
        return payload

    @app.get("/review", response_model=list[ReviewItem])
    def list_review(limit: int = Query(50, ge=1, le=100)):
        return app.state.store.pending(limit)

    @app.post(
        "/review/{request_id}",
        response_model=ReviewResolved,
        responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    )
    def resolve_review(request_id: int, decision: ReviewDecision, background: BackgroundTasks):
        if decision.label not in app.state.labels:
            raise HTTPException(status_code=422, detail="unknown label")
        if not app.state.store.resolve(request_id, decision.label):
            if app.state.store.get(request_id) is None:
                raise HTTPException(status_code=404, detail="request not found")
            raise HTTPException(status_code=409, detail="request is not pending review")
        if app.state.target is not None:
            app.state.store.mark_delivery(request_id, "pending")
            background.add_task(deliver, app.state.store, app.state.target, request_id)
        return {"id": request_id, "status": "resolved", "final_label": decision.label}

    @app.post(
        "/deliveries/retry",
        response_model=RetryResult,
        responses={409: {"model": ErrorResponse}},
    )
    def retry_deliveries(limit: int = Query(100, ge=1, le=500)):
        if app.state.target is None:
            raise HTTPException(status_code=409, detail="no delivery target configured")
        ids = app.state.store.retryable_deliveries(limit)
        for request_id in ids:
            deliver(app.state.store, app.state.target, request_id)
        statuses = [app.state.store.get(i)["delivery_status"] for i in ids]
        return {"retried": len(ids), "sent": statuses.count("sent"), "failed": statuses.count("failed")}

    @app.get("/stats", response_model=StatsResponse)
    def stats():
        return app.state.store.stats()

    return app


app = create_app()