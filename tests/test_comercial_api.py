"""El módulo comercial **por la API**, no por los servicios.

Existe por un defecto concreto y de una clase que se repite: el router de
cuenta corriente llamaba a `create_cc_pago()` por keyword y sin `caja_id`, que
en LibraCore **no tiene default**. Los servicios estaban probados de punta a
punta contra PostgreSQL y el saldo daba bien; el `TypeError` aparecía recién al
apretar «Cobrar» en la pantalla.

O sea: probar el servicio no prueba el endpoint. Todo lo que sigue entra por
HTTP y hace altas de verdad — un alta se prueba dando de alta.

Los módulos comerciales están gateados por plan, pero **sin plan asignado todo
queda habilitado** (es la garantía de adopción que fija
`test_modulos_y_planes.py`), así que estos tests no encienden nada. La primera
versión de este archivo abría cada test con `PUT /api/modulos/<m>`, **un
endpoint que no existe** — el mismo error que ya está anotado en
`test_api_stock.py`, y que acá habría hecho fallar la fixture antes de
ejercitar una sola ruta.
"""
import pytest


def _login(client) -> None:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200


@pytest.fixture
def comercial(client):
    """Cliente autenticado. Sin plan asignado los módulos están habilitados."""
    _login(client)
    return client


def _crear_base(c):
    """Sucursal, depósito, proveedor, cliente y un producto. Devuelve sus ids."""
    suc = c.post("/api/sucursales", json={"nombre": "CHIVILCOY", "codigo": "CHI"})
    assert suc.status_code == 201, suc.text

    dep = c.post("/api/depositos-stock", json={
        "nombre": "DEPOSITO CENTRAL", "es_default": True,
        "sucursal_id": suc.json()["id"],
    })
    assert dep.status_code == 201, dep.text

    prov = c.post("/api/proveedores", json={"nombre": "Unify Argentina"})
    assert prov.status_code == 201, prov.text

    cli = c.post("/api/clientes", json={
        "nombre": "Neumyser S.A.", "email": "n@t.com", "ciudad": "Chivilcoy",
    })
    assert cli.status_code == 201, cli.text

    prod = c.post("/api/consumibles", json={
        "nombre": "PLUG RJ 45 CAT 6", "costo": 95, "precio": 160,
        "stock_minimo": 50, "codigo": "10000315",
    })
    assert prod.status_code == 201, prod.text

    return {
        "sucursal": suc.json()["id"], "deposito": dep.json()["id"],
        "proveedor": prov.json()["id"], "cliente": cli.json()["id"],
        "producto": prod.json()["id"],
    }


