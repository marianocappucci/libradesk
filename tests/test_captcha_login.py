"""El captcha ALTCHA del login está cableado (libraauth v0.40.0, ADR-014).

El resto de la suite corre con un doble que acepta cualquier captcha (ver
`_captcha_siempre_valido` en el conftest). Estos tests restauran la función
real, así que miden lo que ve un navegador: que `GET /auth/captcha` emite un
desafío, que sin resolverlo no se entra aunque la contraseña sea buena, y que
resolviéndolo sí.

El captcha en sí —firmas, vencimiento, anti-replay— lo prueba libraauth. Lo que
se prueba acá es que ESTE producto lo prendió: si alguien le saca
`captcha=True` al router de `app/routers/auth.py`, el primer test da 404 y el
segundo da 200.
"""
import pytest
from conftest import CAPTCHA_DE_ORIGINAL
from libraauth.captcha import Captcha
from libraauth.session_auth import CAPTCHA_INVALIDO

CREDENCIALES = {"username": "admin", "password": "admin"}


@pytest.fixture
def captcha_real(monkeypatch):
    """Devuelve `_captcha_de` a la función real de libraauth para este test."""
    monkeypatch.setattr("libraauth.session_auth._captcha_de", CAPTCHA_DE_ORIGINAL)


def _barato(client) -> None:
    """Un `Captcha` de costo mínimo en la instancia, para resolverlo rápido.

    `_captcha_de` usa el que haya en `app.state.captcha`; sin esto arma uno con
    el costo de producción, que tarda del orden de un segundo por desafío.
    """
    client.app.state.captcha = Captcha("clave-de-prueba", costo=1, contador_min=1, contador_rango=5)


def _resolver(client) -> str:
    from altcha import Challenge, Payload, solve_challenge

    desafio = Challenge.from_dict(client.get("/auth/captcha").json())
    solucion = solve_challenge(desafio)
    assert solucion is not None
    return Payload(desafio, solucion).to_base64()


def test_get_captcha_emite_un_desafio(client, captcha_real):
    r = client.get("/auth/captcha")
    assert r.status_code == 200
    cuerpo = r.json()
    assert isinstance(cuerpo["parameters"], dict)
    assert isinstance(cuerpo["signature"], str)
    # Un desafío cacheado se podría servir a dos navegadores, y el segundo que
    # lo mande recibe el 400 del anti-replay.
    assert "no-store" in r.headers["cache-control"]


def test_login_sin_captcha_no_entra_aunque_la_clave_sea_buena(client, captcha_real):
    r = client.post("/auth/login", json=CREDENCIALES)
    assert r.status_code == 400
    assert r.json()["detail"] == CAPTCHA_INVALIDO
    assert client.get("/auth/me").status_code == 401


def test_control_con_el_doble_de_la_suite_las_mismas_credenciales_entran(client):
    # Sin `captcha_real`: el 400 de arriba es por el captcha y no por la clave.
    r = client.post("/auth/login", json=CREDENCIALES)
    assert r.status_code == 200


def test_con_captcha_resuelto_entra(client, captcha_real):
    _barato(client)
    r = client.post("/auth/login", json={**CREDENCIALES, "captcha": _resolver(client)})
    assert r.status_code == 200
    assert client.get("/auth/me").status_code == 200


def test_un_captcha_resuelto_sirve_una_sola_vez(client, captcha_real):
    _barato(client)
    payload = _resolver(client)
    assert client.post("/auth/login", json={**CREDENCIALES, "captcha": payload}).status_code == 200
    client.post("/auth/logout")
    r = client.post("/auth/login", json={**CREDENCIALES, "captcha": payload})
    assert r.status_code == 400
    assert r.json()["detail"] == CAPTCHA_INVALIDO
