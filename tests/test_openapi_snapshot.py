"""dashboard/openapi.json is the schema the dashboard's TypeScript types are generated from.

If this test fails, the API changed. Regenerate the file and the types:

    python scripts/export_openapi.py
    cd dashboard && npm run api:types
"""
import json

from routeiq.api import create_app
from routeiq.config import ROOT

SNAPSHOT = ROOT / "dashboard" / "openapi.json"
HOW_TO_FIX = "the API schema changed: run `python scripts/export_openapi.py` and `npm run api:types` in dashboard/"


def test_the_committed_schema_matches_the_api():
    committed = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    current = create_app(tiers=[], labels=[]).openapi()
    assert committed == current, HOW_TO_FIX


def test_the_snapshot_is_formatted_the_way_the_script_writes_it():
    text = SNAPSHOT.read_text(encoding="utf-8")
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"


def test_the_snapshot_describes_every_endpoint_the_dashboard_calls():
    paths = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["paths"]
    for path in ("/config", "/requests", "/review", "/review/{request_id}",
                 "/stats", "/stats/timeseries", "/deliveries/retry"):
        assert path in paths


def test_the_dashboard_client_only_calls_endpoints_that_exist():
    """Paths used by dashboard/src/api/endpoints.ts must be part of the schema."""
    paths = json.loads(SNAPSHOT.read_text(encoding="utf-8"))["paths"]
    source = (ROOT / "dashboard" / "src" / "api" / "endpoints.ts").read_text(encoding="utf-8")
    for used in ("/config", "/review", "/requests", "/stats", "/stats/timeseries", "/deliveries/retry"):
        assert f'"{used}' in source or f"`{used}" in source, used
        assert used in paths
