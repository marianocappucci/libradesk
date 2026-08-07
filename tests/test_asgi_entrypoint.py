"""El entrypoint ASGI: `uvicorn app.asgi:app`, que es lo que corre el contenedor.

**Por qué existe este archivo.** Hasta el 2026-08-07 ningún test apuntaba a
`app/asgi.py`, pero todos lo importaban de paso: cada fixture hacía
`from app.asgi import app` para armar su instancia. Al mover la construcción a
`create_app()` en conftest.py, ese import incidental desapareció y el módulo
quedó en 0% — o sea que el único archivo que produccion ejecuta tal cual dejó
de estar probado, y el número de cobertura no lo iba a delatar porque bajó 0,27
puntos sobre un piso de 79.

Lo que se fija acá es el contrato del módulo, que es todo entorno:

1. Que `DATA_DIR` decida dónde vive la base, y que el directorio se cree si no
   está — es lo que permite arrancar un contenedor con un volumen vacío.
2. Que `DATABASE_URL`, si está, gane sobre el default derivado de `DATA_DIR`.
3. Que la app que expone sea la real y responda.

No se prueba el montaje de la SPA (líneas 19-29): depende de que exista
`frontend/dist`, que el job de tests del CI no construye. Ese camino lo cubre
el build de la imagen, que es donde el `dist` existe de verdad.
"""
import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def importar_asgi(tmp_path, monkeypatch):
    """Importa `app.asgi` en limpio y lo saca de `sys.modules` al terminar.

    Es el único archivo de la suite que necesita reimportar: el módulo lee el
    entorno y construye la app **en el import**, así que no hay otra forma de
    ejercitar ese contrato. La limpieza al salir evita que la instancia quede
    cacheada para el resto de la corrida.
    """
    def _importar(**entorno):
        for var, valor in entorno.items():
            if valor is None:
                monkeypatch.delenv(var, raising=False)
            else:
                monkeypatch.setenv(var, str(valor))
        sys.modules.pop("app.asgi", None)
        return importlib.import_module("app.asgi")

    yield _importar
    sys.modules.pop("app.asgi", None)


def test_data_dir_decide_donde_vive_la_base(importar_asgi, tmp_path):
    destino = tmp_path / "datos"
    asgi = importar_asgi(ENV="development", DATA_DIR=destino, DATABASE_URL=None)

    assert asgi.DATA_DIR == str(destino)
    assert asgi.database_url == f"sqlite:///{destino}/libradesk.db"
    # 🔴 El directorio se crea solo. Sin esto, un contenedor con el volumen
    # vacío no arranca — y el volumen vacío es el primer arranque de toda
    # instancia nueva.
    assert destino.is_dir()
    assert (destino / "libradesk.db").is_file()


def test_database_url_le_gana_al_default(importar_asgi, tmp_path):
    """El `DATA_DIR` sigue mandando para logos y backups, pero la base va donde
    diga `DATABASE_URL`. Es como se apunta una instancia a otro motor sin tocar
    el resto de la configuración."""
    destino = tmp_path / "datos"
    otra = tmp_path / "otra.db"
    asgi = importar_asgi(ENV="development", DATA_DIR=destino, DATABASE_URL=f"sqlite:///{otra}")

    assert asgi.database_url == f"sqlite:///{otra}"
    assert otra.is_file()
    assert not (destino / "libradesk.db").exists()


def test_la_app_que_expone_responde(importar_asgi, tmp_path):
    asgi = importar_asgi(ENV="development", DATA_DIR=tmp_path / "datos", DATABASE_URL=None)

    with TestClient(asgi.app, base_url="https://testserver") as c:
        assert c.get("/api/health").status_code == 200
        # Y es la app completa, no un esqueleto: el login del producto entra.
        r = c.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 200, r.text
