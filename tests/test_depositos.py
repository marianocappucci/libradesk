"""Depositos y el movimiento de equipos entre ellos (2026-08-04).

Lo que estos tests fijan, en orden de lo que puede romperse en silencio:

1. **Que un equipo no termine en el deposito de otro cliente.** Es el unico
   error del modulo que no se ve despues: el equipo sigue figurando como del
   cliente correcto y solo la ubicacion miente.
2. **Que mover un equipo deje movimiento en su historial**, con el nombre del
   deposito como origen/destino. Sin eso el traslado ocurre pero la ficha del
   equipo no lo cuenta, que fue exactamente el agujero que tuvo
   `equipos_movimientos` hasta el 2026-07-29.
3. **Que no se pueda borrar un deposito con equipos adentro** — vaciarlo solo
   seria mover los equipos a ninguna parte.
4. Que la unicidad de nombre por dueño se valide en el repositorio: la
   `UniqueConstraint` no sirve porque en SQLite dos NULL son distintos, asi que
   dos depositos propios homonimos entrarian sin chistar.
"""

import pytest


# `client` sale de conftest.py.


@pytest.fixture
def escenario(client):
    """Dos clientes, un equipo de cada uno, un deposito propio y uno del
    primer cliente. El segundo cliente existe para que cualquier filtro que
    falte se note."""
    assert client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    ).status_code == 200

    uno = client.post("/api/clientes", json={
        "nombre": "Compulibra", "email": "c@test.com",
    }).json()["id"]
    dos = client.post("/api/clientes", json={
        "nombre": "Otro", "email": "o@test.com",
    }).json()["id"]

    equipo_uno = client.post("/api/equipos", json={
        "cliente_id": uno, "tipo": "Notebook", "marca": "Lenovo",
        "serial": "S-1", "sector": "Admisión",
    }).json()["id"]
    equipo_dos = client.post("/api/equipos", json={
        "cliente_id": dos, "tipo": "Impresora", "serial": "S-2", "sector": "Ventas",
    }).json()["id"]

    taller = client.post("/api/depositos", json={"nombre": "Taller"}).json()["id"]
    panol = client.post("/api/depositos", json={
        "nombre": "Pañol", "cliente_id": uno,
    }).json()["id"]

    return {
        "cliente_uno": uno, "cliente_dos": dos,
        "equipo_uno": equipo_uno, "equipo_dos": equipo_dos,
        "taller": taller, "panol": panol,
    }


# --- el dueño ---------------------------------------------------------------

def test_el_primer_deposito_propio_queda_como_predeterminado(client):
    client.post("/auth/login", json={"username": "admin", "password": "admin"})

    primero = client.post("/api/depositos", json={"nombre": "Taller"}).json()
    segundo = client.post("/api/depositos", json={"nombre": "Central"}).json()

    assert primero["es_default"] is True
    # Y el segundo no se lo roba solo: hay que marcarlo.
    assert segundo["es_default"] is False


def test_un_deposito_de_cliente_no_puede_ser_el_predeterminado(client, escenario):
    """El default lo consulta el reemplazo cuando un equipo "vuelve a
    deposito", y ahi el equipo puede ser de cualquier cliente."""
    r = client.post(f"/api/depositos/{escenario['panol']}/set-default")

    assert r.status_code == 422
    assert "propio de la empresa" in r.json()["detail"]


def test_el_deposito_de_cliente_no_arranca_como_default(client, escenario):
    panol = client.get(f"/api/depositos/{escenario['panol']}").json()

    assert panol["es_default"] is False
    assert panol["cliente_nombre"] == "Compulibra"


def test_no_se_repite_el_nombre_para_el_mismo_dueno(client, escenario):
    """La `UniqueConstraint` no alcanza: con `cliente_id` en NULL, SQLite
    considera distintas a dos filas homonimas."""
    repetido = client.post("/api/depositos", json={"nombre": "taller"})

    assert repetido.status_code == 409

    # Pero el mismo nombre para OTRO dueño sí se puede: son dos lugares.
    del_cliente = client.post("/api/depositos", json={
        "nombre": "Taller", "cliente_id": escenario["cliente_uno"],
    })
    assert del_cliente.status_code == 201


# --- un equipo no entra a un depósito ajeno ---------------------------------

def test_un_equipo_no_entra_al_deposito_de_otro_cliente(client, escenario):
    r = client.put(f"/api/equipos/{escenario['equipo_dos']}", json={
        "cliente_id": escenario["cliente_dos"], "tipo": "Impresora",
        "deposito_id": escenario["panol"],
    })

    assert r.status_code == 422
    assert "otro cliente" in r.json()["detail"]


def test_un_equipo_entra_al_deposito_propio_de_la_empresa(client, escenario):
    """El propio recibe equipos de cualquier cliente: es el taller."""
    for equipo_id, cliente_id, tipo in (
        (escenario["equipo_uno"], escenario["cliente_uno"], "Notebook"),
        (escenario["equipo_dos"], escenario["cliente_dos"], "Impresora"),
    ):
        r = client.put(f"/api/equipos/{equipo_id}", json={
            "cliente_id": cliente_id, "tipo": tipo,
            "deposito_id": escenario["taller"],
        })
        assert r.status_code == 200, r.text
        assert r.json()["deposito_nombre"] == "Taller"

    contenido = client.get(f"/api/depositos/{escenario['taller']}/equipos").json()
    assert len(contenido) == 2
    # El cliente viene resuelto: en un depósito propio conviven varios parques
    # y sin esa columna la lista no se puede leer.
    assert {e["cliente_nombre"] for e in contenido} == {"Compulibra", "Otro"}


