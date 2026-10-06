import asyncio
import sqlite3
from contextlib import closing

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fakes import Fake
from routeiq import demo as demo_module
from routeiq import evaluation
from routeiq.api import create_app
from routeiq.demo import DemoConfigError, DemoGuard, DemoSettings, SlidingWindow, client_key, settings_from_env
from routeiq.integrations.mock_erp import MockErpStore
from routeiq.replay import ReplayError
from routeiq.store import Store

TIERS = """tiers:
  - name: baseline
    model: sklearn_tfidf_logreg
    accept_threshold: 0.7
  - name: llm
    model: openrouter
    model_id: v/m
    price_in_per_m: 0.1
    price_out_per_m: 0.3
    accept_threshold: 0.9
"""


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


# --- the settings --------------------------------------------------------------------------------

@pytest.mark.parametrize("value", [None, "", "0", "false", "no", "off", "maybe"])
def test_the_demo_is_off_unless_it_is_switched_on(value):
    environ = {} if value is None else {"ROUTEIQ_DEMO": value}
    assert settings_from_env(environ) is None


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " Yes ", "on"])
def test_the_demo_is_switched_on_by_any_of_the_usual_words(value):
    assert settings_from_env({"ROUTEIQ_DEMO": value}) is not None


def test_the_defaults_are_modest(tmp_path):
    settings = settings_from_env({"ROUTEIQ_DEMO": "1"})
    assert (settings.routes_per_minute, settings.routes_per_day, settings.writes_per_minute) == (10, 500, 30)
    assert (settings.max_text, settings.max_body, settings.reset_hours) == (500, 8192, 24.0)


def test_every_setting_can_be_changed_from_the_environment():
    settings = settings_from_env({
        "ROUTEIQ_DEMO": "1", "ROUTEIQ_DEMO_ROUTES_PER_MINUTE": "3", "ROUTEIQ_DEMO_ROUTES_PER_DAY": "40",
        "ROUTEIQ_DEMO_WRITES_PER_MINUTE": "7", "ROUTEIQ_DEMO_MAX_TEXT": "200", "ROUTEIQ_DEMO_RESET_HOURS": "0.5",
        "ROUTEIQ_DEMO_DB": "/somewhere/demo.db",
    })
    assert (settings.routes_per_minute, settings.routes_per_day, settings.writes_per_minute) == (3, 40, 7)
    assert (settings.max_text, settings.reset_hours, settings.db_path) == (200, 0.5, "/somewhere/demo.db")


def test_the_demo_has_a_database_of_its_own_in_the_temporary_folder():
    path = settings_from_env({"ROUTEIQ_DEMO": "1"}).db_path
    assert path.endswith("routeiq-demo.db")


@pytest.mark.parametrize(
    "name, value, message",
    [
        ("ROUTEIQ_DEMO_ROUTES_PER_MINUTE", "many", "must be a number"),
        ("ROUTEIQ_DEMO_ROUTES_PER_DAY", "0", "must be above 0"),
        ("ROUTEIQ_DEMO_WRITES_PER_MINUTE", "-3", "must be above 0"),
        ("ROUTEIQ_DEMO_RESET_HOURS", "nan", "must be above 0"),
        ("ROUTEIQ_DEMO_RESET_HOURS", "inf", "must be above 0"),
        ("ROUTEIQ_DEMO_MAX_TEXT", "5001", "at most 5000"),
        ("ROUTEIQ_DEMO_MAX_TEXT", "1.5", "must be a number"),
    ],
)
def test_wrong_settings_are_refused_with_the_reason(name, value, message):
    with pytest.raises(DemoConfigError, match=message):
        settings_from_env({"ROUTEIQ_DEMO": "1", name: value})


def test_every_wrong_setting_is_reported_at_once():
    with pytest.raises(DemoConfigError) as info:
        settings_from_env({"ROUTEIQ_DEMO": "1", "ROUTEIQ_DEMO_ROUTES_PER_DAY": "x", "ROUTEIQ_DEMO_MAX_TEXT": "0"})
    assert str(info.value).count("\n  - ") == 2


# --- the sliding window --------------------------------------------------------------------------------

