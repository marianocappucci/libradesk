"""La fecha de negocio sale del reloj de Argentina del motor, no del proceso.

`libracore.fechas` (ADR-070) es la fuente única, y `app/services/fecha.py`
—el «hoy» y «ahora» del producto— delega en él. La recepción y la entrega de un
equipo, el «emitido» del informe, los movimientos de material y los días que
faltan para un vencimiento tienen que salir con el día de Argentina aunque el
proceso corra en UTC —como los contenedores que no tienen `TZ`— y sea de noche
allá.

🔴 Con `datetime.now()` / `date.today()` el día salía de la `TZ` del proceso:
entre las 21:00 y la medianoche de Argentina el equipo se recibía **mañana** y
los vencimientos de hoy contaban un día de menos. La suite entera corre con
`TZ=America/Argentina/Buenos_Aires` (ver `conftest.py`), así que ningún otro test
lo podía ver: éstos vuelven el proceso a UTC y pisan el instante del motor.
"""
import os
import time
from datetime import UTC, datetime

import pytest
from libracore import fechas

from app.services import fecha, inventario, materiales

#: 02:30 UTC del 1 de abril de 2031 = 23:30 del 31 de marzo en Argentina. Una fecha
#: lejana a propósito: así el reloj real del proceso nunca coincide con la esperada.
INSTANTE = datetime(2031, 4, 1, 2, 30, tzinfo=UTC)
DIA_EN_ARGENTINA = "2031-03-31"


@pytest.fixture
def _proceso_en_utc_a_las_23_30_de_argentina(monkeypatch):
    """El proceso en UTC y el reloj del motor clavado en `INSTANTE`."""
    antes = os.environ.get("TZ")
    os.environ["TZ"] = "UTC"
    time.tzset()
    monkeypatch.setattr(fechas, "_ahora_utc", lambda: INSTANTE)
    try:
        yield
    finally:
        if antes is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = antes
        time.tzset()


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
    cliente = client.post("/api/clientes", json={"nombre": "Estudio Sur"}).json()
    equipo = client.post("/api/equipos", json={
        "cliente_id": cliente["id"], "tipo": "Notebook", "marca": "Lenovo",
        # Vence dos días después del 31 de marzo de Argentina.
        "garantia_vence": "2031-04-02",
    }).json()
    return {"cliente": cliente, "equipo": equipo}


def test_el_hoy_y_el_ahora_del_producto_son_los_del_motor(_proceso_en_utc_a_las_23_30_de_argentina):
    assert fecha.hoy() == DIA_EN_ARGENTINA
    assert fecha.ahora() == datetime(2031, 3, 31, 23, 30)
    assert fecha.ahora().tzinfo is None


def test_recibir_y_entregar_un_equipo_fechan_con_el_dia_de_argentina(
    client, escenario, _proceso_en_utc_a_las_23_30_de_argentina,
):
    r = client.post("/api/ingresos-reparacion", json={
        "cliente_id": escenario["cliente"]["id"], "equipo_id": escenario["equipo"]["id"],
        "falla_declarada": "No enciende",
    })
    assert r.status_code == 201, r.text
    ingreso = r.json()
    assert ingreso["fecha_recepcion"].startswith(f"{DIA_EN_ARGENTINA}T23:30")

    e = client.post(f"/api/ingresos-reparacion/{ingreso['id']}/entregar", json={})
    assert e.status_code == 200, e.text
    assert e.json()["fecha_entrega"].startswith(f"{DIA_EN_ARGENTINA}T23:30")


def test_el_informe_se_emite_con_el_dia_de_argentina(
    client, escenario, _proceso_en_utc_a_las_23_30_de_argentina,
):
    informe = client.app.state.informes.cliente(
        escenario["cliente"]["id"], "2031-03-01", "2031-03-31",
    )
    assert informe["periodo"]["emitido"] == DIA_EN_ARGENTINA


def test_los_dias_que_faltan_para_la_garantia_cuentan_desde_hoy_en_argentina(
    client, escenario, _proceso_en_utc_a_las_23_30_de_argentina,
):
    r = client.get("/api/dashboard/operativo?dias=30")
    assert r.status_code == 200, r.text
    garantias = r.json()["vencimientos"]["garantias"]["items"]
    assert [g["dias_restantes"] for g in garantias] == [2]


def test_un_material_cargado_lleva_la_hora_de_argentina(
    client, escenario, _proceso_en_utc_a_las_23_30_de_argentina,
):
    incidencia = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "Central sin tono",
        "descripcion": "No hay tono en los internos",
    }).json()
    item = inventario.crear_item("Plug RJ45", costo=120.0)
    deposito = inventario.crear_deposito("Kangoo")
    inventario.ajustar(item["id"], deposito["id"], 40)

    materiales.cargar(incidencia["id"], item["id"], deposito["id"], 10)

    cargado = materiales.listar(incidencia["id"])[0]
    assert str(cargado["fecha"]).startswith(DIA_EN_ARGENTINA)
