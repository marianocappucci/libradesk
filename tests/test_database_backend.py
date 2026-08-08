"""Smoke tests del primer estrato PostgreSQL del piloto LibraDesk."""

import os

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select


def test_sqlite_backend_keeps_the_existing_contract(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/backend.db", pool_pre_ping=True)
    metadata = MetaData()
    table = Table("backend_probe", metadata, Column("id", Integer, primary_key=True), Column("value", String))
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(table.insert().values(value="sqlite"))
        assert connection.scalar(select(table.c.value)) == "sqlite"


def test_postgres_backend_when_configured():
    url = os.environ.get("LIBRADESK_POSTGRES_URL")
    if not url:
        pytest.skip("LIBRADESK_POSTGRES_URL no configurada; el CI la provee")

    engine = create_engine(url, pool_pre_ping=True)
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


def test_application_starts_against_postgres(tmp_path, monkeypatch):
    """El gate de verdad del piloto: la app entera arranca contra PostgreSQL.

    Es el unico test que ejerce el camino completo —cadena de Alembic del
    producto, `create_all()` de los motores y bootstrap— contra un PostgreSQL
    real, y por eso es el que fue encontrando los defectos de dialecto uno por
    uno el 2026-08-08: `BOOLEAN DEFAULT 1` en las revisiones 0007/0008, y el
    `datetime('now','localtime')` de `auth_log` en LibraAuth.

    `ENV=development` es lo mismo que hace la fixture `data_dir` del conftest
    para el resto de la suite: sin eso `libraauth.bootstrap` exige
    `LIBRADESK_ADMIN_PASSWORD` y aborta el arranque. Este archivo no usa esa
    fixture —construye la app contra PostgreSQL y no contra la plantilla
    SQLite— asi que tiene que armar el entorno por su cuenta.
    """
    url = os.environ.get("LIBRADESK_POSTGRES_URL")
    if not url:
        pytest.skip("LIBRADESK_POSTGRES_URL no configurada; el CI la provee")

    from fastapi.testclient import TestClient

    from app.main import create_app

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))

    app = create_app(url, str(tmp_path))
    with TestClient(app) as client:
        assert client.get("/api/health").status_code == 200
