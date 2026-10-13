"""El CRUD de clientes va por `libracore.db.clients` (ADR-013) y `Cliente` es de solo lectura.

Lo que fija, en orden de lo que se rompe sin que se note:

1. Que `Cliente` siga describiendo la tabla `clients` **del motor**: el modelo ya no la crea
   ni la escribe, pero siete FK y unos veinticinco joins dependen de que la describa bien, y
   `crear_cliente`/`actualizar_cliente` aceptan lo que la instancia tenga.
2. Que escribir un `Cliente` por la sesion **falle en voz alta**: seguiria andando, pero sin
   dejar fila en el log.
3. Que lo que se vacia desde la pantalla quede en NULL, que borrar con remitos sea un 409
   con mensaje claro y que ese intento no deje rastro en el log.
4. Que el diff del log salga en el orden del modelo aunque el motor entregue la fila en otro.
"""
import json
from datetime import datetime

import pytest
from sqlalchemy import inspect as sa_inspect

from app import database
from app.auditoria import registrador_del_motor
from app.services.clientes import Cliente, atributos_por_columna, columnas_por_atributo

#: Columnas de `clients` que son de LibraDesk y no del motor.
PROPIAS_DE_LIBRADESK = {"price_list_id"}


def _login(client) -> None:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text


# ── 1. El modelo describe la tabla del motor ──────────────────────────────

@pytest.fixture
def base_del_motor(tmp_path):
    """Una base vacía a la que SOLO se le corre la cadena de migraciones del motor."""
    from conftest import _borrar_base, _sql_admin, _url_de

    nombre = "ld_cliente_motor_" + tmp_path.name[-12:].replace("-", "_").lower()
    _sql_admin(f'DROP DATABASE IF EXISTS "{nombre}"', f'CREATE DATABASE "{nombre}"')
    yield _url_de(nombre)
    _borrar_base(nombre)


def test_cliente_describe_la_tabla_del_motor(base_del_motor):
    """`Cliente` declara las columnas de `clients` del motor, mas las propias de LibraDesk.

    Si el motor suma una columna a `clients` y el modelo no la declara, `crear_cliente` y
    `actualizar_cliente` la aceptan igual (escriben lo que la instancia tiene), pero
    `--autogenerate` propone borrarla y el modelo deja de describir la tabla. Se mide contra
    la cadena del motor corrida de verdad (`libracore.migrar.upgrade`) y no contra una copia
    escrita aca, que es la que se desactualiza.
    """
    from libracore.migrar import upgrade
    from sqlalchemy import create_engine

    upgrade(base_del_motor)
    engine = create_engine(base_del_motor)
    try:
        del_motor = {c["name"] for c in sa_inspect(engine).get_columns("clients")}
    finally:
        engine.dispose()

    # Control: que la introspeccion vio la tabla de verdad y no un conjunto vacio.
    assert {"id", "name", "cuit_dni", "email", "activo", "created_at"} <= del_motor

    del_modelo = {c.name for c in Cliente.__table__.columns}
    assert del_motor == del_modelo - PROPIAS_DE_LIBRADESK, (
        f"el motor tiene de mas {sorted(del_motor - del_modelo)}; "
        f"el modelo tiene de mas {sorted(del_modelo - del_motor - PROPIAS_DE_LIBRADESK)}"
    )


def test_el_mapa_de_atributos_sale_del_modelo_y_cubre_toda_la_api(client):
    """El mapa API -> columna no se escribe a mano: sale de `column_attrs`."""
    por_atributo = columnas_por_atributo()
    assert por_atributo["nombre"] == "name"
    assert por_atributo["cuit"] == "cuit_dni"
    assert por_atributo["telefono"] == "phone"
    assert por_atributo["price_list_id"] == "price_list_id"
    assert atributos_por_columna()["name"] == "nombre"
    # Todo lo que acepta `POST /api/clientes` tiene columna.
    from app.routers.clientes import ClienteIn

    assert set(ClienteIn.model_fields) <= set(por_atributo)


