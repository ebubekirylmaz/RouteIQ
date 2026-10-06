"""Public-demo mode (ROUTEIQ_DEMO=1).

The service has no authentication. On the open internet that means anybody could spend the owner's
model credit through POST /route, read every stored text and decide reviews. Demo mode is what makes
it reasonable to publish a demo anyway:

- It never touches the real database: it uses a temporary one of its own (ROUTEIQ_DEMO_DB).
- On start, and then every ROUTEIQ_DEMO_RESET_HOURS hours, it deletes everything and refills the
  database with real recorded decisions (routeiq/replay.py), so what visitors typed does not stay.
- It limits how fast texts can be sent per address, and how many in total per day. The total caps
  what the demo can spend, whatever an attacker does about addresses.
- It limits the length of a text and the size of a request.

It is not authentication, and it does not make the service fit for real data.
"""
import asyncio
import logging
import math
import os
import sqlite3
import tempfile
import time
from collections import deque
from contextlib import closing, suppress
from dataclasses import dataclass
from pathlib import Path

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

TRUE_VALUES = {"1", "true", "yes", "on"}
MAX_TEXT_LENGTH = 5000      # what the API itself accepts
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


class DemoConfigError(ValueError):
    """The settings of the demo are wrong. The message lists every problem."""


@dataclass(frozen=True)
class DemoSettings:
    routes_per_minute: int = 10      # POST /route, for one address
    routes_per_day: int = 500        # POST /route, for everybody together
    writes_per_minute: int = 30      # every other POST, for one address
    max_text: int = 500              # characters in a text
    max_body: int = 8192             # bytes in a request
    reset_hours: float = 24.0
    db_path: str = ""


# field -> (environment variable, type)
ENVIRONMENT = {
    "routes_per_minute": ("ROUTEIQ_DEMO_ROUTES_PER_MINUTE", int),
    "routes_per_day": ("ROUTEIQ_DEMO_ROUTES_PER_DAY", int),
    "writes_per_minute": ("ROUTEIQ_DEMO_WRITES_PER_MINUTE", int),
    "max_text": ("ROUTEIQ_DEMO_MAX_TEXT", int),
    "reset_hours": ("ROUTEIQ_DEMO_RESET_HOURS", float),
}


def settings_from_env(environ=None):
    """The settings of the demo, or None when ROUTEIQ_DEMO is not switched on."""
    environ = os.environ if environ is None else environ
    if environ.get("ROUTEIQ_DEMO", "").strip().lower() not in TRUE_VALUES:
        return None

    defaults = DemoSettings()
    values, errors = {}, []
    for field, (name, kind) in ENVIRONMENT.items():
        raw = environ.get(name)
        if raw is None or raw.strip() == "":
            values[field] = getattr(defaults, field)
            continue
        try:
            value = kind(raw)
        except ValueError:
            errors.append(f"{name} must be a number, not '{raw}'")
            continue
        if not math.isfinite(value) or value <= 0:
            errors.append(f"{name} must be above 0")
            continue
        values[field] = value
    if values.get("max_text", 0) > MAX_TEXT_LENGTH:
        errors.append(f"ROUTEIQ_DEMO_MAX_TEXT must be at most {MAX_TEXT_LENGTH}")
    if errors:
        raise DemoConfigError("invalid demo settings:\n" + "\n".join(f"  - {e}" for e in errors))

    db_path = environ.get("ROUTEIQ_DEMO_DB") or str(Path(tempfile.gettempdir()) / "routeiq-demo.db")
    return DemoSettings(**values, db_path=db_path)


class SlidingWindow:
    """At most `limit` hits in any `window` seconds, counted separately for every key."""

    MAX_KEYS = 10_000

    def __init__(self, limit, window, clock=time.monotonic):
        self.limit, self.window, self._clock = limit, window, clock
        self._hits = {}

    def retry_after(self, key=""):
        """0 when another hit is allowed now, otherwise the seconds until it will be."""
        hits = self._hits.get(key)
        if not hits:
            return 0.0
        now = self._clock()
        self._expire(hits, now)
        if len(hits) < self.limit:
            return 0.0
        return max(0.0, hits[0] + self.window - now)

    def record(self, key=""):
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        self._expire(hits, now)
        hits.append(now)
        if len(self._hits) > self.MAX_KEYS:
            self._forget_idle(now)

    def clear(self):
        self._hits.clear()

    def _expire(self, hits, now):
        while hits and hits[0] <= now - self.window:
            hits.popleft()

    def _forget_idle(self, now):
        for key in [k for k, hits in self._hits.items() if not hits or hits[-1] <= now - self.window]:
            del self._hits[key]


