"""Reparaciones (bloque de service / RMA) — pendientes 19 y 18.

Cubre el ciclo completo tal como lo va a usar la mesa de ayuda: el equipo sale
a service dentro del mismo gesto con el que se lo retira, y vuelve dentro del
mismo gesto con el que se lo reinstala. Los tests del ABM de proveedores estan
para la parte que no pasa por el reemplazo.
"""
import os
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import sys
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    from app.asgi import app

    with TestClient(app, base_url="https://testserver") as c:
        r = c.post("/auth/login", json={
            "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
            "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
        })
        assert r.status_code == 200, r.text
        yield c


@pytest.fixture
def escenario(client):
    """Un cliente, dos equipos (el que falla y el prestado), un ticket y un
    proveedor — el caso de la impresora que sale a service."""
    cliente = client.post("/api/clientes", json={"nombre": "Compulibra"}).json()
    hp = client.post("/api/equipos", json={
        "cliente_id": cliente["id"], "tipo": "Impresora", "marca": "HP",
        "modelo": "M404", "sector": "Admisión", "ubicacion_oficina": "Mostrador",
    }).json()
    prestada = client.post("/api/equipos", json={
        "cliente_id": cliente["id"], "tipo": "Impresora", "marca": "Pantum",
        "modelo": "P2500", "sector": "Depósito", "estado": "almacenado",
    }).json()
    ticket = client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "equipo_id": hp["id"],
        "titulo": "Ruido mecánico al imprimir",
    }).json()
    proveedor = client.post("/api/proveedores", json={
        "nombre": "Compu Service SRL", "telefono": "11-5555-0000",
    }).json()
    return {
        "cliente": cliente, "hp": hp, "prestada": prestada,
        "ticket": ticket, "proveedor": proveedor,
    }


HOY = date.today()
AYER = HOY - timedelta(days=1)


def _enviar_a_service(client, esc, **extra):
    payload = {
        "equipo_retirado_id": esc["hp"]["id"],
        "equipo_sustituto_id": esc["prestada"]["id"],
        "destino": "service",
        "motivo": "Ruido mecánico",
        "service": {
            "proveedor_id": esc["proveedor"]["id"],
            "fecha_envio": AYER.isoformat(),
            "remito_salida": "R-0001",
            "rma": "RMA-99",
            "en_garantia": True,
        },
    }
    payload.update(extra)
    return client.post(
        f"/api/incidencias/{esc['ticket']['id']}/reemplazar-equipo", json=payload
    )


# ── El ciclo completo ────────────────────────────────────────────────────────

def test_el_envio_a_service_abre_la_reparacion_en_el_mismo_gesto(client, escenario):
    """El punto del pendiente 19: proveedor, remito, RMA y garantia dejan de ser
    texto libre dentro del motivo del movimiento."""
    r = _enviar_a_service(client, escenario)
    assert r.status_code == 201, r.text
    reparacion = r.json()["reparacion"]

    assert reparacion["proveedor_nombre"] == "Compu Service SRL"
    assert reparacion["remito_salida"] == "R-0001"
    assert reparacion["rma"] == "RMA-99"
    assert reparacion["en_garantia"] is True
    assert reparacion["abierta"] is True
    assert reparacion["fecha_retorno"] is None
    # Queda atada a las dos puntas: al equipo que salio y al ticket que lo causo.
    assert reparacion["equipo_id"] == escenario["hp"]["id"]
    assert reparacion["incidencia_id"] == escenario["ticket"]["id"]


def test_la_vuelta_cierra_la_reparacion_y_calcula_los_dias(client, escenario):
    _enviar_a_service(client, escenario)

    # La vuelta es el mismo reemplazo al reves: sale la prestada, entra la HP.
    r = client.post(
        f"/api/incidencias/{escenario['ticket']['id']}/reemplazar-equipo",
        json={
            "equipo_retirado_id": escenario["prestada"]["id"],
            "equipo_sustituto_id": escenario["hp"]["id"],
            "destino": "deposito",
            "cierre_service": {
                "fecha_retorno": HOY.isoformat(),
                "diagnostico": "Se cambió el fusor",
                "costo": 45000,
            },
        },
    )
    assert r.status_code == 201, r.text
    cerrada = r.json()["reparacion_cerrada"]

    assert cerrada["abierta"] is False
    assert cerrada["fecha_retorno"] == HOY.isoformat()
    assert cerrada["diagnostico"] == "Se cambió el fusor"
    assert cerrada["costo"] == 45000
    assert cerrada["dias_afuera"] == 1

    # Y los dos equipos terminan donde corresponde.
    hp = client.get(f"/api/equipos/{escenario['hp']['id']}").json()
    prestada = client.get(f"/api/equipos/{escenario['prestada']['id']}").json()
    assert (hp["estado"], hp["sector"], hp["ubicacion_oficina"]) == (
        "activo", "Admisión", "Mostrador",
    )
    assert prestada["estado"] == "almacenado"


