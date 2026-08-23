"""El gate de Términos, medido en ESTE producto.

🔴 **Por qué hace falta un test acá y no alcanza con el del motor.** El gate se
enciende con una sola línea del armado de la app de este repo
(`app.state.terminos = TerminosRepository(...)`). Si esa línea faltara, libraauth
no falla: `hay_terminos_pendientes` devuelve `False` y la instancia queda sin
gate, en silencio y con toda la suite en verde. Es un opt-in por ausencia, y la
única contramedida es medirlo del lado del consumidor.

Estos tests llevan la marca `sin_aceptar_terminos`, que los deja afuera de la
excepción autouse del `conftest`: son los únicos de la suite que ven el gate
puesto de verdad.
"""
import os

import pytest


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin — mismo patrón que
    el resto de los archivos de esta suite."""
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.mark.sin_aceptar_terminos
def test_una_llamada_gateada_corta_hasta_aceptar(client):
    respuesta = client.get("/api/incidencias")
    assert respuesta.status_code == 403
    assert respuesta.json()["detail"]["code"] == "terminos_pendientes"


@pytest.mark.sin_aceptar_terminos
def test_aceptar_destraba_la_instancia(client):
    estado = client.get("/terminos").json()
    assert estado["pendiente"] is True
    assert estado["puede_aceptar"] is True

    aceptada = client.post("/terminos/aceptar", json={"version": estado["version"]})
    assert aceptada.status_code == 200, aceptada.text
    assert aceptada.json()["pendiente"] is False

    assert client.get("/api/incidencias").status_code == 200


@pytest.mark.sin_aceptar_terminos
def test_el_camino_para_salir_del_gate_no_se_gatea_a_si_mismo(client):
    """El control que hace útil al primero: con la instancia frenada, lo que
    permite destrabarla tiene que seguir contestando 200. Sin esto, un gate que
    cortara TODO también pasaría el test de arriba — y dejaría la instancia sin
    salida."""
    assert client.get("/auth/me").status_code == 200
    assert client.get("/terminos").status_code == 200


@pytest.mark.sin_aceptar_terminos
def test_la_fila_probatoria_guarda_version_hash_y_quien(client):
    from libraauth.terminos import hash_vigente

    estado = client.get("/terminos").json()
    client.post("/terminos/aceptar", json={"version": estado["version"]})

    historial = client.get("/terminos/historial").json()
    assert len(historial) == 1
    assert historial[0]["version"] == estado["version"]
    assert historial[0]["hash_texto"] == hash_vigente()
    assert historial[0]["username"] == "admin"
