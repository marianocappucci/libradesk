"""De una venta al remito — el camino a facturación que la venta no tenía.

Hasta el 2026-08-16 una venta registraba, descontaba stock y debitaba la cuenta
corriente, y **no tenía ningún camino a facturarse**: la bandeja acepta sólo
remitos y una venta no generaba ninguno. Mientras tanto la pantalla ya prometía
lo contrario.

Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que el remito de una venta NO debite en cuenta corriente.** Es la
   decisión de fondo del cambio y la que produce plata mal contada si se rompe:
   una venta en cuenta corriente quedaría debiendo el doble, y una venta ya
   cobrada quedaría debiendo algo que el cliente pagó.
2. 🔴 **Que una venta no se pueda facturar dos veces.** La conversión es
   idempotente y el vínculo queda guardado.
3. 🔴 **Que una venta sin cliente no emita un remito a nombre de nadie**, y que
   con la venta ya identificada no se pueda emitir a nombre de otro.
4. **Que la alícuota de cada línea salga del catálogo**, que es lo que hace que
   la factura de SOS pueda discriminar IVA.
5. Que una venta anulada o devuelta no se convierta.
"""

import os
from datetime import datetime

import pytest

from app.services import cuenta_corriente, inventario, iva, ventas

CUANDO = datetime(2026, 8, 16, 10, 0, 0)


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin."""
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def escenario(client):
    """Un cliente, un depósito con stock, y dos productos con alícuotas DISTINTAS.

    Las alícuotas distintas son el punto: con los dos al 21% el test pasaría
    aunque la conversión le pusiera a todo el default, que es exactamente el
    defecto que tiene que poder ver.
    """
    cliente = client.post("/api/clientes", json={
        "nombre": "Medici Neumatec", "empresa": "NEUMYSER SRL",
        "cuit": "30-11111111-7", "ciudad": "Chivilcoy",
    }).json()
    central = inventario.crear_item(
        "Central HiPath 1120", costo=80000.0, precio=200000.0,
        iva_rate=iva.DEFECTO,                      # 21%
    )
    libro = inventario.crear_item(
        "Manual de usuario", costo=1000.0, precio=4000.0,
        iva_rate="0.105",                          # 10,5%
    )
    deposito = inventario.crear_deposito("Depósito central")
    inventario.ajustar(central["id"], deposito["id"], 5, fecha=CUANDO)
    inventario.ajustar(libro["id"], deposito["id"], 20, fecha=CUANDO)
    return client, cliente, central, libro, deposito


def _vender(client, deposito, *, cliente_id=None, items=None, pagos=None):
    r = client.post("/api/ventas", json={
        "cliente_id": cliente_id,
        "items": items,
        "pagos": pagos or [],
        "deposito_id": deposito["id"],
    })
    assert r.status_code == 201, r.text
    return r.json()


def _convertir(client, venta_id, **cuerpo):
    return client.post(
        f"/api/ventas/{venta_id}/convertir-en-remito", json=cuerpo or {},
    )


# ── 1. El débito, que es la decisión de fondo ────────────────────────────


def test_el_remito_de_una_venta_no_debita_en_cuenta_corriente(escenario):
    """La venta ya registró lo que el cliente debe. El remito no lo vuelve a cargar.

    Se mide el saldo **antes y después** del envío, no sólo después: un saldo
    "correcto" leído una sola vez no distingue "no se debitó" de "se debitó y la
    venta no había cargado nada".
    """
    client, cliente, central, _libro, deposito = escenario
    _vender(
        client, deposito, cliente_id=cliente["id"],
        items=[{"item_id": central["id"], "descripcion": "Central",
                "cantidad": 1, "precio": 200000.0}],
        pagos=[{"medio": "cuenta_corriente", "monto": 200000.0}],
    )
    venta_id = client.get("/api/ventas").json()[0]["id"]

    saldo_antes = cuenta_corriente.saldo(cliente["id"])
    assert saldo_antes == pytest.approx(200000.0), (
        "la venta en cuenta corriente ya tiene que haber cargado la deuda"
    )

    r = _convertir(client, venta_id)
    assert r.status_code == 201, r.text
    remito_id = r.json()["id"]

    # El corte vive en el puente, así que se lo llama como lo llama el envío.
    # El puente real de la app, igual que `test_facturacion_debita_cuenta_corriente`.
    client.app.state.puente_facturacion._debitar_en_cuenta_corriente(
        "remito", {"id": remito_id, "client_id": cliente["id"],
                   "total": 200000.0, "number": "REM-00000001"},
    )

    assert cuenta_corriente.saldo(cliente["id"]) == pytest.approx(saldo_antes), (
        "el remito de una venta no puede volver a debitar: la deuda ya estaba"
    )


def test_un_remito_que_no_viene_de_una_venta_si_debita(escenario):
    """La contraprueba, y es la que hace que el test de arriba signifique algo.

    Sin esto, un `_debitar_en_cuenta_corriente` que no debitara **nunca** pasaría
    el test anterior en verde.
    """
    client, cliente, _central, _libro, _deposito = escenario
    remito = client.post("/api/remitos", json={
        "date": "2026-08-16", "client_id": cliente["id"],
        "client_name": "NEUMYSER SRL", "client_cuit": "30-11111111-7",
        "items": [{"description": "Trabajo", "qty": 1, "unit_price": 50000.0}],
    }).json()

    client.app.state.puente_facturacion._debitar_en_cuenta_corriente(
        "remito", {"id": remito["id"], "client_id": cliente["id"],
                   "total": 50000.0, "number": remito.get("number") or "REM-1"},
    )

    assert cuenta_corriente.saldo(cliente["id"]) == pytest.approx(50000.0), (
        "un remito de un reclamo sí tiene que debitar — si no, el corte de "
        "arriba está apagando el débito de todo el mundo"
    )


# ── 2. Idempotencia ──────────────────────────────────────────────────────


def test_convertir_dos_veces_devuelve_el_mismo_remito(escenario):
    client, cliente, central, _libro, deposito = escenario
    _vender(
        client, deposito, cliente_id=cliente["id"],
        items=[{"item_id": central["id"], "descripcion": "Central",
                "cantidad": 1, "precio": 200000.0}],
    )
    venta_id = client.get("/api/ventas").json()[0]["id"]

    primero = _convertir(client, venta_id)
    segundo = _convertir(client, venta_id)

    assert primero.status_code == 201 and segundo.status_code == 201
    assert primero.json()["id"] == segundo.json()["id"], (
        "el doble click no puede emitir dos remitos por la misma venta"
    )
    assert len(client.get("/api/remitos").json()) == 1


def test_el_vinculo_queda_guardado(escenario):
    client, cliente, central, _libro, deposito = escenario
    _vender(
        client, deposito, cliente_id=cliente["id"],
        items=[{"item_id": central["id"], "descripcion": "Central",
                "cantidad": 1, "precio": 200000.0}],
    )
    venta_id = client.get("/api/ventas").json()[0]["id"]
    remito_id = _convertir(client, venta_id).json()["id"]

    assert ventas.remito_de(venta_id) == remito_id
    assert ventas.nacio_de_una_venta(remito_id) is True


# ── 3. A nombre de quién ─────────────────────────────────────────────────


def test_una_venta_sin_cliente_no_se_convierte_sola(escenario):
    client, _cliente, central, _libro, deposito = escenario
    _vender(
        client, deposito, cliente_id=None,
        items=[{"item_id": central["id"], "descripcion": "Central",
                "cantidad": 1, "precio": 200000.0}],
    )
    venta_id = client.get("/api/ventas").json()[0]["id"]

    r = _convertir(client, venta_id)
    assert r.status_code == 409
    assert "sin cliente" in r.json()["detail"]


def test_una_venta_sin_cliente_se_convierte_eligiendo_uno(escenario):
    client, cliente, central, _libro, deposito = escenario
    _vender(
        client, deposito, cliente_id=None,
        items=[{"item_id": central["id"], "descripcion": "Central",
                "cantidad": 1, "precio": 200000.0}],
    )
    venta_id = client.get("/api/ventas").json()[0]["id"]

    r = _convertir(client, venta_id, cliente_id=cliente["id"])
    assert r.status_code == 201, r.text
    assert r.json()["client_cuit"] == "30-11111111-7"


def test_no_se_emite_a_nombre_de_otro_si_la_venta_ya_tiene_cliente(escenario):
    client, cliente, central, _libro, deposito = escenario
    otro = client.post("/api/clientes", json={
        "nombre": "Otro", "empresa": "OTRO SRL", "ciudad": "Suipacha",
    }).json()
    _vender(
        client, deposito, cliente_id=cliente["id"],
        items=[{"item_id": central["id"], "descripcion": "Central",
                "cantidad": 1, "precio": 200000.0}],
    )
    venta_id = client.get("/api/ventas").json()[0]["id"]

    r = _convertir(client, venta_id, cliente_id=otro["id"])
    assert r.status_code == 409
    assert "mismo" in r.json()["detail"]


# ── 4. La alícuota sale del catálogo ─────────────────────────────────────


def test_cada_linea_lleva_la_alicuota_de_su_producto(escenario):
    """Dos productos con alícuotas distintas tienen que salir distintos.

    Es lo que le permite a SOS discriminar el IVA. Con los dos al 21% este test
    pasaría aunque la conversión le pusiera el default a todo.
    """
    client, cliente, central, libro, deposito = escenario
    _vender(
        client, deposito, cliente_id=cliente["id"],
        items=[
            {"item_id": central["id"], "descripcion": "Central",
             "cantidad": 1, "precio": 200000.0},
            {"item_id": libro["id"], "descripcion": "Manual",
             "cantidad": 2, "precio": 4000.0},
        ],
    )
    venta_id = client.get("/api/ventas").json()[0]["id"]
    remito_id = _convertir(client, venta_id).json()["id"]

    items = client.get(f"/api/remitos/{remito_id}").json()["items"]
    por_nombre = {i["description"]: float(i["tax_rate"]) for i in items}
    assert por_nombre["Central"] == pytest.approx(0.21)
    assert por_nombre["Manual"] == pytest.approx(0.105)


def test_una_linea_de_servicio_sale_con_la_alicuota_de_defecto(escenario):
    """Sin `item_id` no hay producto del que leerla."""
    client, cliente, _central, _libro, deposito = escenario
    _vender(
        client, deposito, cliente_id=cliente["id"],
        items=[{"item_id": None, "descripcion": "Instalación",
                "cantidad": 1, "precio": 30000.0}],
    )
    venta_id = client.get("/api/ventas").json()[0]["id"]
    remito_id = _convertir(client, venta_id).json()["id"]

    items = client.get(f"/api/remitos/{remito_id}").json()["items"]
    assert float(items[0]["tax_rate"]) == pytest.approx(float(iva.DEFECTO))


def test_editar_un_producto_no_le_borra_la_alicuota(escenario):
    """🔴 `save_catalog_item()` pisa la fila entera: sin el rescate de
    `editar_item`, corregir el precio dejaba el producto sin IVA."""
    _client, _cliente, _central, libro, _deposito = escenario
    assert inventario.alicuotas_de_items([libro["id"]])[libro["id"]] == iva.validar("0.105")

    inventario.editar_item(
        libro["id"], nombre="Manual de usuario", costo=1000.0, precio=4500.0,
    )

    assert inventario.alicuotas_de_items([libro["id"]])[libro["id"]] == iva.validar("0.105"), (
        "editar el precio no puede borrar la alícuota"
    )


def test_una_alicuota_que_arca_no_mapea_se_rechaza(escenario):
    """13% no es una de las cuatro: entra y se declararía como 21% sin aviso."""
    with pytest.raises(iva.AlicuotaInvalida):
        inventario.crear_item("Cosa rara", precio=100.0, iva_rate="0.13")


def test_la_alicuota_se_carga_y_se_lee_por_la_API(escenario):
    """El cableado del router, que es por donde la carga la pantalla."""
    client, *_ = escenario
    r = client.post("/api/consumibles", json={
        "nombre": "Ficha telefónica", "precio": 900.0, "iva_rate": 0.105,
    })
    assert r.status_code == 201, r.text

    fila = next(
        p for p in client.get("/api/consumibles").json()
        if p["nombre"] == "Ficha telefónica"
    )
    assert fila["iva_rate"] == pytest.approx(0.105)


def test_un_PUT_que_no_manda_la_alicuota_no_la_borra(escenario):
    """🔴 El caso real del rescate: un cliente viejo de la API, o cualquier
    pantalla que no muestre el campo, guardando el precio."""
    client, *_ = escenario
    creado = client.post("/api/consumibles", json={
        "nombre": "Ficha telefónica", "precio": 900.0, "iva_rate": 0.105,
    }).json()

    r = client.put(f"/api/consumibles/{creado['id']}", json={
        "nombre": "Ficha telefónica", "precio": 1200.0,   # sin `iva_rate`
    })
    assert r.status_code == 200, r.text

    fila = next(
        p for p in client.get("/api/consumibles").json()
        if p["id"] == creado["id"]
    )
    assert fila["precio"] == pytest.approx(1200.0), "el precio sí tenía que cambiar"
    assert fila["iva_rate"] == pytest.approx(0.105), (
        "guardar el precio no puede llevarse puesta la alícuota"
    )


def test_una_alicuota_invalida_por_la_API_da_422(escenario):
    client, *_ = escenario
    r = client.post("/api/consumibles", json={
        "nombre": "Cosa rara", "precio": 100.0, "iva_rate": 0.13,
    })
    assert r.status_code == 422
    assert "13" in r.json()["detail"]


# ── 5. Estados que no se convierten ──────────────────────────────────────


@pytest.fixture
def venta_id(escenario):
    client, cliente, central, _libro, deposito = escenario
    _vender(
        client, deposito, cliente_id=cliente["id"],
        items=[{"item_id": central["id"], "descripcion": "Central",
                "cantidad": 1, "precio": 200000.0}],
    )
    return client.get("/api/ventas").json()[0]["id"]


@pytest.mark.parametrize("parche, error, por_que", [
    ({"items": []}, "vacío", "el alta por la API exige ítems"),
    ({"estado": "cancelled"}, "cancelled", "hoy no hay forma de anular una venta"),
    ({"estado": "returned"}, "returned", "ni de registrar una devolución total"),
])
def test_lo_que_no_se_convierte(monkeypatch, venta_id, parche, error, por_que):
    """Se prueba contra el servicio y no por HTTP **a propósito**.

    Ninguno de estos tres estados se puede producir hoy desde la aplicación —se
    verificó: no existe ningún endpoint que anule una venta ni que registre una
    devolución, y el alta rechaza una venta sin ítems—. O sea que por la API el
    test se saltearía siempre, que es un verde que no ejercita nada.

    Las guardas igual son reales: `sales.status` **sí** admite esos valores (los
    declara el motor), y una devolución es funcionalidad que este producto va a
    tener. Mismo criterio y misma forma que
    `test_lo_que_no_se_puede_debitar_se_saltea_sin_romper`.
    """
    original = ventas.obtener
    monkeypatch.setattr(
        ventas, "obtener",
        lambda vid: {**original(vid), **parche} if original(vid) else None,
    )
    with pytest.raises(ValueError, match=error):
        ventas.convertir_a_remito(venta_id, remitos=None, clientes=None), por_que