def test_las_abiertas_son_las_que_estan_hoy_afuera(client, escenario):
    _enviar_a_service(client, escenario)
    assert len(client.get("/api/reparaciones?abiertas=true").json()) == 1

    reparacion = client.get("/api/reparaciones").json()[0]
    client.post(f"/api/reparaciones/{reparacion['id']}/cerrar",
                json={"fecha_retorno": HOY.isoformat()})

    assert client.get("/api/reparaciones?abiertas=true").json() == []
    assert len(client.get("/api/reparaciones?abiertas=false").json()) == 1


# ── Las invariantes ──────────────────────────────────────────────────────────

def test_un_equipo_no_puede_tener_dos_reparaciones_abiertas(client, escenario):
    """Un equipo no esta en dos services a la vez. Sin esta regla el historial
    admite estados imposibles que despues nadie sabe leer."""
    _enviar_a_service(client, escenario)
    r = client.post("/api/reparaciones", json={
        "equipo_id": escenario["hp"]["id"],
        "proveedor_id": escenario["proveedor"]["id"],
        "fecha_envio": HOY.isoformat(),
    })
    assert r.status_code == 409
    assert "abierta" in r.json()["detail"]


def test_los_datos_de_service_con_otro_destino_se_rechazan(client, escenario):
    """Cargar proveedor y RMA para un equipo que se da de baja describe algo que
    no paso. Se rechaza en vez de ignorarse: el que los cargo creia que iban a
    alguna parte."""
    r = _enviar_a_service(client, escenario, destino="baja")
    assert r.status_code == 422
    assert "service" in r.json()["detail"]


def test_no_se_puede_volver_de_un_service_que_no_existe(client, escenario):
    r = client.post(
        f"/api/incidencias/{escenario['ticket']['id']}/reemplazar-equipo",
        json={
            "equipo_retirado_id": escenario["prestada"]["id"],
            "equipo_sustituto_id": escenario["hp"]["id"],
            "destino": "deposito",
            "cierre_service": {"fecha_retorno": HOY.isoformat()},
        },
    )
    assert r.status_code == 422
    assert "abierta" in r.json()["detail"]


def test_la_fecha_de_retorno_no_puede_ser_anterior_a_la_de_envio(client, escenario):
    """Sin esto `dias_afuera` da negativo y la lista de demoras queda sin sentido."""
    _enviar_a_service(client, escenario)
    reparacion = client.get("/api/reparaciones").json()[0]
    r = client.post(
        f"/api/reparaciones/{reparacion['id']}/cerrar",
        json={"fecha_retorno": (AYER - timedelta(days=3)).isoformat()},
    )
    assert r.status_code == 409
    assert "anterior" in r.json()["detail"]


def test_una_reparacion_cerrada_no_se_cierra_dos_veces(client, escenario):
    _enviar_a_service(client, escenario)
    reparacion = client.get("/api/reparaciones").json()[0]
    ruta = f"/api/reparaciones/{reparacion['id']}/cerrar"
    assert client.post(ruta, json={"fecha_retorno": HOY.isoformat()}).status_code == 200
    r = client.post(ruta, json={"fecha_retorno": HOY.isoformat()})
    assert r.status_code == 409
    assert "cerrada" in r.json()["detail"]


# ── El proveedor ─────────────────────────────────────────────────────────────

