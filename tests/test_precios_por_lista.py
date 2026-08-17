"""Que las listas de precios sirvan para algo.

Hasta el 2026-08-16 Lagrace tenía **tres listas con 43 precios cargados** y
**ningún circuito las aplicaba**: ni ventas, ni remitos, ni presupuestos, ni los
materiales de un reclamo. Todo cotizaba por `default_sale_price`. Alguien cargó
esos precios creyendo que servían.

Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **La precedencia**: la lista de la operación pisa a la del cliente, y la
   del cliente pisa a la de defecto. Es la decisión del humano, y si se invierte
   se factura mal sin que nada falle.
2. 🔴 **Que enchufar esto no mueva ningún precio de hoy.** Una lista que no
   tiene cargado el ítem cae al catálogo — si no, correr la migración le
   cambiaría el precio a todo lo que no esté en ninguna lista.
3. 🔴 **Que el remito de un reclamo valorice por la lista del cliente.** Es el
   circuito donde el precio termina en un comprobante que se factura.
"""

import os

import pytest

from app.services import listas_precio, precios


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
    """Un producto a $1.000 de catálogo, y dos listas con precios distintos.

    Los tres valores distintos son el punto: con dos, no se distingue cuál de
    las dos reglas de precedencia se aplicó.
    """
    from app.services import inventario

    item = inventario.crear_item("Cable UTP", costo=400.0, precio=1000.0)
    general = [l for l in listas_precio.listar() if l.get("es_default")]
    reseller = listas_precio.crear("Resellers")
    mostrador = listas_precio.crear("Mostrador")

    listas_precio.fijar_precio(reseller["id"], item["id"], 700.0)
    listas_precio.fijar_precio(mostrador["id"], item["id"], 1200.0)

    cliente = client.post("/api/clientes", json={"nombre": "Reseller SRL"}).json()
    return client, item, reseller, mostrador, cliente, general


def _asignar_lista(client, cliente_id, lista_id):
    ficha = client.get(f"/api/clientes/{cliente_id}").json()
    r = client.put(f"/api/clientes/{cliente_id}",
                   json={**ficha, "price_list_id": lista_id})
    assert r.status_code == 200, r.text


# ── 1. La precedencia ────────────────────────────────────────────────────


def test_sin_lista_asignada_cotiza_por_el_catalogo(escenario):
    """El comportamiento de hoy, que no se puede mover: los 14 clientes de
    Lagrace no tienen lista y ninguno puede cambiar de precio."""
    _client, item, _res, _most, cliente, _gen = escenario
    assert precios.precio_de(item["id"], cliente_id=cliente["id"]) == pytest.approx(1000.0)


def test_la_lista_del_cliente_manda_sobre_el_catalogo(escenario):
    client, item, reseller, _most, cliente, _gen = escenario
    _asignar_lista(client, cliente["id"], reseller["id"])

    assert precios.precio_de(item["id"], cliente_id=cliente["id"]) == pytest.approx(700.0)


def test_la_lista_de_la_operacion_pisa_a_la_del_cliente(escenario):
    """🔴 La decisión del humano. Si se invierte, se factura mal y nada falla."""
    client, item, reseller, mostrador, cliente, _gen = escenario
    _asignar_lista(client, cliente["id"], reseller["id"])

    # El cliente es reseller ($700) pero esta operación puntual va a mostrador.
    assert precios.precio_de(
        item["id"], cliente_id=cliente["id"], lista_id=mostrador["id"],
    ) == pytest.approx(1200.0)


def test_sin_cliente_la_operacion_igual_manda(escenario):
    """Una venta de mostrador sin cliente puede elegir lista igual."""
    _client, item, reseller, _most, _cli, _gen = escenario
    assert precios.precio_de(
        item["id"], lista_id=reseller["id"],
    ) == pytest.approx(700.0)


# ── 2. Que no mueva nada de lo que hoy funciona ──────────────────────────


def test_una_lista_sin_ese_item_cae_al_catalogo(escenario):
    """🔴 Es lo que hace que enchufar las listas no cambie ningún precio.

    Sin esta caída, asignarle una lista a un cliente le pondría **cero** a todo
    lo que esa lista no tenga cargado — que al principio es casi todo.
    """
    client, _item, reseller, _most, cliente, _gen = escenario
    from app.services import inventario

    otro = inventario.crear_item("Ficha RJ45", precio=350.0)
    _asignar_lista(client, cliente["id"], reseller["id"])

    assert precios.precio_de(otro["id"], cliente_id=cliente["id"]) == pytest.approx(350.0)


def test_un_item_que_no_existe_da_cero_y_no_explota(escenario):
    """Mismo criterio que `materiales.valorizados()`: inventar un precio sería
    peor, y la bandeja se niega a mandar un comprobante en cero."""
    assert precios.precio_de(999999) == pytest.approx(0.0)


# ── 3. El circuito donde el precio termina en un comprobante ─────────────


def test_el_remito_de_un_reclamo_valoriza_por_la_lista_del_cliente(escenario):
    """🔴 Es el circuito que factura. Antes de esto, un reseller y un cliente de
    mostrador pagaban lo mismo por el mismo cable."""
    client, item, reseller, _most, cliente, _gen = escenario
    from app.services import inventario

    _asignar_lista(client, cliente["id"], reseller["id"])
    deposito = inventario.crear_deposito("Depósito")
    inventario.ajustar(item["id"], deposito["id"], 20)

    inc = client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "titulo": "Cableado", "horas_invertidas": 1,
    }).json()
    client.post(f"/api/incidencias/{inc['id']}/materiales", json={
        "item_id": item["id"], "deposito_id": deposito["id"], "cantidad": 2,
    })
    ficha = client.get(f"/api/incidencias/{inc['id']}").json()
    client.put(f"/api/incidencias/{inc['id']}", json={**ficha, "estado": "cerrado"})

    remito = client.post("/api/incidencias/convertir-en-remito",
                         json={"incidencia_ids": [inc["id"]]}).json()

    linea = next(i for i in remito["items"] if "Cable UTP" in i["description"])
    assert float(linea["unit_price"]) == pytest.approx(700.0), (
        "el material tiene que salir al precio de reseller, no al de catálogo"
    )
