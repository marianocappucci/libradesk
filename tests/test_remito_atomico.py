"""Un remito y su origen se escriben juntos o no se escriben (2026-10-16).

Hasta hoy el remito entraba por la conexion de LibraCore y el vinculo con su
origen (`incidencias.remito_id`, `contratos_cuotas.remito_id`, `ventas_remitos`,
`presupuestos.remito_id`) por SQLAlchemy: dos commits. Si el proceso caia entre
los dos quedaba un **remito huerfano**, y eso duele por dos lados:

1. El puente de facturacion lo ofrece (y lo manda) igual: es un remito con total.
2. El origen sigue "pendiente de remitir", asi que se vuelve a remitir y el mismo
   trabajo sale en dos comprobantes.

Core y dominio son la MISMA base PostgreSQL, asi que `RemitoService.create(
vincular=...)` emite el remito por la sesion de SQLAlchemy que despues lo ata y
commitea las dos cosas juntas.

La caida se simula haciendo que la escritura del vinculo levante despues de que
el remito ya se inserto. Cada test falla con el codigo anterior (queda un remito
sin origen) y pasa con el actual (no queda nada).
"""
import json
import os

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.services import inventario, iva


class Caida(RuntimeError):
    """El proceso muere (o la base corta la conexion) justo despues del remito."""


