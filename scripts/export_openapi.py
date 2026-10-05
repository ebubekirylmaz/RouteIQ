"""Writes the OpenAPI schema of the API to dashboard/openapi.json. No server is needed.

Run it whenever the API changes, then regenerate the TypeScript types:

    python scripts/export_openapi.py
    cd dashboard && npm run api:types
"""
import json
from pathlib import Path

from routeiq.api import create_app

OUT = Path(__file__).resolve().parent.parent / "dashboard" / "openapi.json"


def main():
    spec = create_app(tiers=[], labels=[]).openapi()
    OUT.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("wrote", OUT)


if __name__ == "__main__":
    main()
