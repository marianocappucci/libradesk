"""Materiales consumidos en una incidencia — la bisagra con el stock.

Los tests que importan no son los del camino feliz: son el de atomicidad
(`test_si_falla_la_fila_no_queda_el_movimiento`) y el de reapertura, que son
las dos razones por las que esta funcion se escribio como se escribio.
"""

import os
from datetime import datetime

import pytest

from app.services import inventario, materiales

CUANDO = datetime(2026, 8, 12, 10, 0, 0)


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
    """Un ticket abierto, y una camioneta con 40 plugs."""
    cliente = client.post("/api/clientes", json={"nombre": "Lagrace"}).json()
    incidencia = client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "titulo": "Central sin tono",
        "descripcion": "No hay tono en los internos",
    }).json()
    item = inventario.crear_item("Plug RJ45", costo=120.0)
    camioneta = inventario.crear_deposito("Kangoo")
    inventario.ajustar(item["id"], camioneta["id"], 40, fecha=CUANDO)
    return client, incidencia, item, camioneta


# ── El circuito ──────────────────────────────────────────────────────────


def test_cargar_material_descuenta_del_deposito(escenario):
    _, incidencia, item, camioneta = escenario

    materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                      cuando=CUANDO)

    assert inventario.stock_actual(item["id"], camioneta["id"]) == 30
    cargados = materiales.listar(incidencia["id"])
    assert len(cargados) == 1
    assert cargados[0]["cantidad"] == 10
    assert cargados[0]["descripcion"] == "Plug RJ45"


def test_no_se_puede_consumir_lo_que_no_hay(escenario):
    _, incidencia, item, camioneta = escenario

    with pytest.raises(ValueError):
        materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 41,
                          cuando=CUANDO)

    assert inventario.stock_actual(item["id"], camioneta["id"]) == 40
    assert materiales.listar(incidencia["id"]) == []


def test_quitar_devuelve_el_stock_y_no_borra_el_rastro(escenario):
    _, incidencia, item, camioneta = escenario
    cargado = materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                                cuando=CUANDO)

    materiales.quitar(cargado["id"], cuando=CUANDO)

    assert inventario.stock_actual(item["id"], camioneta["id"]) == 40
    assert materiales.listar(incidencia["id"]) == []
    historial = materiales.listar(incidencia["id"], incluir_devueltos=True)
    assert len(historial) == 1 and historial[0]["devuelto"] is True


def test_quitar_dos_veces_no_inventa_mercaderia(escenario):
    """Un doble click no puede devolver el stock dos veces."""
    _, incidencia, item, camioneta = escenario
    cargado = materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                                cuando=CUANDO)

    materiales.quitar(cargado["id"], cuando=CUANDO)
    materiales.quitar(cargado["id"], cuando=CUANDO)

    assert inventario.stock_actual(item["id"], camioneta["id"]) == 40


def test_el_material_sale_del_deposito_que_se_elige(escenario):
    """Cada linea dice de que deposito salio: la camioneta o el central."""
    _, incidencia, item, camioneta = escenario
    central = inventario.crear_deposito("Central")
    inventario.ajustar(item["id"], central["id"], 100, fecha=CUANDO)

    materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 5, cuando=CUANDO)
    materiales.cargar(incidencia["id"], item["id"], central["id"], 7, cuando=CUANDO)

    assert inventario.stock_actual(item["id"], camioneta["id"]) == 35
    assert inventario.stock_actual(item["id"], central["id"]) == 93


def test_los_movimientos_del_ticket_se_recuperan_por_su_origen(escenario):
    """Sin joins contra tablas de otro dueno."""
    from libracommerce.db.repository import SqliteCommerceRepository
    from libracore.db import core as libracore_core

    _, incidencia, item, camioneta = escenario
    materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 3, cuando=CUANDO)

    with libracore_core.get_connection() as conn:
        movs = SqliteCommerceRepository(conn).list_stock_movements_by_source(
            materiales.ORIGEN, incidencia["id"]
        )
    assert [float(m.quantity_delta) for m in movs] == [-3.0]
    assert movs[0].reason_code == "consumo_incidencia"


# ── Las dos razones por las que se escribio asi ──────────────────────────


def test_si_falla_la_fila_no_queda_el_movimiento(escenario, monkeypatch):
    """🔴 El motivo por el que la tabla NO es un modelo de SQLAlchemy.

    El dominio de este producto escribe por SQLAlchemy y el stock por la
    conexion cruda de libracore: son dos conexiones. Si la fila del material
    se escribiera por una y el movimiento por la otra, un fallo entre medio
    dejaria stock descontado sin material anotado --mercaderia que se fue y
    nadie sabe a que ticket--. Acá las dos van por la misma conexion, dentro
    de `repo.transaction()`.
    """
    _, incidencia, item, camioneta = escenario

    original = materiales._descripcion

    def falla(repo, item_id):
        original(repo, item_id)
        raise RuntimeError("fallo al escribir la fila del material")

    monkeypatch.setattr(materiales, "_descripcion", falla)

    with pytest.raises(RuntimeError):
        materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                          cuando=CUANDO)

    assert inventario.stock_actual(item["id"], camioneta["id"]) == 40, (
        "el movimiento quedo grabado sin su material: se perdio mercaderia"
    )
    assert materiales.listar(incidencia["id"]) == []


def test_cerrar_y_reabrir_el_ticket_no_toca_el_stock(escenario):
    """🔴 El motivo por el que el stock se mueve al cargar y no al cerrar.

    LibraDesk **reabre** incidencias. Si el descuento colgara del cierre,
    reabrir obligaria a revertir y volver a aplicar los movimientos: una
    maquina de estados con efectos sobre un ledger append-only. Moviendolo al
    cargar, el ciclo de estados del ticket no toca el stock ni una vez.
    """
    client, incidencia, item, camioneta = escenario
    materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                      cuando=CUANDO)
    assert inventario.stock_actual(item["id"], camioneta["id"]) == 30

    # El PUT es un reemplazo completo, asi que se manda el ticket entero con
    # el estado cambiado — que es lo que hace la pantalla.
    base = {"cliente_id": incidencia["cliente_id"], "titulo": incidencia["titulo"],
            "descripcion": incidencia["descripcion"]}

    for estado in ("resuelta", "cerrado", "abierto", "cerrado"):
        r = client.put(f"/api/incidencias/{incidencia['id']}",
                       json={**base, "estado": estado})
        assert r.status_code == 200, r.text
        assert r.json()["estado"] == estado
        assert inventario.stock_actual(item["id"], camioneta["id"]) == 30, (
            f"pasar a '{estado}' movio el stock"
        )