def test_el_circuito_completo_por_la_api(comercial):
    """Compra → stock → venta en cuenta corriente → cobro → recibo.

    Es un solo test y no seis porque lo que se verifica es que las piezas se
    enganchen: cada paso consume el id del anterior. Seis tests aislados con
    fixtures propias probarían seis endpoints y ninguna de las cinco uniones,
    que es donde estuvo el defecto que motivó este archivo.
    """
    c = comercial
    ids = _crear_base(c)

    # --- La recepción de compra es la que genera stock -----------------------
    r = c.post("/api/recepciones-compra", json={
        "proveedor_id": ids["proveedor"], "deposito_id": ids["deposito"],
        "documento": "FC A 0001-00012345",
        "items": [{"item_id": ids["producto"], "cantidad": 200, "costo": 95}],
    })
    assert r.status_code == 201, r.text

    stock = c.get(f"/api/consumibles/{ids['producto']}/stock").json()
    assert [d["stock"] for d in stock if d["id"] == ids["deposito"]] == [200]

    # --- Venta en cuenta corriente: descuenta stock y genera deuda -----------
    v = c.post("/api/ventas", json={
        "cliente_id": ids["cliente"], "deposito_id": ids["deposito"],
        "sucursal_id": ids["sucursal"],
        "items": [{"item_id": ids["producto"], "descripcion": "PLUG RJ 45 CAT 6",
                   "cantidad": 10, "precio": 160}],
        "pagos": [{"medio": "cuenta_corriente", "monto": 1600}],
    })
    assert v.status_code == 201, v.text
    venta_id = v.json()["id"]

    stock = c.get(f"/api/consumibles/{ids['producto']}/stock").json()
    assert [d["stock"] for d in stock if d["id"] == ids["deposito"]] == [190]

    # 🔴 El assert que importa: el saldo sale de `ventas_pagos` (LibraCore)
    # unido a `sales` (LibraCommerce). Si los pagos se hubieran escrito en
    # `sale_payments`, esto daría 0 **sin fallar** y el cliente aparecería sin
    # deuda. Ver `app/services/ventas.py`.
    cc = c.get("/api/cuenta-corriente").json()
    assert cc["resumen"]["total_adeudado"] == 1600
    assert [x["cliente_id"] for x in cc["clientes"]] == [ids["cliente"]]

    # --- El cobro, que es donde estaba el TypeError --------------------------
    pago = c.post("/api/cuenta-corriente/pagos", json={
        "cliente_id": ids["cliente"], "monto": 600, "fecha": "2026-08-12",
        "concepto": "Pago a cuenta", "medio_pago": "transferencia",
    })
    assert pago.status_code == 201, pago.text

    detalle = c.get(f"/api/cuenta-corriente/{ids['cliente']}").json()
    assert detalle["saldo"] == 1000
    assert len(detalle["movimientos"]) == 2

    # --- El recibo, y que sea idempotente -----------------------------------
    r1 = c.post(f"/api/ventas/{venta_id}/recibo")
    assert r1.status_code == 201, r1.text
    r2 = c.post(f"/api/ventas/{venta_id}/recibo")
    assert r2.status_code == 201
    assert r1.json()["id"] == r2.json()["id"], "emitió un segundo recibo"

    assert len(c.get("/api/recibos").json()) == 1


def test_el_debito_directo_tambien_entra_al_saldo(comercial):
    """`cc_debitos` es la única vía para la deuda que no nace de una venta de
    esta base — y es el enganche previsto para lo que factura SOS Contador."""
    c = comercial
    ids = _crear_base(c)

    r = c.post("/api/cuenta-corriente/debitos", json={
        "cliente_id": ids["cliente"], "monto": 45000, "fecha": "2026-08-12",
        "concepto": "Factura B 0001-00004521 (SOS)",
    })
    assert r.status_code == 201, r.text

    assert c.get(f"/api/cuenta-corriente/{ids['cliente']}").json()["saldo"] == 45000


def test_el_egreso_lleva_pagos_parciales(comercial):
    """El estado lo deriva el motor del total pagado, no lo fija la pantalla.

    Y `create_pago_egreso()` busca la caja por defecto con un `SELECT id FROM
    cajas`: sin esa tabla —que este producto crea vacía a propósito— registrar
    el pago falla. Esta ruta es la que lo ejercita.
    """
    c = comercial
    ids = _crear_base(c)

    e = c.post("/api/egresos", json={
        "fecha": "2026-08-12", "concepto": "Compra de cableado", "total": 19000,
        "proveedor_id": ids["proveedor"], "proveedor_nombre": "Unify Argentina",
        "numero": "0001-00012345", "categoria": "Mercadería",
    })
    assert e.status_code == 201, e.text
    egreso_id = e.json()["id"]

    p = c.post(f"/api/egresos/{egreso_id}/pagos", json={
        "fecha": "2026-08-12", "monto": 9000, "medio_pago": "transferencia",
    })
    assert p.status_code == 201, p.text

    detalle = c.get(f"/api/egresos/{egreso_id}").json()
    assert detalle["estado"] == "parcial"
    assert detalle["pagado"] == 9000 and detalle["saldo"] == 10000


def test_la_lista_de_precios_se_ajusta_en_masa(comercial):
    """El ajuste por porcentaje es la operación que justifica que las listas
    existan como entidad. Devuelve cuántos precios movió: si diera 0 sobre una
    lista con precios, el endpoint estaría mintiendo."""
    c = comercial
    ids = _crear_base(c)

    lista = c.post("/api/listas-precio", json={"nombre": "Resellers"})
    assert lista.status_code == 201, lista.text
    lista_id = lista.json()["id"]

    assert c.put(f"/api/listas-precio/{lista_id}/precios", json={
        "item_id": ids["producto"], "precio": 100,
    }).status_code == 200

    r = c.post(f"/api/listas-precio/{lista_id}/ajuste", json={"porcentaje": 12})
    assert r.status_code == 200, r.text
    assert r.json()["actualizados"] == 1

    precios = c.get(f"/api/listas-precio/{lista_id}/precios").json()
    assert precios[0]["precio"] == 112