# --- la transferencia -------------------------------------------------------

def test_mover_al_deposito_deja_movimiento_con_el_nombre(client, escenario):
    r = client.post("/api/depositos/transferir", json={
        "equipo_ids": [escenario["equipo_uno"]],
        "destino_id": escenario["taller"],
        "motivo": "Se retira para revisión",
    })

    assert r.status_code == 200
    assert r.json()[0]["deposito_nombre"] == "Taller"

    movimientos = client.get(
        f"/api/equipos/{escenario['equipo_uno']}/movimientos"
    ).json()
    traslado = next(m for m in movimientos if m["tipo"] == "traslado")
    # El historial guarda el NOMBRE, no el id: describe dónde estaba el equipo
    # entonces, y renombrar el depósito no puede reescribir el pasado.
    assert traslado["sector_origen"] == "Admisión"
    assert traslado["sector_destino"] == "Taller"
    assert traslado["motivo"] == "Se retira para revisión"


def test_sacar_del_deposito_lo_devuelve_al_sector(client, escenario):
    client.post("/api/depositos/transferir", json={
        "equipo_ids": [escenario["equipo_uno"]], "destino_id": escenario["taller"],
    })

    r = client.post("/api/depositos/transferir", json={
        "equipo_ids": [escenario["equipo_uno"]], "destino_id": None,
    })

    assert r.status_code == 200
    equipo = r.json()[0]
    assert equipo["deposito_id"] is None
    # El sector nunca se pisó, así que vuelve a ser la ubicación efectiva.
    assert equipo["sector"] == "Admisión"

    movimientos = client.get(
        f"/api/equipos/{escenario['equipo_uno']}/movimientos"
    ).json()
    vuelta = movimientos[0]
    assert (vuelta["sector_origen"], vuelta["sector_destino"]) == ("Taller", "Admisión")


def test_mover_entre_depositos_encadena_los_dos_lugares(client, escenario):
    client.post("/api/depositos/transferir", json={
        "equipo_ids": [escenario["equipo_uno"]], "destino_id": escenario["taller"],
    })

    client.post("/api/depositos/transferir", json={
        "equipo_ids": [escenario["equipo_uno"]], "destino_id": escenario["panol"],
    })

    ultimo = client.get(f"/api/equipos/{escenario['equipo_uno']}/movimientos").json()[0]
    assert (ultimo["sector_origen"], ultimo["sector_destino"]) == ("Taller", "Pañol")


def test_la_transferencia_rechaza_el_deposito_ajeno(client, escenario):
    r = client.post("/api/depositos/transferir", json={
        "equipo_ids": [escenario["equipo_dos"]], "destino_id": escenario["panol"],
    })

    assert r.status_code == 422


def test_una_transferencia_con_un_equipo_inexistente_no_mueve_ninguno(client, escenario):
    """En una transaccion: no puede quedar la mitad del lote movida."""
    r = client.post("/api/depositos/transferir", json={
        "equipo_ids": [escenario["equipo_uno"], 9999],
        "destino_id": escenario["taller"],
    })

    assert r.status_code == 404
    assert client.get(
        f"/api/equipos/{escenario['equipo_uno']}"
    ).json()["deposito_id"] is None


# --- borrado ----------------------------------------------------------------

def test_no_se_borra_un_deposito_con_equipos_adentro(client, escenario):
    client.post("/api/depositos/transferir", json={
        "equipo_ids": [escenario["equipo_uno"]], "destino_id": escenario["taller"],
    })

    r = client.delete(f"/api/depositos/{escenario['taller']}")

    assert r.status_code == 409
    assert "1 equipo" in r.json()["detail"]
    assert client.get(f"/api/depositos/{escenario['taller']}").status_code == 200


def test_un_deposito_vacio_se_borra(client, escenario):
    assert client.delete(f"/api/depositos/{escenario['panol']}").status_code == 204
    assert client.get(f"/api/depositos/{escenario['panol']}").status_code == 404


# --- el listado -------------------------------------------------------------

def test_el_listado_trae_el_conteo_de_lo_que_hay_adentro(client, escenario):
    client.post("/api/depositos/transferir", json={
        "equipo_ids": [escenario["equipo_uno"]], "destino_id": escenario["taller"],
    })

    por_id = {d["id"]: d for d in client.get("/api/depositos").json()}

    assert por_id[escenario["taller"]]["total_equipos"] == 1
    assert por_id[escenario["panol"]]["total_equipos"] == 0


def test_solo_activos_deja_afuera_los_desactivados(client, escenario):
    client.put(f"/api/depositos/{escenario['panol']}", json={
        "nombre": "Pañol", "activo": False,
    })

    activos = client.get("/api/depositos?solo_activos=true").json()

    assert escenario["panol"] not in {d["id"] for d in activos}
    assert escenario["taller"] in {d["id"] for d in activos}
