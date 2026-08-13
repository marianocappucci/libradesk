"""Smoke tests del primer estrato PostgreSQL del piloto LibraDesk."""


import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select

from app import database


# Acá vivía `test_sqlite_backend_keeps_the_existing_contract`, que fijaba el
# contrato del backend SQLite del piloto. Se retiró el 2026-08-12 junto con
# SQLite: probaba que un motor que el producto ya no usa sigue andando. Pasaba
# —usaba su propio `MetaData`, así que no lo alcanzaba el DDL del schema real—
# y ese verde era el problema: un test que no puede fallar por nada que le
# importe al producto.


def test_postgres_backend_when_configured(url_de_base):
    """Se saltea el `skip`: la suite entera corre contra PostgreSQL desde el
    2026-08-12, asi que ya no hay un caso "sin configurar" que saltear — y un
    skip permanente es un test que no corre nunca."""
    engine = create_engine(url_de_base, pool_pre_ping=True)
    metadata = MetaData()
    table = Table("backend_probe", metadata, Column("id", Integer, primary_key=True), Column("value", String))
    metadata.create_all(engine)
    try:
        with engine.begin() as connection:
            connection.execute(table.delete())
            connection.execute(table.insert().values(value="postgresql"))
            assert connection.scalar(select(table.c.value)) == "postgresql"
    finally:
        metadata.drop_all(engine)
        # `url_de_base` dropea la base en su teardown, y `DROP DATABASE` falla
        # si queda una conexion viva en el pool.
        engine.dispose()


def test_application_starts_against_postgres(tmp_path, monkeypatch, url_de_base):
    """El gate de verdad del piloto: la app entera arranca contra PostgreSQL.

    Es el unico test que ejerce el camino completo —cadena de Alembic del
    producto, `create_all()` de los motores y bootstrap— contra un PostgreSQL
    real, y por eso es el que fue encontrando los defectos de dialecto uno por
    uno el 2026-08-08: `BOOLEAN DEFAULT 1` en las revisiones 0007/0008, y el
    `datetime('now','localtime')` de `auth_log` en LibraAuth.

    `ENV=development` es lo mismo que hace la fixture `data_dir` del conftest
    para el resto de la suite: sin eso `libraauth.bootstrap` exige
    `LIBRADESK_ADMIN_PASSWORD` y aborta el arranque. Este archivo construye la
    app por su cuenta, asi que tiene que armar el entorno tambien.

    🔴 **Este test se salteaba** porque pedia `LIBRADESK_POSTGRES_URL`, una
    variable que la suite dejo de usar: el conftest lee
    `LIBRADESK_SUITE_POSTGRES_URL`. O sea que "el gate de verdad del piloto"
    no corria — ni local ni, salvo que el CI definiera las dos, en CI. Se pasa
    a `url_de_base`, que es la misma base por test que usa el resto.
    """
    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    app = create_app(url_de_base, str(tmp_path))
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200


# ————————————————————————————————————————————————————————————————
# El driver: `postgresql://` a secas es psycopg2, y acá no existe
# ————————————————————————————————————————————————————————————————

@pytest.mark.parametrize("esquema", ["postgresql", "postgresql+psycopg"])
def test_configure_siempre_termina_en_psycopg3(esquema):
    """La medicion directa: sea cual sea la forma que traiga el compose, el
    engine tiene que quedar hablando psycopg 3.

    `postgresql://` a secas lo resuelve SQLAlchemy al dialecto **psycopg2**, que
    este producto no instala —la dependencia es `psycopg[binary]`—. Y no falla
    al conectarse: falla al IMPORTARSE, con `ModuleNotFoundError`, o sea que el
    contenedor entra en crash loop sin llegar a levantar.

    Paso el 2026-08-13 con `libradesk-lagrace`, la primera instancia creada por
    el alta del backoffice: 28 reinicios. Las anteriores tenian el sufijo puesto
    a mano.
    """
    database.configure(f"{esquema}://u:p@host:5432/libradesk")
    try:
        assert database.get_engine().dialect.driver == "psycopg"
    finally:
        database.get_engine().dispose()


def test_sin_normalizar_el_engine_ni_se_construye():
    """Contraprueba de la de arriba, y la razon por la que normalizar no es
    cosmetico: `create_engine` con el esquema pelado revienta ACÁ MISMO, en este
    entorno, exactamente como en el contenedor.

    Si algun dia alguien instala psycopg2 en la imagen, este test se pone rojo —
    y esa es la señal correcta: querria decir que el crash loop dejo de
    reproducirse por una dependencia nueva, no porque el defecto se arreglara.
    """
    with pytest.raises(ModuleNotFoundError, match="psycopg2"):
        create_engine("postgresql://u:p@host:5432/libradesk")


def test_configure_sigue_rechazando_lo_que_no_es_postgres():
    """La normalizacion no puede haber ablandado la guarda: `sqlite://` tiene
    que seguir siendo un error, no convertirse en algo con `+psycopg` pegado."""
    with pytest.raises(ValueError, match="PostgreSQL"):
        database.configure("sqlite:///tmp/x.db")