def test_la_venta_no_puede_dejar_el_deposito_en_negativo(comercial):
    """LibraDesk valida disponibilidad, que **no** es el default del motor.

    Y el 422 tiene que llegar sin haber grabado nada: si la venta quedara a
    medias, el stock diría una cosa y el comprobante otra.
    """
    c = comercial
    ids = _crear_base(c)

    r = c.post("/api/ventas", json={
        "cliente_id": ids["cliente"], "deposito_id": ids["deposito"],
        "items": [{"item_id": ids["producto"], "descripcion": "PLUG",
                   "cantidad": 5, "precio": 160}],
        "pagos": [{"medio": "efectivo", "monto": 800}],
    })
    assert r.status_code == 422, r.text
    assert "stock" in r.json()["detail"].lower()

    assert c.get("/api/ventas").json() == []
    stock = c.get(f"/api/consumibles/{ids['producto']}/stock").json()
    assert all(d["stock"] == 0 for d in stock)


def test_el_espejo_de_parties_se_crea_al_dar_de_alta(comercial):
    """Sin `parties` no hay compra ni venta: sus FK son NOT NULL.

    Se verifica por el efecto —que una recepción a nombre de un proveedor
    recién creado funcione— y no leyendo la tabla: lo que importa es que el
    circuito cierre, no que haya una fila.
    """
    c = comercial
    ids = _crear_base(c)

    otro = c.post("/api/proveedores", json={"nombre": "Distribuidora Nueva"})
    assert otro.status_code == 201

    r = c.post("/api/recepciones-compra", json={
        "proveedor_id": otro.json()["id"], "deposito_id": ids["deposito"],
        "items": [{"item_id": ids["producto"], "cantidad": 5, "costo": 90}],
    })
    assert r.status_code == 201, r.text

    listado = c.get("/api/recepciones-compra").json()
    assert [x["proveedor"] for x in listado] == ["Distribuidora Nueva"]


def test_las_sucursales_no_estan_gateadas_por_plan(client, destino_base):
    """Son estructura de la empresa, como sectores y categorías: existen aunque
    el plan no incluya ningún módulo comercial.

    Si algún día alguien las gatea, esta prueba se pone roja y obliga a
    decidirlo — en vez de que el selector del encabezado desaparezca en silencio
    para los planes bajos.
    """
    from plans import aplicar_plan_en_db

    aplicar_plan_en_db(destino_base, "basico")
    _login(client)

    assert client.get("/api/sucursales").status_code == 200
    # Y lo comercial SÍ queda cortado. Sin este assert, la línea de arriba
    # pasaría igual con el gate desactivado y no probaría nada.
    assert client.get("/api/cuenta-corriente").status_code == 403
    assert client.get("/api/egresos").status_code == 403


def test_las_rutas_comerciales_existen_de_verdad(client):
    """Guarda contra el fallback de la SPA: `asgi.py` monta
    `/{full_path:path}` → index.html, así que **cualquier ruta inventada
    devuelve 200 con HTML**. Sin esto, un rename de endpoint dejaría a todo
    este archivo midiendo el catch-all.

    Se consulta el schema de OpenAPI, igual que `_existe_de_verdad` de
    `test_modulos_y_planes.py`.
    """
    paths = client.app.openapi()["paths"]
    for ruta in ("/api/sucursales", "/api/consumibles", "/api/depositos-stock",
                 "/api/listas-precio", "/api/ordenes-compra",
                 "/api/recepciones-compra", "/api/egresos", "/api/ventas",
                 "/api/recibos", "/api/cuenta-corriente",
                 "/api/cuenta-corriente/pagos", "/api/cuenta-corriente/debitos",
                 "/api/stock/grilla", "/api/stock/bajo-minimo"):
        assert ruta in paths, f"{ruta} no la sirve ningun router"
