"""Sacar un equipo del deposito y ponerlo en un sector del cliente (2026-08-31).

El caso que motivo el endpoint: el hospital guarda sus equipos nuevos en su
propio panol y los va instalando —"este va a Consultorios, consultorio 6"—.
Eso ya se podia hacer editando el equipo entero, pero por dos campos que en el
formulario no se ven relacionados (Deposito = Ninguno **y** Sector = texto), y
sobre todo por un `PUT` que manda el equipo completo.

Lo que estos tests fijan, en orden de lo que puede romperse en silencio:

1. **Que mover un equipo no le toque nada mas que la ubicacion.** Es el motivo
   entero de que el endpoint exista aparte del `PUT`: ese payload lleva el
   equipo completo, asi que una clave que el formulario no mande llega como
   `null` y se guarda. Ya paso dos veces en esa pantalla —borro la garantia de
   todo el parque, y estuvo a punto de borrar el dueno tercero—. Con el `PUT`
   ese defecto no se ve: el equipo queda "movido" y correcto en la columna que
   uno mira.
2. **Que el traslado quede en el historial con los nombres de los dos
   extremos**, que es la trazabilidad que se vino a buscar.
3. **Que el destino sea uno solo.** Con deposito y sector a la vez `lugar_de()`
   muestra el deposito, o sea que el sector se guarda y no se ve en ninguna
   pantalla.
4. Que no se pueda mandar el equipo al deposito de otro cliente — el unico
   error del modulo que no se nota despues.
"""

import pytest


# `client` sale de conftest.py.


@pytest.fixture
def escenario(client):
    """Un hospital con su panol, un taller propio, y un equipo guardado en el
    panol **con garantia y dueno tercero cargados**. Esos dos campos no son
    decorado: son los que el `PUT` borraba."""
    assert client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    ).status_code == 200

    hospital = client.post("/api/clientes", json={
        "nombre": "Hospital Municipal Esteban Iribarne", "email": "h@test.com",
    }).json()["id"]
    otro = client.post("/api/clientes", json={
        "nombre": "Otro cliente", "email": "o@test.com",
    }).json()["id"]

    proveedor = client.post("/api/proveedores", json={
        "nombre": "Rental SA",
    }).json()["id"]

    panol = client.post("/api/depositos", json={
        "nombre": "Pañol", "cliente_id": hospital,
    }).json()["id"]
    taller = client.post("/api/depositos", json={"nombre": "Taller"}).json()["id"]
    ajeno = client.post("/api/depositos", json={
        "nombre": "Pañol del otro", "cliente_id": otro,
    }).json()["id"]

    equipo = client.post("/api/equipos", json={
        "cliente_id": hospital, "tipo": "Monitor multiparamétrico",
        "marca": "Mindray", "serial": "MP-1",
        "deposito_id": panol, "estado": "almacenado",
        "proveedor_id": proveedor,
        "garantia_vence": "2027-05-30",
        "observaciones": "Entró con dos sensores",
    }).json()["id"]

    return {
        "hospital": hospital, "otro": otro, "proveedor": proveedor,
        "panol": panol, "taller": taller, "ajeno": ajeno, "equipo": equipo,
    }


# --- lo que el endpoint existe para NO tocar --------------------------------

def test_mover_no_toca_garantia_proveedor_ni_observaciones(client, escenario):
    """El motivo de que esto no sea un `PUT`.

    El payload del traslado nombra tres campos; el equipo tiene doce. Si
    alguna vez este camino vuelve a mandar el registro entero, los tres que
    el `PUT` ya borro una vez se apagan de nuevo y la pantalla sigue
    mostrando el traslado bien hecho.
    """
    equipo = escenario["equipo"]
    r = client.post(f"/api/equipos/{equipo}/mover", json={
        "sector": "Consultorios", "ubicacion_oficina": "Consultorio 6",
        "motivo": "Se instala",
    })
    assert r.status_code == 200, r.text
    movido = r.json()

    assert movido["garantia_vence"] == "2027-05-30"
    assert movido["proveedor_id"] == escenario["proveedor"]
    assert movido["observaciones"] == "Entró con dos sensores"
    assert movido["serial"] == "MP-1"
    assert movido["marca"] == "Mindray"
    # Y el estado tampoco: entrar o salir del depósito no dice por qué.
    assert movido["estado"] == "almacenado"

    # Releído de la base, no sólo lo que devolvió la llamada.
    guardado = client.get(f"/api/equipos/{equipo}").json()
    assert guardado["garantia_vence"] == "2027-05-30"
    assert guardado["proveedor_id"] == escenario["proveedor"]
    assert guardado["observaciones"] == "Entró con dos sensores"


# --- el traslado ------------------------------------------------------------

