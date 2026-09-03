"""El cruce entre el stock por cantidad y las unidades serializadas.

Hasta el 2026-08-16 **nada cruzaba de uno al otro, en ninguna dirección**: se
vendía una central, se cobraba, se instalaba, y el próximo reclamo sobre ese
equipo no la encontraba. Y dar de alta un activo a mano dejaba la unidad
contada dos veces.

Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que vender un equipo lo deje en el parque del cliente**, uno por unidad.
   Es el pedido, y es lo único que hace contestable "¿este equipo ya nos dio
   problemas antes?".
2. 🔴 **Que vender un consumible NO deje nada.** Sin esto el parque de cada
   cliente se llena de fichas y cables, y deja de servir para lo que existe.
3. 🔴 **Que convertir stock en activo descuente la unidad.** Es el doble conteo,
   y es plata: el mismo equipo aparecería en el stock del depósito y como
   activo disponible para colocar.
4. **Que un fallo al descontar no deje el activo creado** — la compensación.
5. Que editar un producto no le borre la marca de equipo, igual que la alícuota.
"""

import os
from datetime import datetime

import pytest

from app.services import activos as activos_mod
from app.services import inventario

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
    """Un cliente, un depósito con stock, y DOS productos: uno equipo, uno no.

    Los dos en la misma venta es el punto: con un solo producto marcado, el test
    pasaría igual si el alta diera de alta *todo* lo vendido.
    """
    cliente = client.post("/api/clientes", json={
        "nombre": "Medici Neumatec", "empresa": "NEUMYSER SRL",
        "cuit": "30-11111111-7", "ciudad": "Chivilcoy",
    }).json()
    central = inventario.crear_item(
        "Central HiPath 1120", costo=80000.0, precio=200000.0, es_equipo=True,
    )
    ficha = inventario.crear_item(
        "Ficha RJ11", costo=200.0, precio=800.0,   # sin marcar: consumible
    )
    deposito = inventario.crear_deposito("Depósito central")
    inventario.ajustar(central["id"], deposito["id"], 5, fecha=CUANDO)
    inventario.ajustar(ficha["id"], deposito["id"], 100, fecha=CUANDO)
    return client, cliente, central, ficha, deposito


def _vender(client, deposito, cliente_id, items):
    r = client.post("/api/ventas", json={
        "cliente_id": cliente_id, "deposito_id": deposito["id"],
        "items": items, "pagos": [],
    })
    assert r.status_code == 201, r.text
    return r.json()


def _parque(client, cliente_id):
    return client.get(f"/api/equipos?cliente_id={cliente_id}").json()


# ── 1 y 2. Qué queda en el parque ────────────────────────────────────────


def test_vender_dos_centrales_deja_dos_equipos_y_la_ficha_ninguno(escenario):
    client, cliente, central, ficha, deposito = escenario
    assert _parque(client, cliente["id"]) == []

    venta = _vender(client, deposito, cliente["id"], [
        {"item_id": central["id"], "descripcion": "Central HiPath 1120",
         "cantidad": 2, "precio": 200000.0},
        {"item_id": ficha["id"], "descripcion": "Ficha RJ11",
         "cantidad": 10, "precio": 800.0},
    ])

    parque = _parque(client, cliente["id"])
    assert len(parque) == 2, (
        "dos centrales son dos equipos, y las 10 fichas ninguno"
    )
    assert {e["tipo"] for e in parque} == {"Central HiPath 1120"}
    assert venta["equipos_dados_de_alta"] == 2


def test_el_equipo_nace_sin_serie_y_dice_de_que_venta_salio(escenario):
    client, cliente, central, _ficha, deposito = escenario
    venta = _vender(client, deposito, cliente["id"], [
        {"item_id": central["id"], "descripcion": "Central HiPath 1120",
         "cantidad": 1, "precio": 200000.0},
    ])

    equipo = _parque(client, cliente["id"])[0]
    # Sin serie a propósito: el stock es por cantidad y no las conoce.
    assert not equipo["serial"]
    assert venta["numero"] in (equipo["observaciones"] or "")


def test_el_alta_deja_su_movimiento_en_el_historial(escenario):
    """`EquipoRepository.create()` escribe el movimiento de alta. Pasar por ahí
    —y no insertar el modelo a mano— es lo que hace que el equipo nazca con
    historial como cualquier otro."""
    client, cliente, central, _ficha, deposito = escenario
    _vender(client, deposito, cliente["id"], [
        {"item_id": central["id"], "descripcion": "Central HiPath 1120",
         "cantidad": 1, "precio": 200000.0},
    ])

    equipo = _parque(client, cliente["id"])[0]
    movs = client.get(f"/api/equipos/{equipo['id']}/movimientos").json()
    assert [m["tipo"] for m in movs] == ["alta"]


