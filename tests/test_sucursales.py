"""Sucursales como eje transversal: ABM, filtros y movimiento de stock.

El eje se decidio el 2026-08-14 y las tres respuestas que lo definen estan en
`comercial.listar_sucursales()`. Lo que se prueba aca es que el codigo haga
**esas** tres cosas, incluidas las que consisten en NO filtrar:

- filtran stock, depositos, ventas, compras y listas de precio;
- **no** filtra la cuenta corriente, porque el saldo de un cliente es uno solo
  entre sucursales --si algun dia alguien "arregla" eso, este archivo tiene que
  ponerse en rojo--;
- mover stock entre sucursales es el mismo movimiento que entre depositos, en
  una transaccion, y se distingue por el `reason_code`.

⚠️ **Todo escenario siembra filas.** Un test que crea el schema y consulta
tablas vacias pasa igual con el filtro roto: `[] == []` no distingue "filtro
que funciona" de "consulta que no devuelve nada".
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
def dos_sucursales(client):
    chivilcoy = client.post("/api/sucursales", json={
        "nombre": "Chivilcoy", "codigo": "CHI", "direccion": "San Martin 100",
    })
    assert chivilcoy.status_code == 201, chivilcoy.text
    mercedes = client.post("/api/sucursales", json={
        "nombre": "Mercedes", "codigo": "MER",
    })
    assert mercedes.status_code == 201, mercedes.text
    return chivilcoy.json()["id"], mercedes.json()["id"]


@pytest.fixture
def escenario(client, dos_sucursales):
    """Un consumible, un deposito en cada sucursal y stock cargado en uno solo.

    El stock arranca **desbalanceado a proposito** (120 en Chivilcoy, 0 en
    Mercedes): con la misma cantidad de los dos lados, un filtro que no filtra
    nada devolveria el mismo numero y el test pasaria igual.
    """
    chi, mer = dos_sucursales
    item = client.post("/api/consumibles", json={
        "nombre": "Plug RJ45", "stock_minimo": 50,
    }).json()
    dep_chi = client.post("/api/depositos-stock", json={
        "nombre": "Central Chivilcoy", "es_default": True, "sucursal_id": chi,
    }).json()
    dep_mer = client.post("/api/depositos-stock", json={
        "nombre": "Central Mercedes", "sucursal_id": mer,
    }).json()
    r = client.post(f"/api/consumibles/{item['id']}/ajuste", json={
        "deposito_id": dep_chi["id"], "cantidad": 120, "nota": "Carga inicial",
    })
    assert r.status_code == 200, r.text
    return {"chi": chi, "mer": mer, "item": item["id"],
            "dep_chi": dep_chi["id"], "dep_mer": dep_mer["id"]}


# ── ABM ──────────────────────────────────────────────────────────────────


def test_editar_una_sucursal(client, dos_sucursales):
    chi, _ = dos_sucursales

    r = client.put(f"/api/sucursales/{chi}", json={
        "nombre": "Chivilcoy Centro", "codigo": "CHI", "direccion": "Rivadavia 50",
    })
    assert r.status_code == 200, r.text

    fila = next(s for s in client.get("/api/sucursales").json() if s["id"] == chi)
    assert fila["nombre"] == "Chivilcoy Centro"
    assert fila["direccion"] == "Rivadavia 50"


def test_editar_una_sucursal_que_no_existe_rebota(client):
    r = client.put("/api/sucursales/9999", json={"nombre": "Fantasma"})
    assert r.status_code == 422


def test_no_se_puede_dar_de_baja_una_sucursal_con_depositos_activos(client, escenario):
    """La guarda existe porque `branch_id` no tiene FK: la baja no cascadea y
    el stock parado ahi se volveria invisible sin que nadie lo haya movido."""
    r = client.post(f"/api/sucursales/{escenario['chi']}/estado",
                    json={"activa": False})

    assert r.status_code == 422
    assert "deposito" in r.json()["detail"].lower()
    # Y la sucursal sigue activa: la guarda no puede dejarla a medio camino.
    assert any(s["id"] == escenario["chi"] for s in client.get("/api/sucursales").json())


def test_la_baja_logica_la_saca_del_listado_pero_conserva_la_fila(client, dos_sucursales):
    _, mer = dos_sucursales

    assert client.post(f"/api/sucursales/{mer}/estado",
                       json={"activa": False}).status_code == 200

    activas = [s["id"] for s in client.get("/api/sucursales").json()]
    todas = [s["id"] for s in client.get("/api/sucursales?solo_activas=false").json()]
    assert mer not in activas
    assert mer in todas


def test_no_hay_endpoint_para_borrar_una_sucursal(client, dos_sucursales):
    """El borrado dejaria cuatro tablas del motor apuntando a un id inexistente,
    porque ninguna de las cuatro `branch_id` tiene FK contra `sucursales`.

    ⚠️ Se afirma sobre 405 y no sobre "no 200": un 404 significaria que la ruta
    no existe **para ese id**, que es lo que devolveria un DELETE implementado
    contra una sucursal borrada. 405 es el metodo ausente.
    """
    _, mer = dos_sucursales
    assert client.delete(f"/api/sucursales/{mer}").status_code == 405


def test_un_deposito_no_puede_apuntar_a_una_sucursal_inexistente(client):
    """Sin FK, el id inventado entra y el deposito desaparece de toda pantalla
    filtrada. La guarda esta en `comercial.verificar_sucursal()`."""
    r = client.post("/api/depositos-stock", json={
        "nombre": "Fantasma", "sucursal_id": 9999,
    })
    assert r.status_code == 422


def test_un_deposito_no_puede_apuntar_a_una_sucursal_dada_de_baja(client, dos_sucursales):
    _, mer = dos_sucursales
    client.post(f"/api/sucursales/{mer}/estado", json={"activa": False})

    r = client.post("/api/depositos-stock", json={"nombre": "Tarde", "sucursal_id": mer})
    assert r.status_code == 422


# ── Filtros del modulo comercial ─────────────────────────────────────────


def test_los_depositos_se_filtran_por_sucursal(client, escenario):
    todos = client.get("/api/depositos-stock").json()
    solo_chi = client.get(f"/api/depositos-stock?sucursal_id={escenario['chi']}").json()

    assert {d["id"] for d in todos} >= {escenario["dep_chi"], escenario["dep_mer"]}
    assert [d["id"] for d in solo_chi] == [escenario["dep_chi"]]
    assert solo_chi[0]["sucursal"] == "Chivilcoy"


def test_el_stock_del_catalogo_es_el_de_la_sucursal_mirada(client, escenario):
    """El catalogo NO se recorta --el consumible existe en las dos-- pero la
    columna de stock si."""
    item = escenario["item"]

    def stock_de(url):
        return next(c for c in client.get(url).json() if c["id"] == item)["stock"]

    assert stock_de("/api/consumibles") == 120
    assert stock_de(f"/api/consumibles?sucursal_id={escenario['chi']}") == 120
    assert stock_de(f"/api/consumibles?sucursal_id={escenario['mer']}") == 0


def test_bajo_minimo_mira_el_stock_de_la_sucursal(client, escenario):
    """120 contra un minimo de 50: la empresa esta sobrada y Mercedes en cero.

    Es la decision documentada en `inventario.bajo_minimo()`: el minimo es uno
    solo por consumible, y mirando una sucursal se compara contra el stock de
    esa sucursal. Sin eso la vista no diria donde reponer.
    """
    sin_filtro = client.get("/api/stock/bajo-minimo").json()
    en_mercedes = client.get(
        f"/api/stock/bajo-minimo?sucursal_id={escenario['mer']}"
    ).json()

    assert [c["id"] for c in sin_filtro] == []
    assert [c["id"] for c in en_mercedes] == [escenario["item"]]


def test_la_grilla_recorta_las_columnas_y_las_celdas(client, escenario):
    grilla = client.get(f"/api/stock/grilla?sucursal_id={escenario['chi']}").json()

    assert [d["id"] for d in grilla["depositos"]] == [escenario["dep_chi"]]
    # Los items NO se recortan: una fila en cero dice "aca no hay de eso".
    assert escenario["item"] in [i["id"] for i in grilla["items"]]
    assert all(c["deposito_id"] == escenario["dep_chi"] for c in grilla["celdas"])


def test_las_ventas_se_filtran_por_sucursal(client, escenario):
    cliente = client.post("/api/clientes", json={"nombre": "Cooperativa"}).json()
    venta = client.post("/api/ventas", json={
        "cliente_id": cliente["id"],
        "deposito_id": escenario["dep_chi"],
        "sucursal_id": escenario["chi"],
        "items": [{"descripcion": "Plug", "cantidad": 2, "precio": 100,
                   "item_id": escenario["item"], "es_producto": True}],
    })
    assert venta.status_code == 201, venta.text

    en_chi = client.get(f"/api/ventas?sucursal_id={escenario['chi']}").json()
    en_mer = client.get(f"/api/ventas?sucursal_id={escenario['mer']}").json()
    assert [v["id"] for v in en_chi] == [venta.json()["id"]]
    assert en_mer == []


def test_la_cuenta_corriente_NO_se_filtra_por_sucursal(client, escenario):
    """🔴 El test que protege la decision de fondo.

    El saldo de un cliente es **uno solo** entre sucursales: es lo que descarta
    "una instancia por sucursal" y lo que justifica todo este eje. Si alguna vez
    alguien le agrega `sucursal_id` al endpoint de cuenta corriente, esto tiene
    que romperse antes de llegar a produccion.

    Se afirma sobre el **saldo**, y no sobre que el endpoint ignore el
    parametro: FastAPI descarta los query params que no declara, asi que
    "mandarlo y que no pase nada" pasaria igual con el filtro implementado.
    """
    cliente = client.post("/api/clientes", json={"nombre": "Cooperativa"}).json()
    for sucursal in (escenario["chi"], escenario["mer"]):
        r = client.post("/api/ventas", json={
            "cliente_id": cliente["id"],
            "deposito_id": escenario["dep_chi"],
            "sucursal_id": sucursal,
            "items": [{"descripcion": "Mano de obra", "cantidad": 1,
                       "precio": 1000, "es_producto": False}],
            "pagos": [{"medio": "cuenta_corriente", "monto": 1000}],
        })
        assert r.status_code == 201, r.text

    cc = client.get("/api/cuenta-corriente").json()
    fila = next(s for s in cc["clientes"] if s["cliente_id"] == cliente["id"])
    # Las dos ventas, aunque cada una se hizo en una sucursal distinta.
    assert fila["saldo"] == 2000


def test_las_ordenes_de_compra_se_filtran_por_sucursal(client, escenario):
    prov = client.post("/api/proveedores", json={"nombre": "Distribuidora Sur"}).json()
    orden = client.post("/api/ordenes-compra", json={
        "proveedor_id": prov["id"],
        "sucursal_id": escenario["mer"],
        "items": [{"item_id": escenario["item"], "cantidad": 10, "costo": 5}],
    })
    assert orden.status_code == 201, orden.text

    en_mer = client.get(f"/api/ordenes-compra?sucursal_id={escenario['mer']}").json()
    en_chi = client.get(f"/api/ordenes-compra?sucursal_id={escenario['chi']}").json()
    assert [o["id"] for o in en_mer] == [orden.json()["id"]]
    assert en_mer[0]["sucursal"] == "Mercedes"
    assert en_chi == []


def test_una_orden_no_puede_apuntar_a_una_sucursal_inexistente(client, escenario):
    prov = client.post("/api/proveedores", json={"nombre": "Distribuidora Sur"}).json()
    r = client.post("/api/ordenes-compra", json={
        "proveedor_id": prov["id"], "sucursal_id": 9999,
        "items": [{"item_id": escenario["item"], "cantidad": 1, "costo": 5}],
    })
    assert r.status_code == 422


def test_la_recepcion_se_ubica_por_el_deposito_y_no_por_la_orden(client, escenario):
    """`purchase_receipts` no tiene `branch_id`: la sucursal sale del deposito
    donde entro la mercaderia.

    El escenario es el que distingue una implementacion de la otra: **la orden
    es de Mercedes y la mercaderia entra en Chivilcoy**. Deducir la sucursal por
    la orden pondria la recepcion en Mercedes, que es donde el stock no esta.
    """
    prov = client.post("/api/proveedores", json={"nombre": "Distribuidora Sur"}).json()
    orden = client.post("/api/ordenes-compra", json={
        "proveedor_id": prov["id"], "sucursal_id": escenario["mer"],
        "items": [{"item_id": escenario["item"], "cantidad": 10, "costo": 5}],
    }).json()
    recepcion = client.post("/api/recepciones-compra", json={
        "proveedor_id": prov["id"],
        "deposito_id": escenario["dep_chi"],
        "orden_id": orden["id"],
        "items": [{"item_id": escenario["item"], "cantidad": 10, "costo": 5}],
    })
    assert recepcion.status_code == 201, recepcion.text

    en_chi = client.get(f"/api/recepciones-compra?sucursal_id={escenario['chi']}").json()
    en_mer = client.get(f"/api/recepciones-compra?sucursal_id={escenario['mer']}").json()
    assert [r["id"] for r in en_chi] == [recepcion.json()["id"]]
    assert en_chi[0]["deposito"] == "Central Chivilcoy"
    assert en_mer == []


def test_una_recepcion_sin_orden_igual_tiene_sucursal(client, escenario):
    """La compra de mostrador no tiene orden que consultar, y es la mayoria."""
    prov = client.post("/api/proveedores", json={"nombre": "Ferreteria"}).json()
    recepcion = client.post("/api/recepciones-compra", json={
        "proveedor_id": prov["id"],
        "deposito_id": escenario["dep_mer"],
        "items": [{"item_id": escenario["item"], "cantidad": 3, "costo": 7}],
    })
    assert recepcion.status_code == 201, recepcion.text

    en_mer = client.get(f"/api/recepciones-compra?sucursal_id={escenario['mer']}").json()
    assert [r["id"] for r in en_mer] == [recepcion.json()["id"]]
    assert en_mer[0]["orden_id"] is None


# ── Precios por sucursal ─────────────────────────────────────────────────


def test_el_precio_de_sucursal_le_gana_al_general_sin_pisarlo(client, escenario):
    lista = client.post("/api/listas-precio", json={"nombre": "Mostrador"}).json()
    item = escenario["item"]
    client.put(f"/api/listas-precio/{lista['id']}/precios",
               json={"item_id": item, "precio": 100})
    client.put(f"/api/listas-precio/{lista['id']}/precios",
               json={"item_id": item, "precio": 130, "sucursal_id": escenario["mer"]})

    en_chi = client.get(
        f"/api/listas-precio/{lista['id']}/precios?sucursal_id={escenario['chi']}"
    ).json()
    en_mer = client.get(
        f"/api/listas-precio/{lista['id']}/precios?sucursal_id={escenario['mer']}"
    ).json()
    todos = client.get(f"/api/listas-precio/{lista['id']}/precios").json()

    # Una fila por producto de cada lado, y el precio que se aplica ahi.
    assert [(p["precio"], p["propio_de_sucursal"]) for p in en_chi] == [(100, False)]
    assert [(p["precio"], p["propio_de_sucursal"]) for p in en_mer] == [(130, True)]
    # Y el general sigue existiendo: cargar el de sucursal no lo piso.
    assert len(todos) == 2


def test_fijar_dos_veces_el_precio_general_no_duplica_la_fila(client, escenario):
    """El `DELETE` previo tiene que matchear su propia fila.

    Con `branch_id = ?` en vez de `IS NULL`, `NULL = NULL` da NULL, el DELETE no
    borra nada y cada guardado deja una fila mas — hasta que `resolve_price()`
    empieza a depender del orden de insercion.
    """
    lista = client.post("/api/listas-precio", json={"nombre": "Mostrador"}).json()
    for precio in (100, 110, 120):
        client.put(f"/api/listas-precio/{lista['id']}/precios",
                   json={"item_id": escenario["item"], "precio": precio})

    filas = client.get(f"/api/listas-precio/{lista['id']}/precios").json()
    assert [p["precio"] for p in filas] == [120]


def test_borrar_el_precio_de_sucursal_devuelve_el_producto_al_general(client, escenario):
    lista = client.post("/api/listas-precio", json={"nombre": "Mostrador"}).json()
    item = escenario["item"]
    client.put(f"/api/listas-precio/{lista['id']}/precios",
               json={"item_id": item, "precio": 100})
    client.put(f"/api/listas-precio/{lista['id']}/precios",
               json={"item_id": item, "precio": 130, "sucursal_id": escenario["mer"]})

    r = client.delete(
        f"/api/listas-precio/{lista['id']}/precios/{item}?sucursal_id={escenario['mer']}"
    )
    assert r.status_code == 204, r.text

    en_mer = client.get(
        f"/api/listas-precio/{lista['id']}/precios?sucursal_id={escenario['mer']}"
    ).json()
    assert [(p["precio"], p["propio_de_sucursal"]) for p in en_mer] == [(100, False)]


def test_el_ajuste_masivo_por_sucursal_no_toca_el_general(client, escenario):
    lista = client.post("/api/listas-precio", json={"nombre": "Mostrador"}).json()
    item = escenario["item"]
    client.put(f"/api/listas-precio/{lista['id']}/precios",
               json={"item_id": item, "precio": 100})
    client.put(f"/api/listas-precio/{lista['id']}/precios",
               json={"item_id": item, "precio": 200, "sucursal_id": escenario["mer"]})

    r = client.post(f"/api/listas-precio/{lista['id']}/ajuste",
                    json={"porcentaje": 10, "sucursal_id": escenario["mer"]})
    assert r.json()["actualizados"] == 1

    por_sucursal = {
        p["sucursal_id"]: p["precio"]
        for p in client.get(f"/api/listas-precio/{lista['id']}/precios").json()
    }
    assert por_sucursal[None] == 100
    assert por_sucursal[escenario["mer"]] == 220


# ── Mover stock entre sucursales ─────────────────────────────────────────


def test_transferir_entre_sucursales_mueve_el_stock_de_las_dos_puntas(client, escenario):
    r = client.post("/api/consumibles/transferir", json={
        "item_id": escenario["item"],
        "origen_id": escenario["dep_chi"],
        "destino_id": escenario["dep_mer"],
        "cantidad": 30,
        "nota": "Reposicion Mercedes",
    })
    assert r.status_code == 200, r.text
    assert r.json()["entre_sucursales"] is True

    def stock_en(sucursal):
        item = next(
            c for c in client.get(f"/api/consumibles?sucursal_id={sucursal}").json()
            if c["id"] == escenario["item"]
        )
        return item["stock"]

    assert stock_en(escenario["chi"]) == 90
    assert stock_en(escenario["mer"]) == 30


def test_transferir_dentro_de_la_misma_sucursal_no_se_marca_como_entre_sucursales(
    client, escenario
):
    """El grupo de control del test de arriba.

    Sin este, `entre_sucursales` podria estar devolviendo `True` siempre y el
    otro test pasaria igual.
    """
    otro = client.post("/api/depositos-stock", json={
        "nombre": "Kangoo", "sucursal_id": escenario["chi"],
    }).json()

    r = client.post("/api/consumibles/transferir", json={
        "item_id": escenario["item"], "origen_id": escenario["dep_chi"],
        "destino_id": otro["id"], "cantidad": 5,
    })
    assert r.status_code == 200, r.text
    assert r.json()["entre_sucursales"] is False


def test_la_transferencia_entre_sucursales_no_alcanza_para_la_que_no_hay_stock(
    client, escenario
):
    """Cruzar sucursales no relaja la validacion de disponibilidad."""
    r = client.post("/api/consumibles/transferir", json={
        "item_id": escenario["item"],
        "origen_id": escenario["dep_mer"],  # esta en cero
        "destino_id": escenario["dep_chi"],
        "cantidad": 1,
    })
    assert r.status_code == 422
    assert "insuficiente" in r.json()["detail"].lower()


def test_el_historial_distingue_las_transferencias_entre_sucursales(client, escenario):
    interna = client.post("/api/depositos-stock", json={
        "nombre": "Kangoo", "sucursal_id": escenario["chi"],
    }).json()
    client.post("/api/consumibles/transferir", json={
        "item_id": escenario["item"], "origen_id": escenario["dep_chi"],
        "destino_id": interna["id"], "cantidad": 5,
    })
    client.post("/api/consumibles/transferir", json={
        "item_id": escenario["item"], "origen_id": escenario["dep_chi"],
        "destino_id": escenario["dep_mer"], "cantidad": 30,
    })

    todas = client.get("/api/stock/transferencias").json()
    cruzadas = client.get("/api/stock/transferencias?solo_entre_sucursales=true").json()

    assert len(todas) == 2
    assert len(cruzadas) == 1
    assert cruzadas[0]["origen_sucursal"] == "Chivilcoy"
    assert cruzadas[0]["destino_sucursal"] == "Mercedes"
    assert cruzadas[0]["cantidad"] == 30
    assert cruzadas[0]["nota"] == ""


def test_el_historial_de_una_sucursal_trae_lo_que_salio_y_lo_que_entro(client, escenario):
    """Filtrar solo por destino contestaria "que me llego", que es la mitad."""
    client.post("/api/consumibles/transferir", json={
        "item_id": escenario["item"], "origen_id": escenario["dep_chi"],
        "destino_id": escenario["dep_mer"], "cantidad": 30,
    })
    client.post("/api/consumibles/transferir", json={
        "item_id": escenario["item"], "origen_id": escenario["dep_mer"],
        "destino_id": escenario["dep_chi"], "cantidad": 4,
    })

    de_mercedes = client.get(
        f"/api/stock/transferencias?sucursal_id={escenario['mer']}"
    ).json()
    assert sorted(t["cantidad"] for t in de_mercedes) == [4, 30]


def test_la_transferencia_no_deja_media_operacion_si_el_destino_no_existe(
    client, escenario
):
    """Las dos escrituras van en una transaccion: o entran las dos o ninguna."""
    r = client.post("/api/consumibles/transferir", json={
        "item_id": escenario["item"], "origen_id": escenario["dep_chi"],
        "destino_id": 9999, "cantidad": 10,
    })
    assert r.status_code == 422

    item = next(
        c for c in client.get(f"/api/consumibles?sucursal_id={escenario['chi']}").json()
        if c["id"] == escenario["item"]
    )
    assert item["stock"] == 120