def test_un_proveedor_con_reparaciones_no_se_borra_y_el_409_dice_cuantas(client, escenario):
    """El 409 lo decide el repositorio contando, no un `except IntegrityError`:
    el pragma `foreign_keys` esta apagado, asi que la base nunca lo levantaria y
    el DELETE pasaria dejando las reparaciones apuntando a un id inexistente."""
    _enviar_a_service(client, escenario)
    r = client.delete(f"/api/proveedores/{escenario['proveedor']['id']}")
    assert r.status_code == 409
    assert "1 reparaciones" in r.json()["detail"]

    # Y la reparacion sigue apuntando a un proveedor que existe.
    assert client.get("/api/reparaciones").json()[0]["proveedor_nombre"] == "Compu Service SRL"


def test_un_proveedor_sin_reparaciones_si_se_borra(client, escenario):
    """Uno cargado por error. Es la contraparte del test de arriba: sin este, el
    409 podria estar rechazando todos los borrados y el otro test pasaria igual."""
    otro = client.post("/api/proveedores", json={"nombre": "Cargado por error"}).json()
    assert client.delete(f"/api/proveedores/{otro['id']}").status_code == 204


def test_el_proveedor_desactivado_no_se_ofrece_pero_sigue_existiendo(client, escenario):
    _enviar_a_service(client, escenario)
    client.post(f"/api/proveedores/{escenario['proveedor']['id']}/desactivar")

    assert client.get("/api/proveedores?solo_activos=true").json() == []
    # Pero la reparacion historica lo sigue nombrando.
    assert client.get("/api/reparaciones").json()[0]["proveedor_nombre"] == "Compu Service SRL"


def test_dos_proveedores_no_pueden_llamarse_igual(client, escenario):
    r = client.post("/api/proveedores", json={"nombre": "Compu Service SRL"})
    assert r.status_code == 409


# ── El desenlace al borrar el ticket ─────────────────────────────────────────

def test_borrar_el_ticket_desvincula_la_reparacion_pero_no_la_borra(client, escenario):
    """El equipo estuvo en service de verdad, con su remito y su RMA, aunque el
    ticket que lo origino ya no exista. Mismo criterio que los movimientos."""
    _enviar_a_service(client, escenario)
    client.delete(f"/api/incidencias/{escenario['ticket']['id']}")

    reparaciones = client.get("/api/reparaciones").json()
    assert len(reparaciones) == 1
    assert reparaciones[0]["incidencia_id"] is None
    assert reparaciones[0]["rma"] == "RMA-99"


# ── La cronologia ────────────────────────────────────────────────────────────

def test_la_reparacion_queda_sellada_en_su_lugar_de_la_cronologia(client, escenario):
    """`_sellar_cronologia` sella `fecha` en unas tablas y `created_at` en otras.
    Sin eso, la reparacion se queda con el `CURRENT_TIMESTAMP` por default.

    **El defecto no es un empate, es el orden**, que es lo que la primera version
    de este test no distinguia: `CURRENT_TIMESTAMP` tiene resolucion de un
    segundo y trunca hacia abajo, asi que la reparacion casi nunca cae exacto
    sobre otra fila —el `set()` no la delata— pero si cae **antes** del retiro
    que la causo. El timeline la muestra ocurriendo primero: el envio a service
    aparece antes de que el equipo se haya retirado. Lo agarro `forzar_fallos.py`.
    """
    creado = _enviar_a_service(client, escenario).json()

    retiro, envio_a_service, instalacion = creado["actividades"]
    assert envio_a_service["descripcion"].startswith("Enviado a service")

    sello_reparacion = creado["reparacion"]["created_at"]
    # El orden causal: primero se retira, despues se registra que salio a
    # service, despues entra el sustituto.
    assert retiro["fecha"] < sello_reparacion < envio_a_service["fecha"], (
        f"la reparación quedó fuera de lugar: retiro={retiro['fecha']} "
        f"reparación={sello_reparacion} envío={envio_a_service['fecha']}"
    )
    assert envio_a_service["fecha"] < instalacion["fecha"]

    # Y nada empata al truncar a milisegundo, que es donde trunca el `Date` de
    # JavaScript: sellar por microsegundos dejaria estos valores distintos en la
    # base y empatados en el navegador (ya paso — ver `_sellar_cronologia`).
    sellos = [a["fecha"] for a in creado["actividades"]]
    sellos += [m["fecha"] for m in creado["movimientos"]]
    sellos.append(sello_reparacion)
    hasta_ms = [s[:23] for s in sellos]
    assert len(set(hasta_ms)) == len(hasta_ms), f"empatan al truncar a ms: {hasta_ms}"