@pytest.fixture
def client(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def cliente(client):
    return client.post("/api/clientes", json={"nombre": "Metalmax"}).json()


def _remitos(client):
    return client.get("/api/remitos").json()


def _bandeja(client):
    r = client.get("/api/facturacion/pendientes")
    assert r.status_code == 200, r.text
    return [p["id"] for p in r.json()["items"] if p["origen_tipo"] == "remito"]


def _sin_remito_facturable(client):
    """Ni un remito, ni uno en la bandeja del puente."""
    assert _remitos(client) == [], "quedo un remito huerfano"
    assert _bandeja(client) == [], "el puente ofreceria un remito huerfano"


def _caida_en_el_vinculo(monkeypatch, *, sentencia: str):
    """Hace que la sesion levante al escribir el vinculo, no el remito.

    Se intercepta `Session.execute` y no una funcion del producto: asi el test
    vale con el codigo anterior (donde esa misma sentencia corria en la sesion
    del vinculo, despues del commit del remito) y con el actual.
    """
    original = Session.execute

    def _execute(self, statement, *a, **k):
        if sentencia in str(statement):
            raise Caida(sentencia)
        return original(self, statement, *a, **k)

    monkeypatch.setattr(Session, "execute", _execute)


def _reclamo_cerrado(client, cliente_id, titulo="Central sin tono"):
    r = client.post("/api/incidencias", json={"cliente_id": cliente_id, "titulo": titulo})
    assert r.status_code == 201, r.text
    creado = r.json()
    r = client.put(f"/api/incidencias/{creado['id']}", json={
        "cliente_id": cliente_id, "titulo": titulo, "estado": "cerrado",
        "horas_invertidas": 2,
    })
    assert r.status_code == 200, r.text
    return r.json()


def _remito_id_de(client, incidencia_id):
    return client.get(f"/api/incidencias/{incidencia_id}").json()["remito_id"]


# ── Reclamos: POST /api/remitos con incidencia_ids ─────────────────────────


def test_caida_al_crear_un_remito_con_reclamos_no_deja_remito_ni_vinculo(
        client, cliente, monkeypatch):
    rec = _reclamo_cerrado(client, cliente["id"])
    cuerpo = {
        "client_id": cliente["id"],
        "items": [{"description": "Trabajo", "qty": 1, "unit_price": 100}],
        "incidencia_ids": [rec["id"]],
    }
    with monkeypatch.context() as m:
        _caida_en_el_vinculo(m, sentencia="UPDATE incidencias")
        with pytest.raises(Caida):
            client.post("/api/remitos", json=cuerpo)

    _sin_remito_facturable(client)
    assert _remito_id_de(client, rec["id"]) is None, "el reclamo sigue pendiente"

    # Y se rehace sin mas: un solo remito, con el reclamo atado.
    r = client.post("/api/remitos", json=cuerpo)
    assert r.status_code == 201, r.text
    assert [x["id"] for x in _remitos(client)] == [r.json()["id"]]
    assert _remito_id_de(client, rec["id"]) == r.json()["id"]


def test_un_reclamo_que_ya_tiene_remito_no_genera_un_segundo_remito(client, cliente):
    """Antes el POST emitia igual y el vinculo se saltaba al reclamo en silencio:
    quedaba un segundo remito por el mismo trabajo, sin nada que lo respalde."""
    rec = _reclamo_cerrado(client, cliente["id"])
    cuerpo = {
        "client_id": cliente["id"],
        "items": [{"description": "Trabajo", "qty": 1, "unit_price": 100}],
        "incidencia_ids": [rec["id"]],
    }
    primero = client.post("/api/remitos", json=cuerpo)
    assert primero.status_code == 201, primero.text

    segundo = client.post("/api/remitos", json=cuerpo)

    assert segundo.status_code == 409, segundo.text
    assert [x["id"] for x in _remitos(client)] == [primero.json()["id"]]
    assert _remito_id_de(client, rec["id"]) == primero.json()["id"]


def test_un_reclamo_que_no_existe_no_deja_un_remito_a_medias(client, cliente):
    r = client.post("/api/remitos", json={
        "client_id": cliente["id"],
        "items": [{"description": "Trabajo", "qty": 1, "unit_price": 100}],
        "incidencia_ids": [9999],
    })
    assert r.status_code == 409, r.text
    assert _remitos(client) == []


def test_un_renglon_en_dolares_sin_cotizacion_sigue_siendo_422(client, cliente):
    """El `ValueError` del renglon no se confunde con el conflicto del vinculo."""
    rec = _reclamo_cerrado(client, cliente["id"])
    r = client.post("/api/remitos", json={
        "client_id": cliente["id"],
        "items": [{"description": "Licencia", "qty": 1, "unit_price": 10, "moneda": "USD"}],
        "incidencia_ids": [rec["id"]],
    })
    assert r.status_code == 422, r.text
    assert _remito_id_de(client, rec["id"]) is None


# ── Reclamos: convertir en remito (uno y lote) ─────────────────────────────


def test_caida_al_convertir_un_lote_de_reclamos_no_deja_remito_ni_vinculo(
        client, cliente, monkeypatch):
    ids = [_reclamo_cerrado(client, cliente["id"], t)["id"] for t in ("Uno", "Dos", "Tres")]
    with monkeypatch.context() as m:
        _caida_en_el_vinculo(m, sentencia="UPDATE incidencias")
        with pytest.raises(Caida):
            client.post("/api/incidencias/convertir-en-remito", json={"incidencia_ids": ids})

    _sin_remito_facturable(client)
    assert [_remito_id_de(client, x) for x in ids] == [None, None, None]

    r = client.post("/api/incidencias/convertir-en-remito", json={"incidencia_ids": ids})
    assert r.status_code == 201, r.text
    assert len(_remitos(client)) == 1
    assert {_remito_id_de(client, x) for x in ids} == {r.json()["id"]}


def test_caida_al_convertir_un_reclamo_suelto(client, cliente, monkeypatch):
    rec = _reclamo_cerrado(client, cliente["id"])
    with monkeypatch.context() as m:
        _caida_en_el_vinculo(m, sentencia="UPDATE incidencias")
        with pytest.raises(Caida):
            client.post(f"/api/incidencias/{rec['id']}/convertir-en-remito")

    _sin_remito_facturable(client)
    r = client.post(f"/api/incidencias/{rec['id']}/convertir-en-remito")
    assert r.status_code == 201, r.text
    assert len(_remitos(client)) == 1


# ── Cuotas ──────────────────────────────────────────────────────────────────


def test_caida_al_convertir_una_cuota_no_deja_remito_ni_vinculo(
        client, cliente, monkeypatch):
    r = client.post("/api/contratos", json={
        "tipo_contrato": "alquiler", "cliente_id": cliente["id"],
        "fecha_inicio": "2026-08-01", "estado": "activo", "importe": 31000,
    })
    assert r.status_code in (200, 201), r.text
    generadas = client.post("/api/cuotas/generar", json={"ancla": "2026-08-15"}).json()
    cuota = generadas["generadas"][0]

    with monkeypatch.context() as m:
        _caida_en_el_vinculo(m, sentencia="UPDATE contratos_cuotas")
        with pytest.raises(Caida):
            client.post("/api/cuotas/convertir-en-remito", json={"cuota_ids": [cuota["id"]]})

    _sin_remito_facturable(client)
    assert client.get(f"/api/cuotas/{cuota['id']}").json()["remito_id"] is None

    r = client.post("/api/cuotas/convertir-en-remito", json={"cuota_ids": [cuota["id"]]})
    assert r.status_code == 201, r.text
    assert client.get(f"/api/cuotas/{cuota['id']}").json()["remito_id"] == r.json()["id"]
    assert len(_remitos(client)) == 1


# ── Ventas ──────────────────────────────────────────────────────────────────


def test_caida_al_convertir_una_venta_no_deja_remito_ni_vinculo(
        client, cliente, monkeypatch):
    from datetime import datetime

    item = inventario.crear_item("Central HiPath", costo=80000.0, precio=200000.0,
                                 iva_rate=iva.DEFECTO)
    deposito = inventario.crear_deposito("Depósito central")
    inventario.ajustar(item["id"], deposito["id"], 5, fecha=datetime(2026, 8, 16, 10))
    r = client.post("/api/ventas", json={
        "cliente_id": cliente["id"], "pagos": [], "deposito_id": deposito["id"],
        "items": [{"item_id": item["id"], "descripcion": "Central",
                   "cantidad": 1, "precio": 200000.0}],
    })
    assert r.status_code == 201, r.text
    venta_id = client.get("/api/ventas").json()[0]["id"]

    with monkeypatch.context() as m:
        original = Session.add

        def _add(self, instancia, *a, **k):
            if type(instancia).__name__ == "VentaRemito":
                raise Caida("VentaRemito")
            return original(self, instancia, *a, **k)

        m.setattr(Session, "add", _add)
        with pytest.raises(Caida):
            client.post(f"/api/ventas/{venta_id}/convertir-en-remito", json={})

    _sin_remito_facturable(client)

    r = client.post(f"/api/ventas/{venta_id}/convertir-en-remito", json={})
    assert r.status_code == 201, r.text
    assert len(_remitos(client)) == 1


# ── Presupuestos ────────────────────────────────────────────────────────────


def test_caida_al_convertir_un_presupuesto_no_deja_remito_ni_vinculo(
        client, cliente, monkeypatch):
    p = client.post("/api/presupuestos", json={
        "client_id": cliente["id"],
        "items": [{"description": "Reparacion", "qty": 2, "unit_price": 15000}],
    })
    assert p.status_code == 201, p.text
    pid = p.json()["id"]

    with monkeypatch.context() as m:
        # El vinculo se escribe hoy por la sesion del remito; antes lo escribia el
        # motor con su propia conexion, despues de crearlo. Se corta en los dos
        # lugares para que el test valga con cualquiera de las dos versiones.
        _caida_en_el_vinculo(m, sentencia="UPDATE presupuestos")

        def _cae(*a, **k):
            raise Caida("update_presupuesto_remito_id")

        m.setattr("libracore.db.remitos_presupuestos.update_presupuesto_remito_id", _cae)
        with pytest.raises(Caida):
            client.post(f"/api/presupuestos/{pid}/convertir-en-remito")

    _sin_remito_facturable(client)
    despues = client.get(f"/api/presupuestos/{pid}").json()
    assert despues["remito_id"] is None
    assert despues["status"] == "borrador"

    r = client.post(f"/api/presupuestos/{pid}/convertir-en-remito")
    assert r.status_code == 201, r.text
    despues = client.get(f"/api/presupuestos/{pid}").json()
    assert despues["remito_id"] == r.json()["id"]
    assert despues["status"] == "aceptado"
    assert len(_remitos(client)) == 1


# ── La copia del INSERT del motor ──────────────────────────────────────────


def test_el_insert_transaccional_escribe_lo_mismo_que_el_del_motor(client, cliente):
    """`_insertar_remito` copia el INSERT de `rp.create_remito` (el motor no
    ofrece `conn=`). Si el motor suma una columna, esto se pone rojo al subir el
    pin y no en produccion: las dos filas tienen que ser identicas salvo lo que
    la base genera."""
    from app.services.remitos_presupuestos import RemitoService

    base = dict(
        date="2026-10-16", client_id=cliente["id"], client_name="Metalmax",
        client_address="Calle 1", client_cuit="30-71234567-9",
        client_email="a@b.com", client_phone="123",
        items=[{"description": "Trabajo ñandú", "qty": 2, "unit_price": 100.5}],
        observations="obs", usuario_id=None,
    )
    servicio = RemitoService()
    comun = servicio.create(**base)
    atado = servicio.create(
        **base, vincular=lambda sesion, remito_id: sesion.execute(text("SELECT 1")))

    generado = {"id", "number", "created_at"}
    a = {k: v for k, v in comun.items() if k not in generado}
    b = {k: v for k, v in atado.items() if k not in generado}
    assert a == b
    assert set(comun) == set(atado)
    assert json.dumps(a["items"], sort_keys=True) == json.dumps(b["items"], sort_keys=True)
