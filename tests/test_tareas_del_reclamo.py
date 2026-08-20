"""Tareas dentro del reclamo — brecha 4 del relevamiento de Lagrace.

Un reclamo de LibraDesk se resolvía de una sola vez o no se podía representar.
La ficha de Integridad tiene una grilla `Item · Detalle Tarea · F. Inicio ·
F. Fin · Estado · Observación · Tipo Servicio`: **N tareas por reclamo, cada
una con su propio estado y sus propias fechas** — se va, se diagnostica, se pide
un repuesto, se vuelve.

Lo que este archivo defiende, en orden de lo que duele si se rompe:

1. 🔴 **Que un reclamo pueda tener varias tareas, cada una con su estado y sus
   fechas.** Es la brecha entera; sin esto no hay dónde colgar las otras tres
   del bloque (técnicos por tarea, horas con importe, y el «continúa en»).
2. 🔴 **Que el `orden` sea del repositorio y no del que llama**, y que borrar no
   deje huecos. La columna `Item` es lo que el usuario lee para decir "la tres".
3. **Que el tipo de servicio salga del catálogo ya resuelto**, no como un id
   pelado ni desde una tabla propia — que es el error que este producto ya
   cometió con `servicios` y dropeó en la revisión `0031`.
4. **Que vaciar una fecha sea distinto de no mandarla.** Es lo que separa
   `exclude_unset` de `exclude_none`, y se nota justo cuando alguien cierra una
   tarea por error y la quiere reabrir.
5. **Que las tareas no reemplacen al log.** `actividades_incidencia` contesta
   "qué se hizo"; las tareas, "qué falta". Las dos conviven.
"""
import os
from datetime import date

import pytest

from app.services.incidencias import ESTADOS_TAREA, ESTADOS_VALIDOS


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
def reclamo(client) -> int:
    cliente = client.post("/api/clientes", json={
        "nombre": "Neumyser S.A.", "cuit": "30-71234567-9",
    }).json()
    r = client.post("/api/incidencias", json={
        "titulo": "Tienen problemas con las líneas",
        "cliente_id": cliente["id"],
        "prioridad": "media",
    })
    assert r.status_code in (200, 201), r.text
    return r.json()["id"]


def _tarea(client, reclamo, **campos):
    payload = {"detalle": "Diagnóstico en el lugar", **campos}
    return client.post(f"/api/incidencias/{reclamo}/tareas", json=payload)


# ── 1. N tareas por reclamo, cada una con lo suyo ─────────────────────────

def test_un_reclamo_tiene_varias_tareas_con_su_estado_y_sus_fechas(client, reclamo):
    """El caso de Lagrace: se va, se diagnostica, se pide un repuesto, se
    vuelve. Tres intervenciones, tres estados distintos a la vez."""
    _tarea(client, reclamo, detalle="Diagnóstico en el lugar",
           fecha_inicio="2026-08-03", fecha_fin="2026-08-03", estado="terminada")
    _tarea(client, reclamo, detalle="Pedido de repuesto al proveedor",
           fecha_inicio="2026-08-04", estado="en_progreso")
    _tarea(client, reclamo, detalle="Cambio de placa y prueba")

    tareas = client.get(f"/api/incidencias/{reclamo}/tareas").json()
    assert len(tareas) == 3

    # 🔴 Lo que la brecha pedía: cada una con SU estado, no el del reclamo.
    assert [t["estado"] for t in tareas] == ["terminada", "en_progreso", "pendiente"]
    assert [t["fecha_inicio"] for t in tareas] == ["2026-08-03", "2026-08-04", None]
    assert [t["fecha_fin"] for t in tareas] == ["2026-08-03", None, None]

    # Y el reclamo sigue teniendo el suyo, que es otra cosa.
    assert client.get(f"/api/incidencias/{reclamo}").json()["estado"] == "abierto"


