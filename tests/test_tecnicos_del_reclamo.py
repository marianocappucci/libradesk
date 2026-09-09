"""Los técnicos del RECLAMO, con sus horas (revisión `0040`).

**El circuito que esto modela**, contado por el humano el 2026-09-09:

> *"El técnico va, hace el reclamo y anota en el CDS desde qué hora hasta qué
> hora estuvo. Esas horas por técnico después se cargan en esa incidencia al
> otro día, cuando ya está cerrado el reclamo."*

Es la brecha 5 subida un nivel: de la tarea al reclamo. `incidencias_tareas_
tecnicos` sigue viva para las instancias que usan la grilla de tareas — acá se
prueba la otra vía, la del modo simple.

## El test que hay que mirar primero

`test_reasignar_no_borra_las_horas_de_los_que_quedan`. Un multi-select manda la
lista entera cada vez que se toca; si el repositorio rehiciera las filas, las
horas ya cargadas de los técnicos que siguen tildados se perderían **en
silencio** — la pantalla se vería igual y los tramos volverían a `None` al
recargar.
"""
import os

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


@pytest.fixture
def escenario(client):
    cliente = client.post("/api/clientes", json={"nombre": "Metalmax"}).json()
    ana = client.post("/api/tecnicos", json={
        "nombre": "Ana Gómez", "es_tecnico": True,
    }).json()
    beto = client.post("/api/tecnicos", json={
        "nombre": "Beto Ruiz", "es_tecnico": True,
    }).json()
    r = client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "titulo": "Central sin tono",
    })
    assert r.status_code == 201, r.text
    return {"cliente": cliente, "ana": ana, "beto": beto, "incidencia": r.json()}


def poner(client, incidencia_id, ids):
    return client.put(f"/api/incidencias/{incidencia_id}/tecnicos",
                      json={"tecnico_ids": ids})


# ── Asignar ────────────────────────────────────────────────────────────────

def test_van_varios_tecnicos_al_mismo_reclamo(client, escenario):
    """Lo que hoy no se puede: `incidencias.tecnico_id` es **uno solo**, y
    varios técnicos sólo existía colgando de una tarea."""
    r = poner(client, escenario["incidencia"]["id"],
              [escenario["ana"]["id"], escenario["beto"]["id"]])
    assert r.status_code == 200, r.text

    nombres = [a["tecnico"] for a in r.json()]
    assert nombres == ["Ana Gómez", "Beto Ruiz"]


