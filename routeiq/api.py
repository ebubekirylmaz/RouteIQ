import os
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Literal
from pathlib import Path
from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Response

from fastapi.responses import RedirectResponse
from routeiq.dashboard import SPAFiles, dashboard_dir, is_built
from routeiq.cascade import route
from routeiq.config import ROOT, load_config
from routeiq.delivery import deliver
from routeiq.integrations import build_target
from routeiq.integrations import mock_erp as mock_erp_module
from routeiq.models.registry import build_tiers
from routeiq.schemas import (
    ConfigResponse, ErrorResponse, EvaluationResponse, HealthResponse, RequestItem, ReviewDecision,
    ReviewItem, ReviewResolved, RetryResult, RouteRequest, RouteResponse, StatsResponse,
    TimeseriesResponse,
)
from routeiq.store import Store
from routeiq.timeutil import BUCKET_STEPS, as_utc, floor_to_bucket
from routeiq.views import describe_config, request_item

MAX_BUCKETS = 1000
DEFAULT_WINDOWS = {"hour": timedelta(hours=24), "day": timedelta(days=30)}


def create_app(tiers=None, labels=None, db_path=None, mock_erp=False, target=None, dashboard=None):
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
            app.state.config = config
            app.state.config_view = describe_config(config=config)
        else:
            app.state.tiers = tiers
            app.state.labels = labels
            app.state.target = target
            app.state.config = None
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
    directory = Path(dashboard) if dashboard is not None else dashboard_dir()
    if is_built(directory):
        app.mount("/dashboard", SPAFiles(directory=directory, html=True), name="dashboard")

        @app.get("/", include_in_schema=False)
        def home():
            return RedirectResponse("/dashboard/")


    @app.get("/health", response_model=HealthResponse)
    def health():
        return {"status": "ok"}
    
    @app.get("/config", response_model=ConfigResponse)
    def get_config():
        return app.state.config_view

    @app.get(
        "/evaluation",
        response_model=EvaluationResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_evaluation():
        """Accuracy, cost and calibration measured offline on labeled examples, not on live traffic."""
        # pandas and scikit-learn are only needed here, so the service starts without loading them.
        from routeiq import evaluation

        if app.state.config is None:
            raise HTTPException(status_code=404, detail="no evaluation is available for this configuration")
        try:
            return evaluation.build_report(app.state.config)
        except evaluation.EvaluationUnavailable as error:
            raise HTTPException(status_code=404, detail=str(error))

    @app.get(
        "/requests",
        response_model=list[RequestItem],
        responses={200: {"headers": {"X-Total-Count": {
            "description": "Number of requests matching the filters, ignoring limit and offset",
            "schema": {"type": "integer"},
        }}}},
    )
    def list_requests(
        response: Response,
        action: Literal["accepted", "human_review"] | None = None,
        tier: str | None = Query(None, max_length=50),
        review_status: Literal["pending", "resolved"] | None = None,
        delivery_status: Literal["pending", "sent", "failed"] | None = None,
        degraded: bool | None = None,
        q: str | None = Query(None, max_length=200),
        limit: int = Query(50, ge=1, le=200),
        offset: int = Query(0, ge=0),
        order: Literal["newest", "oldest"] = "newest",
    ):
        rows, total = app.state.store.list_requests(
            action=action, tier=tier, review_status=review_status,
            delivery_status=delivery_status, degraded=degraded, q=q,
            limit=limit, offset=offset, newest_first=(order == "newest"),
        )
        response.headers["X-Total-Count"] = str(total)
        return [request_item(row) for row in rows]

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

    @app.get("/review", response_model=list[ReviewItem], responses={200: {"headers": {"X-Total-Count": {
        "description": "Number of requests pending review, ignoring limit",
        "schema": {"type": "integer"},
    }}}})
    def list_review(response: Response, limit: int = Query(50, ge=1, le=100), offset: int = Query(0, ge=0)):
        response.headers["X-Total-Count"] = str(app.state.store.pending_count())
        return app.state.store.pending(limit, offset)

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
    def stats(since: datetime | None = None):
        return app.state.store.stats(since)
    
    @app.get("/stats/timeseries", response_model=TimeseriesResponse)
    def timeseries(
        bucket: Literal["hour", "day"] = "hour",
        since: datetime | None = None,
        until: datetime | None = None,
    ):
        until = as_utc(until) if until else datetime.now(timezone.utc)
        since = as_utc(since) if since else until - DEFAULT_WINDOWS[bucket]
        if since >= until:
            raise HTTPException(status_code=422, detail="since must be earlier than until")
        if (until - floor_to_bucket(since, bucket)) / BUCKET_STEPS[bucket] > MAX_BUCKETS:
            raise HTTPException(
                status_code=422, detail=f"the range covers more than {MAX_BUCKETS} buckets"
            )
        points = app.state.store.timeseries(bucket, since, until)
        return {"bucket": bucket, "since": since, "until": until, "points": points}

    return app


app = create_app()