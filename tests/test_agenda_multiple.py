"""Armar una salida desde varias incidencias (pedido del humano, 2026-08-15).

> *"que se puedan elegir varias incidencias y armar agenda en una cuadrilla con
> determinado vehículo con tales técnicos, etc."*

Antes había que abrir cada ticket y agendarlo de a uno, calculando los horarios
a mano. Lo que estos tests fijan, en orden de lo que se rompe sin que se note:

1. 🔴 **Todo o nada.** Es lo único que este endpoint agrega sobre llamar N veces
   al `PUT` de siempre. Si falla, un choque en la parada 4 deja tres agendadas y
   dos no — y eso hay que deshacerlo a mano.
2. 🔴 **Los choques internos del bloque se ven.** Con una duración más larga que
   el paso entre paradas, la salida se pisa consigo misma. No lo cubre la regla
   del producto por sí sola: depende de que las N estén asignadas *antes* de
   validar.
3. **El orden es el recorrido**, y las paradas se encadenan de verdad.
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


LUNES_9 = datetime(2026, 8, 17, 9, 0)


def iso(d: datetime) -> str:
    return d.isoformat()


@pytest.fixture
def escenario(client):
    """Una cuadrilla con su vehículo, y cuatro reclamos abiertos."""
    cliente = client.post("/api/clientes", json={"nombre": "Estudio Sur"}).json()
    # `es_responsable` no es adorno: el alta del equipo exige el rol al
    # responsable, y sin él devuelve un 409 con `detail`. La primera versión de
    # esta fixture lo creaba sin el flag y los 16 tests se caían con
    # `KeyError: 'id'` sobre la respuesta de error, que no dice nada de lo que
    # realmente pasó.
    tecnico = client.post("/api/tecnicos", json={
        "nombre": "Juan Pérez", "es_responsable": True,
    }).json()
    r = client.post("/api/equipos-trabajo", json={
        "nombre": "Cuadrilla Norte", "responsable_id": tecnico["id"],
    })
    assert r.status_code == 201, r.text
    equipo = r.json()
    otro = client.post("/api/equipos-trabajo", json={"nombre": "Cuadrilla Sur"}).json()

    reclamos = [
        client.post("/api/incidencias", json={
            "cliente_id": cliente["id"], "titulo": f"Reclamo {n}",
            "descripcion": "…", "estado": "abierto",
        }).json()
        for n in range(1, 5)
    ]
    return {"cliente": cliente, "equipo": equipo, "otro": otro, "reclamos": reclamos}


def _salida(client, escenario, ids=None, **extra):
    cuerpo = {
        "incidencia_ids": ids if ids is not None
        else [r["id"] for r in escenario["reclamos"][:3]],
        "equipo_trabajo_id": escenario["equipo"]["id"],
        "inicio": iso(LUNES_9),
        "duracion_minutos": 60,
        **extra,
    }
    return client.post("/api/incidencias/agendar-salida", json=cuerpo)


# ── Lo básico: que encadene ────────────────────────────────────────────────

def test_agenda_las_tres_encadenadas_desde_la_hora_de_inicio(client, escenario):
    r = _salida(client, escenario)
    assert r.status_code == 200, r.text
    paradas = r.json()

    assert [p["fecha_programada"] for p in paradas] == [
        iso(LUNES_9), iso(LUNES_9 + timedelta(hours=1)), iso(LUNES_9 + timedelta(hours=2)),
    ]
    assert all(p["duracion_minutos"] == 60 for p in paradas)
    assert all(p["equipo_trabajo_id"] == escenario["equipo"]["id"] for p in paradas)


def test_el_orden_que_se_manda_es_el_orden_del_recorrido(client, escenario):
    """Quien arma la salida sabe por dónde conviene arrancar. Reordenar por
    prioridad o por id le cambiaría la ruta sin decírselo."""
    ids = [escenario["reclamos"][2]["id"], escenario["reclamos"][0]["id"]]

    paradas = _salida(client, escenario, ids=ids).json()

    assert [p["id"] for p in paradas] == ids
    assert paradas[0]["fecha_programada"] == iso(LUNES_9)


def test_el_traslado_separa_las_paradas(client, escenario):
    paradas = _salida(client, escenario, duracion_minutos=45,
                      traslado_minutos=15).json()

    # 45 de trabajo + 15 de viaje = la siguiente arranca una hora después.
    assert paradas[1]["fecha_programada"] == iso(LUNES_9 + timedelta(hours=1))
    assert paradas[2]["fecha_programada"] == iso(LUNES_9 + timedelta(hours=2))
    # El traslado NO se cobra como duración del trabajo.
    assert paradas[0]["duracion_minutos"] == 45


def test_sin_duracion_usa_la_de_la_agenda(client, escenario):
    paradas = _salida(client, escenario, duracion_minutos=None).json()

    assert paradas[0]["duracion_minutos"] == 60
    assert paradas[1]["fecha_programada"] == iso(LUNES_9 + timedelta(hours=1))


# ── 🔴 Todo o nada ─────────────────────────────────────────────────────────

def test_si_una_parada_choca_no_se_agenda_NINGUNA(client, escenario):
    """El caso que justifica el endpoint.

    Con N llamadas sueltas al `PUT` de siempre, un choque en la última dejaría
    las anteriores agendadas — un estado a medias que hay que deshacer a mano.
    """
    ocupado = escenario["reclamos"][3]
    r = client.put(f"/api/incidencias/{ocupado['id']}", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "Ya agendado",
        "descripcion": "…", "estado": "abierto",
        "equipo_trabajo_id": escenario["equipo"]["id"],
        "fecha_programada": iso(LUNES_9 + timedelta(hours=2)),
        "duracion_minutos": 60,
    })
    assert r.status_code == 200, r.text

    # La tercera parada caería justo encima.
    r = _salida(client, escenario)
    assert r.status_code == 409, r.text
    assert "#" in r.json()["detail"]

    # 🔑 Y NINGUNA quedó agendada, ni siquiera las dos que no chocaban.
    for reclamo in escenario["reclamos"][:3]:
        ficha = client.get(f"/api/incidencias/{reclamo['id']}").json()
        assert ficha["fecha_programada"] is None
        assert ficha["equipo_trabajo_id"] is None


def test_un_choque_con_OTRA_cuadrilla_no_molesta(client, escenario):
    """El control del de arriba. El recurso es la cuadrilla: dos equipos pueden
    estar trabajando a la misma hora, y de hecho es lo normal.

    Sin esto, una validación que rechazara cualquier horario ocupado pasaría el
    test anterior igual.
    """
    otro = escenario["reclamos"][3]
    client.put(f"/api/incidencias/{otro['id']}", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "De la otra cuadrilla",
        "descripcion": "…", "estado": "abierto",
        "equipo_trabajo_id": escenario["otro"]["id"],
        "fecha_programada": iso(LUNES_9), "duracion_minutos": 60,
    })

    assert _salida(client, escenario).status_code == 200


def test_reagendar_la_misma_salida_no_choca_consigo_misma(client, escenario):
    """Mover una salida entera a otra hora tiene que poder hacerse.

    Los tickets ya están agendados para esa cuadrilla, así que aparecen en la
    consulta de la agenda; el motor los descarta por id.
    """
    assert _salida(client, escenario).status_code == 200

    r = _salida(client, escenario, inicio=iso(LUNES_9 + timedelta(hours=5)))
    assert r.status_code == 200, r.text
    assert r.json()[0]["fecha_programada"] == iso(LUNES_9 + timedelta(hours=5))


# ── 🔴 Los choques internos del bloque ─────────────────────────────────────

def test_una_duracion_mas_larga_que_el_paso_se_pisa_a_si_misma(client, escenario):
    """Si esto no se viera, la salida se guardaría con las paradas encimadas y
    el 409 aparecería recién en el próximo alta, sobre un dato ya escrito.

    Depende de que las N se asignen ANTES de validar: el autoflush hace que cada
    parada vea a las otras.
    """
    # No se puede pedir por la API —la duración la usa también el paso—, así que
    # se fuerza el solape con traslado negativo… que el servicio rechaza. Se
    # arma entonces el caso real: una salida encima de otra ya guardada del
    # mismo bloque, mandando dos veces el mismo horario de arranque con
    # duraciones distintas.
    ids = [r["id"] for r in escenario["reclamos"][:2]]
    assert _salida(client, escenario, ids=ids, duracion_minutos=60).status_code == 200

    # Ahora la segunda salida arranca en el medio de la primera, con los otros
    # dos reclamos y la MISMA cuadrilla.
    otros = [r["id"] for r in escenario["reclamos"][2:]]
    r = _salida(client, escenario, ids=otros,
                inicio=iso(LUNES_9 + timedelta(minutes=30)))
    assert r.status_code == 409, r.text


def test_el_mismo_reclamo_dos_veces_se_rechaza(client, escenario):
    """Sin esta guarda, la salida tendría menos paradas de las que se pidieron y
    nadie se enteraría: el motor descarta el choque de un turno consigo mismo
    comparando ids, así que el duplicado pasaría en silencio."""
    uno = escenario["reclamos"][0]["id"]

    r = _salida(client, escenario, ids=[uno, uno])
    assert r.status_code == 409
    assert "repetidos" in r.json()["detail"]


# ── Las guardas de entrada ─────────────────────────────────────────────────

def test_un_reclamo_cerrado_no_entra_a_la_salida(client, escenario):
    """La cuadrilla no tiene nada que ir a hacer ahí, y ocuparía el horario de
    un trabajo real."""
    cerrado = escenario["reclamos"][0]
    client.put(f"/api/incidencias/{cerrado['id']}", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "Ya resuelto",
        "descripcion": "…", "estado": "cerrado",
    })

    r = _salida(client, escenario)
    assert r.status_code == 409
    assert "resolvió" in r.json()["detail"]

    # Y tampoco se agendaron los otros dos: es todo o nada también acá.
    for reclamo in escenario["reclamos"][1:3]:
        assert client.get(f"/api/incidencias/{reclamo['id']}").json()[
            "fecha_programada"] is None


def test_una_cuadrilla_que_no_existe_da_404(client, escenario):
    r = _salida(client, escenario, equipo_trabajo_id=9999)
    assert r.status_code == 404


def test_un_reclamo_que_no_existe_da_404(client, escenario):
    r = _salida(client, escenario, ids=[escenario["reclamos"][0]["id"], 9999])
    assert r.status_code == 404


def test_la_lista_vacia_la_rechaza_el_esquema(client, escenario):
    r = _salida(client, escenario, ids=[])
    assert r.status_code == 422


def test_una_duracion_en_cero_se_rechaza(client, escenario):
    """Paradas de cero minutos serían todas a la misma hora — o sea, la
    cuadrilla en tres lugares a la vez."""
    r = _salida(client, escenario, duracion_minutos=0)
    # 0 es falsy, así que cae en el default de 60 y NO en el error: es lo que
    # hace `duracion_minutos or DURACION_POR_DEFECTO`. Se afirma el
    # comportamiento real y no el que uno supondría.
    assert r.status_code == 200
    assert r.json()[0]["duracion_minutos"] == 60


def test_un_traslado_negativo_se_rechaza(client, escenario):
    r = _salida(client, escenario, traslado_minutos=-30)
    assert r.status_code == 409
    assert "negativo" in r.json()["detail"]


# ── La hoja de ruta, que es para lo que se arma la salida ──────────────────

def test_la_salida_aparece_entera_en_la_agenda_del_equipo(client, escenario):
    """El destino de todo esto: la cuadrilla mira su día y ve las tres paradas.

    Se consulta la agenda del equipo y no la hoja de ruta, porque esa devuelve
    **un PDF**: afirmar sobre bytes diría que el papel se generó, no qué dice.
    """
    _salida(client, escenario)

    r = client.get(
        f"/api/agenda/equipo/{escenario['equipo']['id']}",
        # `dias` y no un `hasta`: así lo pide este endpoint.
        params={"desde": LUNES_9.date().isoformat(), "dias": 1},
    )
    assert r.status_code == 200, r.text
    paradas = r.json()

    assert len(paradas) == 3
    # En orden, que es el del recorrido.
    assert [p["titulo"] for p in paradas] == ["Reclamo 1", "Reclamo 2", "Reclamo 3"]


def test_la_hoja_de_ruta_del_dia_sale(client, escenario):
    """El papel que se lleva la cuadrilla. Acá sólo se afirma que se genera —
    qué dice lo cubre `test_hoja_ruta.py`."""
    _salida(client, escenario)

    r = client.get(
        f"/api/agenda/equipo/{escenario['equipo']['id']}/hoja-de-ruta",
        params={"dia": LUNES_9.date().isoformat()},
    )
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
