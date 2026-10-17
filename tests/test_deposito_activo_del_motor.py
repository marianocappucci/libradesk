"""El deposito por defecto y los depositos dados de baja, desde libracommerce v0.63.0 (ADR-051 del motor).

Hasta v0.16.4 el motor no miraba si un deposito estaba activo: `editar_deposito` podia apagar el por defecto, y una
venta, una recepcion de compra o una transferencia entraban o salian de un deposito dado de baja. Desde que el motor
lo rechaza (`DepositoInexistente` y `DepositoPorDefectoInactivo`, los dos `ValueError`), los routers contestan 422.
Estos tests fijan esa conducta **por la API de este producto**; si el motor la cambiara, se enteraria la suite.

No cubren el stock que un deposito ya tenia al apagarse: sigue ahi, se puede leer y se puede sacar con el ajuste
manual y con los materiales de una incidencia (que escriben el movimiento directo y no pasan por la regla).
"""
import os

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
    """Un deposito por defecto, otro activo y uno dado de baja con stock; un consumible y un proveedor."""
    item = client.post("/api/consumibles", json={"nombre": "Plug RJ45", "precio": 160}).json()
    central = client.post("/api/depositos-stock", json={"nombre": "Central", "es_default": True}).json()
    kangoo = client.post("/api/depositos-stock", json={"nombre": "Kangoo"}).json()
    viejo = client.post("/api/depositos-stock", json={"nombre": "Viejo"}).json()
    proveedor = client.post("/api/proveedores", json={"nombre": "Proveedor Ficticio"}).json()
    for dep in (central, viejo):
        r = client.post(f"/api/consumibles/{item['id']}/ajuste", json={"deposito_id": dep["id"], "cantidad": 20})
        assert r.status_code == 200, r.text
    r = client.put(f"/api/depositos-stock/{viejo['id']}", json={"nombre": "Viejo", "activo": False})
    assert r.status_code == 200, r.text
    return item, central, kangoo, viejo, proveedor


def _stock(client, item, deposito):
    return {f["id"]: f["stock"] for f in client.get(f"/api/consumibles/{item['id']}/stock").json()}[deposito["id"]]


def test_el_deposito_por_defecto_no_se_desactiva(client, escenario):
    _, central, _, _, _ = escenario

    r = client.put(f"/api/depositos-stock/{central['id']}", json={"nombre": "Central", "activo": False})

    assert r.status_code == 422, r.text
    assert "por defecto" in r.json()["detail"]
    assert [d["activo"] for d in client.get("/api/depositos-stock").json() if d["id"] == central["id"]] == [True]


def test_un_deposito_que_no_es_el_por_defecto_si_se_desactiva(client, escenario):
    _, _, kangoo, _, _ = escenario

    r = client.put(f"/api/depositos-stock/{kangoo['id']}", json={"nombre": "Kangoo", "activo": False})

    assert r.status_code == 200, r.text


def test_una_venta_no_sale_de_un_deposito_dado_de_baja(client, escenario):
    item, _, _, viejo, _ = escenario

    r = client.post("/api/ventas", json={
        "deposito_id": viejo["id"],
        "items": [{"item_id": item["id"], "descripcion": "Plug", "cantidad": 1, "precio": 160}],
        "pagos": [{"medio": "efectivo", "monto": 160}],
    })

    assert r.status_code == 422, r.text
    assert "no existe o no está activo" in r.json()["detail"]
    assert _stock(client, item, viejo) == 20
    assert client.get("/api/ventas").json() == []


def test_una_recepcion_de_compra_no_entra_a_un_deposito_dado_de_baja(client, escenario):
    item, _, _, viejo, proveedor = escenario

    r = client.post("/api/recepciones-compra", json={
        "proveedor_id": proveedor["id"], "deposito_id": viejo["id"],
        "items": [{"item_id": item["id"], "cantidad": 5, "costo": 90}],
    })

    assert r.status_code == 422, r.text
    assert "no existe o no está activo" in r.json()["detail"]
    assert _stock(client, item, viejo) == 20
    assert client.get("/api/recepciones-compra").json() == []


@pytest.mark.parametrize("sentido", ["hacia", "desde"])
def test_una_transferencia_no_toca_un_deposito_dado_de_baja(client, escenario, sentido):
    item, central, _, viejo, _ = escenario
    origen, destino = (central, viejo) if sentido == "hacia" else (viejo, central)

    r = client.post("/api/consumibles/transferir", json={
        "item_id": item["id"], "origen_id": origen["id"], "destino_id": destino["id"], "cantidad": 5,
    })

    assert r.status_code == 422, r.text
    assert "no existe o no está activo" in r.json()["detail"]
    assert (_stock(client, item, central), _stock(client, item, viejo)) == (20, 20)


def test_el_camino_normal_sigue_andando(client, escenario):
    """Control: con depositos activos la venta, la recepcion y la transferencia entran como siempre."""
    item, central, kangoo, _, proveedor = escenario

    venta = client.post("/api/ventas", json={
        "deposito_id": central["id"],
        "items": [{"item_id": item["id"], "descripcion": "Plug", "cantidad": 2, "precio": 160}],
        "pagos": [{"medio": "efectivo", "monto": 320}],
    })
    recepcion = client.post("/api/recepciones-compra", json={
        "proveedor_id": proveedor["id"], "deposito_id": kangoo["id"],
        "items": [{"item_id": item["id"], "cantidad": 10, "costo": 90}],
    })
    transferencia = client.post("/api/consumibles/transferir", json={
        "item_id": item["id"], "origen_id": kangoo["id"], "destino_id": central["id"], "cantidad": 4,
    })

    assert (venta.status_code, recepcion.status_code, transferencia.status_code) == (201, 201, 200)
    assert (_stock(client, item, central), _stock(client, item, kangoo)) == (22, 6)