def test_a_window_allows_its_limit_and_then_says_how_long_to_wait():
    clock = Clock()
    window = SlidingWindow(3, 60, clock)
    for _ in range(3):
        assert window.retry_after("a") == 0
        window.record("a")
        clock.advance(10)
    assert window.retry_after("a") == pytest.approx(30)       # the first hit leaves the window 30 s from now


def test_a_hit_leaves_the_window_after_the_window_has_passed():
    clock = Clock()
    window = SlidingWindow(1, 60, clock)
    window.record("a")
    assert window.retry_after("a") > 0
    clock.advance(60)
    assert window.retry_after("a") == 0


def test_every_key_has_its_own_count():
    window = SlidingWindow(1, 60, Clock())
    window.record("a")
    assert window.retry_after("a") > 0
    assert window.retry_after("b") == 0


def test_asking_does_not_use_up_the_allowance():
    window = SlidingWindow(1, 60, Clock())
    for _ in range(5):
        assert window.retry_after("a") == 0


def test_clear_forgets_everything():
    window = SlidingWindow(1, 60, Clock())
    window.record("a")
    window.clear()
    assert window.retry_after("a") == 0


def test_keys_that_have_gone_quiet_are_forgotten_so_the_memory_does_not_grow():
    clock = Clock()
    window = SlidingWindow(1, 60, clock)
    window.MAX_KEYS = 5
    for i in range(5):
        window.record(f"old{i}")
    clock.advance(120)
    for i in range(3):
        window.record(f"new{i}")
    assert len(window._hits) <= 5


# --- who is asking ---------------------------------------------------------------------------------------

class FakeRequest:
    def __init__(self, headers=None, host="10.0.0.1"):
        self.headers = headers or {}
        self.client = None if host is None else type("Client", (), {"host": host})()


@pytest.mark.parametrize(
    "headers, host, expected",
    [
        ({"x-forwarded-for": "203.0.113.5"}, "10.0.0.1", "203.0.113.5"),
        ({"x-forwarded-for": "6.6.6.6, 203.0.113.5"}, "10.0.0.1", "203.0.113.5"),     # the client wrote the first one
        ({"x-forwarded-for": "6.6.6.6,   203.0.113.5  "}, "10.0.0.1", "203.0.113.5"),
        ({"x-forwarded-for": ""}, "10.0.0.1", "10.0.0.1"),
        ({"x-forwarded-for": "6.6.6.6, "}, "10.0.0.1", "10.0.0.1"),
        ({}, "10.0.0.1", "10.0.0.1"),
        ({}, None, "unknown"),
    ],
)
def test_the_address_is_the_last_one_a_proxy_saw(headers, host, expected):
    assert client_key(FakeRequest(headers, host)) == expected


# --- the demo inside the service ---------------------------------------------------------------------------

ROWS = (
    [("a", 0.95, "a", 0.99)] * 4 + [("b", 0.4, "a", 0.95)] * 3 + [("b", 0.4, "b", 0.6)] * 3
)


def small_settings(**changes):
    values = dict(routes_per_minute=3, routes_per_day=100, writes_per_minute=2, max_text=50, max_body=300,
                  reset_hours=24.0, db_path="")
    values.update(changes)
    return DemoSettings(**values)


@pytest.fixture
def world(tmp_path, monkeypatch):
    """A config for a tiny domain, ten recorded predictions for it, fake tiers, and a place for the databases."""
    config_file = tmp_path / "cfg.yaml"
    config_file.write_text(f"domain: mini\nlabels: [a, b]\n{TIERS}", encoding="utf-8")
    recorded = tmp_path / "recorded"
    recorded.mkdir()
    pd.DataFrame([
        {
            "text": f"example {i}", "true": "a",
            "baseline_label": bl, "baseline_confidence": bc, "baseline_cost_usd": 0.0, "baseline_latency_ms": 2.0,
            "llm_label": ll, "llm_confidence": lc, "llm_cost_usd": 0.00002, "llm_latency_ms": 900.0,
        }
        for i, (bl, bc, ll, lc) in enumerate(ROWS)
    ]).to_csv(recorded / "mini_test_predictions.csv", index=False)
    monkeypatch.setattr(evaluation, "RECORDED_DIR", recorded)
    monkeypatch.setenv("ROUTEIQ_CONFIG", str(config_file))
    monkeypatch.delenv("ROUTEIQ_DEMO", raising=False)
    tiers = [({"name": "baseline", "accept_threshold": 0.7}, Fake("a", 0.95)), ({"name": "llm", "accept_threshold": 0.9}, Fake("a", 0.99))]
    monkeypatch.setattr("routeiq.api.build_tiers", lambda config: tiers)
    return tmp_path


