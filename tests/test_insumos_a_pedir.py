"""Fase 3: lo que el historial permite anticipar (2026-08-24).

Las fases 1 y 2 registran lo que pasó. Ésta contesta lo único que evita que la
máquina se pare: **cuándo hay que pedir el próximo**, con el historial que ya se
venía cargando y sin ninguna tabla nueva.

Los tests van en dos capas, y no es adorno:

1. **La aritmética, sin base de datos** (`ResumenDeConsumo`). Es donde vive el
   cálculo, y probarlo con objetos armados a mano deja ver el caso raro —el
   contador que retrocede, la máquina sin historial— sin sembrar media
   instancia por cada uno.
2. **El endpoint contra la API**, para lo que la primera capa no puede ver: el
   agrupamiento por (equipo, insumo), el orden y los filtros.
"""
import os
from datetime import date, timedelta

import pytest

from app.services.insumos import MARGEN_ANTICIPO, ResumenDeConsumo


HOY = date.today()


def _dias(n: int) -> str:
    return (HOY - timedelta(days=n)).isoformat()


class FilaFalsa:
    """Lo mínimo que `ResumenDeConsumo` mira de una fila.

    Un doble y no el modelo de SQLAlchemy: la clase no toca la base, así que
    construir una sesión para probar una resta sería pagar el arranque entero
    por cada caso. Los campos son los cuatro que el cálculo lee — si alguno
    dejara de existir, la capa 2 (contra la API real) se pone en rojo.
    """

    _proximo_id = 0

    def __init__(self, colocacion=None, contador=None, pedido=None, entrega=None):
        FilaFalsa._proximo_id += 1
        self.id = FilaFalsa._proximo_id
        self.fecha_colocacion = colocacion
        self.contador_copias = contador
        self.fecha_pedido = pedido
        self.fecha_entrega = entrega


def _resumen(colocaciones, pendientes=(), demora=None, hoy=None):
    return ResumenDeConsumo(
        equipo_id=1, insumo_item_id=1, insumo_nombre="Tóner",
        colocaciones=list(colocaciones), pendientes=list(pendientes),
        hoy_=hoy or HOY, demora_proveedor=demora,
    )


# ── La aritmética ───────────────────────────────────────────────────────────

def test_con_una_sola_colocacion_no_hay_nada_que_estimar():
    """🔴 **No se inventa una duración por defecto.** Una predicción sacada de
    la nada se lee igual que una medida, y la primera vez que falle nadie
    vuelve a mirar la lista."""
    r = _resumen([FilaFalsa(colocacion=HOY - timedelta(days=10), contador=100)])

    assert r.cambios == 1
    assert r.dias_entre_cambios is None
    assert r.proximo_cambio_estimado is None
    assert r.pedir_desde is None
    assert r.estado == "sin_historial"
    # Lo que SÍ se sabe con una sola colocación se informa igual: cuándo fue.
    assert r.dias_desde_el_ultimo == 10


def test_la_cadencia_sale_del_promedio_de_los_intervalos():
    r = _resumen([
        FilaFalsa(colocacion=HOY - timedelta(days=100)),
        FilaFalsa(colocacion=HOY - timedelta(days=60)),   # 40 días
        FilaFalsa(colocacion=HOY - timedelta(days=10)),   # 50 días
    ])

    assert r.cambios == 3
    assert r.dias_entre_cambios == 45
    assert r.ultimo_cambio == HOY - timedelta(days=10)
    assert r.proximo_cambio_estimado == HOY + timedelta(days=35)


def test_las_colocaciones_desordenadas_dan_el_mismo_intervalo():
    """El repositorio las trae en el orden que devuelva la base. Si el cálculo
    dependiera de ese orden, los intervalos saldrían negativos sin que nada
    avise."""
    fechas = [HOY - timedelta(days=d) for d in (10, 100, 60)]
    r = _resumen([FilaFalsa(colocacion=f) for f in fechas])

    assert r.dias_entre_cambios == 45


def test_el_aviso_se_adelanta_por_la_demora_del_proveedor():
    """Avisar el día del cambio estimado es avisar tarde: el insumo tarda en
    llegar. Se descuenta lo que tarda ESE proveedor más un margen sobre la
    propia cadencia de la máquina."""
    colocaciones = [
        FilaFalsa(colocacion=HOY - timedelta(days=60)),
        FilaFalsa(colocacion=HOY - timedelta(days=10)),  # cada 50 días
    ]
    sin_demora = _resumen(colocaciones)
    con_demora = _resumen(colocaciones, demora=7)

    # Sin demora: sólo el margen sobre la cadencia (50 × 10% = 5 días).
    assert sin_demora.pedir_desde == HOY + timedelta(days=40 - 5)
    # Con demora: siete días más de anticipación.
    assert con_demora.pedir_desde == sin_demora.pedir_desde - timedelta(days=7)
    assert MARGEN_ANTICIPO == 0.10


