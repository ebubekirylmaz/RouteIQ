import pytest
from fastapi.testclient import TestClient

from fakes import Fake
from routeiq.api import create_app
from routeiq.dashboard import ASSET_CACHE, dashboard_dir, is_built

INDEX = "<!doctype html><title>RouteIQ dashboard</title><div id=root></div>"
ASSET = "console.log('app');"
SECRET = "do-not-serve-this"


@pytest.fixture
def site(tmp_path):
    """A built dashboard with a secret file next to it, outside the served folder."""
    root = tmp_path / "site"
    (root / "dist" / "assets").mkdir(parents=True)
    (root / "dist" / "index.html").write_text(INDEX, encoding="utf-8")
    (root / "dist" / "assets" / "app.abc123.js").write_text(ASSET, encoding="utf-8")
    (root / "dist" / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (root / "secret.txt").write_text(SECRET, encoding="utf-8")
    (tmp_path / "secret-outside.txt").write_text(SECRET, encoding="utf-8")
    return root / "dist"


def make_client(tmp_path, dashboard):
    tiers = [
        ({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9)),
        ({"name": "llm", "accept_threshold": 0.7}, Fake("b", 0.9)),
    ]
    app = create_app(tiers=tiers, labels=["a", "b"], db_path=tmp_path / "t.db", dashboard=dashboard)
    return TestClient(app)


@pytest.fixture
def client(tmp_path, site):
    with make_client(tmp_path, site) as client:
        yield client


# --- serving ---------------------------------------------------------------------------

def test_the_root_of_the_dashboard_serves_index_html(client):
    response = client.get("/dashboard/")
    assert response.status_code == 200
    assert response.text == INDEX
    assert response.headers["content-type"].startswith("text/html")


def test_dashboard_without_a_trailing_slash_redirects(client):
    response = client.get("/dashboard", follow_redirects=False)
    assert response.status_code in (301, 307)
    assert response.headers["location"].endswith("/dashboard/")


def test_explicit_index_html_is_served(client):
    assert client.get("/dashboard/index.html").text == INDEX


def test_static_files_are_served_with_their_content_type(client):
    response = client.get("/dashboard/assets/app.abc123.js")
    assert response.status_code == 200
    assert response.text == ASSET
    assert "javascript" in response.headers["content-type"]
    assert client.get("/dashboard/favicon.svg").status_code == 200


# --- single-page-app routes ------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/dashboard/review",
    "/dashboard/requests",
    "/dashboard/review/42",
    "/dashboard/some/deep/page",
    "/dashboard/v1.2/overview",
])
def test_page_routes_fall_back_to_index_html(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.text == INDEX


@pytest.mark.parametrize("path", [
    "/dashboard/assets/missing.js",
    "/dashboard/missing.css",
    "/dashboard/assets/app.abc123.js.map",
    "/dashboard/robots.txt",
])
def test_missing_files_are_a_real_404_not_the_index_page(client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert INDEX not in response.text


# --- caching ---------------------------------------------------------------------------

def test_index_html_is_never_cached(client):
    for path in ("/dashboard/", "/dashboard/index.html", "/dashboard/review"):
        assert client.get(path).headers["cache-control"] == "no-cache"


def test_hashed_assets_are_cached_for_a_year_and_immutable(client):
    cache = client.get("/dashboard/assets/app.abc123.js").headers["cache-control"]
    assert cache == ASSET_CACHE
    assert "immutable" in cache and "max-age=31536000" in cache


def test_other_static_files_keep_the_default_caching(client):
    cache = client.get("/dashboard/favicon.svg").headers.get("cache-control")
    assert cache is None or ("immutable" not in cache and cache != "no-cache")


# --- safety ----------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/dashboard/../secret.txt",
    "/dashboard/..%2fsecret.txt",
    "/dashboard/%2e%2e/secret.txt",
    "/dashboard/%2e%2e%2fsecret.txt",
    "/dashboard/assets/../../secret.txt",
    "/dashboard/....//secret.txt",
    "/dashboard//etc/passwd",
])
def test_path_traversal_never_serves_files_outside_the_folder(client, path):
    response = client.get(path)
    assert SECRET not in response.text
    assert "root:" not in response.text


def test_only_reading_is_allowed(client):
    assert client.post("/dashboard/", json={}).status_code == 405
    assert client.delete("/dashboard/assets/app.abc123.js").status_code == 405


# --- the API keeps working -------------------------------------------------------------

def test_api_routes_are_not_shadowed_by_the_dashboard(client):
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/review").json() == []
    assert client.get("/stats").json()["requests"] == 0
    assert client.post("/route", json={"text": "hello"}).status_code == 200


def test_the_dashboard_is_not_part_of_the_api_schema(client):
    assert not any(path.startswith("/dashboard") or path == "/" for path in client.get("/openapi.json").json()["paths"])


def test_the_root_redirects_to_the_dashboard(client):
    response = client.get("/", follow_redirects=False)
    assert response.status_code in (302, 307)
    assert response.headers["location"].endswith("/dashboard/")


# --- not built -------------------------------------------------------------------------

def test_without_a_built_dashboard_the_app_still_works(tmp_path):
    with make_client(tmp_path, tmp_path / "does-not-exist") as client:
        assert client.get("/health").status_code == 200
        assert client.get("/dashboard/").status_code == 404
        assert client.get("/dashboard/review").status_code == 404
        assert client.get("/").status_code == 404


def test_a_folder_without_index_html_is_not_served(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "app.js").write_text(ASSET)
    with make_client(tmp_path, empty) as client:
        assert client.get("/dashboard/app.js").status_code == 404
        assert client.get("/").status_code == 404


def test_a_file_instead_of_a_folder_is_not_served(tmp_path):
    not_a_folder = tmp_path / "file"
    not_a_folder.write_text("x")
    with make_client(tmp_path, not_a_folder) as client:
        assert client.get("/dashboard/").status_code == 404


# --- configuration ---------------------------------------------------------------------

def test_is_built_needs_index_html(tmp_path, site):
    assert is_built(site)
    assert not is_built(tmp_path / "missing")
    (site / "index.html").unlink()
    assert not is_built(site)


def test_the_folder_comes_from_the_environment(monkeypatch, site):
    monkeypatch.setenv("ROUTEIQ_DASHBOARD_DIR", str(site))
    assert dashboard_dir() == site


def test_the_default_folder_is_dashboard_dist_in_the_repository(monkeypatch):
    monkeypatch.delenv("ROUTEIQ_DASHBOARD_DIR", raising=False)
    assert dashboard_dir().parts[-2:] == ("dashboard", "dist")


def test_an_empty_environment_value_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("ROUTEIQ_DASHBOARD_DIR", "")
    assert dashboard_dir().parts[-2:] == ("dashboard", "dist")


def test_create_app_uses_the_environment_when_no_folder_is_given(monkeypatch, tmp_path, site):
    monkeypatch.setenv("ROUTEIQ_DASHBOARD_DIR", str(site))
    tiers = [({"name": "baseline", "accept_threshold": 0.5}, Fake("a", 0.9))]
    app = create_app(tiers=tiers, labels=["a"], db_path=tmp_path / "t.db")
    with TestClient(app) as client:
        assert client.get("/dashboard/").text == INDEX