def make_client(world, settings=None, **kwargs):
    settings = settings if settings is not None else small_settings()
    path = world / "demo.db"
    app = create_app(demo=settings, db_path=path, **kwargs)
    return TestClient(app), app, path


def counts(path):
    return Store(path).list_requests(limit=1)[1]


def route(client, text="hello", headers=None):
    return client.post("/route", json={"text": text}, headers=headers or {})


def from_address(ip):
    return {"X-Forwarded-For": ip}


def test_a_demo_starts_with_the_recorded_decisions_in_its_database(world):
    client, _, path = make_client(world)
    with client:
        assert counts(path) == 10
        rows = Store(path).list_requests(limit=100)[0]
        assert {r["tier"] for r in rows} <= {"baseline", "llm"}


def test_without_the_demo_nothing_is_seeded_and_nothing_is_limited(world):
    app = create_app(demo=False, db_path=world / "plain.db")
    with TestClient(app) as client:
        assert counts(world / "plain.db") == 0
        statuses = {route(client).status_code for _ in range(20)}
    assert statuses == {200}


def test_the_config_says_it_is_a_demo_and_how_long_a_text_may_be(world):
    client, _, _ = make_client(world, small_settings(max_text=50))
    with client:
        body = client.get("/config").json()
    assert (body["demo"], body["max_text_length"]) == (True, 50)


def test_the_config_of_a_normal_service_says_it_is_not_a_demo(world):
    with TestClient(create_app(demo=False, db_path=world / "plain.db")) as client:
        body = client.get("/config").json()
    assert (body["demo"], body["max_text_length"]) == (False, 5000)


def test_the_settings_come_from_the_environment_when_none_are_given(world, monkeypatch):
    monkeypatch.setenv("ROUTEIQ_DEMO", "1")
    monkeypatch.setenv("ROUTEIQ_DEMO_DB", str(world / "from_env.db"))
    monkeypatch.setenv("ROUTEIQ_DEMO_MAX_TEXT", "120")
    with TestClient(create_app()) as client:
        assert client.get("/config").json()["max_text_length"] == 120
    assert counts(world / "from_env.db") == 10


def test_a_demo_never_touches_the_real_database(world, monkeypatch):
    real = world / "real.db"
    store = Store(real)
    from routeiq.cascade import RouteResult
    for i in range(3):
        store.log(f"customer {i}", RouteResult("a", 0.9, "baseline", "accepted", 0.0, 1.0))
    monkeypatch.setenv("ROUTEIQ_DB", str(real))
    monkeypatch.setenv("ROUTEIQ_DEMO", "1")
    monkeypatch.setenv("ROUTEIQ_DEMO_DB", str(world / "demo_only.db"))
    with TestClient(create_app()):
        assert counts(world / "demo_only.db") == 10
    assert counts(real) == 3


def test_a_demo_cannot_run_on_injected_tiers(world):
    with pytest.raises(ValueError, match="needs the configuration file"):
        create_app(tiers=[({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9))], labels=["a"], demo=small_settings())


def test_a_demo_without_recorded_predictions_does_not_start_and_says_why(world, monkeypatch):
    monkeypatch.setattr(evaluation, "RECORDED_DIR", world / "nowhere")
    client, _, _ = make_client(world)
    with pytest.raises(ReplayError, match="recorded predictions for the domain 'mini'"):
        with client:
            pass


# --- the limits on sending texts -----------------------------------------------------------------------------