def test_una_maquina_atrasada_pide_ahora_y_una_reciente_no():
    vieja = _resumen([
        FilaFalsa(colocacion=HOY - timedelta(days=120)),
        FilaFalsa(colocacion=HOY - timedelta(days=70)),  # cada 50, ya vencida
    ])
    reciente = _resumen([
        FilaFalsa(colocacion=HOY - timedelta(days=55)),
        FilaFalsa(colocacion=HOY - timedelta(days=5)),   # cada 50, recién puesta
    ])

    assert vieja.estado == "pedir_ahora"
    assert vieja.dias_para_pedir < 0          # hace días que había que pedirlo
    assert reciente.estado == "al_dia"
    assert reciente.dias_para_pedir > 0


def test_lo_que_ya_esta_pedido_no_se_vuelve_a_pedir():
    """🔑 `ya_pedido` gana sobre `pedir_ahora`. Sin esa precedencia, una máquina
    vencida seguiría gritando después de que alguien la atendió — y una lista
    que grita por lo ya resuelto se deja de mirar."""
    colocaciones = [
        FilaFalsa(colocacion=HOY - timedelta(days=120)),
        FilaFalsa(colocacion=HOY - timedelta(days=70)),
    ]
    assert _resumen(colocaciones).estado == "pedir_ahora"

    # La misma máquina, con un tóner ya pedido esperando.
    con_pedido = _resumen(colocaciones, pendientes=[FilaFalsa(pedido=HOY)])
    assert con_pedido.estado == "ya_pedido"


def test_el_rinde_en_copias_saltea_los_tramos_que_no_se_pueden_medir():
    """Sin lectura, o con el contador más bajo que el anterior —la placa
    cambiada—, ese tramo no se puede medir. **No vale cero**: promediarlo como
    cero hundiría el rinde de la máquina e inventaría un problema."""
    r = _resumen([
        FilaFalsa(colocacion=HOY - timedelta(days=150), contador=10_000),
        FilaFalsa(colocacion=HOY - timedelta(days=100), contador=18_000),  # 8.000
        FilaFalsa(colocacion=HOY - timedelta(days=50), contador=None),     # sin leer
        FilaFalsa(colocacion=HOY - timedelta(days=10), contador=100),      # placa nueva
    ])

    # Un solo tramo medible, y es ése.
    assert r.copias_promedio == 8_000
    # Y el cálculo por días no se ve afectado: son dos cosas distintas.
    assert r.dias_entre_cambios is not None


def test_sin_ninguna_lectura_el_rinde_es_vacio_y_no_cero():
    r = _resumen([
        FilaFalsa(colocacion=HOY - timedelta(days=60)),
        FilaFalsa(colocacion=HOY - timedelta(days=10)),
    ])
    assert r.copias_promedio is None
    # Pero la cadencia sí se puede estimar: para eso no hace falta el contador.
    assert r.dias_entre_cambios == 50
    assert r.estado in ("al_dia", "pedir_ahora")


# ── El endpoint, contra la API real ─────────────────────────────────────────

