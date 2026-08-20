"""Entrypoint ASGI: `uvicorn app.asgi:app`. Mismo patron que
`gestiolibra/app/asgi.py` — sirve el build del frontend si existe (baked
fuera de `/app` en `/opt/frontend-dist`, ver `Dockerfile`), catch-all a
`index.html` para el ruteo client-side de la SPA."""
import os

from libracore.db.url_de_instancia import url_de_instancia
from pathlib import Path


from app.spa import montar_spa

from .main import create_app

DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
os.makedirs(DATA_DIR, exist_ok=True)
# `requerida=True` y sin default: **LibraDesk corre sobre PostgreSQL y nada
# más** (2026-08-12). El default que había acá era un archivo SQLite, así que
# una instancia a la que le faltara la variable de entorno **arrancaba igual**,
# contra una base vacía recién creada, y se veía sana. Que falte la URL tiene
# que tumbar el arranque, no inventar una base.
database_url = url_de_instancia("libradesk", requerida=True)

app = create_app(database_url, DATA_DIR)

_DOCKER_FRONTEND_DIST = Path("/opt/frontend-dist")
_LOCAL_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
FRONTEND_DIST = _DOCKER_FRONTEND_DIST if _DOCKER_FRONTEND_DIST.is_dir() else _LOCAL_FRONTEND_DIST

if FRONTEND_DIST.is_dir():
    montar_spa(app, FRONTEND_DIST)
