"""Los endpoints de stock, y el gate del modulo.

El test que mas importa es el del gate: sin el modulo `stock` **ninguno** de
estos endpoints tiene que existir, incluidos los materiales de una incidencia
--que cuelgan del mismo modulo porque sin stock no hay de donde descontar.
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
    item = client.post("/api/consumibles", json={
        "nombre": "Plug RJ45", "stock_minimo": 50,
    }).json()
    central = client.post("/api/depositos-stock", json={
        "nombre": "Central", "es_default": True,
    }).json()
    camioneta = client.post("/api/depositos-stock", json={"nombre": "Kangoo"}).json()
    client.post(f"/api/consumibles/{item['id']}/ajuste", json={
        "deposito_id": central["id"], "cantidad": 189, "nota": "Carga inicial",
    })
    return item, central, camioneta


def test_alta_de_consumible_y_deposito(client):
    item = client.post("/api/consumibles", json={"nombre": "Cable UTP"})
    assert item.status_code == 201, item.text
    dep = client.post("/api/depositos-stock", json={"nombre": "Central"})
    assert dep.status_code == 201, dep.text
    assert [c["nombre"] for c in client.get("/api/consumibles").json()] == ["Cable UTP"]


def test_el_stock_lista_todos_los_depositos_incluidos_los_vacios(client, escenario):
    """La pregunta es "¿de donde saco un plug?": un deposito que falta de la
    lista es indistinguible de uno que existe y esta en cero."""
    item, central, camioneta = escenario

    filas = client.get(f"/api/consumibles/{item['id']}/stock").json()

    por_id = {f["id"]: f["stock"] for f in filas}
    assert por_id[central["id"]] == 189
    assert por_id[camioneta["id"]] == 0


def test_ajuste_suma_y_resta(client, escenario):
    item, central, _ = escenario

    r = client.post(f"/api/consumibles/{item['id']}/ajuste", json={
        "deposito_id": central["id"], "cantidad": -9,
    })

    assert r.status_code == 200
    assert r.json()["stock"] == 180


def test_no_se_puede_ajustar_a_negativo(client, escenario):
    item, central, _ = escenario

    r = client.post(f"/api/consumibles/{item['id']}/ajuste", json={
        "deposito_id": central["id"], "cantidad": -200,
    })

    assert r.status_code == 422
    assert "insuficiente" in r.json()["detail"].lower()


def test_transferencia_por_la_api(client, escenario):
    item, central, camioneta = escenario

    r = client.post("/api/consumibles/transferir", json={
        "item_id": item["id"], "origen_id": central["id"],
        "destino_id": camioneta["id"], "cantidad": 40,
    })

    assert r.status_code == 200, r.text
    por_id = {f["id"]: f["stock"]
              for f in client.get(f"/api/consumibles/{item['id']}/stock").json()}
    assert por_id[central["id"]] == 149
    assert por_id[camioneta["id"]] == 40


def test_transferir_al_mismo_deposito_se_rechaza(client, escenario):
    item, central, _ = escenario

    r = client.post("/api/consumibles/transferir", json={
        "item_id": item["id"], "origen_id": central["id"],
        "destino_id": central["id"], "cantidad": 1,
    })

    assert r.status_code == 422


# ── Materiales de una incidencia, por la API ─────────────────────────────


@pytest.fixture
def incidencia(client):
    cliente = client.post("/api/clientes", json={"nombre": "Lagrace"}).json()
    return client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "titulo": "Central sin tono",
        "descripcion": "No hay tono",
    }).json()


def test_cargar_material_descuenta_y_listarlo(client, escenario, incidencia):
    item, central, _ = escenario

    r = client.post(f"/api/incidencias/{incidencia['id']}/materiales", json={
        "item_id": item["id"], "deposito_id": central["id"], "cantidad": 10,
    })

    assert r.status_code == 201, r.text
    cargados = client.get(f"/api/incidencias/{incidencia['id']}/materiales").json()
    assert [m["cantidad"] for m in cargados] == [10]
    por_id = {f["id"]: f["stock"]
              for f in client.get(f"/api/consumibles/{item['id']}/stock").json()}
    assert por_id[central["id"]] == 179


def test_quitar_material_devuelve_el_stock(client, escenario, incidencia):
    item, central, _ = escenario
    material = client.post(f"/api/incidencias/{incidencia['id']}/materiales", json={
        "item_id": item["id"], "deposito_id": central["id"], "cantidad": 10,
    }).json()

    r = client.delete(
        f"/api/incidencias/{incidencia['id']}/materiales/{material['id']}"
    )

    assert r.status_code == 204
    assert client.get(f"/api/incidencias/{incidencia['id']}/materiales").json() == []
    por_id = {f["id"]: f["stock"]
              for f in client.get(f"/api/consumibles/{item['id']}/stock").json()}
    assert por_id[central["id"]] == 189


def test_no_se_puede_consumir_lo_que_no_hay(client, escenario, incidencia):
    item, _, camioneta = escenario

    r = client.post(f"/api/incidencias/{incidencia['id']}/materiales", json={
        "item_id": item["id"], "deposito_id": camioneta["id"], "cantidad": 1,
    })

    assert r.status_code == 422


# ── El gate del modulo ───────────────────────────────────────────────────
#
# NO vive aca: esta en `tests/test_modulos_y_planes.py`, que es donde ya viven
# los de los otros cinco modulos y --sobre todo-- donde esta `_existe_de_verdad`,
# la guarda contra el fallback de la SPA. `asgi.py` monta
# `/{full_path:path}` -> index.html, asi que **cualquier ruta inventada
# devuelve 200 con HTML** y un test de gating que apunte al path equivocado
# pasa en verde sin haber ejercitado nada.
#
# La primera version de este archivo tenia su propio test de gate apagando el
# modulo con `PUT /api/modulos/stock`, un endpoint que no existe. Habria dado
# un 404 disfrazado de "no llegue a probar el gate".