def test_el_vocabulario_de_la_tarea_no_es_el_del_reclamo(client, reclamo):
    """`cerrado` existe en el reclamo porque alguien controla el comprobante
    contra la hoja de ruta antes de facturar. Una tarea no pasa por eso."""
    assert ESTADOS_TAREA == ("pendiente", "en_progreso", "terminada")
    assert "cerrado" in ESTADOS_VALIDOS and "cerrado" not in ESTADOS_TAREA

    r = _tarea(client, reclamo, estado="cerrado")
    assert r.status_code == 422, r.text
    assert "pendiente" in r.json()["detail"]


# ── 2. El orden lo pone el repositorio, y borrar no deja huecos ───────────

def test_el_orden_es_del_repositorio_y_no_del_que_llama(client, reclamo):
    for i in range(1, 4):
        _tarea(client, reclamo, detalle=f"Tarea {i}")
    tareas = client.get(f"/api/incidencias/{reclamo}/tareas").json()
    assert [t["orden"] for t in tareas] == [1, 2, 3]

    # Mandar `orden` no lo mueve: el payload lo ignora.
    r = _tarea(client, reclamo, detalle="Cuarta", orden=99)
    assert r.status_code == 201, r.text
    assert r.json()["orden"] == 4


def test_borrar_recompacta_el_orden(client, reclamo):
    """🔴 Sin recompactar, la grilla queda (1, 2, 4) y la próxima que se agregue
    toma el 5 — o peor, repite un número que el usuario ya vio."""
    ids = [_tarea(client, reclamo, detalle=f"Tarea {i}").json()["id"] for i in range(1, 4)]

    r = client.delete(f"/api/incidencias/{reclamo}/tareas/{ids[1]}")
    assert r.status_code == 204, r.text

    tareas = client.get(f"/api/incidencias/{reclamo}/tareas").json()
    assert [t["orden"] for t in tareas] == [1, 2]
    assert [t["detalle"] for t in tareas] == ["Tarea 1", "Tarea 3"]

    # Y la siguiente sigue después de la última, sin repetir.
    assert _tarea(client, reclamo, detalle="Tarea 4").json()["orden"] == 3


# ── 3. El tipo de servicio sale del catálogo ──────────────────────────────

def test_el_tipo_de_servicio_viene_resuelto_del_catalogo(client, reclamo):
    """La columna `Tipo Servicio` muestra el nombre. Resolverlo acá y no en la
    pantalla evita un request por fila — y que la ficha y el comprobante
    nombren distinto al mismo ítem."""
    servicio = client.post("/api/servicios", json={
        "nombre": "Reparación de central", "precio": 15000, "iva_rate": 0.21,
    })
    assert servicio.status_code in (200, 201), servicio.text
    item_id = servicio.json()["id"]

    r = _tarea(client, reclamo, detalle="Cambio de placa", item_id=item_id)
    assert r.status_code == 201, r.text
    assert r.json()["item_id"] == item_id
    assert r.json()["tipo_servicio"] == "Reparación de central"


def test_una_tarea_sin_tipo_de_servicio_es_valida(client, reclamo):
    """Al cargarla puede no saberse todavía qué se va a facturar."""
    r = _tarea(client, reclamo, detalle="Ir a ver qué pasa")
    assert r.status_code == 201, r.text
    assert r.json()["item_id"] is None
    assert r.json()["tipo_servicio"] is None


# ── 4. Editar: parcial, y vaciar no es lo mismo que no mandar ─────────────

def test_editar_solo_toca_lo_que_se_manda(client, reclamo):
    t = _tarea(client, reclamo, detalle="Diagnóstico",
               fecha_inicio="2026-08-03", observacion="Llamar antes").json()

    r = client.patch(f"/api/incidencias/{reclamo}/tareas/{t['id']}",
                     json={"estado": "terminada"})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "terminada"
    # Lo que no se mandó sigue igual.
    assert r.json()["detalle"] == "Diagnóstico"
    assert r.json()["fecha_inicio"] == "2026-08-03"
    assert r.json()["observacion"] == "Llamar antes"


