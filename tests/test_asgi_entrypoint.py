"""El entrypoint ASGI: `uvicorn app.asgi:app`, que es lo que corre el contenedor.

**Por qué existe este archivo.** Hasta el 2026-08-07 ningún test apuntaba a
`app/asgi.py`, pero todos lo importaban de paso: cada fixture hacía
`from app.asgi import app` para armar su instancia. Al mover la construcción a
`create_app()` en conftest.py, ese import incidental desapareció y el módulo
quedó en 0% — o sea que el único archivo que produccion ejecuta tal cual dejó
de estar probado, y el número de cobertura no lo iba a delatar porque bajó 0,27
puntos sobre un piso de 79.

Lo que se fija acá es el contrato del módulo, que es todo entorno:

1. Que `DATA_DIR` se cree si no está — es lo que permite arrancar un
   contenedor con un volumen vacío.
2. Que **sin URL de base el arranque se caiga**, en vez de inventar una. Hasta
   el 2026-08-12 había un default a un archivo SQLite dentro de `DATA_DIR`, y
   una instancia sin la variable puesta arrancaba contra una base vacía recién
   creada **viéndose sana**.
3. Que una URL que no sea PostgreSQL se rechace.
4. Que la app que expone sea la real y responda.
5. Que el catch-all de la SPA **no se coma `/health`**, que es lo que permite
   servir la salud en la raíz como el resto de la familia.

No se prueba el *montaje* de la SPA (líneas 19-29): depende de que exista
`frontend/dist`, que el job de tests del CI no construye. Ese camino lo cubre
el build de la imagen, que es donde el `dist` existe de verdad. Lo que sí se
prueba (punto 5) es la **precedencia de rutas** frente a un catch-all
equivalente, que es el mecanismo del que depende `/health`.
"""
import importlib
import sys

import pytest
from fastapi.responses import HTMLResponse
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


def test_data_dir_se_crea_solo(importar_asgi, tmp_path, url_de_base):
    """🔴 El directorio se crea solo. Sin esto, un contenedor con el volumen
    vacío no arranca — y el volumen vacío es el primer arranque de toda
    instancia nueva. `DATA_DIR` sigue mandando para logos y backups aunque la
    base viva en el sidecar."""
    destino = tmp_path / "datos"
    asgi = importar_asgi(ENV="development", DATA_DIR=destino, DATABASE_URL=url_de_base)

    assert asgi.DATA_DIR == str(destino)
    assert asgi.database_url == url_de_base
    assert destino.is_dir()


def test_sin_url_de_base_el_arranque_se_cae(importar_asgi, tmp_path):
    """No hay default y **tiene que no haberlo** (2026-08-12).

    Hasta esta fecha el default era un archivo SQLite en `DATA_DIR`, así que
    una instancia a la que le faltara la variable de entorno **arrancaba
    igual**, contra una base vacía recién creada, y se veía sana: healthcheck
    en verde, login del admin sembrado, y cero datos del cliente. Que falte la
    URL tiene que tumbar el arranque, no inventar una base.
    """
    with pytest.raises(RuntimeError) as e:
        importar_asgi(ENV="development", DATA_DIR=tmp_path / "datos", DATABASE_URL=None)

    # El mensaje nombra las variables aceptadas: durante la transición hay dos
    # y no saber cuál se esperaba es la mitad del problema.
    assert "LIBRADESK_DATABASE_URL" in str(e.value)


def test_una_url_que_no_es_postgres_se_rechaza(importar_asgi, tmp_path):
    """LibraDesk corre sobre PostgreSQL y nada más. Una URL SQLite acá
    levantaba la app con un motor donde las FK no se chequean y los tipos son
    dinámicos — los defectos que PostgreSQL rechaza de entrada pasaban
    desapercibidos hasta producción."""
    with pytest.raises(ValueError) as e:
        importar_asgi(
            ENV="development", DATA_DIR=tmp_path / "datos",
            DATABASE_URL=f"sqlite:///{tmp_path}/otra.db",
        )

    assert "PostgreSQL" in str(e.value)


def test_la_app_que_expone_responde(importar_asgi, tmp_path, url_de_base):
    asgi = importar_asgi(ENV="development", DATA_DIR=tmp_path / "datos", DATABASE_URL=url_de_base)

    with TestClient(asgi.app, base_url="https://testserver") as c:
        assert c.get("/health").status_code == 200
        # Y es la app completa, no un esqueleto: el login del producto entra.
        r = c.post("/auth/login", json={"username": "admin", "password": "admin"})
        assert r.status_code == 200, r.text


def test_el_catch_all_de_la_spa_no_se_come_el_health(armar_cliente):
    """🔴 `/health` le gana al catch-all de la SPA.

    Es lo que hace posible servir la salud en la raíz como los otros cinco
    productos, y también lo que mantenía invisible el desvío a la ruta vieja:
    con el `dist` horneado **cualquier** ruta devuelve 200 con el `index.html`,
    así que un healthcheck que sólo mire el status da verde exista o no la
    ruta. Medido contra `libradesk-demo` el 2026-08-12: las dos rutas daban
    200 y sólo se distinguían parseando el cuerpo.

    El catch-all se registra acá igual que en `app/asgi.py` en vez de importar
    ese módulo, porque el suyo sólo se monta si existe `frontend/dist` y el job
    de tests no lo construye. Lo que se fija es la precedencia: una ruta
    explícita registrada en `create_app()` le gana a un catch-all registrado
    después.

    El assert de control —la ruta inventada **sí** cae en el `index.html`— no
    es decorativo: sin él, un catch-all que no llegara a registrarse dejaría
    este test en verde sin haber probado nada.

    Y desde que se sacó el alias, `/api/health` **es** uno de esos controles: se
    lo come el catch-all igual que a cualquier ruta inventada. Vale la pena
    verlo escrito, porque es la forma en que este cambio puede lastimar a algo
    de afuera — un chequeo que haya quedado apuntado ahí no recibe un 404, sino
    un 200 con HTML, y si sólo mira el código dice "ok" para siempre.
    """
    app, cliente = armar_cliente()

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        del full_path
        return HTMLResponse("<!doctype html><title>LibraDesk</title>")

    for control in ("/una-ruta-que-no-existe", "/api/health"):
        r = cliente.get(control)
        # Los dos mensajes se distinguen a proposito: llevando los dos el mismo
        # texto, el rojo no decia si la ruta habia dejado de contestar o si
        # habia vuelto a ser una ruta del router, que son diagnosticos opuestos.
        assert r.status_code == 200, f"{control}: el catch-all no contesto (HTTP {r.status_code})"
        assert r.headers["content-type"].startswith("text/html"), (
            f"{control}: contesto {r.headers['content-type']}, o sea que la sirve el router "
            "y no el catch-all — dejo de servir como control"
        )

    r = cliente.get("/health")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.json()["status"] == "ok"
