"""La agenda de los equipos (pedido 42, fase B).

Lo que cierra esta fase: la fase A dejó la disponibilidad en "está o no está en
otro equipo", porque la incidencia no sabía **cuándo** se iba a atender. Con
`fecha_programada` el motor de turnos puede decir si dos trabajos se pisan.

**LibraGenda se usa como librería de reglas, no de persistencia** — de todo el
motor se importa `find_conflicts()`, que es pura. Estos tests afirman el
comportamiento resultante, no la integración: si algún día se cambiara el motor
por otro, lo que tiene que seguir valiendo es esto.
"""
import os
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin."""
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


MARTES = datetime(2026, 8, 11, 9, 0)


def f(dt: datetime) -> str:
    return dt.isoformat()


@pytest.fixture
def escenario(client):
    cliente = client.post("/api/clientes", json={"nombre": "Estudio Sur"}).json()
    jefe = client.post("/api/tecnicos", json={
        "nombre": "Rubén Actis", "es_tecnico": True, "es_responsable": True,
    }).json()
    norte = client.post("/api/equipos-trabajo", json={
        "nombre": "Cuadrilla Norte", "responsable_id": jefe["id"],
    }).json()
    sur = client.post("/api/equipos-trabajo", json={
        "nombre": "Cuadrilla Sur", "responsable_id": jefe["id"],
    }).json()
    kangoo = client.post("/api/equipos-trabajo/vehiculos", json={
        "patente": "AB123CD", "marca": "Renault", "modelo": "Kangoo",
    }).json()
    client.post(f"/api/equipos-trabajo/vehiculos/{kangoo['id']}/asignar",
                json={"equipo_id": norte["id"]})
    return {"cliente": cliente, "norte": norte, "sur": sur, "kangoo": kangoo}


def _agendar(client, escenario, *, desde, minutos=60, equipo=None, titulo="Visita"):
    return client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": titulo,
        "fecha_programada": f(desde), "duracion_minutos": minutos,
        "equipo_trabajo_id": (equipo or escenario["norte"])["id"],
    })


# ── Agendar ────────────────────────────────────────────────────────────────

def test_un_ticket_se_agenda_con_equipo_y_duracion(client, escenario):
    r = _agendar(client, escenario, desde=MARTES)
    assert r.status_code == 201, r.text
    t = r.json()
    assert t["fecha_programada"].startswith("2026-08-11T09:00")
    assert t["duracion_minutos"] == 60
    assert t["equipo_trabajo_id"] == escenario["norte"]["id"]


def test_agendar_es_opcional(client, escenario):
    """Un ticket que entra por teléfono y se resuelve en el momento no se
    agenda nunca. Las tres columnas son nullable por eso."""
    r = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "Consulta",
    })
    assert r.status_code == 201
    assert r.json()["fecha_programada"] is None
    assert r.json()["equipo_trabajo_id"] is None


# ── La disponibilidad, que es el punto de la fase ──────────────────────────

def test_el_equipo_no_puede_tener_dos_trabajos_pisados(client, escenario):
    """Lo que la fase A no podía contestar. Sin `fecha_programada` esto era
    invisible: los dos tickets simplemente tenían el mismo equipo."""
    _agendar(client, escenario, desde=MARTES, minutos=120, titulo="Primero")

    r = _agendar(client, escenario, desde=MARTES + timedelta(minutes=60),
                 titulo="Se pisa")
    assert r.status_code == 409
    assert "ya tiene el trabajo" in r.json()["detail"]


def test_pegados_no_se_pisan(client, escenario):
    """Los intervalos son semiabiertos: uno que termina 10:00 y otro que
    empieza 10:00 conviven. Sin esto, agendar la mañana completa en bloques
    seguidos sería imposible."""
    _agendar(client, escenario, desde=MARTES, minutos=60, titulo="9 a 10")
    r = _agendar(client, escenario, desde=MARTES + timedelta(hours=1),
                 minutos=60, titulo="10 a 11")
    assert r.status_code == 201, r.text


def test_otro_equipo_a_la_misma_hora_si_puede(client, escenario):
    """El recurso es el equipo. Dos cuadrillas distintas trabajan a la vez —
    es lo normal."""
    _agendar(client, escenario, desde=MARTES, titulo="Norte")
    r = _agendar(client, escenario, desde=MARTES, equipo=escenario["sur"],
                 titulo="Sur")
    assert r.status_code == 201, r.text


def test_un_ticket_sin_equipo_no_ocupa_a_nadie(client, escenario):
    """Agendado pero sin equipo asignado: no puede chocar con nada, porque no
    hay recurso ocupado."""
    client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "Sin equipo",
        "fecha_programada": f(MARTES), "duracion_minutos": 120,
    })
    r = _agendar(client, escenario, desde=MARTES, titulo="Con equipo")
    assert r.status_code == 201, r.text


def test_mover_la_hora_no_choca_consigo_mismo(client, escenario):
    """Sin excluir el propio ticket de la comparación, editarle la hora daría
    un 409 contra sí mismo — y sería imposible reprogramar nada."""
    t = _agendar(client, escenario, desde=MARTES).json()
    r = client.put(f"/api/incidencias/{t['id']}", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": t["titulo"],
        "fecha_programada": f(MARTES + timedelta(minutes=30)),
        "duracion_minutos": 60,
        "equipo_trabajo_id": escenario["norte"]["id"],
    })
    assert r.status_code == 200, r.text
    assert r.json()["fecha_programada"].startswith("2026-08-11T09:30")


def test_mover_la_hora_encima_de_otro_si_choca(client, escenario):
    _agendar(client, escenario, desde=MARTES, minutos=60, titulo="Ocupado")
    otro = _agendar(client, escenario, desde=MARTES + timedelta(hours=3),
                    titulo="Movible").json()

    r = client.put(f"/api/incidencias/{otro['id']}", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": otro["titulo"],
        "fecha_programada": f(MARTES + timedelta(minutes=30)),
        "duracion_minutos": 60,
        "equipo_trabajo_id": escenario["norte"]["id"],
    })
    assert r.status_code == 409


def test_si_choca_no_queda_nada_escrito(client, escenario):
    """La validación corre antes del commit, así que el rechazo no deja el
    ticket a medio crear."""
    _agendar(client, escenario, desde=MARTES, minutos=120, titulo="Primero")
    antes = len(client.get("/api/incidencias").json())

    _agendar(client, escenario, desde=MARTES + timedelta(minutes=60), titulo="Se pisa")

    assert len(client.get("/api/incidencias").json()) == antes


def test_un_trabajo_cerrado_sigue_ocupando_su_horario(client, escenario):
    """Cerrar el ticket **no** libera la agenda, y está bien: el equipo estuvo
    ahí. `find_conflicts()` solo perdona `cancelled`/`no_show`.

    Este test existe porque el código llegó a mapear cerrado→`COMPLETED` con un
    comentario que decía que liberaba el horario — y el motor igual lo contaba
    como choque. La creencia estaba escrita, el comportamiento era el otro."""
    t = _agendar(client, escenario, desde=MARTES, minutos=120, titulo="Hecho").json()
    cerrar = client.put(f"/api/incidencias/{t['id']}", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": t["titulo"],
        "fecha_programada": t["fecha_programada"], "duracion_minutos": 120,
        "equipo_trabajo_id": escenario["norte"]["id"], "estado": "cerrado",
    })
    assert cerrar.json()["estado"] == "cerrado"

    r = _agendar(client, escenario, desde=MARTES + timedelta(minutes=60),
                 titulo="Encima del cerrado")
    assert r.status_code == 409


def test_desagendar_es_lo_que_libera_el_horario(client, escenario):
    """La salida real cuando el trabajo terminó antes: sacarle la fecha, no
    cambiarle el estado."""
    t = _agendar(client, escenario, desde=MARTES, minutos=120, titulo="Terminó antes").json()
    client.put(f"/api/incidencias/{t['id']}", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": t["titulo"],
        "fecha_programada": None, "equipo_trabajo_id": escenario["norte"]["id"],
    })

    r = _agendar(client, escenario, desde=MARTES + timedelta(minutes=60),
                 titulo="Ocupa el hueco")
    assert r.status_code == 201, r.text


# ── La vista de agenda ─────────────────────────────────────────────────────

def test_la_agenda_del_equipo_dice_en_que_vehiculo_sale(client, escenario):
    """Cierra el pedido entero: qué hace el equipo, cuándo, y en qué sale — lo
    último derivado de la asignación de la fase A, no guardado en el ticket."""
    _agendar(client, escenario, desde=MARTES, titulo="Primera visita")
    _agendar(client, escenario, desde=MARTES + timedelta(hours=2), titulo="Segunda")

    r = client.get(f"/api/agenda/equipo/{escenario['norte']['id']}?desde=2026-08-11")
    assert r.status_code == 200, r.text
    dia = r.json()
    assert [x["titulo"] for x in dia] == ["Primera visita", "Segunda"]
    assert dia[0]["vehiculos"] == ["AB123CD"]
    assert dia[0]["cliente_nombre"] == "Estudio Sur"
    assert dia[0]["hasta"].startswith("2026-08-11T10:00")


def test_la_agenda_acota_al_rango(client, escenario):
    _agendar(client, escenario, desde=MARTES, titulo="Del martes")
    _agendar(client, escenario, desde=MARTES + timedelta(days=3), titulo="Del viernes")

    un_dia = client.get(f"/api/agenda/equipo/{escenario['norte']['id']}?desde=2026-08-11").json()
    assert [x["titulo"] for x in un_dia] == ["Del martes"]

    semana = client.get(
        f"/api/agenda/equipo/{escenario['norte']['id']}?desde=2026-08-11&dias=7"
    ).json()
    assert [x["titulo"] for x in semana] == ["Del martes", "Del viernes"]


def test_la_agenda_de_un_equipo_sin_nada(client, escenario):
    r = client.get(f"/api/agenda/equipo/{escenario['sur']['id']}?desde=2026-08-11")
    assert r.status_code == 200
    assert r.json() == []


def test_la_agenda_valida_sus_parametros(client, escenario):
    assert client.get("/api/agenda/equipo/999?desde=2026-08-11").status_code == 404
    assert client.get(
        f"/api/agenda/equipo/{escenario['norte']['id']}?desde=ayer"
    ).status_code == 422
    assert client.get(
        f"/api/agenda/equipo/{escenario['norte']['id']}?desde=2026-08-11&dias=99"
    ).status_code == 422


def test_borrar_el_equipo_desagenda_sin_borrar_los_tickets(client, escenario):
    """El `ondelete` no corre (el pragma de FK está apagado), así que hay que
    mirarlo: el ticket tiene que sobrevivir al equipo."""
    t = _agendar(client, escenario, desde=MARTES).json()
    client.delete(f"/api/equipos-trabajo/{escenario['norte']['id']}")

    despues = client.get(f"/api/incidencias/{t['id']}")
    assert despues.status_code == 200
    assert despues.json()["titulo"] == "Visita"
