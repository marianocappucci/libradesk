"""Fixtures compartidas de la suite.

**Qué reemplaza.** Hasta el 2026-08-07 cada archivo de tests traía su propia
fixture `client`, y las 24 hacían lo mismo: purgar `app.*` de `sys.modules` y
`from app.asgi import app`. Eso reconstruía la instancia entera **por test** —
las 13 revisiones de Alembic, los tres `create_all`, el hash bcrypt del admin,
la siembra de módulos y la reimportación de unos 200 módulos. Medido el
2026-08-07: 453 tests en 718 s, y las 25 duraciones más lentas de la corrida
eran todas de `setup`, ninguna de `call`. En GitHub Actions ese job era la
línea más cara de todo el ecosistema: 1.148 minutos facturables en 30 días,
el 28% del cupo mensual de la cuenta.

**Por qué la purga de `sys.modules` no hacía falta.** Se hacía para poder
reimportar `app.asgi`, que lee `DATA_DIR`/`DATABASE_URL` **en el import** (línea
13) y construye la app ahí mismo. Pero la app la arma `create_app(url,
data_dir)`, que recibe las dos cosas por parámetro: llamándola directo, el
estado global de `app.database` (`_engine`/`_session_factory`) lo pisa la propia
`configure()` en cada llamada, y no queda nada que reimportar. Se verificó que
`app/asgi.py` es el **único** módulo de `app/` que lee el entorno en tiempo de
import (`grep -rn 'os.environ\\|os.getenv' app/`), así que no hay ninguna otra
variable que dependa de reimportar. Lo que se leía en tiempo de llamada
—`DEMO_MODE`, `LIBRAAUTH_SMTP_*`, `LIBRADESK_RESET_URL_BASE`— se sigue leyendo
en tiempo de llamada, dentro de `create_app`.

**Qué hace ahora.** El schema y las semillas se construyen **una vez por
corrida** en un DATA_DIR plantilla, y cada test recibe una copia de ese
directorio. Copiar un SQLite de unos cientos de KB es del orden del
milisegundo; migrarlo y sembrarlo, del orden del segundo y medio.

🔴 **Se copia el DATA_DIR entero, no sólo el `.db`.** `create_app` también
configura LibraCore contra ese directorio (`rp_service.configure`) y deja ahí
`logos/` y `backups/`. Copiar sólo la base dejaría a `test_config_backup` con
un directorio a medias, que es justamente lo que ese archivo existe para
detectar.

**El aislamiento entre tests no cambia**: cada uno sigue teniendo su propio
archivo de base y su propia app, sólo que partiendo de una copia ya migrada en
lugar de reconstruirla. No hay estado compartido entre tests — la plantilla se
lee, nunca se escribe.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Variables que definen QUÉ instancia se construye. Se neutralizan al armar la
# plantilla para que no dependa de lo que tenga cargado la máquina donde corre
# la suite, y para que los tests que las usan (`DEMO_MODE` en
# test_demo_arranque, `LIBRAAUTH_SMTP_*` en test_password_reset) partan siempre
# del mismo piso. No se neutralizan al construir la app de cada test: ahí es
# donde el test las quiere puestas.
_ENV_DE_INSTANCIA = (
    "DEMO_MODE", "DEMO_USERNAME", "DATABASE_URL",
    # El emparejamiento con Contalibra (`app/services/facturacion_externa.py`).
    # Van acá por el mismo motivo que las de arriba: si la máquina que corre la
    # suite las tuviera puestas, los tests que ejercen el camino "sin
    # configurar" pasarían a ejercer el otro **sin fallar**, que es el peor modo
    # de romperse.
    "CONTALIBRA_URL", "CONTALIBRA_SERVICE_TOKEN", "INSTANCIA_SLUG",
)


def construir_app(data_dir: Path):
    """La app de LibraDesk sobre un DATA_DIR ya migrado y sembrado.

    Se importa `create_app` acá adentro y no arriba: importar `app.main` levanta
    los ~200 módulos del producto, y la plantilla tiene que poder decidir el
    entorno antes de que eso pase.
    """
    from app.main import create_app

    return create_app(f"sqlite:///{data_dir}/libradesk.db", str(data_dir))


@pytest.fixture(scope="session")
def _plantilla(tmp_path_factory) -> Path:
    """DATA_DIR con el schema en head y las semillas puestas, armado una vez.

    Construir la app tiene efectos sobre globales de módulo (`app.database`,
    `libracore`), pero cada test los vuelve a pisar con su propia
    `create_app`, así que lo único que sobrevive de acá es el directorio.
    """
    destino = tmp_path_factory.mktemp("plantilla")

    previo = {k: os.environ.get(k) for k in ("ENV",) + _ENV_DE_INSTANCIA}
    os.environ["ENV"] = "development"
    for var in _ENV_DE_INSTANCIA:
        os.environ.pop(var, None)
    try:
        construir_app(destino)
    finally:
        for var, valor in previo.items():
            if valor is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = valor

    return destino


@pytest.fixture
def data_dir(_plantilla, tmp_path, monkeypatch) -> Path:
    """Un DATA_DIR propio del test, copiado de la plantilla.

    Se copia **sobre `tmp_path`** y no en un subdirectorio para que el contrato
    con los tests sea el mismo de antes: `DATA_DIR == tmp_path`, la base en
    `tmp_path/libradesk.db`.
    """
    shutil.copytree(_plantilla, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


@pytest.fixture
def armar_cliente(data_dir):
    """Fábrica: construye la app **cuando el test la pide**, no antes.

    Para los archivos que deciden el entorno dentro del test y no en la
    fixture — `DEMO_MODE`/`DEMO_USERNAME` en test_demo_arranque,
    `LIBRAAUTH_SMTP_*` en test_password_reset. Con la fixture `client` no
    alcanza: pytest la resuelve antes de entrar al cuerpo del test, así que la
    app quedaría armada con el entorno viejo.

    Devuelve `(app, cliente)` porque un par de tests parchean `app.state`.
    """
    def _armar() -> tuple:
        app = construir_app(data_dir)
        return app, TestClient(app, base_url="https://testserver")

    return _armar


@pytest.fixture
def client(data_dir):
    """Cliente HTTP contra una instancia limpia, **sin loguear**.

    `base_url` https a propósito: la cookie de sesión se crea con `secure=True`
    (ver `libraauth/session_auth.py`), y sobre http:// el cliente la descarta —
    cualquier request post-login vuelve 401. Mismo gotcha que documentan los
    tests de libraauth.

    Como gestor de contexto —que es lo que hacían 7 de los 24 archivos— para
    que corra el ciclo de vida de la app. Hoy LibraDesk no registra handlers de
    `lifespan`, así que no cambia nada; el día que registre uno, los tests lo
    van a estar ejercitando.

    Los archivos que necesitan la sesión abierta **redefinen `client` pidiendo
    éste como parámetro** y le hacen el login encima; pytest resuelve el del
    módulo contra el de acá. Así el login queda a la vista en el archivo que lo
    necesita en vez de repartirse en dos fixtures con el mismo nombre.
    """
    with TestClient(construir_app(data_dir), base_url="https://testserver") as c:
        # Lo consume test_config_backup para comparar el ZIP contra el
        # directorio real de la instancia.
        c.data_dir = data_dir
        yield c
