"""Las listas de precios llegan a la venta y al presupuesto.

Antes de esto las listas se resolvían en **dos** de los cuatro circuitos: los
materiales de un reclamo y los cargos de mano de obra. La venta prellenaba el
precio del catálogo y el presupuesto sugería el del catálogo, así que las tres
listas de Lagrace seguían sin aplicarse donde más se usa.

🔑 **Esto no se podía hacer antes de mudar los servicios al catálogo**: el
formulario de presupuestos sugería desde la tabla vieja, y resolver precios ahí
habría mezclado ids de los dos espacios — el pozo que en dev costó $29.000 en vez
de $43.000 sin fallar nada.

Lo que fijan estos tests:

1. 🔴 **Que la sugerencia del presupuesto traiga el precio del cliente.** Es lo
   que ve quien arma el comprobante, y si muestra uno y el comprobante sale con
   otro, el número que se acordó con el cliente no es el que se factura.
2. 🔴 **Que el resolvedor respete la precedencia** — operación sobre cliente.
3. 🔴 **Que sin cliente y sin lista siga cotizando como antes.** Es lo que hace
   que enchufar esto no mueva ningún precio.
"""

import os

import pytest

from app.services import inventario, listas_precio


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
    """Un servicio a $15.000 de catálogo, con $9.000 para resellers."""
    cliente = client.post("/api/clientes", json={"nombre": "Medici Neumatec"}).json()
    servicio = client.post("/api/servicios", json={
        "nombre": "Hora de servicio técnico", "precio": 15000, "iva_rate": 0.21,
    }).json()
    producto = inventario.crear_item("Cable UTP", precio=1000.0)
    reseller = listas_precio.crear("Resellers")
    listas_precio.fijar_precio(reseller["id"], servicio["id"], 9000.0)
    listas_precio.fijar_precio(reseller["id"], producto["id"], 700.0)
    return client, cliente, servicio, producto, reseller


def _asignar(client, cliente_id, lista_id):
    ficha = client.get(f"/api/clientes/{cliente_id}").json()
    r = client.put(f"/api/clientes/{cliente_id}",
                   json={**ficha, "price_list_id": lista_id})
    assert r.status_code == 200, r.text


# ── 1. La sugerencia del presupuesto ─────────────────────────────────────


def test_la_sugerencia_trae_el_precio_del_cliente(escenario):
    """🔴 Es lo que ve quien arma el comprobante. Si muestra un número y el
    comprobante sale con otro, el precio que se acordó no es el que se factura."""
    client, cliente, _s, _p, reseller = escenario
    _asignar(client, cliente["id"], reseller["id"])

    r = client.get(f"/api/servicios/buscar?q=Hora&cliente_id={cliente['id']}")
    assert r.status_code == 200, r.text
    assert r.json()[0]["precio"] == pytest.approx(9000.0)


def test_sin_cliente_la_sugerencia_cotiza_como_antes(escenario):
    """🔴 La garantía de que enchufar esto no movió nada."""
    client, _c, _s, _p, _r = escenario
    r = client.get("/api/servicios/buscar?q=Hora")
    assert r.json()[0]["precio"] == pytest.approx(15000.0)


def test_la_lista_de_la_operacion_pisa_en_la_sugerencia(escenario):
    client, cliente, _s, _p, reseller = escenario
    # El cliente NO tiene lista asignada; la operación elige una igual.
    r = client.get(
        f"/api/servicios/buscar?q=Hora&cliente_id={cliente['id']}"
        f"&lista_id={reseller['id']}"
    )
    assert r.json()[0]["precio"] == pytest.approx(9000.0)


def test_una_busqueda_sin_resultados_no_explota(escenario):
    client, cliente, *_ = escenario
    r = client.get(f"/api/servicios/buscar?q=zzzz&cliente_id={cliente['id']}")
    assert r.status_code == 200
    assert r.json() == []


# ── 2. El resolvedor que usa la venta ────────────────────────────────────


def test_el_resolvedor_da_el_precio_del_cliente(escenario):
    client, cliente, _s, producto, reseller = escenario
    _asignar(client, cliente["id"], reseller["id"])

    r = client.get(
        f"/api/precios/resolver?item_id={producto['id']}&cliente_id={cliente['id']}"
    )
    assert r.status_code == 200, r.text
    assert r.json()["precio"] == pytest.approx(700.0)


def test_el_resolvedor_sin_cliente_da_el_del_catalogo(escenario):
    """La venta de mostrador sigue cotizando como cotizaba."""
    client, _c, _s, producto, _r = escenario
    r = client.get(f"/api/precios/resolver?item_id={producto['id']}")
    assert r.json()["precio"] == pytest.approx(1000.0)


def test_el_resolvedor_respeta_la_precedencia(escenario):
    """🔴 La operación pisa al cliente. Si se invierte se factura mal y nada
    falla."""
    client, cliente, _s, producto, reseller = escenario
    general = listas_precio.crear("Mayorista")
    listas_precio.fijar_precio(general["id"], producto["id"], 850.0)
    _asignar(client, cliente["id"], reseller["id"])   # el cliente es reseller ($700)

    r = client.get(
        f"/api/precios/resolver?item_id={producto['id']}"
        f"&cliente_id={cliente['id']}&lista_id={general['id']}"
    )
    assert r.json()["precio"] == pytest.approx(850.0), (
        "la lista de la operación tiene que pisar a la del cliente"
    )


def test_un_item_inexistente_da_cero_y_no_500(escenario):
    client, *_ = escenario
    r = client.get("/api/precios/resolver?item_id=999999")
    assert r.status_code == 200
    assert r.json()["precio"] == pytest.approx(0.0)
