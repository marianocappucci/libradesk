"""Entrypoint ASGI: `uvicorn app.asgi:app`. Mismo patron que
`gestiolibra/app/asgi.py` — sirve el build del frontend si existe (baked
fuera de `/app` en `/opt/frontend-dist`, ver `Dockerfile`), catch-all a
`index.html` para el ruteo client-side de la SPA."""
import os

from libracore.db.url_de_instancia import url_de_instancia
from pathlib import Path

from fastapi.responses import FileResponse

from app.spa import TIPOS_PROPIOS, archivo_publico
from fastapi.staticfiles import StaticFiles

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

#: 🔴 **`index.html` no se cachea, y esto no es una optimización: es lo que
#: hace que un deploy se vea.**
#:
#: Vite le pone un hash en el nombre a cada bundle, así que el archivo nuevo
#: nunca pisa al viejo — pero `index.html` **conserva el nombre** y es el único
#: que dice cuál es el bundle de ahora. Sin `Cache-Control`, el navegador aplica
#: caché heurística (una fracción de la antigüedad del `Last-Modified`) y puede
#: servir el `index.html` guardado sin preguntar. El usuario recarga, no ve el
#: cambio, y del lado del servidor está todo bien: el contenedor tiene el código
#: nuevo, el bundle nuevo está publicado, y el navegador sigue pidiendo el viejo
#: — que además existe, porque el nombre lleva hash.
#:
#: Le pasó a LibraCargo el 2026-08-19 con la pantalla de Backup, y estas seis
#: instancias servían el `index.html` sin la cabecera hasta el 2026-08-20 —
#: medido contra los dominios, no leído del compose.
#:
#: `no-cache` **no** es "no guardes": es "guardá, pero revalidá siempre".
SIN_CACHE = "no-cache, must-revalidate"

#: Los assets, al revés: el nombre lleva el hash del contenido, así que **el
#: mismo nombre nunca cambia de contenido** y se pueden cachear para siempre. Un
#: `index.html` que revalida siempre es lo que hace seguro esto: cuando el
#: contenido cambia, el nombre cambia, y el `index.html` fresco pide el nuevo.
PARA_SIEMPRE = "public, max-age=31536000, immutable"


class AssetsInmutables(StaticFiles):
    """`StaticFiles` con la cabecera de caché larga."""

    def file_response(self, *args, **kwargs):
        respuesta = super().file_response(*args, **kwargs)
        respuesta.headers["Cache-Control"] = PARA_SIEMPRE
        return respuesta


if FRONTEND_DIST.is_dir():
    app.mount(
        "/assets", AssetsInmutables(directory=FRONTEND_DIST / "assets"),
        name="frontend-assets",
    )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        archivo = archivo_publico(FRONTEND_DIST, full_path)
        if archivo is not None:
            # Los archivos sueltos del dist (favicon, manifest) tampoco
            # llevan hash en el nombre: mismo criterio que el index.
            return FileResponse(archivo, media_type=TIPOS_PROPIOS.get(archivo.suffix),
                                headers={"Cache-Control": SIN_CACHE})
        return FileResponse(FRONTEND_DIST / "index.html",
                            headers={"Cache-Control": SIN_CACHE})