@pytest.fixture
def client(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def escenario(client):
    hospital = client.post("/api/clientes", json={"nombre": "Hospital"}).json()
    junin = client.post("/api/proveedores", json={"nombre": "Sistemas Junín"}).json()
    equipo = client.post("/api/equipos", json={
        "cliente_id": hospital["id"], "tipo": "Fotocopiadora", "marca": "Kyocera",
        "sector": "Laboratorio", "proveedor_id": junin["id"],
    }).json()
    otro = client.post("/api/equipos", json={
        "cliente_id": hospital["id"], "tipo": "Fotocopiadora", "marca": "Brother",
        "sector": "Admisión", "proveedor_id": junin["id"],
    }).json()
    negro = client.post("/api/consumibles", json={"nombre": "Tóner negro"}).json()
    cyan = client.post("/api/consumibles", json={"nombre": "Tóner cyan"}).json()
    return {
        "cliente": hospital, "equipo": equipo, "otro_equipo": otro,
        "negro": negro, "cyan": cyan,
    }


def _colocar(client, equipo_id, item_id, dias_atras, contador=None):
    r = client.post("/api/insumos", json={
        "equipo_id": equipo_id, "insumo_item_id": item_id,
        "fecha_colocacion": _dias(dias_atras), "contador_copias": contador,
    })
    assert r.status_code == 201, r.text
    return r.json()[0]


def test_el_resumen_agrupa_por_equipo_y_por_insumo(client, escenario):
    """Cuatro filas, tres consumos distintos: el negro y el cyan de la misma
    máquina son dos cadencias, y la otra máquina es una tercera."""
    _colocar(client, escenario["equipo"]["id"], escenario["negro"]["id"], 100)
    _colocar(client, escenario["equipo"]["id"], escenario["negro"]["id"], 50)
    _colocar(client, escenario["equipo"]["id"], escenario["cyan"]["id"], 30)
    _colocar(client, escenario["otro_equipo"]["id"], escenario["negro"]["id"], 20)

    filas = client.get("/api/insumos/resumen").json()
    assert len(filas) == 3

    negro = next(
        f for f in filas
        if f["equipo_id"] == escenario["equipo"]["id"]
        and f["insumo_item_id"] == escenario["negro"]["id"]
    )
    assert negro["cambios"] == 2
    assert negro["dias_entre_cambios"] == 50
    assert negro["equipo_descripcion"] == "Fotocopiadora Kyocera"
    assert negro["cliente_nombre"] == "Hospital"

    # El cyan de la misma máquina tiene una sola colocación: no se contamina
    # con la cadencia del negro.
    cyan = next(f for f in filas if f["insumo_item_id"] == escenario["cyan"]["id"])
    assert cyan["cambios"] == 1
    assert cyan["estado"] == "sin_historial"


def test_la_bandeja_trae_lo_que_hay_que_pedir_y_deja_afuera_lo_demas(client, escenario):
    # Atrasada: cada 50 días y hace 70 del último cambio.
    _colocar(client, escenario["equipo"]["id"], escenario["negro"]["id"], 120)
    _colocar(client, escenario["equipo"]["id"], escenario["negro"]["id"], 70)
    # Al día: misma cadencia, cambiada hace 5.
    _colocar(client, escenario["otro_equipo"]["id"], escenario["negro"]["id"], 55)
    _colocar(client, escenario["otro_equipo"]["id"], escenario["negro"]["id"], 5)

    a_pedir = client.get("/api/insumos/resumen?estado=pedir_ahora").json()
    assert [f["equipo_id"] for f in a_pedir] == [escenario["equipo"]["id"]]

    # El control: sin filtro salen las dos, así que el 1 de arriba es el filtro
    # y no una carga que falló.
    assert len(client.get("/api/insumos/resumen").json()) == 2
    # Y lo que hay que pedir va primero, que es el orden de lectura.
    assert client.get("/api/insumos/resumen").json()[0]["estado"] == "pedir_ahora"


def test_pedir_un_toner_saca_la_maquina_de_la_bandeja(client, escenario):
    """El circuito completo: la máquina avisa, alguien pide, y deja de avisar
    —sin haber cambiado nada del historial—."""
    _colocar(client, escenario["equipo"]["id"], escenario["negro"]["id"], 120)
    _colocar(client, escenario["equipo"]["id"], escenario["negro"]["id"], 70)
    assert len(client.get("/api/insumos/resumen?estado=pedir_ahora").json()) == 1

    client.post("/api/insumos", json={
        "equipo_id": escenario["equipo"]["id"],
        "insumo_item_id": escenario["negro"]["id"], "fecha_pedido": _dias(0),
    })

    assert client.get("/api/insumos/resumen?estado=pedir_ahora").json() == []
    ya = client.get("/api/insumos/resumen?estado=ya_pedido").json()
    assert len(ya) == 1
    # El historial no se tocó: sigue diciendo dos cambios y su cadencia.
    assert ya[0]["cambios"] == 2
    assert ya[0]["dias_entre_cambios"] == 50


def test_el_resumen_de_un_equipo_es_el_de_su_ficha(client, escenario):
    _colocar(client, escenario["equipo"]["id"], escenario["negro"]["id"], 60)
    _colocar(client, escenario["equipo"]["id"], escenario["negro"]["id"], 10, 5000)
    _colocar(client, escenario["otro_equipo"]["id"], escenario["negro"]["id"], 10)

    solo = client.get(
        f"/api/insumos/resumen?equipo_id={escenario['equipo']['id']}"
    ).json()
    assert len(solo) == 1
    assert solo[0]["equipo_id"] == escenario["equipo"]["id"]
    # Control: sin el filtro hay dos.
    assert len(client.get("/api/insumos/resumen").json()) == 2


def test_la_ruta_del_resumen_no_la_atiende_la_ficha(client, escenario):
    """`/resumen` va declarada ANTES que `/{insumo_id}`. Sin ese orden, la ruta
    caería en la ficha, `resumen` no parsearía como entero y esto sería un 422
    — un fallo que se lee como "el endpoint no existe"."""
    r = client.get("/api/insumos/resumen")
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_un_estado_inventado_se_rechaza(client, escenario):
    r = client.get("/api/insumos/resumen?estado=urgentisimo")
    assert r.status_code == 422, r.text