# ── 2. Cliente es de solo lectura ─────────────────────────────────────────

def test_escribir_un_cliente_por_la_sesion_falla(client):
    _login(client)
    cid = client.post("/api/clientes", json={"nombre": "Lectura"}).json()["id"]
    sessions = database.get_session_factory()

    with sessions() as s, pytest.raises(RuntimeError, match="solo lectura"):
        s.add(Cliente(nombre="Por la sesion"))
        s.commit()

    with sessions() as s, pytest.raises(RuntimeError, match="solo lectura"):
        s.get(Cliente, cid).nombre = "Cambiado por la sesion"
        s.commit()

    with sessions() as s, pytest.raises(RuntimeError, match="solo lectura"):
        s.delete(s.get(Cliente, cid))
        s.commit()

    # No se escribio nada.
    assert client.get(f"/api/clientes/{cid}").json()["nombre"] == "Lectura"


def test_leer_o_tocar_sin_cambiar_un_cliente_no_dispara_la_guarda(client):
    """Una coleccion o un setattr al mismo valor no son una escritura de la fila."""
    _login(client)
    cid = client.post("/api/clientes", json={"nombre": "Lectura"}).json()["id"]
    with database.get_session_factory()() as s:
        c = s.get(Cliente, cid)
        c.nombre = "Lectura"
        s.commit()


# ── 3. Lo que se vacia, lo que se borra ───────────────────────────────────

def test_vaciar_un_campo_guarda_null(client):
    """`update_client` del motor toma `None` por «no tocar»: por eso no se usa. Aca vaciar un
    campo desde la pantalla (`ciudad: null`) tiene que dejar NULL de verdad."""
    from libracore.db.clients import get_client

    _login(client)
    cid = client.post("/api/clientes", json={
        "nombre": "Con ciudad", "ciudad": "Rosario", "observaciones": "algo",
    }).json()["id"]
    r = client.put(f"/api/clientes/{cid}", json={"nombre": "Con ciudad", "ciudad": None})
    assert r.status_code == 200, r.text
    assert r.json()["ciudad"] is None and r.json()["observaciones"] is None

    crudo = get_client(cid)
    assert crudo["ciudad"] is None and crudo["observaciones"] is None


def test_el_alta_deja_el_espejo_en_parties_y_la_edicion_lo_mantiene(client):
    """Efecto de pasar por el motor: el `parties` espejo (mismo id) se crea y se mantiene en
    la misma transaccion. Antes el alta no lo hacia y el cliente nuevo no se podia vender hasta
    el proximo arranque (`sincronizar_parties`)."""
    from libracore.db.core import get_connection

    _login(client)
    cid = client.post("/api/clientes", json={"nombre": "Espejado", "email": "e@t.com"}).json()["id"]
    client.put(f"/api/clientes/{cid}", json={"nombre": "Espejado SA", "email": "e@t.com"})
    with get_connection() as conn:
        fila = conn.execute("SELECT display_name, email FROM parties WHERE id = ?", (cid,)).fetchone()
    assert (fila["display_name"], fila["email"]) == ("Espejado SA", "e@t.com")


def test_email_duplicado_sigue_siendo_409(client):
    """La violacion del UNIQUE llega ahora como `sqlite3.IntegrityError` (la capa dual del
    motor), no como el de SQLAlchemy: el router tiene que seguir devolviendo el 409."""
    _login(client)
    assert client.post("/api/clientes", json={"nombre": "Uno", "email": "dup@t.com"}).status_code == 201
    r = client.post("/api/clientes", json={"nombre": "Dos", "email": "dup@t.com"})
    assert r.status_code == 409 and "email duplicado" in r.json()["detail"]

    otro = client.post("/api/clientes", json={"nombre": "Tres", "email": "tres@t.com"}).json()["id"]
    r = client.put(f"/api/clientes/{otro}", json={"nombre": "Tres", "email": "dup@t.com"})
    assert r.status_code == 409 and "email duplicado" in r.json()["detail"]
    # La edicion rechazada no cambio nada ni dejo fila en el log.
    assert client.get(f"/api/clientes/{otro}").json()["email"] == "tres@t.com"
    ediciones = client.get("/api/logs", params={"entidad": "cliente", "accion": "editar"}).json()
    assert ediciones["actividad"] == []


