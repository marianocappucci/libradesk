"""Equipos de trabajo y flota (pedido 42, fase A).

Lo que concentra el valor y lo que más tests tiene:

1. **"En qué vehículo sale el equipo"** — la asignación equipo↔vehículo, y que
   un vehículo **no pueda estar en dos equipos**. Esa es la disponibilidad de
   esta fase: el modelo no puede representar el estado malo, porque la
   asignación vive en una sola columna del vehículo.
2. **El responsable sale del catálogo de personal**, con el rol marcado — no de
   una tabla de coordinadores.
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
def gente(client):
    """Un responsable que además es técnico —el caso normal en una empresa
    chica— y dos técnicos que responden a él."""
    jefe = client.post("/api/tecnicos", json={
        "nombre": "Sofía Núñez", "es_tecnico": True, "es_responsable": True,
    }).json()
    t1 = client.post("/api/tecnicos", json={"nombre": "Diego Ramos"}).json()
    t2 = client.post("/api/tecnicos", json={"nombre": "Ana Paz"}).json()
    return {"jefe": jefe, "t1": t1, "t2": t2}


def _equipo(client, gente, **extra):
    r = client.post("/api/equipos-trabajo", json={
        "nombre": "Cuadrilla Norte",
        "responsable_id": gente["jefe"]["id"],
        "integrantes": [gente["t1"]["id"], gente["t2"]["id"]],
        **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _vehiculo(client, patente="AB123CD", **extra):
    r = client.post("/api/equipos-trabajo/vehiculos", json={
        "patente": patente, "marca": "Renault", "modelo": "Kangoo", **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


# ── El equipo y su responsable ─────────────────────────────────────────────

def test_el_equipo_tiene_responsable_e_integrantes(client, gente):
    e = _equipo(client, gente)
    assert e["responsable_nombre"] == "Sofía Núñez"
    assert [i["nombre"] for i in e["integrantes"]] == ["Ana Paz", "Diego Ramos"]


def test_el_responsable_tiene_que_tener_el_rol(client, gente):
    """Sin el chequeo, cualquiera del personal aparecería como opción para
    mandar un equipo y el rol no querría decir nada."""
    r = client.post("/api/equipos-trabajo", json={
        "nombre": "Otra", "responsable_id": gente["t1"]["id"],
    })
    assert r.status_code == 409
    assert "no tiene el rol de responsable" in r.json()["detail"]


def test_un_integrante_puede_ser_cualquiera_del_personal(client, gente):
    """A diferencia del responsable: el rol marca quién manda, no quién va."""
    e = _equipo(client, gente)
    assert len(e["integrantes"]) == 2


def test_una_persona_puede_estar_en_dos_equipos(client, gente):
    """La unicidad es sobre el PAR equipo-persona, no sobre la persona: el
    mismo técnico refuerza dos cuadrillas según el día."""
    _equipo(client, gente)
    otro = client.post("/api/equipos-trabajo", json={
        "nombre": "Cuadrilla Sur", "responsable_id": gente["jefe"]["id"],
        "integrantes": [gente["t1"]["id"]],
    })
    assert otro.status_code == 201
    assert [i["nombre"] for i in otro.json()["integrantes"]] == ["Diego Ramos"]


def test_editar_reemplaza_el_juego_de_integrantes(client, gente):
    """La pantalla manda la lista completa. Un diff parcial dejaría integrantes
    fantasma al sacar dos personas a la vez."""
    e = _equipo(client, gente)
    r = client.put(f"/api/equipos-trabajo/{e['id']}", json={
        "nombre": e["nombre"], "responsable_id": gente["jefe"]["id"],
        "integrantes": [gente["t2"]["id"]],
    })
    assert r.status_code == 200
    assert [i["nombre"] for i in r.json()["integrantes"]] == ["Ana Paz"]


def test_el_rol_responsable_filtra(client, gente):
    responsables = client.get("/api/tecnicos?rol=responsable").json()
    assert [t["nombre"] for t in responsables] == ["Sofía Núñez"]
    # Y sigue siendo técnica: los roles son banderas, no un campo único.
    assert "tecnico" in responsables[0]["roles"]
    assert "responsable" in responsables[0]["roles"]
    # Las banderas también salen en la respuesta, no sólo la lista derivada:
    # la pantalla de personal marca los checkboxes con éstas. Se afirman las
    # cuatro porque el dict se arma iterando `ROLES`, y sin esto una bandera
    # nueva podía quedar fuera de la salida sin que nada se pusiera en rojo.
    assert responsables[0]["es_responsable"] is True
    assert responsables[0]["es_tecnico"] is True
    assert responsables[0]["es_recepcionista"] is False
    assert responsables[0]["es_vendedor"] is False


# ── La flota y la asignación: "en qué vehículo sale" ───────────────────────

def test_asignar_le_da_el_vehiculo_al_equipo(client, gente):
    e = _equipo(client, gente)
    v = _vehiculo(client)
    assert v["estado"] == "disponible"

    r = client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/asignar",
                    json={"equipo_id": e["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["estado"] == "asignado"
    assert r.json()["equipo_nombre"] == "Cuadrilla Norte"

    # Y la ficha del equipo lo muestra: es la respuesta a "en qué sale".
    ficha = client.get(f"/api/equipos-trabajo/{e['id']}").json()
    assert [x["patente"] for x in ficha["vehiculos"]] == ["AB123CD"]


def test_un_vehiculo_no_puede_estar_en_dos_equipos(client, gente):
    """La disponibilidad de esta fase. La asignación vive en una sola columna
    del vehículo, así que el modelo no puede representar el estado malo — pero
    igual hay que rechazar el intento con un mensaje que se entienda."""
    uno = _equipo(client, gente)
    otro = client.post("/api/equipos-trabajo", json={
        "nombre": "Cuadrilla Sur", "responsable_id": gente["jefe"]["id"],
    }).json()
    v = _vehiculo(client)
    client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/asignar",
                json={"equipo_id": uno["id"]})

    r = client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/asignar",
                    json={"equipo_id": otro["id"]})
    assert r.status_code == 409
    assert "ya está asignado a Cuadrilla Norte" in r.json()["detail"]


def test_un_vehiculo_en_taller_no_sale(client, gente):
    e = _equipo(client, gente)
    v = _vehiculo(client)
    client.put(f"/api/equipos-trabajo/vehiculos/{v['id']}", json={"estado": "en_taller"})

    r = client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/asignar",
                    json={"equipo_id": e["id"]})
    assert r.status_code == 409
    assert "en_taller" in r.json()["detail"]


def test_desasignar_lo_devuelve_a_disponible(client, gente):
    e = _equipo(client, gente)
    v = _vehiculo(client)
    client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/asignar",
                json={"equipo_id": e["id"]})

    r = client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/desasignar", json={})
    assert r.status_code == 200
    assert r.json()["estado"] == "disponible"
    assert r.json()["equipo_id"] is None


def test_desasignar_a_taller(client, gente):
    """El que sale del equipo porque se rompió no vuelve al pool de
    disponibles."""
    e = _equipo(client, gente)
    v = _vehiculo(client)
    client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/asignar",
                json={"equipo_id": e["id"]})
    r = client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/desasignar",
                    json={"estado": "en_taller"})
    assert r.json()["estado"] == "en_taller"
    assert client.get("/api/equipos-trabajo/vehiculos?disponibles=true").json() == []


def test_asignado_no_se_setea_a_mano(client, gente):
    """Igual que `colocado` en los activos: si se pudiera por los dos lados, un
    vehículo podría decir que está asignado sin ningún equipo que lo tenga."""
    v = _vehiculo(client)
    r = client.put(f"/api/equipos-trabajo/vehiculos/{v['id']}", json={"estado": "asignado"})
    assert r.status_code == 409
    assert "no se setea a mano" in r.json()["detail"]


def test_no_se_cambia_el_estado_de_uno_asignado(client, gente):
    e = _equipo(client, gente)
    v = _vehiculo(client)
    client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/asignar",
                json={"equipo_id": e["id"]})
    r = client.put(f"/api/equipos-trabajo/vehiculos/{v['id']}", json={"estado": "en_taller"})
    assert r.status_code == 409
    assert "Cuadrilla Norte" in r.json()["detail"]


def test_el_equipo_no_se_cambia_por_el_put(client, gente):
    e = _equipo(client, gente)
    v = _vehiculo(client)
    r = client.put(f"/api/equipos-trabajo/vehiculos/{v['id']}",
                   json={"equipo_id": e["id"]})
    # Pydantic lo descarta por no estar en el modelo de update; lo que importa
    # es que el vehículo no quedó asignado por un camino que no valida nada.
    assert r.status_code == 200
    assert client.get(f"/api/equipos-trabajo/vehiculos/{v['id']}").json()["equipo_id"] is None


def test_borrar_el_equipo_libera_sus_vehiculos(client, gente):
    """Los `ondelete` no corren nunca (el pragma de FK está apagado), así que la
    liberación es explícita. Sin esto el vehículo quedaría `asignado` a un
    equipo que ya no existe — el estado imposible que la asignación evita."""
    e = _equipo(client, gente)
    v = _vehiculo(client)
    client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/asignar",
                json={"equipo_id": e["id"]})

    assert client.delete(f"/api/equipos-trabajo/{e['id']}").status_code == 204

    despues = client.get(f"/api/equipos-trabajo/vehiculos/{v['id']}").json()
    assert despues["equipo_id"] is None
    assert despues["estado"] == "disponible"


def test_no_se_borra_un_vehiculo_asignado(client, gente):
    e = _equipo(client, gente)
    v = _vehiculo(client)
    client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/asignar",
                json={"equipo_id": e["id"]})
    r = client.delete(f"/api/equipos-trabajo/vehiculos/{v['id']}")
    assert r.status_code == 409
    assert "desasignalo" in r.json()["detail"]


# ── La patente identifica al vehículo ──────────────────────────────────────

def test_la_patente_es_unica_y_se_normaliza(client):
    _vehiculo(client, patente="ab123cd")
    assert client.get("/api/equipos-trabajo/vehiculos").json()[0]["patente"] == "AB123CD"
    # Y en minúscula choca igual: se compara normalizada.
    r = client.post("/api/equipos-trabajo/vehiculos", json={"patente": "AB123CD"})
    assert r.status_code == 409
    assert "Ya hay un vehículo" in r.json()["detail"]


def test_disponibles_no_incluye_los_asignados(client, gente):
    e = _equipo(client, gente)
    _vehiculo(client, patente="AA111AA")
    v2 = _vehiculo(client, patente="BB222BB")
    client.post(f"/api/equipos-trabajo/vehiculos/{v2['id']}/asignar",
                json={"equipo_id": e["id"]})

    libres = client.get("/api/equipos-trabajo/vehiculos?disponibles=true").json()
    assert [x["patente"] for x in libres] == ["AA111AA"]


def test_404_de_los_recursos(client, gente):
    assert client.get("/api/equipos-trabajo/999").status_code == 404
    assert client.get("/api/equipos-trabajo/vehiculos/999").status_code == 404
    v = _vehiculo(client)
    r = client.post(f"/api/equipos-trabajo/vehiculos/{v['id']}/asignar",
                    json={"equipo_id": 999})
    assert r.status_code == 404
    assert r.json()["detail"] == "equipo not found"