def test_se_asignan_sin_horas_y_se_cargan_despues(client, escenario):
    """Es el circuito textual: se tilda quién fue, y las horas entran al día
    siguiente desde el CDS."""
    incidencia_id = escenario["incidencia"]["id"]
    asignados = poner(client, incidencia_id, [escenario["ana"]["id"]]).json()
    assert asignados[0]["desde"] is None
    assert asignados[0]["horas"] is None

    r = client.patch(
        f"/api/incidencias/{incidencia_id}/tecnicos/{asignados[0]['id']}",
        json={"desde": "2026-09-08T08:30:00", "hasta": "2026-09-08T12:00:00"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["horas"] == 3.5


def test_cada_tecnico_puede_tener_horas_distintas(client, escenario):
    """*"Cada uno puede tener una cantidad de minutos diferentes."*"""
    incidencia_id = escenario["incidencia"]["id"]
    asignados = poner(client, incidencia_id,
                      [escenario["ana"]["id"], escenario["beto"]["id"]]).json()

    client.patch(f"/api/incidencias/{incidencia_id}/tecnicos/{asignados[0]['id']}",
                 json={"desde": "2026-09-08T08:00:00", "hasta": "2026-09-08T12:00:00"})
    client.patch(f"/api/incidencias/{incidencia_id}/tecnicos/{asignados[1]['id']}",
                 json={"desde": "2026-09-08T09:00:00", "hasta": "2026-09-08T10:30:00"})

    horas = {a["tecnico"]: a["horas"]
             for a in client.get(f"/api/incidencias/{incidencia_id}/tecnicos").json()}
    assert horas == {"Ana Gómez": 4.0, "Beto Ruiz": 1.5}


def test_un_tecnico_sin_horas_es_None_y_no_cero(client, escenario):
    """🔴 Un técnico tildado al que nadie le cargó las horas **no trabajó cero
    horas**: no se sabe cuántas. Un cero borraría la diferencia justo donde
    importa, que es el total que se va a cobrar."""
    incidencia_id = escenario["incidencia"]["id"]
    asignados = poner(client, incidencia_id,
                      [escenario["ana"]["id"], escenario["beto"]["id"]]).json()
    client.patch(f"/api/incidencias/{incidencia_id}/tecnicos/{asignados[0]['id']}",
                 json={"desde": "2026-09-08T08:00:00", "hasta": "2026-09-08T12:00:00"})

    horas = [a["horas"]
             for a in client.get(f"/api/incidencias/{incidencia_id}/tecnicos").json()]
    assert 0.0 not in horas
    assert None in horas


# ── Reasignar, que es donde se pierde todo ─────────────────────────────────

def test_reasignar_no_borra_las_horas_de_los_que_quedan(client, escenario):
    """🔴 **El test central.**

    El multi-select manda la lista entera cada vez. Si `set_tecnicos` rehiciera
    las filas, las horas de Ana —que sigue tildada— volverían a `None`, y nadie
    lo notaría hasta mirar el total antes de facturar.
    """
    incidencia_id = escenario["incidencia"]["id"]
    asignados = poner(client, incidencia_id, [escenario["ana"]["id"]]).json()
    client.patch(f"/api/incidencias/{incidencia_id}/tecnicos/{asignados[0]['id']}",
                 json={"desde": "2026-09-08T08:00:00", "hasta": "2026-09-08T12:00:00"})

    # Se agrega a Beto sin tocar a Ana: es un tilde más en la misma lista.
    r = poner(client, incidencia_id,
              [escenario["ana"]["id"], escenario["beto"]["id"]])
    assert r.status_code == 200, r.text

    ana = next(a for a in r.json() if a["tecnico"] == "Ana Gómez")
    assert ana["horas"] == 4.0, "se perdieron las horas de quien seguía asignado"


def test_destildar_saca_al_tecnico(client, escenario):
    incidencia_id = escenario["incidencia"]["id"]
    poner(client, incidencia_id, [escenario["ana"]["id"], escenario["beto"]["id"]])

    r = poner(client, incidencia_id, [escenario["beto"]["id"]])
    assert [a["tecnico"] for a in r.json()] == ["Beto Ruiz"]


def test_la_lista_vacia_los_saca_a_todos(client, escenario):
    incidencia_id = escenario["incidencia"]["id"]
    poner(client, incidencia_id, [escenario["ana"]["id"]])

    assert poner(client, incidencia_id, []).json() == []


def test_mandar_dos_veces_el_mismo_no_lo_duplica(client, escenario):
    """El `UNIQUE` lo impediría igual, pero con un 500. Se deduplica antes."""
    incidencia_id = escenario["incidencia"]["id"]
    r = poner(client, incidencia_id,
              [escenario["ana"]["id"], escenario["ana"]["id"]])
    assert r.status_code == 200, r.text
    assert len(r.json()) == 1


# ── Lo que tiene que fallar ────────────────────────────────────────────────

def test_un_tecnico_que_no_existe_es_422(client, escenario):
    r = poner(client, escenario["incidencia"]["id"], [99999])
    assert r.status_code == 422, r.text
    assert "99999" in r.text


def test_un_reclamo_que_no_existe_es_404(client, escenario):
    assert poner(client, 99999, [escenario["ana"]["id"]]).status_code == 404


def test_un_tramo_al_reves_es_422(client, escenario):
    incidencia_id = escenario["incidencia"]["id"]
    asignados = poner(client, incidencia_id, [escenario["ana"]["id"]]).json()

    r = client.patch(
        f"/api/incidencias/{incidencia_id}/tecnicos/{asignados[0]['id']}",
        json={"desde": "2026-09-08T12:00:00", "hasta": "2026-09-08T08:00:00"},
    )
    assert r.status_code == 422, r.text


# ── Lo que NO se toca ──────────────────────────────────────────────────────

def test_la_via_por_tarea_sigue_viva(client, escenario):
    """Las dos formas de trabajar conviven: esta tabla no reemplaza a
    `incidencias_tareas_tecnicos`, la acompaña."""
    incidencia_id = escenario["incidencia"]["id"]
    tarea = client.post(f"/api/incidencias/{incidencia_id}/tareas",
                        json={"detalle": "Diagnóstico"})
    assert tarea.status_code == 201, tarea.text

    r = client.post(
        f"/api/incidencias/{incidencia_id}/tareas/{tarea.json()['id']}/tecnicos",
        json={"tecnico_id": escenario["ana"]["id"]},
    )
    assert r.status_code == 201, r.text

    # Y las dos vías no se pisan: asignar por tarea no asigna en el reclamo.
    assert client.get(f"/api/incidencias/{incidencia_id}/tecnicos").json() == []
