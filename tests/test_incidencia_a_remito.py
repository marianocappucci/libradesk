"""De un reclamo cerrado al remito — el camino a facturación de un servicio.

LibraDesk manda a facturar **sólo remitos** (ver `app/routers/facturacion.py`),
así que sin esta conversión un trabajo por servicio no tenía cómo llegar a la
bandeja. Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que no se pueda facturar dos veces el mismo reclamo.** La conversión es
   idempotente y el vínculo queda guardado; sin eso, dos clicks son dos remitos
   y —desde que el envío debita en cuenta corriente— deuda de más para un
   cliente real.
2. 🔴 **Que el vínculo no se pierda editando el ticket.** El PUT de incidencias
   manda el objeto entero, y este producto ya perdió un dato así antes.
3. 🔴 **Que no se pueda borrar el remito por abajo** dejando al reclamo
   apuntando a un id que no existe. Acá no hay FK que lo ataje: `incidencias`
   es SQLAlchemy y `remitos` no.
4. Que sólo se convierta un ticket **cerrado**, que es donde el circuito real
   decide si va a facturación.
5. Que lo que entra en el remito sea el trabajo y los materiales que
   efectivamente se usaron, valorizados.
"""

import os
from datetime import datetime

import pytest

from app.services import inventario, materiales

CUANDO = datetime(2026, 8, 13, 10, 0, 0)


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
    """Un cliente, un ticket abierto con horas, y una camioneta con 40 plugs.

    El plug tiene `precio` (de venta) distinto del `costo`: es lo que hace que
    el test note si el remito se valoriza con el precio equivocado.
    """
    cliente = client.post("/api/clientes", json={
        "nombre": "Medici Neumatec", "empresa": "NEUMYSER SRL",
        "cuit": "30-11111111-7", "ciudad": "Chivilcoy",
    }).json()
    incidencia = client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "titulo": "Central sin tono",
        "descripcion": "No hay tono en los internos",
        "horas_invertidas": 2,
    }).json()
    item = inventario.crear_item("Plug RJ45", costo=120.0, precio=500.0)
    camioneta = inventario.crear_deposito("Kangoo")
    inventario.ajustar(item["id"], camioneta["id"], 40, fecha=CUANDO)
    return client, cliente, incidencia, item, camioneta


def _cerrar(client, incidencia, **extra):
    """Cierra el ticket por el PUT real, que es como se cierra en la pantalla."""
    payload = {**incidencia, **extra, "estado": "cerrado"}
    r = client.put(f"/api/incidencias/{incidencia['id']}", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _convertir(client, incidencia_id):
    return client.post(f"/api/incidencias/{incidencia_id}/convertir-en-remito")


# ── El circuito ──────────────────────────────────────────────────────────


def test_un_reclamo_cerrado_genera_el_remito_con_trabajo_y_materiales(escenario):
    client, cliente, incidencia, item, camioneta = escenario
    materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                      cuando=CUANDO)
    _cerrar(client, incidencia)

    r = _convertir(client, incidencia["id"])

    assert r.status_code == 201, r.text
    remito = r.json()
    assert remito["client_name"] == "NEUMYSER SRL"
    assert remito["client_cuit"] == "30-11111111-7"

    lineas = {i["description"]: i for i in remito["items"]}
    # La línea del trabajo: las horas van como cantidad y el precio queda en
    # cero porque este producto no tiene valor hora en ningún lado.
    assert lineas["Central sin tono"]["qty"] == 2
    assert lineas["Central sin tono"]["unit_price"] == 0
    # La del material, al precio de VENTA (500) y no al costo (120).
    assert lineas["Plug RJ45"]["qty"] == 10
    assert lineas["Plug RJ45"]["unit_price"] == 500


def test_sin_horas_cargadas_el_trabajo_va_como_una_visita(escenario):
    """`qty` 1 y no 0: un `qty` en 0 daría un remito que no cobra el trabajo
    aunque después le pongan precio a la línea."""
    client, _, incidencia, _, _ = escenario
    sin_horas = client.put(f"/api/incidencias/{incidencia['id']}", json={
        **incidencia, "horas_invertidas": None, "estado": "cerrado",
    }).json()
    assert sin_horas["horas_invertidas"] is None

    remito = _convertir(client, incidencia["id"]).json()

    assert remito["items"][0]["qty"] == 1


def test_el_material_devuelto_no_entra_en_el_remito(escenario):
    """Lo que volvió al depósito no se usó, y cobrarlo sería cobrar de más."""
    client, _, incidencia, item, camioneta = escenario
    cargado = materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                                cuando=CUANDO)
    materiales.quitar(cargado["id"], cuando=CUANDO)
    _cerrar(client, incidencia)

    remito = _convertir(client, incidencia["id"]).json()

    assert [i["description"] for i in remito["items"]] == ["Central sin tono"]


