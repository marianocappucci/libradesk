"""Recuperación de contraseña: el cableado de LibraDesk sobre libraauth.

La lógica vive probada en el motor (libraauth, 25 tests). Acá se prueba lo
que el motor no puede: que ESTE producto la tenga montada, que el link del
mail apunte a su propia pantalla, y que el flujo entero funcione contra la
app real.

Mismo `client` que test_api.py: reimporta los módulos de `app` en limpio,
porque `app.database`/`app.main` tienen engine y session_factory globales.
"""
import sys

import pytest
from fastapi.testclient import TestClient


def _fresh_app(tmp_path, monkeypatch, con_smtp: bool):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if con_smtp:
        monkeypatch.setenv("LIBRAAUTH_SMTP_HOST", "smtp.test")
        monkeypatch.setenv("LIBRAAUTH_SMTP_FROM_EMAIL", "no-reply@test")
    else:
        monkeypatch.delenv("LIBRAAUTH_SMTP_HOST", raising=False)
        monkeypatch.delenv("LIBRAAUTH_SMTP_FROM_EMAIL", raising=False)
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    from app.asgi import app
    return app, TestClient(app, base_url="https://testserver")


def test_los_endpoints_estan_montados(tmp_path, monkeypatch):
    _, client = _fresh_app(tmp_path, monkeypatch, con_smtp=False)
    # Sin SMTP responde 503: prueba de que el endpoint existe y llega al
    # servicio (un 404 sería "no montado").
    assert client.post("/auth/forgot-password",
                       json={"identificador": "admin"}).status_code == 503


def test_forgot_password_responde_igual_exista_o_no(tmp_path, monkeypatch):
    app, client = _fresh_app(tmp_path, monkeypatch, con_smtp=True)
    app.state.password_reset._send_email = lambda **kw: None

    real = client.post("/auth/forgot-password", json={"identificador": "admin"})
    fantasma = client.post("/auth/forgot-password", json={"identificador": "nadie"})

    assert real.status_code == fantasma.status_code == 200
    assert real.json() == fantasma.json()


def test_flujo_completo(tmp_path, monkeypatch):
    app, client = _fresh_app(tmp_path, monkeypatch, con_smtp=True)
    enviados = []
    app.state.password_reset._send_email = lambda **kw: enviados.append(kw)
    app.state.users.create(username="ana", name="Ana", password="vieja123",
                           role="staff", email="ana@empresa.com")

    assert client.post("/auth/forgot-password",
                       json={"identificador": "ana@empresa.com"}).status_code == 200
    assert len(enviados) == 1
    cuerpo = enviados[0]["cuerpo"]
    assert "libradesk.com.ar/reset-password?token=" in cuerpo
    token = cuerpo.split("?token=")[1].split("\n")[0].strip()

    assert client.post("/auth/reset-password",
                       json={"token": token, "new_password": "nueva-clave-1"}).status_code == 200
    assert client.post("/auth/login",
                       json={"username": "ana", "password": "nueva-clave-1"}).status_code == 200
    assert client.post("/auth/login",
                       json={"username": "ana", "password": "vieja123"}).status_code == 401
    # Un solo uso.
    assert client.post("/auth/reset-password",
                       json={"token": token, "new_password": "otra-clave-2"}).status_code == 400


def test_token_invalido_da_400(tmp_path, monkeypatch):
    _, client = _fresh_app(tmp_path, monkeypatch, con_smtp=True)
    assert client.post("/auth/reset-password",
                       json={"token": "inventado", "new_password": "nueva-clave-1"}).status_code == 400