def client_key(request):
    """Who is asking. Behind a proxy every request comes from the proxy, so the address it saw is
    used: the last entry of X-Forwarded-For, which the nearest proxy adds. The first entries can be
    written by the client, so they are not trusted."""
    forwarded = request.headers.get("x-forwarded-for", "")
    last = forwarded.split(",")[-1].strip() if forwarded else ""
    if last:
        return last
    return request.client.host if request.client else "unknown"


def _refusal(status, detail, wait=0.0):
    headers = {"Retry-After": str(max(1, math.ceil(wait)))} if wait else None
    return JSONResponse({"detail": detail}, status_code=status, headers=headers)


class DemoGuard:
    """HTTP middleware: refuses a POST that is too big, too fast or too many."""

    def __init__(self, settings, clock=time.monotonic):
        self.settings = settings
        self.route_minute = SlidingWindow(settings.routes_per_minute, 60, clock)
        self.route_day = SlidingWindow(settings.routes_per_day, 86_400, clock)
        self.writes_minute = SlidingWindow(settings.writes_per_minute, 60, clock)

    def reset(self):
        for window in (self.route_minute, self.route_day, self.writes_minute):
            window.clear()

    async def __call__(self, request, call_next):
        if request.method == "POST":
            refusal = self._check(request)
            if refusal is not None:
                return refusal
        return await call_next(request)

    def _check(self, request):
        # The service posts to itself (deliveries to the built-in mock ERP). That traffic comes from
        # the machine, without a proxy header, and is not the visitors' to be limited.
        internal = (request.client is not None and request.client.host in LOOPBACK
                    and "x-forwarded-for" not in request.headers)
        if internal:
            return None

        length = request.headers.get("content-length")
        if length is None:
            return _refusal(411, "the request must say how long it is")
        if not length.isdigit() or int(length) > self.settings.max_body:
            return _refusal(413, "the request is larger than this demo accepts")

        key = client_key(request)
        if request.url.path == "/route":
            wait_day = self.route_day.retry_after()
            if wait_day:
                return _refusal(429, "the demo has reached its daily limit of texts; it starts again after the next reset", wait_day)
            wait_minute = self.route_minute.retry_after(key)
            if wait_minute:
                return _refusal(429, "too many texts from your address; wait a moment and try again", wait_minute)
            self.route_minute.record(key)
            self.route_day.record()
        else:
            wait = self.writes_minute.retry_after(key)
            if wait:
                return _refusal(429, "too many requests from your address; wait a moment and try again", wait)
            self.writes_minute.record(key)
        return None


def reset_database(app):
    """Deletes everything the visitors made and fills the database with the recorded decisions again."""
    # The recorded predictions are found the same way the Evaluation screen finds them.
    from routeiq.evaluation import predictions_path
    from routeiq.replay import ReplayError, replay

    config, db_path = app.state.config, app.state.db_path
    path = predictions_path(config["domain"])
    if not path.exists():
        raise ReplayError(f"demo mode needs recorded predictions for the domain '{config['domain']}'")

    with closing(sqlite3.connect(db_path, isolation_level=None)) as conn:
        conn.execute("DELETE FROM requests")
        with suppress(sqlite3.OperationalError):          # there is no counter table before the first insert
            conn.execute("DELETE FROM sqlite_sequence WHERE name = 'requests'")
    replay(db_path, path, config)

    erp = getattr(app.state, "erp", None)
    if erp is not None:
        erp.clear()
    guard = getattr(app.state, "demo_guard", None)
    if guard is not None:
        guard.reset()


async def run_resets(interval_seconds, reset):
    """Calls `reset` every `interval_seconds` until cancelled. A failed reset is logged, not fatal."""
    while True:
        await asyncio.sleep(interval_seconds)
        try:
            await asyncio.to_thread(reset)
        except Exception:                                   # keep the loop alive: the next reset may work
            logger.exception("the daily reset of the demo failed")