def test_el_numero_del_papel_firmado_queda_en_el_remito(escenario):
    """El `N° CDS` es lo único que ata la conformidad firmada con el ticket.
    Quien concilia después busca por ese número."""
    client, _, incidencia, _, _ = escenario
    _cerrar(client, incidencia, nro_cds="0001-00041996")

    remito = _convertir(client, incidencia["id"]).json()

    assert "0001-00041996" in remito["observations"]


# ── Que no se facture dos veces ──────────────────────────────────────────


def test_convertir_dos_veces_devuelve_el_mismo_remito(escenario):
    client, _, incidencia, _, _ = escenario
    _cerrar(client, incidencia)

    primero = _convertir(client, incidencia["id"])
    segundo = _convertir(client, incidencia["id"])

    assert primero.status_code == segundo.status_code == 201
    assert primero.json()["id"] == segundo.json()["id"]
    # Y no quedó un segundo remito emitido por el mismo trabajo.
    assert len(client.get("/api/remitos").json()) == 1


def test_el_reclamo_queda_linkeado_al_remito(escenario):
    client, _, incidencia, _, _ = escenario
    _cerrar(client, incidencia)

    remito = _convertir(client, incidencia["id"]).json()

    ticket = client.get(f"/api/incidencias/{incidencia['id']}").json()
    assert ticket["remito_id"] == remito["id"]


def test_editar_el_ticket_no_borra_el_vinculo_con_el_remito(escenario):
    """El PUT de incidencias manda el objeto entero y lo que no viaja vuelve a
    `null`. Este producto ya perdió el `nro_cds` así una vez; `remito_id` es el
    mismo tipo de dato caro, y el que decide si un trabajo ya se facturó."""
    client, _, incidencia, _, _ = escenario
    _cerrar(client, incidencia)
    remito = _convertir(client, incidencia["id"]).json()

    editado = client.put(f"/api/incidencias/{incidencia['id']}", json={
        **incidencia, "estado": "cerrado", "prioridad": "alta",
    })

    assert editado.status_code == 200, editado.text
    assert editado.json()["remito_id"] == remito["id"]


def test_no_se_puede_borrar_el_remito_que_genero_un_reclamo(escenario):
    """Sin esto el reclamo queda diciendo "ya se remitió" apuntando a nada, y
    el trabajo no se puede facturar nunca. Acá **no hay FK que lo ataje**:
    `incidencias` es SQLAlchemy y `remitos` no."""
    client, _, incidencia, _, _ = escenario
    _cerrar(client, incidencia)
    remito = _convertir(client, incidencia["id"]).json()

    r = client.delete(f"/api/remitos/{remito['id']}")

    assert r.status_code == 409, r.text
    assert "reclamo" in r.json()["detail"]
    assert client.get(f"/api/remitos/{remito['id']}").status_code == 200


# ── Sólo un ticket cerrado ───────────────────────────────────────────────


@pytest.mark.parametrize("estado", ["abierto", "en_progreso", "resuelta"])
def test_un_reclamo_que_no_esta_cerrado_no_genera_remito(escenario, estado):
    """`resuelta` está en la lista a propósito: el técnico ya terminó, pero en
    el circuito real todavía falta el control del comprobante contra la hoja de
    ruta, y es al cerrar cuando se decide si va a facturación."""
    client, _, incidencia, _, _ = escenario
    client.put(f"/api/incidencias/{incidencia['id']}",
               json={**incidencia, "estado": estado})

    r = _convertir(client, incidencia["id"])

    assert r.status_code == 409, r.text
    assert client.get("/api/remitos").json() == []


def test_un_reclamo_que_no_existe_da_404(client):
    assert _convertir(client, 9999).status_code == 404


# ── Y de ahí a la bandeja ────────────────────────────────────────────────


def test_el_remito_generado_es_lo_que_llega_a_la_bandeja(escenario):
    """El circuito completo: reclamo cerrado → remito → pendientes.

    Y **una sola fila**: el reclamo no aparece por su cuenta.
    """
    client, _, incidencia, item, camioneta = escenario
    materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                      cuando=CUANDO)
    _cerrar(client, incidencia)
    remito = _convertir(client, incidencia["id"]).json()

    items = client.get("/api/facturacion/pendientes").json()["items"]

    assert [(i["origen_tipo"], i["id"]) for i in items] == [("remito", remito["id"])]
