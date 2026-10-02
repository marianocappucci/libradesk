"""El tema de la suite en esta instancia (libracore ADR-012, libra-ui ADR-007/008): `GET /api/tema` público y `PUT /api/tema` del admin o
del token de servicio del backoffice.

🔴 El caso que importa para el backoffice es el del token: `require_admin` a secas NO lo acepta (sólo `require_admin_o_servicio`), y sin
esto la pantalla «Apariencia» no podría empujar nada.
"""
import os

import pytest
from libraauth.session_auth import SERVICE_TOKEN_ENV, SERVICE_TOKEN_HEADER

TEMA = {"menuActivoFondo": "#FDF2F8", "menuActivoBorde": "#F9A8D4"}
NORMALIZADO = {"menuActivoFondo": "#fdf2f8", "menuActivoBorde": "#f9a8d4"}
TOKEN = "un-token-de-servicio-de-prueba"


def _entrar(client, username, password):
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text


@pytest.fixture
def sin_sesion(client):
    """El `client` de conftest.py, sin loguear: es como llega el backoffice."""
    return client


@pytest.fixture
def admin(client):
    _entrar(client, os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"), os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"))
    return client


def test_la_lectura_es_publica_y_arranca_vacia(sin_sesion):
    r = sin_sesion.get("/api/tema")
    assert r.status_code == 200
    assert r.json() == {"tema": {}}
    assert r.headers["cache-control"] == "no-cache"


def test_el_admin_guarda_y_cualquiera_lo_lee_sin_sesion(admin):
    r = admin.put("/api/tema", json={"tema": TEMA})
    assert r.status_code == 200, r.text
    assert r.json() == {"tema": NORMALIZADO}
    admin.post("/auth/logout")
    assert admin.get("/api/tema").json() == {"tema": NORMALIZADO}


def test_un_tema_vacio_restaura_los_valores_por_defecto(admin):
    admin.put("/api/tema", json={"tema": TEMA})
    assert admin.put("/api/tema", json={"tema": {}}).status_code == 200
    assert admin.get("/api/tema").json() == {"tema": {}}


def test_un_usuario_staff_no_escribe_el_tema(admin):
    alta = admin.post("/api/usuarios", json={"username": "staff-tema", "name": "S", "password": "clave-larga-1", "role": "staff"})
    assert alta.status_code == 201, alta.text
    admin.post("/auth/logout")
    _entrar(admin, "staff-tema", "clave-larga-1")
    assert admin.put("/api/tema", json={"tema": TEMA}).status_code == 403
    assert admin.get("/api/tema").json() == {"tema": {}}


def test_sin_sesion_ni_token_no_escribe(sin_sesion):
    assert sin_sesion.put("/api/tema", json={"tema": TEMA}).status_code == 401


def test_el_token_de_servicio_del_backoffice_escribe_el_tema(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    r = sin_sesion.put("/api/tema", json={"tema": TEMA}, headers={SERVICE_TOKEN_HEADER: TOKEN})
    assert r.status_code == 200, r.text
    assert sin_sesion.get("/api/tema").json() == {"tema": NORMALIZADO}


def test_un_token_equivocado_o_sin_la_variable_no_escribe(sin_sesion, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, TOKEN)
    assert sin_sesion.put("/api/tema", json={"tema": TEMA}, headers={SERVICE_TOKEN_HEADER: "otro"}).status_code == 401
    monkeypatch.delenv(SERVICE_TOKEN_ENV, raising=False)
    assert sin_sesion.put("/api/tema", json={"tema": TEMA}, headers={SERVICE_TOKEN_HEADER: TOKEN}).status_code == 401


def test_lo_que_no_tiene_la_forma_de_un_color_es_422(admin):
    assert admin.put("/api/tema", json={"tema": {"menuActivoFondo": "verde"}}).status_code == 422
    assert admin.get("/api/tema").json() == {"tema": {}}
