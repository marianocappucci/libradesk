"""El seed **corriendo de verdad**, no inspeccionando sus constantes.

`tests/test_seed_guarda.py` compara listas y valida la guarda de host, y eso ya
atrapó cosas reales (la última: las tres columnas de cobertura del abono que
faltaban en `CAMPOS_INCIDENCIA`). Pero nada ejecutaba `sembrar()`, así que
**cualquier defecto en el cuerpo del seed sólo aparecía corriéndolo contra una
instancia real** — que es la definición de un mecanismo que nadie invoca.

Y pasó: el bloque del cliente con abono se agregó el 2026-08-14, con la suite
entera en verde, y reventó al primer intento contra `dev` —
`POST /api/clientes → 409` por un CUIT inventado que ya era de otro cliente. El
error de fondo no era el número: era que **la idempotencia se chequeaba por un
campo distinto del que el producto usa para deduplicar**, así que el "si no
está, créalo" nunca lo iba a encontrar y siempre iba a chocar.

Este test cierra eso: `sembrar()` corre entero contra la app real y la base real
de la suite. Es lento comparado con el resto, y vale lo que cuesta — es la única
forma de que un defecto del seed se vea antes de un despliegue.
"""

import os
from datetime import date, datetime, timedelta

import pytest

from scripts.seed_dev import sembrar


class ApiDeTest:
    """El `Api` del seed, hablando por el `TestClient` en vez de por la red.

    La costura es `_pedir`: el seed sólo usa `get`/`post`/`put` encima de él, así
    que reemplazarlo alcanza para que **el resto del script sea exactamente el
    que corre en producción** — si se probara una copia, el test no diría nada
    sobre el archivo que se despliega.

    Levanta `RuntimeError` con el mismo formato que el original: los mensajes de
    error del seed son parte de lo que se está probando.
    """

    def __init__(self, client):
        self.client = client

    def _pedir(self, metodo: str, ruta: str, cuerpo=None):
        r = self.client.request(metodo, ruta, json=cuerpo)
        if r.status_code >= 400:
            raise RuntimeError(f"{metodo} {ruta} → {r.status_code}: {r.text[:300]}")
        return r.json() if r.content else None

    def get(self, ruta):
        return self._pedir("GET", ruta)

    def post(self, ruta, cuerpo=None):
        return self._pedir("POST", ruta, cuerpo)

    def put(self, ruta, cuerpo):
        return self._pedir("PUT", ruta, cuerpo)


