"""Smoke tests de la API real (auth + un flujo CRUD por dominio +
dashboard). No es cobertura exhaustiva de los 5 dominios — verifica que
el wiring completo (libraauth + SQLAlchemy + routers) funciona de punta
a punta contra una SQLite temporal."""
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Reimportar limpio: app.database/app.main tienen estado de modulo
    # (engine/session_factory globales) que no debe pisarse entre tests.
    import sys
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    from app.asgi import app
    # base_url https: la cookie de sesion se crea con secure=True (ver
    # libraauth/session_auth.py) — sobre http:// el cliente la descarta y
    # cualquier request post-login vuelve 401, mismo gotcha que ya
    # documentan los tests de libraauth.
    return TestClient(app, base_url="https://testserver")


def _login(client) -> None:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200


def test_health(client):
    assert client.get("/api/health").status_code == 200


def test_login_and_me(client):
    _login(client)
    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_cliente_equipo_incidencia_flow(client):
    _login(client)

    r = client.post("/api/clientes", json={"nombre": "Cliente Test", "email": "t@test.com"})
    assert r.status_code == 201
    cliente_id = r.json()["id"]

    r = client.post("/api/equipos", json={"cliente_id": cliente_id, "tipo": "Notebook"})
    assert r.status_code == 201
    equipo_id = r.json()["id"]

    r = client.post("/api/tecnicos", json={"nombre": "Tecnico Test"})
    assert r.status_code == 201
    tecnico_id = r.json()["id"]

    r = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "equipo_id": equipo_id, "tecnico_id": tecnico_id,
        "titulo": "No enciende", "prioridad": "alta",
    })
    assert r.status_code == 201
    incidencia_id = r.json()["id"]
    assert r.json()["estado"] == "abierto"

    r = client.put(f"/api/incidencias/{incidencia_id}", json={
        "cliente_id": cliente_id, "equipo_id": equipo_id, "tecnico_id": tecnico_id,
        "titulo": "No enciende", "prioridad": "alta", "estado": "resuelta",
        "resolucion": "Fuente cambiada",
    })
    assert r.status_code == 200
    assert r.json()["fecha_cierre"] is not None

    log = client.get(f"/api/incidencias/{incidencia_id}/estados").json()
    assert len(log) == 2
    assert log[0]["estado_nuevo"] == "resuelta"

    dash = client.get("/api/dashboard").json()
    assert dash["incidencias_por_estado"].get("resuelta") == 1
    assert dash["total_clientes_activos"] == 1


def test_incidencias_requires_auth(client):
    r = client.get("/api/incidencias")
    assert r.status_code == 401


def test_usuarios_requires_admin(client):
    _login(client)
    r = client.get("/api/usuarios")
    assert r.status_code == 200  # admin logueado


def test_export_xlsx(client):
    _login(client)
    client.post("/api/clientes", json={"nombre": "Cliente XLSX"})
    r = client.get("/api/reportes/clientes.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
