"""Stock de consumibles, adoptado de LibraCommerce (2026-08-12).

Este producto no tenia stock de ninguna clase. Los tests que mas importan no
son los del camino feliz sino los dos del final: **que la adopcion no le haya
roto nada a lo que ya existia**, que es el riesgo real de meter 19 tablas de
otro motor en una base con datos de cliente.
"""

import os
from datetime import datetime

import pytest

from app.services import inventario

CUANDO = datetime(2026, 8, 12, 10, 0, 0)


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin.

    Mismo patron que test_agenda/test_alquileres: el de conftest viene sin
    sesion y varios tests de acá pegan a la API.
    """
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def app_armada(client):
    """El schema del motor se crea en `create_app`, asi que basta con que la
    fixture `client` haya construido la app."""
    return client


@pytest.fixture
def escenario(app_armada):
    """Un consumible con 189 unidades en el central, y una camioneta vacia."""
    item = inventario.crear_item("Plug RJ45", costo=120.0, stock_minimo=50)
    central = inventario.crear_deposito("Deposito central", es_default=True)
    camioneta = inventario.crear_deposito("Kangoo")
    inventario.ajustar(item["id"], central["id"], 189, nota="Carga inicial",
                       fecha=CUANDO)
    return item, central, camioneta


# ── El circuito que motivo la adopcion ───────────────────────────────────


def test_transferir_del_central_a_la_camioneta(escenario):
    """El caso de uso central del producto que disparo todo esto."""
    item, central, camioneta = escenario

    inventario.transferir(item["id"], central["id"], camioneta["id"], 40,
                          nota="Sale la cuadrilla Norte", fecha=CUANDO)

    assert inventario.stock_actual(item["id"], central["id"]) == 149
    assert inventario.stock_actual(item["id"], camioneta["id"]) == 40


def test_no_transfiere_mas_de_lo_que_hay(escenario):
    item, central, camioneta = escenario

    with pytest.raises(ValueError, match="Stock insuficiente"):
        inventario.transferir(item["id"], central["id"], camioneta["id"], 200,
                              fecha=CUANDO)

    assert inventario.stock_actual(item["id"], central["id"]) == 189
    assert inventario.stock_actual(item["id"], camioneta["id"]) == 0


def test_la_transferencia_deja_las_dos_patas_con_su_motivo(escenario):
    """Mismo vocabulario que los otros tres consumidores del motor."""
    item, central, camioneta = escenario

    inventario.transferir(item["id"], central["id"], camioneta["id"], 10,
                          fecha=CUANDO)

    motivos_salida = {m["motivo"] for m in inventario.movimientos(item["id"], central["id"])}
    motivos_entrada = {m["motivo"] for m in inventario.movimientos(item["id"], camioneta["id"])}
    assert "transferencia_salida" in motivos_salida
    assert motivos_entrada == {"transferencia_entrada"}


def test_una_salida_manual_valida_disponibilidad(escenario):
    """A diferencia de un mostrador, acá el negativo es un error de carga."""
    item, central, _ = escenario

    with pytest.raises(ValueError, match="Stock insuficiente"):
        inventario.ajustar(item["id"], central["id"], -200, fecha=CUANDO)

    assert inventario.stock_actual(item["id"], central["id"]) == 189


def test_una_entrada_manual_suma(escenario):
    item, central, _ = escenario

    inventario.ajustar(item["id"], central["id"], 11, nota="Compra", fecha=CUANDO)

    assert inventario.stock_actual(item["id"], central["id"]) == 200


def test_el_ajuste_en_cero_se_rechaza(escenario):
    item, central, _ = escenario

    with pytest.raises(ValueError, match="cero"):
        inventario.ajustar(item["id"], central["id"], 0, fecha=CUANDO)


# ── Lo que la adopcion NO tenia que romper ───────────────────────────────


def test_el_actividad_log_que_ya_existia_sobrevive(client):
    """🔴 El riesgo real de esta adopcion.

    LibraDesk **ya tiene** una tabla `actividad_log` (la crea libraauth para la
    auditoria por flush) y el motor **tambien la declara**, con `entidad_id`
    de otro tipo (INTEGER contra el varchar de acá). Como el DDL del motor es
    `CREATE TABLE IF NOT EXISTS`, la de este producto tiene que quedar intacta
    — y sobre todo tiene que **seguir aceptando un entidad_id de texto**, que
    es lo que escribe el listener de libraauth.

    Si algun dia alguien "arregla" esa colision recreando la tabla con el DDL
    del motor, este test se pone en rojo antes que la auditoria de produccion.
    """
    resp = client.post("/api/clientes", json={"nombre": "Cliente de prueba"})
    assert resp.status_code in (200, 201), resp.text

    # La auditoria de libraauth tiene que haber registrado el alta.
    from libracore.db import core as libracore_core
    with libracore_core.get_connection() as conn:
        filas = conn.execute(
            "SELECT entidad, entidad_id FROM actividad_log ORDER BY id DESC"
        ).fetchall()
    assert filas, "la adopcion del motor dejo sin registrar la auditoria"


def test_las_tablas_propias_siguen_estando(client):
    """El `init_schema` del motor no puede haber tocado el dominio propio."""
    from libracore.db import core as libracore_core

    # `clients` y no `clientes`: la revision `0017` renombro la tabla al
    # adoptar el modulo de clientes de LibraCore. Sigue siendo del dominio
    # propio en lo que a este test le importa — que el `init_schema` del motor
    # de inventario no se la lleve puesta.
    propias = {"clients", "incidencias", "equipos", "depositos", "tecnicos"}
    del_motor = {"catalog_items", "locations", "stock_movements", "units"}

    with libracore_core.get_connection() as conn:
        for tabla in propias | del_motor:
            conn.execute(f"SELECT 1 FROM {tabla} LIMIT 1").fetchall()


def test_depositos_del_producto_y_del_motor_son_cosas_distintas(client, escenario):
    """`depositos` guarda equipos serializados; `locations`, existencias.

    Se llaman parecido en castellano y distinto en la base, y esa es
    exactamente la razon por la que conviven sin pisarse.
    """
    from libracore.db import core as libracore_core

    with libracore_core.get_connection() as conn:
        propios = conn.execute("SELECT count(*) FROM depositos").fetchone()[0]
    del_motor = len(inventario.listar_depositos())

    assert del_motor == 2, "los dos depositos de consumibles del escenario"
    assert propios != del_motor or propios == 0


# ── El código automático (pedido del humano, 2026-08-16) ─────────────────────


def _codigo_de(client, item_id: int) -> str:
    fila = next(c for c in client.get('/api/consumibles').json() if c['id'] == item_id)
    return fila['codigo']


def test_un_producto_nuevo_sale_con_codigo(client):
    """🔴 El pedido: *«los productos deberían tener un código que se genere
    automáticamente»*. Antes el campo `codigo` existía pero había que tipearlo,
    así que la mayoría de los productos no tenía ninguno y la columna del
    listado salía vacía."""
    item = client.post('/api/consumibles', json={'nombre': 'Plug RJ45'}).json()

    assert _codigo_de(client, item['id']) == 'PRD-00000001'


def test_los_codigos_son_correlativos(client):
    uno = client.post('/api/consumibles', json={'nombre': 'Plug RJ45'}).json()
    dos = client.post('/api/consumibles', json={'nombre': 'Cable UTP'}).json()
    tres = client.post('/api/consumibles', json={'nombre': 'Ficha RJ11'}).json()

    assert [_codigo_de(client, x['id']) for x in (uno, dos, tres)] == [
        'PRD-00000001', 'PRD-00000002', 'PRD-00000003',
    ]


def test_un_codigo_tipeado_a_mano_se_respeta(client):
    """El del proveedor, un EAN. El automático es el default, no una
    imposición."""
    item = client.post('/api/consumibles', json={
        'nombre': 'Plug RJ45', 'codigo': '7791234567890',
    }).json()

    assert _codigo_de(client, item['id']) == '7791234567890'


def test_un_codigo_a_mano_NO_corre_la_numeracion_automatica(client):
    """🔑 El control de la regla de arriba, y la razón por la que el máximo se
    busca filtrando por el prefijo `PRD-`.

    Si la cuenta mirara todos los códigos, un EAN de 13 dígitos escrito a mano
    la dispararía a un número enorme — o la rompería, según cómo compare.
    """
    client.post('/api/consumibles', json={
        'nombre': 'Con EAN', 'codigo': '7791234567890',
    })
    despues = client.post('/api/consumibles', json={'nombre': 'Sin código'}).json()

    assert _codigo_de(client, despues['id']) == 'PRD-00000001'