def test_vaciar_una_fecha_es_distinto_de_no_mandarla(client, reclamo):
    """🔴 El caso real: se cerró una tarea por error y hay que reabrirla. Con
    `exclude_none` en vez de `exclude_unset`, mandar `null` sería
    indistinguible de no mandar el campo y la fecha no se podría borrar."""
    t = _tarea(client, reclamo, detalle="Cambio de placa",
               fecha_inicio="2026-08-03", fecha_fin="2026-08-05").json()
    assert t["fecha_fin"] == "2026-08-05"

    r = client.patch(f"/api/incidencias/{reclamo}/tareas/{t['id']}",
                     json={"fecha_fin": None})
    assert r.status_code == 200, r.text
    assert r.json()["fecha_fin"] is None
    # Y la de inicio, que no se mandó, sigue puesta.
    assert r.json()["fecha_inicio"] == "2026-08-03"


def test_editar_sin_campos_no_es_un_no_op_silencioso(client, reclamo):
    t = _tarea(client, reclamo).json()
    r = client.patch(f"/api/incidencias/{reclamo}/tareas/{t['id']}", json={})
    assert r.status_code == 422, r.text


# ── 5. Validaciones ───────────────────────────────────────────────────────

def test_una_tarea_sin_detalle_no_entra(client, reclamo):
    assert _tarea(client, reclamo, detalle="   ").status_code == 422
    assert _tarea(client, reclamo, detalle="").status_code == 422


def test_la_fecha_de_fin_no_puede_ser_anterior_a_la_de_inicio(client, reclamo):
    r = _tarea(client, reclamo, fecha_inicio="2026-08-05", fecha_fin="2026-08-03")
    assert r.status_code == 422, r.text
    assert "anterior" in r.json()["detail"]


def test_editar_tampoco_deja_invertir_las_fechas(client, reclamo):
    """La validación va en el repositorio y no en el alta: si viviera sólo en
    el `POST`, un `PATCH` la saltearía."""
    t = _tarea(client, reclamo, fecha_inicio="2026-08-05").json()
    r = client.patch(f"/api/incidencias/{reclamo}/tareas/{t['id']}",
                     json={"fecha_fin": "2026-08-03"})
    assert r.status_code == 422, r.text


def test_reclamo_y_tarea_inexistentes(client, reclamo):
    assert _tarea(client, 99999).status_code == 404
    assert client.patch(f"/api/incidencias/{reclamo}/tareas/99999",
                        json={"estado": "terminada"}).status_code == 404
    assert client.delete(f"/api/incidencias/{reclamo}/tareas/99999").status_code == 404


# ── 6. Las tareas no reemplazan al log ────────────────────────────────────

def test_las_tareas_conviven_con_el_log_de_actividades(client, reclamo):
    """`actividades_incidencia` contesta "qué se hizo"; las tareas, "qué falta".
    Si una tarea escribiera en el log, la ficha mostraría el mismo hecho dos
    veces — que es el criterio con el que este producto ya dejó afuera de la
    auditoría a las tablas que ya son historial."""
    antes = client.get(f"/api/incidencias/{reclamo}").json().get("actividades") or []
    _tarea(client, reclamo, detalle="Diagnóstico")
    despues = client.get(f"/api/incidencias/{reclamo}").json().get("actividades") or []
    assert len(despues) == len(antes)


def test_borrar_el_reclamo_se_lleva_sus_tareas(client, reclamo):
    """`ondelete=CASCADE`, y contra PostgreSQL eso se aplica de verdad."""
    _tarea(client, reclamo, detalle="Diagnóstico")
    assert client.get(f"/api/incidencias/{reclamo}/tareas").json()

    r = client.delete(f"/api/incidencias/{reclamo}")
    assert r.status_code in (200, 204), r.text
    assert client.get(f"/api/incidencias/{reclamo}/tareas").json() == []