def test_one_address_can_send_a_few_texts_a_minute_and_then_has_to_wait(world):
    client, _, _ = make_client(world, small_settings(routes_per_minute=3))
    with client:
        me = from_address("203.0.113.5")
        assert [route(client, headers=me).status_code for _ in range(3)] == [200, 200, 200]
        blocked = route(client, headers=me)
    assert blocked.status_code == 429
    assert "wait a moment" in blocked.json()["detail"]
    assert int(blocked.headers["Retry-After"]) >= 1


def test_another_address_has_its_own_allowance(world):
    client, _, _ = make_client(world, small_settings(routes_per_minute=1))
    with client:
        assert route(client, headers=from_address("203.0.113.5")).status_code == 200
        assert route(client, headers=from_address("203.0.113.5")).status_code == 429
        assert route(client, headers=from_address("203.0.113.6")).status_code == 200


def test_a_client_cannot_get_more_by_writing_its_own_forwarding_header(world):
    client, _, _ = make_client(world, small_settings(routes_per_minute=1))
    with client:
        # The proxy adds the real address last; whatever the client wrote before it does not matter.
        assert route(client, headers=from_address("1.1.1.1, 203.0.113.5")).status_code == 200
        assert route(client, headers=from_address("2.2.2.2, 203.0.113.5")).status_code == 429
        assert route(client, headers=from_address("3.3.3.3, 203.0.113.5")).status_code == 429


def test_everybody_together_can_send_only_so_many_a_day(world):
    client, _, _ = make_client(world, small_settings(routes_per_minute=50, routes_per_day=4))
    with client:
        sent = [route(client, headers=from_address(f"203.0.113.{i}")).status_code for i in range(4)]
        refused = route(client, headers=from_address("198.51.100.1"))
    assert sent == [200] * 4
    assert refused.status_code == 429
    assert "daily limit" in refused.json()["detail"]


def test_a_refused_text_does_not_use_up_the_daily_allowance(world):
    client, _, _ = make_client(world, small_settings(routes_per_minute=1, routes_per_day=3))
    with client:
        assert route(client, headers=from_address("203.0.113.1")).status_code == 200
        for _ in range(10):                                     # refused: this address has used its minute
            assert route(client, headers=from_address("203.0.113.1")).status_code == 429
        assert route(client, headers=from_address("203.0.113.2")).status_code == 200
        assert route(client, headers=from_address("203.0.113.3")).status_code == 200
        assert route(client, headers=from_address("203.0.113.4")).status_code == 429       # now the day is used up


def test_reading_is_never_limited(world):
    client, _, _ = make_client(world, small_settings(routes_per_minute=1, routes_per_day=1, writes_per_minute=1))
    with client:
        route(client)
        assert {client.get(path).status_code for path in ["/config", "/stats", "/requests", "/review", "/health"] * 5} == {200}


def test_other_writes_have_their_own_smaller_allowance_that_does_not_touch_the_texts(world):
    client, app, _ = make_client(world, small_settings(writes_per_minute=2, routes_per_minute=5))
    with client:
        me = from_address("203.0.113.5")
        first = client.get("/review").json()
        ids = [item["id"] for item in first]
        assert len(ids) >= 3
        decisions = [client.post(f"/review/{i}", json={"label": "a"}, headers=me).status_code for i in ids[:3]]
        assert decisions == [200, 200, 429]
        assert route(client, headers=me).status_code == 200          # texts are counted apart


def test_a_text_that_is_too_long_for_the_demo_is_refused_and_says_the_limit(world):
    client, _, _ = make_client(world, small_settings(max_text=20, max_body=2000))
    with client:
        ok = route(client, "x" * 20)
        refused = route(client, "x" * 21)
    assert ok.status_code == 200
    assert refused.status_code == 422
    assert "at most 20 characters" in refused.json()["detail"]


def test_a_request_that_is_too_big_is_refused_before_it_is_read(world):
    client, _, _ = make_client(world, small_settings(max_body=300))
    with client:
        big = client.post("/route", content=b'{"text": "' + b"x" * 400 + b'"}', headers={"Content-Type": "application/json"})
    assert big.status_code == 413


