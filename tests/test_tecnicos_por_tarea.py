"""Técnicos por tarea, con su ventana de trabajo — brechas 3 y 5 de Lagrace.

LibraDesk tenía **un** `tecnico_id` en la incidencia. Integridad lista 14
técnicos con checkbox y, al tildar uno, le carga `Fecha Inicio · Hora Inicio ·
Fecha Fin · Hora Fin · Total`: varios ejecutantes por tarea, cada uno con su
tramo.

Lo que este archivo defiende, en orden de lo que duele si se rompe:

1. 🔴 **Que varios técnicos trabajen la misma tarea, cada uno con su tramo.** Es
   la brecha entera.
2. 🔴 **Que un tramo sin cargar sea `None` y no `0`.** Un técnico asignado al
   que todavía no se le pusieron las horas no trabajó cero horas: **no se sabe
   cuántas**. Es la diferencia entre un total cerrado y uno que parece cerrado —
   justo el número que alguien mira antes de facturar.
3. 🔴 **Que el importe se derive y no se guarde.** No hay columna de plata:
   horas × valor hora resuelto por la lista del cliente. Guardarlo sería una
   segunda fuente de verdad al lado de `incidencias_cargos`, que es el error que
   este producto ya pagó con la tabla `servicios`.
4. **Que el mismo técnico no entre dos veces en la misma tarea**, y que eso sea
   un 409 y no un 422: el pedido está bien formado, lo que pasa es que ya existe.
"""
import os
from datetime import datetime

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
def escenario(client) -> dict:
    cliente = client.post("/api/clientes", json={"nombre": "Neumyser S.A."}).json()
    inc = client.post("/api/incidencias", json={
        "titulo": "Problemas con las líneas", "cliente_id": cliente["id"],
        "prioridad": "media",
    }).json()
    tarea = client.post(f"/api/incidencias/{inc['id']}/tareas", json={
        "detalle": "Diagnóstico en el lugar",
    }).json()
    oteiza = client.post("/api/tecnicos", json={"nombre": "Oteiza"}).json()
    cantone = client.post("/api/tecnicos", json={"nombre": "Cantone"}).json()
    return {"inc": inc["id"], "tarea": tarea["id"],
            "oteiza": oteiza["id"], "cantone": cantone["id"]}


def _tareas(client, inc):
    return client.get(f"/api/incidencias/{inc}/tareas").json()


def _asignar(client, e, tecnico, desde=None, hasta=None):
    payload = {"tecnico_id": tecnico}
    if desde:
        payload["desde"] = desde
    if hasta:
        payload["hasta"] = hasta
    return client.post(
        f"/api/incidencias/{e['inc']}/tareas/{e['tarea']}/tecnicos", json=payload,
    )


# ── 1. Varios técnicos, cada uno con su tramo ─────────────────────────────

def test_varios_tecnicos_en_la_misma_tarea_cada_uno_con_lo_suyo(client, escenario):
    e = escenario
    assert _asignar(client, e, e["oteiza"],
                    "2026-08-19T08:00:00", "2026-08-19T11:30:00").status_code == 201
    assert _asignar(client, e, e["cantone"],
                    "2026-08-19T09:00:00", "2026-08-19T10:00:00").status_code == 201

    tarea = _tareas(client, e["inc"])[0]
    assert [t["tecnico"] for t in tarea["tecnicos"]] == ["Oteiza", "Cantone"]
    # 🔴 Cada uno con SUS horas, no las del reclamo.
    assert [t["horas"] for t in tarea["tecnicos"]] == [3.5, 1.0]
    assert tarea["horas_total"] == 4.5


def test_las_asignaciones_viajan_dentro_de_la_tarea(client, escenario):
    """No hay endpoint de listado: la grilla las muestra en la misma fila, y
    pedirlas aparte sería un request por tarea."""
    _asignar(client, escenario, escenario["oteiza"])
    tarea = _tareas(client, escenario["inc"])[0]
    assert "tecnicos" in tarea and len(tarea["tecnicos"]) == 1


def test_el_minuto_cuenta(client, escenario):
    """Integridad muestra dos decimales y se vio `0.08 h`. 5 minutos son 0.08."""
    _asignar(client, escenario, escenario["oteiza"],
             "2026-08-19T08:00:00", "2026-08-19T08:05:00")
    assert _tareas(client, escenario["inc"])[0]["tecnicos"][0]["horas"] == 0.08


# ── 2. Sin tramo cargado es None, no cero ─────────────────────────────────

def test_un_tecnico_asignado_sin_horas_da_None_y_no_cero(client, escenario):
    """🔴 No trabajó cero horas: no se sabe cuántas. Un cero acá daría un total
    que parece cerrado y no lo está."""
    assert _asignar(client, escenario, escenario["oteiza"]).status_code == 201

    tarea = _tareas(client, escenario["inc"])[0]
    assert tarea["tecnicos"][0]["horas"] is None
    assert tarea["tecnicos"][0]["importe"] is None
    # Y el total tampoco es cero: no hay ningún tramo completo.
    assert tarea["horas_total"] is None


def test_el_total_suma_solo_los_tramos_completos(client, escenario):
    e = escenario
    _asignar(client, e, e["oteiza"], "2026-08-19T08:00:00", "2026-08-19T10:00:00")
    _asignar(client, e, e["cantone"])  # tildado, sin horas

    tarea = _tareas(client, e["inc"])[0]
    assert tarea["horas_total"] == 2.0
    assert [t["horas"] for t in tarea["tecnicos"]] == [2.0, None]