@pytest.fixture
def api(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    # El seed aborta si la instancia no tiene clientes: los toma como dados y
    # cuelga de ellos los equipos, depósitos y tickets de ejemplo.
    client.post("/api/clientes", json={
        "nombre": "Cliente Uno", "empresa": "UNO SA", "ciudad": "Chivilcoy",
    })
    client.post("/api/clientes", json={
        "nombre": "Cliente Dos", "empresa": "DOS SA", "ciudad": "Suipacha",
    })
    return ApiDeTest(client)


def test_el_seed_corre_entero(api):
    """Que no explote es la mitad del valor; la otra es que sea **idempotente**.

    Se corre dos veces a propósito: el seed se corre de nuevo sobre instancias
    que ya tienen datos —es lo normal después de cada despliegue— y la segunda
    corrida es la que encuentra las dedup mal chequeadas. La primera versión del
    bloque de abono habría pasado una corrida sobre una base vacía y fallado la
    segunda.
    """
    sembrar(api)
    sembrar(api)


def test_el_seed_deja_un_cliente_con_abono_y_las_tres_coberturas(api):
    """Sin un cliente `mensual` el bloque "Cobertura del abono" no se muestra en
    ninguna pantalla, así que la feature no se puede revisar en dev ni en la
    demo. Y con los tres reclamos iguales, la mitad del comportamiento queda sin
    mirarse."""
    sembrar(api)

    clientes = api.get("/api/clientes")
    con_abono = [c for c in clientes if c["tipo_facturacion"] == "mensual"]
    assert con_abono, "el seed no dejó ningún cliente con abono"

    ids = {c["id"] for c in con_abono}
    coberturas = {
        i["cobertura_abono"]
        for i in api.get("/api/incidencias")
        if i["cliente_id"] in ids and i["cobertura_abono"]
    }
    assert coberturas == {"total", "parcial", "fuera"}, coberturas


def test_el_seed_reusa_el_cliente_con_abono_que_ya_existe(api):
    """El defecto real, en su forma general: **el seed no puede inventar un
    identificador que el producto usa para deduplicar**.

    Acá el cliente con abono ya existe y encima ocupa el CUIT que el seed
    inventaba. Con la versión vieja —buscar por nombre, crear con CUIT fijo—
    esto es un `409` y el seed muere. Con la nueva reusa el que hay.
    """
    api.post("/api/clientes", {
        "nombre": "Estudio Pereyra & Asociados", "empresa": "PEREYRA SRL",
        "cuit": "30-71234567-9", "ciudad": "Chivilcoy",
        "tipo_facturacion": "mensual",
    })

    sembrar(api)

    mensuales = [c for c in api.get("/api/clientes")
                 if c["tipo_facturacion"] == "mensual"]
    assert len(mensuales) == 1, [c["nombre"] for c in mensuales]
    assert mensuales[0]["nombre"] == "Estudio Pereyra & Asociados"


def test_la_agenda_queda_con_dias_para_los_dos_lados(api):
    """Pedido del humano (2026-08-15): la agenda con *"varios días para adelante
    y para atrás"*.

    🔴 **Se cuentan DÍAS DISTINTOS, no trabajos.** Es la diferencia que importa:
    el seed viejo dejaba varios trabajos y la agenda igual abría vacía, porque
    caían todos en una o dos fechas fijas. Un assert sobre "hay N trabajos"
    habría estado verde durante todo ese tiempo.

    Y se mide contra **hoy**, que es el día que la pantalla abre por defecto.
    """
    sembrar(api)

    hoy = str(date.today())
    dias = {
        str(i["fecha_programada"])[:10]
        for i in api.get("/api/incidencias")
        if i.get("fecha_programada")
    }
    assert len(dias) >= 8, f"la agenda quedó apretada en pocos días: {sorted(dias)}"
    assert [d for d in dias if d < hoy], f"nada antes de hoy ({hoy}): {sorted(dias)}"
    assert [d for d in dias if d > hoy], f"nada después de hoy ({hoy}): {sorted(dias)}"


def test_ninguna_cuadrilla_queda_con_dos_trabajos_encimados(api):
    """El producto rechaza el solape con un 409, y el seed tiene que respetarlo.

    Es el defecto que este archivo cazó cuando se escribió el bloque de la
    agenda: repartía franjas sin mirar lo ya agendado y el seed se cortaba a la
    mitad. Este caso lo fija sobre el RESULTADO, que es lo que importa, y no
    sobre el 409 — que con el arreglo puesto ya no llega, así que un test que
    esperara la excepción no mediría nada.

    Dos trabajos **pegados** (uno termina 11:00, el otro empieza 11:00) son
    válidos y el seed los crea a propósito: por eso la comparación es `>=`.
    """
    sembrar(api)

    por_cuadrilla: dict[int, list[tuple]] = {}
    for i in api.get("/api/incidencias"):
        equipo, cuando = i.get("equipo_trabajo_id"), i.get("fecha_programada")
        if not equipo or not cuando:
            continue
        desde = datetime.fromisoformat(str(cuando)[:16])
        hasta = desde + timedelta(minutes=int(i.get("duracion_minutos") or 60))
        por_cuadrilla.setdefault(int(equipo), []).append((desde, hasta, i["id"]))

    # Control: sin esto, una respuesta sin `equipo_trabajo_id` dejaría el dict
    # vacío y el test pasaría sin haber comparado un solo par.
    assert por_cuadrilla, "ninguna incidencia quedó agendada con cuadrilla"

    for equipo, franjas in por_cuadrilla.items():
        franjas.sort()
        for (d1, h1, id1), (d2, _h2, id2) in zip(franjas, franjas[1:]):
            assert d2 >= h1, (
                f"la cuadrilla {equipo} tiene encimados el #{id1} (termina {h1}) "
                f"y el #{id2} (empieza {d2})"
            )