def test_a_post_without_a_length_is_refused(world):
    client, _, _ = make_client(world)

    def body():
        yield b'{"text": "hello"}'

    with client:
        response = client.post("/route", content=body(), headers={"Content-Type": "application/json"})
    assert response.status_code == 411


def test_the_service_talking_to_itself_is_not_limited(world):
    client, app, _ = make_client(world, small_settings(routes_per_minute=1, writes_per_minute=1, routes_per_day=1))
    inside = TestClient(app, client=("127.0.0.1", 50000))
    with client, inside:
        assert {route(inside).status_code for _ in range(5)} == {200}


def test_a_proxy_header_on_a_local_connection_means_a_visitor_and_is_limited(world):
    client, app, _ = make_client(world, small_settings(routes_per_minute=1))
    local = TestClient(app, client=("127.0.0.1", 50000))
    with client, local:
        assert route(local, headers=from_address("203.0.113.5")).status_code == 200
        assert route(local, headers=from_address("203.0.113.5")).status_code == 429


# --- the reset ----------------------------------------------------------------------------------------------------

def test_a_reset_forgets_what_visitors_did_and_starts_the_numbers_again(world):
    client, app, path = make_client(world)
    with client:
        route(client, "typed by a visitor")
        route(client, "typed by another visitor")
        assert counts(path) == 12
        demo_module.reset_database(app)
        assert counts(path) == 10
        rows = Store(path).list_requests(limit=100, newest_first=False)[0]
        assert rows[0]["id"] == 1
        assert "typed by" not in " ".join(r["text"] for r in rows)


def test_a_reset_brings_back_the_waiting_reviews_and_forgets_the_decisions_of_visitors(world):
    client, app, path = make_client(world)
    with client:
        before = Store(path).pending_count()
        waiting = client.get("/review").json()
        client.post(f"/review/{waiting[0]['id']}", json={"label": "a"})
        assert Store(path).pending_count() == before - 1
        demo_module.reset_database(app)
        assert Store(path).pending_count() == before


def test_a_reset_empties_the_built_in_erp(world):
    client, app, _ = make_client(world, mock_erp=True)
    with client:
        app.state.erp.create({"ExternalID": "1", "Category": "a"})
        demo_module.reset_database(app)
        assert app.state.erp.list(10, 0)[1] == 0


def test_a_reset_gives_the_limits_a_fresh_start(world):
    client, app, _ = make_client(world, small_settings(routes_per_minute=1))
    with client:
        me = from_address("203.0.113.5")
        route(client, headers=me)
        assert route(client, headers=me).status_code == 429
        demo_module.reset_database(app)
        assert route(client, headers=me).status_code == 200


def test_the_mock_erp_forgets_its_tickets_and_their_ids_when_cleared():
    store = MockErpStore()
    store.create({"ExternalID": "1"})
    store.create({"ExternalID": "2"})
    store.clear()
    assert store.list(10, 0) == ([], 0)
    ticket, created = store.create({"ExternalID": "1"})
    assert created and ticket["TicketID"] == 1


def test_the_resets_come_on_schedule_and_stop_when_cancelled():
    calls = []

    async def scenario():
        task = asyncio.create_task(demo_module.run_resets(0.01, lambda: calls.append(1)))
        await asyncio.sleep(0.12)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return len(calls)

    assert asyncio.run(scenario()) >= 3


def test_a_failed_reset_is_logged_and_the_next_one_still_happens(caplog):
    calls = []

    def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("disk full")

    async def scenario():
        task = asyncio.create_task(demo_module.run_resets(0.01, flaky))
        await asyncio.sleep(0.12)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with caplog.at_level("ERROR"):
        asyncio.run(scenario())
    assert len(calls) >= 2
    assert "reset of the demo failed" in caplog.text


def test_the_service_stops_cleanly_with_the_reset_task_running(world):
    client, _, _ = make_client(world, small_settings(reset_hours=0.0001))
    with client:
        pass
    # Leaving the block cancelled the task without an error.


def test_the_guard_is_only_a_middleware_with_the_given_settings():
    guard = DemoGuard(small_settings(routes_per_minute=7))
    assert guard.route_minute.limit == 7 and guard.route_minute.window == 60
    assert guard.route_day.window == 86_400
