import os
from pathlib import Path

from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.staticfiles import StaticFiles

from routeiq.config import ROOT

ASSET_CACHE = "public, max-age=31536000, immutable"


def dashboard_dir():
    return Path(os.getenv("ROUTEIQ_DASHBOARD_DIR") or ROOT / "dashboard" / "dist")


def is_built(directory):
    return directory.is_dir() and (directory / "index.html").is_file()


class SPAFiles(StaticFiles):
    """Static files for a single-page app: page routes that are not files get index.html."""

    async def get_response(self, path, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or "." in Path(path).name:
                raise
            path = "index.html"
            response = await super().get_response(path, scope)
        if path.startswith("assets/"):
            response.headers["Cache-Control"] = ASSET_CACHE
        elif Path(path).suffix in ("", ".html"):
            response.headers["Cache-Control"] = "no-cache"
        return response