def test_cargar_el_tramo_despues_de_tildar(client, escenario):
    """Es como funciona la pantalla: se tilda primero y se cargan las horas
    después."""
    e = escenario
    a = _asignar(client, e, e["oteiza"]).json()
    assert a["horas"] is None

    r = client.patch(
        f"/api/incidencias/{e['inc']}/tareas/{e['tarea']}/tecnicos/{a['id']}",
        json={"desde": "2026-08-19T08:00:00", "hasta": "2026-08-19T09:15:00"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["horas"] == 1.25


def test_vaciar_un_tramo_cargado_mal(client, escenario):
    """`exclude_unset`: mandar `null` borra el dato, no mandarlo lo deja."""
    e = escenario
    a = _asignar(client, e, e["oteiza"],
                 "2026-08-19T08:00:00", "2026-08-19T09:00:00").json()
    assert a["horas"] == 1.0

    r = client.patch(
        f"/api/incidencias/{e['inc']}/tareas/{e['tarea']}/tecnicos/{a['id']}",
        json={"hasta": None},
    )
    assert r.status_code == 200, r.text
    assert r.json()["hasta"] is None
    assert r.json()["horas"] is None
    # Y el inicio, que no se mandó, sigue puesto.
    assert r.json()["desde"] is not None


# ── 3. El importe se deriva del valor hora ────────────────────────────────

def test_el_importe_sale_del_valor_hora_del_catalogo(client, escenario):
    e = escenario
    servicio = client.post("/api/servicios", json={
        "nombre": "Hora normal", "precio": 21100, "iva_rate": 0.21,
        "es_valor_hora": True,
    })
    assert servicio.status_code in (200, 201), servicio.text

    _asignar(client, e, e["oteiza"], "2026-08-19T08:00:00", "2026-08-19T08:05:00")
    fila = _tareas(client, e["inc"])[0]["tecnicos"][0]
    assert fila["horas"] == 0.08
    # El caso que se vio en Integridad: 0.08 h → $1.688.
    assert fila["importe"] == pytest.approx(1688.0)


def test_sin_valor_hora_cargado_el_importe_es_None_y_no_cero(client, escenario):
    """`None` es "la instancia no cargó su valor hora", que no es cobrar cero.
    `convertir_a_remito` ya deja la mano de obra sin precio en ese caso, y la
    bandeja se niega a mandar un comprobante en cero: inventar un número acá
    rompería las dos defensas."""
    _asignar(client, escenario, escenario["oteiza"],
             "2026-08-19T08:00:00", "2026-08-19T10:00:00")
    fila = _tareas(client, escenario["inc"])[0]["tecnicos"][0]
    assert fila["horas"] == 2.0
    assert fila["importe"] is None


# ── 4. Validaciones ───────────────────────────────────────────────────────

def test_el_mismo_tecnico_dos_veces_es_409(client, escenario):
    e = escenario
    assert _asignar(client, e, e["oteiza"]).status_code == 201
    r = _asignar(client, e, e["oteiza"])
    # 409 y no 422: el pedido está bien formado, lo que pasa es que ya existe.
    assert r.status_code == 409, r.text
    assert "ya está asignado" in r.json()["detail"]


def test_el_fin_no_puede_ser_anterior_al_inicio(client, escenario):
    r = _asignar(client, escenario, escenario["oteiza"],
                 "2026-08-19T10:00:00", "2026-08-19T08:00:00")
    assert r.status_code == 422, r.text
    assert "anterior" in r.json()["detail"]


def test_editar_tampoco_deja_invertir_el_tramo(client, escenario):
    e = escenario
    a = _asignar(client, e, e["oteiza"], "2026-08-19T10:00:00").json()
    r = client.patch(
        f"/api/incidencias/{e['inc']}/tareas/{e['tarea']}/tecnicos/{a['id']}",
        json={"hasta": "2026-08-19T08:00:00"},
    )
    assert r.status_code == 422, r.text


def test_tecnico_y_tarea_inexistentes(client, escenario):
    e = escenario
    assert _asignar(client, e, 99999).status_code == 422
    r = client.post(
        f"/api/incidencias/{e['inc']}/tareas/99999/tecnicos",
        json={"tecnico_id": e["oteiza"]},
    )
    assert r.status_code == 404, r.text


def test_desasignar(client, escenario):
    e = escenario
    a = _asignar(client, e, e["oteiza"]).json()
    r = client.delete(
        f"/api/incidencias/{e['inc']}/tareas/{e['tarea']}/tecnicos/{a['id']}")
    assert r.status_code == 204, r.text
    assert _tareas(client, e["inc"])[0]["tecnicos"] == []


def test_borrar_la_tarea_se_lleva_sus_asignaciones(client, escenario):
    """`ondelete=CASCADE`, y contra PostgreSQL se aplica de verdad."""
    e = escenario
    _asignar(client, e, e["oteiza"], "2026-08-19T08:00:00", "2026-08-19T09:00:00")
    assert client.delete(
        f"/api/incidencias/{e['inc']}/tareas/{e['tarea']}").status_code == 204
    assert _tareas(client, e["inc"]) == []


def test_el_reclamo_conserva_su_tecnico_y_sus_horas(client, escenario):
    """Expand/contract: `incidencias.tecnico_id` y `horas_invertidas` siguen
    siendo la fuente del remito. Esta fase agrega, no reemplaza."""
    e = escenario
    _asignar(client, e, e["oteiza"], "2026-08-19T08:00:00", "2026-08-19T10:00:00")
    inc = client.get(f"/api/incidencias/{e['inc']}").json()
    assert "horas_invertidas" in inc
    assert "tecnico_id" in inc
