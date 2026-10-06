import threading
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query, Request, Response
from pydantic import BaseModel, Field


class TicketIn(BaseModel):
    ExternalID: str
    Category: str
    Description: str = Field(max_length=5000)
    Confidence: float | None = None
    Source: str


class MockErpStore:
    def __init__(self):
        self._lock = threading.Lock()
        self._tickets = []
        self._by_external = {}

    def create(self, data):
        """(ticket, created) döndürür. Aynı ExternalID varsa mevcut kaydı verir."""
        with self._lock:
            existing = self._by_external.get(data["ExternalID"])
            if existing is not None:
                return existing, False
            ticket = {
                "TicketID": len(self._tickets) + 1,
                **data,
                "Status": "Open",
                "CreatedAt": datetime.now(timezone.utc).isoformat(),
            }
            self._tickets.append(ticket)
            self._by_external[data["ExternalID"]] = ticket
            return ticket, True

    def clear(self):
        """Forgets every ticket. The public demo does this when it resets."""
        with self._lock:
            self._tickets.clear()
            self._by_external.clear()

    def list(self, top, skip):
        with self._lock:
            return list(self._tickets[skip:skip + top]), len(self._tickets)

    def get(self, ticket_id):
        with self._lock:
            if 1 <= ticket_id <= len(self._tickets):
                return self._tickets[ticket_id - 1]
            return None


router = APIRouter(prefix="/mock-erp/api")


@router.post("/tickets", status_code=201)
def create_ticket(body: TicketIn, request: Request, response: Response):
    ticket, created = request.app.state.erp.create(body.model_dump())
    if not created:
        response.status_code = 200
    return ticket


@router.get("/tickets")
def list_tickets(
    request: Request,
    top: int = Query(50, ge=1, le=200, alias="$top"),
    skip: int = Query(0, ge=0, alias="$skip"),
):
    items, total = request.app.state.erp.list(top, skip)
    return {
        "@odata.context": "/mock-erp/api/$metadata#tickets",
        "@odata.count": total,
        "value": items,
    }


@router.get("/tickets/{ticket_id}")
def get_ticket(ticket_id: int, request: Request):
    ticket = request.app.state.erp.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return ticket