def test_borrar_un_cliente_con_remitos_es_409_y_no_deja_rastro(client):
    """El bloqueo es el del motor (`delete_client`): remitos y presupuestos."""
    _login(client)
    cid = client.post("/api/clientes", json={"nombre": "Con remito"}).json()["id"]
    r = client.post("/api/remitos", json={"client_id": cid, "items": [
        {"description": "Reparacion", "qty": 1, "unit_price": 1000},
    ]})
    assert r.status_code == 201, r.text

    r = client.delete(f"/api/clientes/{cid}")
    assert r.status_code == 409, r.text
    detalle = r.json()["detail"]
    assert "1 remito(s)" in detalle and "no puede eliminarse" in detalle
    assert "Desactivalo" in detalle

    assert client.get(f"/api/clientes/{cid}").status_code == 200
    borrados = client.get("/api/logs", params={"entidad": "cliente", "accion": "borrar"}).json()
    assert borrados["actividad"] == []


def test_borrar_o_desactivar_un_cliente_que_no_existe_es_404(client):
    _login(client)
    assert client.delete("/api/clientes/9999").status_code == 404
    assert client.post("/api/clientes/9999/desactivar").status_code == 404
    assert client.post("/api/clientes/9999/activar").status_code == 404
    assert client.put("/api/clientes/9999", json={"nombre": "Nadie"}).status_code == 404


def test_el_cuit_duplicado_sigue_siendo_409(client):
    _login(client)
    client.post("/api/clientes", json={"nombre": "Primero", "cuit": "30-71234567-8"})
    r = client.post("/api/clientes", json={"nombre": "Segundo", "cuit": "30-71234567-8"})
    assert r.status_code == 409 and "Ya existe un cliente con el CUIT" in r.json()["detail"]


# ── 4. El orden del diff ──────────────────────────────────────────────────

def test_el_diff_sale_en_el_orden_del_modelo_aunque_el_motor_entregue_otro(client):
    """La fila que entrega el motor viene en el orden de la tabla de CADA instancia (que
    depende de como se creo); la pantalla muestra las claves en el orden en que llegan. El
    registrador las pone en el orden del modelo, que es el que tenia el log del `flush`."""
    from libracore.auditoria import Cambio

    insertado = {}

    class ConexionFalsa:
        def execute(self, sql, params):
            insertado["params"] = params

    # El orden al reves del modelo.
    columnas = list(columnas_por_atributo().values())
    antes = {c: f"a-{c}" for c in reversed(columnas)}
    despues = {c: f"d-{c}" for c in reversed(columnas)}
    registrador_del_motor()(ConexionFalsa(), Cambio("clients", "editar", 7, antes, despues))

    # Cambian todas las columnas (incluida `id`, en este caso sintetico): lo que importa es el
    # orden de las claves.
    orden_pantalla = list(json.loads(insertado["params"][-1]))
    atributos = atributos_por_columna()
    assert orden_pantalla == [atributos[c] for c in columnas]
    assert datetime.strptime(insertado["params"][0], "%Y-%m-%d %H:%M:%S")


def test_el_registrador_ignora_una_tabla_que_no_es_clients():
    """Lista blanca, como en el ORM: el registrador ignora una tabla que no es `clients` (lista blanca)."""
    from libracore.auditoria import Cambio

    llamadas = []

    class ConexionFalsa:
        def execute(self, sql, params):
            llamadas.append(params)

    registrador_del_motor()(ConexionFalsa(), Cambio("facturas", "crear", 1, None, {"x": 1}))
    assert llamadas == []

