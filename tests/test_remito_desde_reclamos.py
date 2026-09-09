"""Armar el remito trayendo los reclamos del cliente (2026-09-09).

Pedido del humano: *"cuando estoy en remitos, nuevo remito, elijo el cliente,
tengo que poder ver los reclamos cerrados sin facturar para que me deje
elegirlos uno o más para agregarlos en el remito"*. Y, en el mismo mensaje, la
decisión de fondo: **este camino reemplaza al de la grilla**.

## Lo que cambia, y por qué necesita tests propios

Por el camino viejo el remito salía **ya emitido** con lo que el sistema
decidía. Por éste hay **dos pasos**: primero se previsualizan los renglones
(`lineas-para-remito`, que no escribe), se editan, y recién al guardar el remito
se **atan** los reclamos.

🔴 **Ese vínculo es lo único que impide el doble cobro**, y es lo que separa
este camino de "pegar unos renglones a mano". Si `POST /api/remitos` no atara,
el mismo trabajo podría entrar en dos comprobantes — que es el error que este
producto ya tuvo. Los tests de `vincular` de abajo son los que importan.
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
    cliente = client.post("/api/clientes", json={
        "nombre": "Metalmax", "cuit": "30-71234567-9",
    }).json()
    otro = client.post("/api/clientes", json={"nombre": "Frigorífico"}).json()
    return {"cliente": cliente, "otro": otro}


def reclamo_cerrado(client, cliente_id, titulo="Central sin tono", **extra):
    """Un reclamo cerrado y listo para facturar.

    ⚠️ **El `PUT` manda TODOS los campos, no sólo los que cambian.** La primera
    version de este helper cerraba el reclamo con un `PUT` que no reenviaba
    `nro_cds`, y eso **lo borraba** -- el test del CDS fallaba con el CDS
    ausente y parecia un defecto del renglon. `IncidenciaIn` tiene todos los
    campos opcionales con default `None`, asi que omitir uno es pedir que quede
    en `None`.
    """
    r = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "titulo": titulo, **extra,
    })
    assert r.status_code == 201, r.text
    creado = r.json()

    r = client.put(f"/api/incidencias/{creado['id']}", json={
        "cliente_id": cliente_id, "titulo": titulo, "estado": "cerrado",
        "horas_invertidas": 2, **extra,
    })
    assert r.status_code == 200, r.text
    return r.json()


# ── Previsualizar sin escribir ─────────────────────────────────────────────

def test_devuelve_los_renglones_sin_emitir_nada(client, escenario):
    """🔑 **Es lo que hace posible editar antes de emitir.**

    Antes el remito nacía emitido y corregirlo era editar un comprobante hecho.
    """
    rec = reclamo_cerrado(client, escenario["cliente"]["id"])

    r = client.post("/api/incidencias/lineas-para-remito",
                    json={"incidencia_ids": [rec["id"]]})
    assert r.status_code == 200, r.text
    assert len(r.json()["items"]) >= 1
    assert r.json()["incidencia_ids"] == [rec["id"]]

    # 🔴 Y NO emitió: previsualizar no puede dejar un comprobante.
    assert client.get("/api/remitos").json() == []
    # Ni ató nada: el reclamo sigue disponible.
    assert client.get(f"/api/incidencias/{rec['id']}").json()["remito_id"] is None


def test_el_renglon_trae_el_cds(client, escenario):
    """El N° CDS encabeza la línea: es lo único que ata la conformidad firmada
    en papel con el ticket del sistema."""
    rec = reclamo_cerrado(client, escenario["cliente"]["id"], nro_cds="0001-00041996")

    r = client.post("/api/incidencias/lineas-para-remito",
                    json={"incidencia_ids": [rec["id"]]})
    assert "0001-00041996" in r.json()["items"][0]["description"]


def test_las_horas_van_como_cantidad(client, escenario):
    rec = reclamo_cerrado(client, escenario["cliente"]["id"])

    r = client.post("/api/incidencias/lineas-para-remito",
                    json={"incidencia_ids": [rec["id"]]})
    assert r.json()["items"][0]["qty"] == 2


def test_valida_lo_mismo_que_emitir(client, escenario):
    """Un lote que no se podría emitir falla **acá**, y no después de que la
    persona haya tipeado el comprobante entero."""
    a = reclamo_cerrado(client, escenario["cliente"]["id"])
    b = reclamo_cerrado(client, escenario["otro"]["id"], "De otro cliente")

    r = client.post("/api/incidencias/lineas-para-remito",
                    json={"incidencia_ids": [a["id"], b["id"]]})
    assert r.status_code == 409, r.text
    assert "cliente" in r.text.lower()


def test_un_reclamo_abierto_no_se_puede_traer(client, escenario):
    """Sólo `cerrado`: `resuelta` es "el técnico terminó" y todavía falta el
    control del comprobante contra la hoja de ruta."""
    r = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "Abierto",
    })
    abierto = r.json()

    r = client.post("/api/incidencias/lineas-para-remito",
                    json={"incidencia_ids": [abierto["id"]]})
    assert r.status_code == 409, r.text


def test_uno_ya_remitado_da_409_y_no_los_renglones(client, escenario):
    """Previsualizar algo ya facturado no tiene sentido, y devolver el remito
    viejo se leería como "estos son tus renglones"."""
    rec = reclamo_cerrado(client, escenario["cliente"]["id"])
    remito = client.post("/api/remitos", json={
        "client_id": escenario["cliente"]["id"],
        "items": [{"description": "Trabajo", "qty": 1, "unit_price": 1000}],
        "incidencia_ids": [rec["id"]],
    }).json()
    assert remito["id"]

    r = client.post("/api/incidencias/lineas-para-remito",
                    json={"incidencia_ids": [rec["id"]]})
    assert r.status_code == 409, r.text


# ── El vínculo al guardar, que es lo que evita el doble cobro ──────────────

def test_crear_el_remito_ata_los_reclamos(client, escenario):
    """🔴 **El test central de toda esta tanda.**

    Sin este vínculo los renglones traídos serían texto suelto, y el mismo
    trabajo podría entrar en dos comprobantes.
    """
    rec = reclamo_cerrado(client, escenario["cliente"]["id"])

    remito = client.post("/api/remitos", json={
        "client_id": escenario["cliente"]["id"],
        "items": [{"description": "Trabajo", "qty": 2, "unit_price": 21100}],
        "incidencia_ids": [rec["id"]],
    }).json()

    assert client.get(f"/api/incidencias/{rec['id']}").json()["remito_id"] == remito["id"]


def test_ata_varios_de_una(client, escenario):
    """El caso real: tres visitas del mes en un solo remito, porque una factura
    es la que va a salir de ahí."""
    a = reclamo_cerrado(client, escenario["cliente"]["id"], "Uno")
    b = reclamo_cerrado(client, escenario["cliente"]["id"], "Dos")

    remito = client.post("/api/remitos", json={
        "client_id": escenario["cliente"]["id"],
        "items": [{"description": "Trabajos del mes", "qty": 1, "unit_price": 50000}],
        "incidencia_ids": [a["id"], b["id"]],
    }).json()

    for rec in (a, b):
        assert client.get(f"/api/incidencias/{rec['id']}").json()["remito_id"] == remito["id"]


def test_un_remito_sin_reclamos_no_ata_nada(client, escenario):
    """El remito tipeado a mano sigue andando igual que antes de que esto
    existiera: la lista vacía es el caso normal."""
    r = client.post("/api/remitos", json={
        "client_id": escenario["cliente"]["id"],
        "items": [{"description": "Algo suelto", "qty": 1, "unit_price": 100}],
    })
    assert r.status_code == 201, r.text


def test_no_pisa_el_vinculo_de_uno_ya_atado(client, escenario):
    """🔴 Pisar el vínculo dejaría al remito viejo cobrando un trabajo que ahora
    figura en otro, y a nadie enterándose."""
    rec = reclamo_cerrado(client, escenario["cliente"]["id"])
    primero = client.post("/api/remitos", json={
        "client_id": escenario["cliente"]["id"],
        "items": [{"description": "Primero", "qty": 1, "unit_price": 100}],
        "incidencia_ids": [rec["id"]],
    }).json()

    # Un segundo remito intentando llevarse el mismo reclamo.
    client.post("/api/remitos", json={
        "client_id": escenario["cliente"]["id"],
        "items": [{"description": "Segundo", "qty": 1, "unit_price": 100}],
        "incidencia_ids": [rec["id"]],
    })

    # Sigue apuntando al PRIMERO.
    assert client.get(f"/api/incidencias/{rec['id']}").json()["remito_id"] == primero["id"]


def test_el_reclamo_atado_deja_de_estar_disponible(client, escenario):
    """Es lo que el selector consulta para no ofrecerlo: `remito_id` distinto de
    `null` lo saca de la lista."""
    rec = reclamo_cerrado(client, escenario["cliente"]["id"])
    client.post("/api/remitos", json={
        "client_id": escenario["cliente"]["id"],
        "items": [{"description": "Trabajo", "qty": 1, "unit_price": 100}],
        "incidencia_ids": [rec["id"]],
    })

    cerrados = client.get(
        f"/api/incidencias?cliente_id={escenario['cliente']['id']}&estado=cerrado"
    ).json()
    sin_facturar = [i for i in cerrados if i["remito_id"] is None]
    assert sin_facturar == []
