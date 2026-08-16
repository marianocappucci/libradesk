"""Que una visita de mantenimiento se distinga de un reclamo, por la API.

🔴 **Esto es exactamente lo que no cubrió la primera tanda de tests.** La
revisión `0027` guardaba `contrato_id` y `periodo_visita` en la incidencia, y
`_to_dict()` **no los devolvía**: el dato entraba a la base y no salía nunca.

Ningún test lo agarró, y vale entender por qué:

- Los del generador leen **su propia salida** (`{"visitas": [...]}`), no la
  incidencia por la API.
- El de la cobertura sí lee `GET /api/incidencias/{id}`, pero mira
  `cobertura_abono`, que ya estaba en el dict.

O sea que la suite entera pasaba mientras la pantalla no tenía cómo saber que un
ticket era una visita — y el sentido de que la visita **sea** una incidencia es
justamente que aparezca en la misma bandeja, distinguible. Lo destapó ejercitar
el circuito contra dev.

La lección concreta: un campo nuevo en el modelo no está terminado hasta que un
test lo lee **por donde lo lee la pantalla**.
"""

import os
from datetime import date

import pytest


@pytest.fixture
def client(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def escenario(client):
    """Un abono que visita, y un reclamo común del mismo cliente.

    Los dos juntos son el punto: con sólo la visita, un `es_visita_mantenimiento`
    cableado en `True` pasaría el test.
    """
    cliente = client.post("/api/clientes", json={
        "nombre": "Medici Neumatec", "tipo_facturacion": "mensual",
    }).json()
    client.post("/api/contratos", json={
        "tipo_contrato": "abono", "cliente_id": cliente["id"],
        "fecha_inicio": "2026-01-01", "estado": "activo", "importe": 45000,
        "frecuencia_visita": "mensual",
    })
    reclamo = client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "titulo": "No hay tono",
    }).json()
    generadas = client.post("/api/visitas/generar",
                            json={"ancla": date(2026, 9, 1).isoformat()}).json()
    assert generadas["generadas"] == 1, generadas
    return client, cliente, reclamo, generadas["visitas"][0]["incidencia_id"]


def test_la_ficha_de_la_visita_dice_de_que_contrato_salio(escenario):
    client, _cliente, _reclamo, visita_id = escenario

    ficha = client.get(f"/api/incidencias/{visita_id}").json()
    assert ficha["es_visita_mantenimiento"] is True
    assert ficha["contrato_id"] is not None
    assert ficha["periodo_visita"] == "2026-09-01"


def test_un_reclamo_comun_no_se_marca_como_visita(escenario):
    """La contraprueba. Sin ella, devolver `True` siempre pasaría el de arriba."""
    client, _cliente, reclamo, _visita_id = escenario

    ficha = client.get(f"/api/incidencias/{reclamo['id']}").json()
    assert ficha["es_visita_mantenimiento"] is False
    assert ficha["contrato_id"] is None
    assert ficha["periodo_visita"] is None


def test_el_listado_tambien_las_distingue(escenario):
    """Es **el listado** lo que mira quien abre la bandeja, no la ficha."""
    client, cliente, reclamo, visita_id = escenario

    filas = client.get(f"/api/incidencias?cliente_id={cliente['id']}").json()
    por_id = {i["id"]: i for i in filas}

    assert por_id[visita_id]["es_visita_mantenimiento"] is True
    assert por_id[reclamo["id"]]["es_visita_mantenimiento"] is False
