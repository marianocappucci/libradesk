"""Entrypoint ASGI: `uvicorn app.asgi:app`. Mismo patron que
`gestiolibra/app/asgi.py` — sirve el build del frontend si existe (baked
fuera de `/app` en `/opt/frontend-dist`, ver `Dockerfile`), catch-all a
`index.html` para el ruteo client-side de la SPA."""
import os

from libracore.db.url_de_instancia import url_de_instancia
from pathlib import Path

from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .main import create_app

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)
database_url = url_de_instancia(
    "libradesk", default=f"sqlite:///{DATA_DIR}/libradesk.db"
)

app = create_app(database_url, DATA_DIR)

_DOCKER_FRONTEND_DIST = Path("/opt/frontend-dist")
_LOCAL_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
FRONTEND_DIST = _DOCKER_FRONTEND_DIST if _DOCKER_FRONTEND_DIST.is_dir() else _LOCAL_FRONTEND_DIST

if FRONTEND_DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="frontend-assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        del full_path
        return FileResponse(FRONTEND_DIST / "index.html")
