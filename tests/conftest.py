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

**La suite también corre contra PostgreSQL**, con
`LIBRADESK_SUITE_POSTGRES_URL` puesta. Es la misma idea de plantilla, con
`CREATE DATABASE ... TEMPLATE` en lugar del `copytree`. Ver el bloque de
`_SUITE_PG_URL` más abajo para el detalle y para por qué no se usa un rollback
por transacción.
"""
from __future__ import annotations

import os
import re
import shutil
import zlib
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


# --- La suite contra PostgreSQL -------------------------------------------
#
# Con `LIBRADESK_SUITE_POSTGRES_URL` puesta, **toda** la suite corre contra
# PostgreSQL en vez de SQLite. Es opt-in y usa una variable PROPIA, distinta de
# `LIBRADESK_POSTGRES_URL`: esa última la pone el CI hoy para los tests que
# ejercen los dos motores a la vez, y reusarla acá daría vuelta la suite entera
# sin que nadie lo pidiera.
#
# **Por qué una base por test y no un rollback por transacción**, que sería más
# rápido: `create_app()` configura DOS fuentes de conexión independientes —el
# engine de SQLAlchemy y `libracore`, que abre una conexión psycopg nueva en
# cada `get_connection()`—. Una transacción externa sólo envuelve a la primera,
# así que las escrituras de remitos y presupuestos quedarían afuera del
# aislamiento. Un schema por test tampoco sirve de atajo: habría que correr
# Alembic y las semillas en cada uno, que es exactamente el costo que la
# plantilla existe para evitar.
#
# Con `CREATE DATABASE ... TEMPLATE`, en cambio, PostgreSQL copia la plantilla a
# nivel de archivos del lado del servidor — el equivalente exacto del
# `copytree` que hace la variante SQLite.
_SUITE_PG_URL = os.environ.get("LIBRADESK_SUITE_POSTGRES_URL")
_PLANTILLA_PG = "libradesk_plantilla"

if not _SUITE_PG_URL:
    raise RuntimeError(
        "La suite de LibraDesk necesita PostgreSQL: definí "
        "LIBRADESK_SUITE_POSTGRES_URL (ej. "
        "postgresql+psycopg://libradesk:libradesk@localhost:5432/postgres).\n"
        "\n"
        "El modo SQLite se retiró el 2026-08-12: LibraDesk corre sobre "
        "PostgreSQL en las tres instancias desde el 2026-08-11, y una suite "
        "verde sobre SQLite no dice nada sobre el motor real — no chequea las "
        "FK, no valida los tipos y acepta cadenas donde la base pide enteros."
    )


# 🔴 `str(url)` de SQLAlchemy ENMASCARA la contraseña como `***`, así que una
# URL reconstruida con `str()` falla con "password authentication failed" —
# que se lee como un problema de credenciales y es un problema de renderizado.
# Hay que pedir el render explícito.
def _render(url) -> str:
    return url.render_as_string(hide_password=False)


def _url_admin() -> str:
    """URL a la base `postgres`, para crear y borrar bases.

    No se puede hacer `CREATE DATABASE` estando conectado a la base que se está
    por reemplazar, así que las operaciones de administración van por acá. El
    driver se saca del prefijo porque esto lo consume psycopg directo, no
    SQLAlchemy.
    """
    from sqlalchemy.engine import make_url

    return _render(make_url(_SUITE_PG_URL).set(database="postgres")).replace(
        "postgresql+psycopg://", "postgresql://", 1
    )


def _url_de(nombre: str) -> str:
    from sqlalchemy.engine import make_url

    return _render(make_url(_SUITE_PG_URL).set(database=nombre))


def _sql_admin(*sentencias: str) -> None:
    import psycopg

    with psycopg.connect(_url_admin(), autocommit=True) as conn:
        for sentencia in sentencias:
            conn.execute(sentencia)


def _soltar_conexiones() -> None:
    """Devuelve al pool y cierra todo lo que la app dejó abierto.

    Hace falta por dos motivos distintos, y los dos muerden:

    1. `CREATE DATABASE ... TEMPLATE x` falla si **alguien** sigue conectado a
       `x`. Después de construir la plantilla hay que soltarla.
    2. Cada test deja un engine con conexiones en el pool contra SU base. Sin
       cerrarlas, 486 tests dejan cientos de conexiones vivas y PostgreSQL
       corta en `max_connections` (100 por defecto) — un fallo que aparece a
       mitad de la corrida y no se parece en nada a su causa.
    """
    from app import database as db_producto

    engine = db_producto.get_engine()
    if engine is not None:
        engine.dispose()


def construir_app(data_dir: Path, database_url: str | None = None):
    """La app de LibraDesk sobre un DATA_DIR ya migrado y sembrado.

    Se importa `create_app` acá adentro y no arriba: importar `app.main` levanta
    los ~200 módulos del producto, y la plantilla tiene que poder decidir el
    entorno antes de que eso pase.
    """
    from app.main import create_app

    if not database_url:
        raise RuntimeError(
            "construir_app() necesita la URL PostgreSQL del test; el fallback "
            "a SQLite se retiró el 2026-08-12"
        )
    return create_app(database_url, str(data_dir))


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
        if _SUITE_PG_URL:
            # La plantilla se construye en una base propia, y hay que soltarla:
            # `CREATE DATABASE ... TEMPLATE` falla si queda alguien conectado.
            _sql_admin(
                f'DROP DATABASE IF EXISTS "{_PLANTILLA_PG}"',
                f'CREATE DATABASE "{_PLANTILLA_PG}"',
            )
            construir_app(destino, _url_de(_PLANTILLA_PG))
            _soltar_conexiones()
        else:
            construir_app(destino)
    finally:
        for var, valor in previo.items():
            if valor is None:
                os.environ.pop(var, None)
            else:
                os.environ[var] = valor

    yield destino

    if _SUITE_PG_URL:
        _sql_admin(f'DROP DATABASE IF EXISTS "{_PLANTILLA_PG}"')


@pytest.fixture
def data_dir(_plantilla, tmp_path, monkeypatch) -> Path:
    """Un DATA_DIR propio del test, copiado de la plantilla.

    Se copia **sobre `tmp_path`** y no en un subdirectorio para que el contrato
    con los tests sea el mismo de antes: `DATA_DIR == tmp_path`, la base en
    `tmp_path/libradesk.db`.

    En modo PostgreSQL el DATA_DIR se copia igual —`logos/`, `backups/` y lo
    que consume `test_config_backup` siguen viviendo en disco—; lo que cambia
    es de dónde sale la base, y de eso se ocupa `url_de_base`.
    """
    shutil.copytree(_plantilla, tmp_path, dirs_exist_ok=True)
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return tmp_path


@pytest.fixture
def url_de_base(request, _plantilla) -> str:
    """La base propia del test: una PostgreSQL nueva, copiada de la plantilla.

    Antes devolvía `None` en modo SQLite, para que `construir_app` armara una
    URL de archivo dentro del DATA_DIR. Ese modo se retiró el 2026-08-12 junto
    con SQLite, así que siempre devuelve una URL.

    Pide `_plantilla` explícitamente aunque no use su valor: `CREATE DATABASE
    ... TEMPLATE` necesita que la plantilla exista. La venía recibiendo de
    rebote porque todo test que pedía esta fixture pedía también `data_dir`,
    que sí la declara — un test que pidiera sólo la URL fallaba con "template
    database does not exist", que no se parece a una dependencia faltante.
    """
    # El nombre sale del test y no de un contador: si algo queda colgado, el
    # nombre de la base dice cuál lo dejó. Se sanea y se recorta porque
    # PostgreSQL corta los identificadores en 63 bytes, y se le antepone un
    # hash para que dos tests con final parecido no colisionen.
    crudo = re.sub(r"[^a-z0-9_]", "_", request.node.nodeid.lower())
    nombre = f"ld_{zlib.crc32(crudo.encode()):08x}_{crudo[-30:]}"[:60]
    _sql_admin(
        f'DROP DATABASE IF EXISTS "{nombre}"',
        f'CREATE DATABASE "{nombre}" TEMPLATE "{_PLANTILLA_PG}"',
    )

    yield _url_de(nombre)

    # Cerrar ANTES de borrar: una base con conexiones vivas no se puede
    # dropear, y dejarlas abiertas agota `max_connections` a mitad de la
    # corrida — un fallo que aparece lejos de su causa.
    _soltar_conexiones()
    _sql_admin(f'DROP DATABASE IF EXISTS "{nombre}"')


@pytest.fixture
def destino_base(data_dir, url_de_base) -> str:
    """La base de ESTA instancia, como la espera el provisioning: una ruta
    SQLite o una URL PostgreSQL.

    Existe porque los tests de planes construían `tmp_path/libradesk.db` a
    mano. En modo PostgreSQL esa ruta no es la base —el archivo ni siquiera
    tiene la tabla `modulos`— y los cuatro morían con `no such table`. El
    mismo string que recibe `create_app`, que es el que el provisioning le
    pasa a `plans.aplicar_plan_en_db`.
    """
    return url_de_base or f"{data_dir}/libradesk.db"


@pytest.fixture
def armar_cliente(data_dir, url_de_base):
    """Fábrica: construye la app **cuando el test la pide**, no antes.

    Para los archivos que deciden el entorno dentro del test y no en la
    fixture — `DEMO_MODE`/`DEMO_USERNAME` en test_demo_arranque,
    `LIBRAAUTH_SMTP_*` en test_password_reset. Con la fixture `client` no
    alcanza: pytest la resuelve antes de entrar al cuerpo del test, así que la
    app quedaría armada con el entorno viejo.

    Devuelve `(app, cliente)` porque un par de tests parchean `app.state`.
    """
    def _armar() -> tuple:
        app = construir_app(data_dir, url_de_base)
        return app, TestClient(app, base_url="https://testserver")

    return _armar


@pytest.fixture
def client(data_dir, url_de_base):
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
    with TestClient(construir_app(data_dir, url_de_base), base_url="https://testserver") as c:
        # Lo consume test_config_backup para comparar el ZIP contra el
        # directorio real de la instancia.
        c.data_dir = data_dir
        yield c


@pytest.fixture(autouse=True)
def _sin_configuracion_de_facturacion_colgada():
    """La lectura de configuracion de facturacion no se filtra entre tests.

    `configurar_lectura` es un GLOBAL del proceso, y `create_app` lo pone. Sin
    esto, cualquier test que construya la app le deja al SIGUIENTE una
    `ConfiguracionFacturacion` apuntando a una base que `url_de_base` ya
    dropeo: el sintoma seria un error de conexion en un test que no tiene nada
    que ver con facturacion, lejisimos de su causa.

    El import va adentro y no arriba por lo mismo que el resto de este archivo
    difiere los de `app`: importar el paquete antes de que las fixtures fijen el
    entorno resuelve configuracion contra los valores equivocados.

    Se resetea antes **y** despues: antes por si el orden de fixtures dejo la
    app construida primero, despues para no ensuciar al que viene.
    """
    from app.services.facturacion_config import configurar_lectura

    configurar_lectura(None)
    yield
    configurar_lectura(None)