def test_del_deposito_al_sector_del_cliente(client, escenario):
    equipo = escenario["equipo"]
    r = client.post(f"/api/equipos/{equipo}/mover", json={
        "sector": "Consultorios", "ubicacion_oficina": "Consultorio 6",
        "motivo": "Se instala el monitor nuevo",
    })
    assert r.status_code == 200, r.text
    movido = r.json()

    assert movido["deposito_id"] is None
    assert movido["deposito_nombre"] is None
    assert movido["sector"] == "Consultorios"
    assert movido["ubicacion_oficina"] == "Consultorio 6"


def test_el_traslado_queda_en_el_historial_con_los_dos_extremos(client, escenario):
    """La trazabilidad es el pedido: de dónde salió y dónde está."""
    equipo = escenario["equipo"]
    client.post(f"/api/equipos/{equipo}/mover", json={
        "sector": "Consultorios", "ubicacion_oficina": "Consultorio 6",
        "motivo": "Se instala el monitor nuevo",
    })

    movs = client.get(f"/api/equipos/{equipo}/movimientos").json()
    # El más reciente primero (`list_movimientos` ordena descendente).
    traslado = movs[0]
    assert traslado["tipo"] == "traslado"
    assert traslado["sector_origen"] == "Pañol"
    assert traslado["sector_destino"] == "Consultorios"
    assert traslado["ubicacion_destino"] == "Consultorio 6"
    assert traslado["motivo"] == "Se instala el monitor nuevo"
    assert traslado["usuario"] == "admin"
    # Un solo movimiento nuevo: el traslado. El estado no cambió, así que no
    # hay una segunda fila diciendo que sí.
    assert [m["tipo"] for m in movs] == ["traslado", "alta"]


def test_volver_al_deposito_conserva_el_sector_como_de_donde_salio(client, escenario):
    """Y la ubicación puntual NO se conserva: en un estante no hay
    "Consultorio 6", y `ubicacion_texto()` la pegaría al nombre del depósito.
    Queda en el historial, que es donde el dato sigue siendo cierto."""
    equipo = escenario["equipo"]
    client.post(f"/api/equipos/{equipo}/mover", json={
        "sector": "Consultorios", "ubicacion_oficina": "Consultorio 6",
    })

    r = client.post(f"/api/equipos/{equipo}/mover", json={
        "deposito_id": escenario["taller"], "motivo": "Falla la pantalla",
    })
    assert r.status_code == 200, r.text
    guardado = r.json()

    assert guardado["deposito_nombre"] == "Taller"
    assert guardado["sector"] == "Consultorios"
    assert guardado["ubicacion_oficina"] is None

    traslado = client.get(f"/api/equipos/{equipo}/movimientos").json()[0]
    assert traslado["sector_origen"] == "Consultorios"
    assert traslado["sector_destino"] == "Taller"
    assert traslado["ubicacion_origen"] == "Consultorio 6"


# --- lo que el endpoint rechaza ---------------------------------------------

def test_no_se_puede_mandar_a_un_deposito_y_a_un_sector_a_la_vez(client, escenario):
    equipo = escenario["equipo"]
    r = client.post(f"/api/equipos/{equipo}/mover", json={
        "deposito_id": escenario["taller"], "sector": "Consultorios",
    })
    assert r.status_code == 422
    assert "no en los dos" in r.json()["detail"]


def test_sin_destino_no_es_un_traslado(client, escenario):
    """Un payload vacío llegaría como "sacalo del depósito y no lo pongas en
    ningún lado", que no es ningún gesto de la pantalla."""
    equipo = escenario["equipo"]
    r = client.post(f"/api/equipos/{equipo}/mover", json={})
    assert r.status_code == 422
    assert "Falta el destino" in r.json()["detail"]

    # Y el equipo sigue donde estaba.
    assert client.get(f"/api/equipos/{equipo}").json()["deposito_id"] == escenario["panol"]


def test_un_sector_en_blanco_tampoco_alcanza(client, escenario):
    equipo = escenario["equipo"]
    r = client.post(f"/api/equipos/{equipo}/mover", json={"sector": "   "})
    assert r.status_code == 422


def test_no_se_puede_dejar_en_el_deposito_de_otro_cliente(client, escenario):
    equipo = escenario["equipo"]
    r = client.post(f"/api/equipos/{equipo}/mover", json={
        "deposito_id": escenario["ajeno"],
    })
    assert r.status_code == 422
    assert "otro cliente" in r.json()["detail"]

    # Y no quedó movido a medias.
    assert client.get(f"/api/equipos/{equipo}").json()["deposito_id"] == escenario["panol"]


def test_equipo_inexistente(client, escenario):
    r = client.post("/api/equipos/99999/mover", json={"sector": "Guardia"})
    assert r.status_code == 404