def test_una_venta_sin_cliente_no_da_de_alta_nada_y_lo_dice(escenario):
    """No hay a quién atribuirle el equipo — `equipos.cliente_id` es NOT NULL.

    Lo que se afirma no es sólo que no cree equipos: es que **lo diga**. Un cero
    que nadie ve es indistinguible de que la feature no exista.
    """
    client, _cliente, central, _ficha, deposito = escenario
    venta = _vender(client, deposito, None, [
        {"item_id": central["id"], "descripcion": "Central HiPath 1120",
         "cantidad": 1, "precio": 200000.0},
    ])
    assert venta["equipos_dados_de_alta"] == 0


def test_desmarcar_el_producto_deja_de_dar_de_alta(escenario):
    """La contraprueba del flag: sin ella, el test 1 pasaría igual si el alta
    diera de alta todo lo vendido y el flag no se leyera nunca."""
    client, cliente, central, _ficha, deposito = escenario
    inventario.editar_item(
        central["id"], nombre="Central HiPath 1120", precio=200000.0,
        es_equipo=False,
    )

    venta = _vender(client, deposito, cliente["id"], [
        {"item_id": central["id"], "descripcion": "Central HiPath 1120",
         "cantidad": 1, "precio": 200000.0},
    ])
    assert venta["equipos_dados_de_alta"] == 0
    assert _parque(client, cliente["id"]) == []


def test_editar_un_producto_no_le_borra_la_marca_de_equipo(escenario):
    """Mismo pozo que la alícuota: `save_catalog_item()` pisa la fila entera."""
    _client, _cliente, central, _ficha, _deposito = escenario

    inventario.editar_item(
        central["id"], nombre="Central HiPath 1120", precio=250000.0,
    )  # sin `es_equipo`

    assert inventario.es_equipo_de_items([central["id"]]) == {central["id"]}, (
        "guardar el precio no puede llevarse puesta la marca de equipo"
    )


# ── 3 y 4. Stock → activo, sin contar dos veces ──────────────────────────


def test_convertir_stock_en_activo_descuenta_la_unidad(escenario):
    client, _cliente, central, _ficha, deposito = escenario
    antes = inventario.stock_actual(central["id"], deposito["id"])
    assert antes == 5

    r = client.post("/api/activos/desde-stock", json={
        "item_id": central["id"], "deposito_stock_id": deposito["id"],
        "tipo": "Central HiPath 1120", "serial": "SN-0001",
    })
    assert r.status_code == 201, r.text

    assert inventario.stock_actual(central["id"], deposito["id"]) == antes - 1, (
        "sin el descuento la unidad queda contada dos veces: en el stock y "
        "como activo disponible"
    )
    assert r.json()["serial"] == "SN-0001"


def test_sin_stock_no_se_puede_convertir(escenario):
    client, _cliente, central, _ficha, deposito = escenario
    otro = inventario.crear_deposito("Depósito vacío")

    r = client.post("/api/activos/desde-stock", json={
        "item_id": central["id"], "deposito_stock_id": otro["id"],
        "tipo": "Central HiPath 1120",
    })
    assert r.status_code == 409
    assert "disponible" in r.json()["detail"]


def test_si_falla_el_descuento_no_queda_el_activo_creado(escenario, monkeypatch):
    """La compensación. Sin ella, la ventana entre las dos conexiones
    reintroduce exactamente el doble conteo que esto viene a cerrar."""
    _client, _cliente, central, _ficha, deposito = escenario
    repo = activos_mod.ActivoRepository(
        __import__("app.database", fromlist=["x"]).get_session_factory()
    )
    antes = len(repo.list())

    def ajuste_roto(*a, **k):
        raise RuntimeError("el movimiento de stock falló")

    monkeypatch.setattr(inventario, "ajustar", ajuste_roto)

    with pytest.raises(RuntimeError):
        repo.crear_desde_stock(
            central["id"], deposito["id"], tipo="Central HiPath 1120",
        )

    assert len(repo.list()) == antes, (
        "el activo tiene que haberse borrado: si queda, la unidad está contada "
        "dos veces y nadie lo ve"
    )
