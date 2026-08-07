"""Ficha del equipo — `GET /api/dashboard/equipo/{id}` (2026-08-04).

Reemplaza al diálogo "ver historial" de la lista de equipos, que pedía tres
endpoints y **no traía el cliente**: el historial decía que el equipo salió de
Admisión sin decir de quién era Admisión, que fue justamente el pedido.

Lo que estos tests fijan:

1. Que la ruta exista de verdad y no sea el fallback de la SPA (un 404 propio,
   no un 200 con el index.html).
2. Que traiga **el cliente**, que es lo que faltaba.
3. Que los totales sean del equipo y de nadie más — con un segundo equipo del
   mismo cliente en escena, para que un `where` que falte se note.
4. Que `lugar` diga dónde está de verdad: el depósito cuando está guardado, no
   el sector del que salió hace meses.
"""
from datetime import date, timedelta

import pytest

RUTA = "/api/dashboard/equipo/{equipo_id}"


# `client` sale de conftest.py.


@pytest.fixture
def escenario(client):
    assert client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    ).status_code == 200

    cliente_id = client.post("/api/clientes", json={
        "nombre": "Mariano", "empresa": "Compulibra SRL", "email": "c@test.com",
    }).json()["id"]
    tecnico_id = client.post("/api/tecnicos", json={"nombre": "Ana"}).json()["id"]
    proveedor_id = client.post("/api/proveedores", json={"nombre": "Service SA"}).json()["id"]

    equipo_id = client.post("/api/equipos", json={
        "cliente_id": cliente_id, "tipo": "Notebook", "marca": "Lenovo",
        "modelo": "T14", "serial": "S-1", "sector": "Admisión",
        "garantia_vence": (date.today() + timedelta(days=-10)).isoformat(),
    }).json()["id"]
    # El segundo equipo del MISMO cliente: sin él, un filtro por equipo que
    # faltara pasaría inadvertido porque los totales darían igual.
    otro_id = client.post("/api/equipos", json={
        "cliente_id": cliente_id, "tipo": "Impresora", "serial": "S-2",
    }).json()["id"]

    for equipo, titulo in ((equipo_id, "No arranca"), (otro_id, "Atasca papel")):
        client.post("/api/incidencias", json={
            "cliente_id": cliente_id, "equipo_id": equipo, "titulo": titulo,
            "tecnico_id": tecnico_id, "prioridad": "alta", "horas_invertidas": 2,
        })

    reparacion_id = client.post("/api/reparaciones", json={
        "equipo_id": equipo_id, "proveedor_id": proveedor_id,
        "fecha_envio": (date.today() - timedelta(days=10)).isoformat(),
    }).json()["id"]
    assert client.post(f"/api/reparaciones/{reparacion_id}/cerrar", json={
        "fecha_retorno": date.today().isoformat(), "costo": 15000,
        "diagnostico": "Se cambió el teclado",
    }).status_code == 200

    return {"cliente_id": cliente_id, "equipo_id": equipo_id, "otro_id": otro_id}


def test_la_ruta_existe_y_un_id_inventado_da_404(client, escenario):
    """Con el fallback de la SPA, una ruta mal escrita devolvería 200 con el
    index.html y el test pasaría igual."""
    r = client.get(RUTA.format(equipo_id=9999))

    assert r.status_code == 404
    assert r.json()["detail"] == "equipo not found"


def test_la_ficha_dice_de_que_cliente_es_el_equipo(client, escenario):
    """Lo que faltaba y motivó la pantalla."""
    ficha = client.get(RUTA.format(equipo_id=escenario["equipo_id"])).json()

    assert ficha["cliente"]["id"] == escenario["cliente_id"]
    assert ficha["cliente"]["empresa"] == "Compulibra SRL"
    assert ficha["equipo"]["descripcion"] == "Notebook Lenovo T14"


def test_los_totales_son_de_este_equipo_y_no_del_cliente(client, escenario):
    ficha = client.get(RUTA.format(equipo_id=escenario["equipo_id"])).json()

    resumen = ficha["resumen"]
    # Dos incidencias hay en la base; una sola es de este equipo.
    assert resumen["total_incidencias"] == 1
    assert resumen["incidencias_abiertas"] == 1
    assert resumen["horas_invertidas"] == 2.0
    assert resumen["total_reparaciones"] == 1
    assert resumen["reparaciones_abiertas"] == 0
    # Lo que contesta "¿lo reemplazo o lo sigo arreglando?".
    assert resumen["gastado_reparaciones"] == 15000.0
    assert resumen["dias_en_service"] == 10

    otra = client.get(RUTA.format(equipo_id=escenario["otro_id"])).json()
    assert otra["resumen"]["total_reparaciones"] == 0
    assert otra["resumen"]["gastado_reparaciones"] == 0


def test_trae_las_tres_historias_del_equipo(client, escenario):
    ficha = client.get(RUTA.format(equipo_id=escenario["equipo_id"])).json()

    assert [i["titulo"] for i in ficha["incidencias"]] == ["No arranca"]
    assert ficha["incidencias"][0]["tecnico"] == "Ana"
    assert ficha["reparaciones"][0]["proveedor_nombre"] == "Service SA"
    # El alta del equipo ya es un movimiento.
    assert any(m["tipo"] == "alta" for m in ficha["movimientos"])


def test_la_garantia_vencida_llega_con_dias_negativos(client, escenario):
    """Igual que en la ficha del cliente: el signo es lo que distingue "vence
    en 10 días" de "está vencida hace 10"."""
    ficha = client.get(RUTA.format(equipo_id=escenario["equipo_id"])).json()

    assert ficha["equipo"]["dias_garantia_restantes"] == -10


def test_guardado_en_un_deposito_el_lugar_es_el_deposito(client, escenario):
    """`lugar` es la única definición de "dónde está": con el equipo en el
    taller, el sector del que salió ya no es su ubicación."""
    taller = client.post("/api/depositos", json={"nombre": "Taller"}).json()["id"]
    client.post("/api/depositos/transferir", json={
        "equipo_ids": [escenario["equipo_id"]], "destino_id": taller,
    })

    equipo = client.get(RUTA.format(equipo_id=escenario["equipo_id"])).json()["equipo"]

    assert equipo["lugar"] == "Taller"
    assert equipo["deposito_nombre"] == "Taller"
    # El sector se conserva: es de dónde salió, y a dónde vuelve al sacarlo.
    assert equipo["sector"] == "Admisión"


def test_sin_deposito_el_lugar_es_el_sector(client, escenario):
    equipo = client.get(RUTA.format(equipo_id=escenario["equipo_id"])).json()["equipo"]

    assert equipo["lugar"] == "Admisión"
    assert equipo["deposito_nombre"] is None
