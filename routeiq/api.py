import os
from contextlib import asynccontextmanager
from dataclasses import asdict

from pydantic import BaseModel, Field

from routeiq.cascade import route
from routeiq.config import ROOT, load_config
from routeiq.models.registry import build_tiers
from fastapi import FastAPI, HTTPException, Query
from routeiq.store import Store

class RouteRequest(BaseModel):
    text: str = Field(min_length=1, max_length=5000)

class ReviewDecision(BaseModel):
    label: str 


def create_app(tiers=None, labels=None, db_path=None):
    @asynccontextmanager
    async def lifespan(app):
        if tiers is None:
            config = load_config(os.getenv("ROUTEIQ_CONFIG", str(ROOT / "configs" / "clinc150.yaml")))
            app.state.tiers = build_tiers(config)
            app.state.labels = config["labels"]
        else:
            app.state.tiers = tiers
            app.state.labels = labels
        app.state.store = Store(db_path or os.getenv("ROUTEIQ_DB", str(ROOT / "routeiq.db")))
        yield

    app = FastAPI(title="RouteIQ", lifespan=lifespan)

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/route")
    def route_request(req: RouteRequest):
        result = route(req.text, app.state.labels, app.state.tiers)
        payload = asdict(result)
        payload["degraded"] = payload.pop("error") is not None
        payload["request_id"] = app.state.store.log(req.text, result)
        return payload
    
    @app.get("/review")
    def list_review(limit: int = Query(50, ge=1, le=100)):
        return app.state.store.pending(limit)
    
    @app.post("/review/{request_id}")
    def resolve_review(request_id: int, decision: ReviewDecision):
        if decision.label not in app.state.labels:
            raise HTTPException(status_code=422, detail="unknown label")
        if not app.state.store.resolve(request_id, decision.label):
            if app.state.store.get(request_id) is None:
                raise HTTPException(status_code=404, detail="request not found")
            raise HTTPException(status_code=409, detail="request is not pending review")
        return {"id": request_id, "status": "resolved", "final_label": decision.label}

    return app


app = create_app()