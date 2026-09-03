"""Contratos con el proveedor y el reporte de insumos — fase 2 (2026-08-24).

La fase 1 registró que el tóner se pidió, llegó y se puso. Lo que estos tests
fijan es lo que agrega la fase 2: **por qué llegaba sin cobrar**, y el papel con
el que se le reclama al proveedor cuando deja de llegar.

⚠️ El gate del módulo no se prueba acá: `/api/contratos-proveedor` entró al
diccionario `RUTAS` de `test_modulos_y_planes.py`, que es donde vive esa
cobertura para los diez módulos.
"""
import os
from datetime import date, timedelta

import pytest

HOY = date.today()


def _dias(n: int) -> str:
    return (HOY - timedelta(days=n)).isoformat()


def _en(n: int) -> str:
    return (HOY + timedelta(days=n)).isoformat()


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
    """El hospital, Sistemas Junín, dos fotocopiadoras y un tóner."""
    hospital = client.post("/api/clientes", json={
        "nombre": "Hospital Municipal Esteban Iribarne",
    }).json()
    junin = client.post("/api/proveedores", json={"nombre": "Sistemas Junín"}).json()
    otro = client.post("/api/proveedores", json={"nombre": "Copias del Centro"}).json()

    laboratorio = client.post("/api/equipos", json={
        "cliente_id": hospital["id"], "tipo": "Fotocopiadora", "marca": "Kyocera",
        "modelo": "M2540", "sector": "Laboratorio", "proveedor_id": junin["id"],
    }).json()
    admision = client.post("/api/equipos", json={
        "cliente_id": hospital["id"], "tipo": "Fotocopiadora", "marca": "Kyocera",
        "modelo": "M2540", "sector": "Admisión", "proveedor_id": junin["id"],
    }).json()
    client.post(f"/api/equipos/{laboratorio['id']}/referencias", json={
        "etiqueta": "N° interno", "valor": "4471", "proveedor_id": junin["id"],
    })

    negro = client.post("/api/consumibles", json={"nombre": "Tóner TK-1170"}).json()

    return {
        "cliente": hospital, "proveedor": junin, "otro_proveedor": otro,
        "equipo": laboratorio, "otro_equipo": admision, "negro": negro,
    }


def _contrato(client, esc, **payload):
    cuerpo = {
        "proveedor_id": esc["proveedor"]["id"],
        "cliente_id": esc["cliente"]["id"],
        "fecha_inicio": _dias(365),
    }
    cuerpo.update(payload)
    return client.post("/api/contratos-proveedor", json=cuerpo)


def _cubrir(client, contrato_id, equipo_id, **payload):
    return client.post(f"/api/contratos-proveedor/{contrato_id}/equipos",
                       json={"equipo_id": equipo_id, **payload})


def _insumo(client, esc, **payload):
    cuerpo = {"equipo_id": esc["equipo"]["id"], "insumo_item_id": esc["negro"]["id"]}
    cuerpo.update(payload)
    r = client.post("/api/insumos", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()[0]


# ── El contrato ─────────────────────────────────────────────────────────────

def test_el_contrato_se_numera_solo_y_dice_hasta_cuando(client, escenario):
    r = _contrato(client, escenario, fecha_fin=_en(90), numero_externo="SJ-2211",
                  contacto_nombre="Mesa de pedidos", contacto_telefono="2362-44-0000")
    assert r.status_code == 201, r.text
    c = r.json()
    assert c["numero"] == "CPR-00000001"
    assert c["vigente"] is True
    assert c["dias_para_vencer"] == 90
    # El número del proveedor es el que hay que citarle; el nuestro no le sirve.
    assert c["numero_externo"] == "SJ-2211"
    assert c["proveedor_nombre"] == "Sistemas Junín"

    segundo = _contrato(client, escenario).json()
    assert segundo["numero"] == "CPR-00000002"


def test_sin_vencimiento_pactado_no_es_lo_mismo_que_vencido(client, escenario):
    """`fecha_fin` en null es un contrato que sigue corriendo. Si eso se leyera
    como vencido, el caso más común —el contrato sin plazo— aparecería en rojo
    en la lista de renovaciones para siempre."""
    c = _contrato(client, escenario).json()
    assert c["fecha_fin"] is None
    assert c["vigente"] is True
    assert c["dias_para_vencer"] is None


def test_un_contrato_terminado_deja_de_estar_vigente(client, escenario):
    c = _contrato(client, escenario, fecha_inicio=_dias(400),
                  fecha_fin=_dias(30)).json()
    assert c["vigente"] is False
    assert c["dias_para_vencer"] == -30

    # El control: el filtro los separa de verdad, no devuelve siempre todo.
    vigente = _contrato(client, escenario, fecha_fin=_en(10)).json()
    numeros = [x["numero"] for x in client.get(
        "/api/contratos-proveedor?vigentes=true").json()]
    assert numeros == [vigente["numero"]]
    vencidos = [x["numero"] for x in client.get(
        "/api/contratos-proveedor?vigentes=false").json()]
    assert vencidos == [c["numero"]]


def test_la_fecha_de_fin_no_puede_ser_anterior_al_inicio(client, escenario):
    r = _contrato(client, escenario, fecha_inicio=_dias(10), fecha_fin=_dias(20))
    assert r.status_code == 409, r.text


# ── La cobertura ────────────────────────────────────────────────────────────

def test_cubrir_una_maquina_la_muestra_en_la_ficha_con_su_numero(client, escenario):
    c = _contrato(client, escenario).json()
    r = _cubrir(client, c["id"], escenario["equipo"]["id"])
    assert r.status_code == 201, r.text
    assert r.json()["vigente"] is True

    ficha = client.get(f"/api/contratos-proveedor/{c['id']}").json()
    assert ficha["equipos_vigentes"] == 1
    linea = ficha["equipos"][0]
    assert linea["equipo_descripcion"] == "Fotocopiadora Kyocera M2540"
    # El número del proveedor viaja con la línea: es lo que se lee de esta lista
    # cuando hay que pedirle algo.
    assert [x["valor"] for x in linea["referencias"]] == ["4471"]


def test_una_maquina_no_puede_estar_cubierta_por_dos_contratos_a_la_vez(client, escenario):
    """Dos coberturas simultáneas dejan sin respuesta quién pone el insumo, que
    es la pregunta que el módulo vino a contestar. El 409 dice con cuál chocó."""
    uno = _contrato(client, escenario).json()
    _cubrir(client, uno["id"], escenario["equipo"]["id"])

    dos = _contrato(client, escenario, proveedor_id=escenario["otro_proveedor"]["id"]).json()
    r = _cubrir(client, dos["id"], escenario["equipo"]["id"])
    assert r.status_code == 409, r.text
    assert uno["numero"] in r.json()["detail"]


def test_retirada_del_contrato_la_maquina_se_puede_cubrir_con_otro(client, escenario):
    """El control de la guarda de arriba: la exclusión es **en el tiempo**, no
    para siempre. Sin esto, un contrato que se rescinde dejaría la máquina sin
    poder pasar al proveedor nuevo."""
    uno = _contrato(client, escenario).json()
    # Cubierta desde hace tiempo: sin `fecha_alta` la cobertura arranca HOY y
    # cerrarla ayer sería anterior a su propia alta — que es otro 409, y
    # correcto.
    linea = _cubrir(client, uno["id"], escenario["equipo"]["id"],
                    fecha_alta=_dias(300)).json()

    cierre = client.post(
        f"/api/contratos-proveedor/equipos/{linea['id']}/retirar",
        json={"fecha_baja": _dias(1)},
    )
    assert cierre.status_code == 200, cierre.text
    assert cierre.json()["vigente"] is False
    # No se borra: que el contrato la haya cubierto es lo que hace contestable
    # si el tóner de junio entraba.
    assert len(client.get(f"/api/contratos-proveedor/{uno['id']}").json()["equipos"]) == 1

    dos = _contrato(client, escenario, proveedor_id=escenario["otro_proveedor"]["id"]).json()
    r = _cubrir(client, dos["id"], escenario["equipo"]["id"])
    assert r.status_code == 201, r.text


def test_la_cobertura_no_puede_empezar_antes_que_el_contrato(client, escenario):
    c = _contrato(client, escenario, fecha_inicio=_dias(10)).json()
    r = _cubrir(client, c["id"], escenario["equipo"]["id"], fecha_alta=_dias(30))
    assert r.status_code == 409, r.text


# ── El cruce con el insumo, que es el punto de la fase ──────────────────────

def test_el_insumo_dice_que_contrato_lo_cubria(client, escenario):
    c = _contrato(client, escenario).json()
    _cubrir(client, c["id"], escenario["equipo"]["id"], fecha_alta=_dias(300))

    fila = _insumo(client, escenario, fecha_pedido=_dias(5))
    assert fila["contrato_numero"] == c["numero"]
    assert fila["cubierto_por_contrato"] is True


def test_un_contrato_de_service_NO_cubre_los_insumos(client, escenario):
    """🔑 Tener contrato y estar cubierto son dos cosas distintas. Con un solo
    campo "tiene contrato", la pantalla diría que el tóner está cubierto
    justo en el caso en que hay que discutir la factura."""
    c = _contrato(client, escenario, tipo="service", incluye_insumos=False,
                  incluye_service=True).json()
    _cubrir(client, c["id"], escenario["equipo"]["id"], fecha_alta=_dias(300))

    fila = _insumo(client, escenario, fecha_pedido=_dias(5))
    # El contrato aparece —hay que poder verlo— y la cobertura dice que no.
    assert fila["contrato_numero"] == c["numero"]
    assert fila["cubierto_por_contrato"] is False


def test_un_insumo_anterior_al_contrato_no_queda_cubierto(client, escenario):
    """La cobertura se resuelve **contra la fecha de la fila**, no contra hoy.
    Si se resolviera contra hoy, firmar un contrato hoy haría aparecer como
    cubiertos todos los tóners que se pagaron el año pasado."""
    c = _contrato(client, escenario, fecha_inicio=_dias(30)).json()
    _cubrir(client, c["id"], escenario["equipo"]["id"], fecha_alta=_dias(30))

    viejo = _insumo(client, escenario, fecha_pedido=_dias(200))
    nuevo = _insumo(client, escenario, fecha_pedido=_dias(5))

    assert viejo["contrato_numero"] is None
    assert viejo["cubierto_por_contrato"] is False
    # El control por el otro lado: el mismo equipo, con fecha adentro del
    # contrato, sí queda cubierto — así el None de arriba no puede ser "el
    # cruce no anda".
    assert nuevo["contrato_numero"] == c["numero"]


def test_un_contrato_vencido_no_cubre_aunque_la_linea_siga_abierta(client, escenario):
    """La línea de cobertura abierta y el contrato vencido es el estado normal
    de un contrato que se dejó morir: lo que manda es el contrato."""
    c = _contrato(client, escenario, fecha_inicio=_dias(400), fecha_fin=_dias(30)).json()
    _cubrir(client, c["id"], escenario["equipo"]["id"], fecha_alta=_dias(400))

    fila = _insumo(client, escenario, fecha_pedido=_dias(5))
    assert fila["contrato_numero"] is None

    # Control: dentro de la vigencia, el mismo contrato sí lo cubría.
    dentro = _insumo(client, escenario, fecha_pedido=_dias(100))
    assert dentro["contrato_numero"] == c["numero"]


def test_borrar_el_contrato_deja_los_insumos_sin_cobertura_pero_no_los_borra(client, escenario):
    c = _contrato(client, escenario).json()
    _cubrir(client, c["id"], escenario["equipo"]["id"], fecha_alta=_dias(300))
    fila = _insumo(client, escenario, fecha_pedido=_dias(5))
    assert fila["cubierto_por_contrato"] is True

    assert client.delete(f"/api/contratos-proveedor/{c['id']}").status_code == 204

    despues = client.get(f"/api/insumos/{fila['id']}").json()
    assert despues["contrato_numero"] is None
    assert despues["id"] == fila["id"]


def test_un_equipo_con_cobertura_cargada_no_se_borra(client, escenario):
    """La cobertura es historia del CONTRATO: borrarla con el equipo dejaría al
    contrato afirmando algo distinto de lo que pasó."""
    c = _contrato(client, escenario).json()
    _cubrir(client, c["id"], escenario["otro_equipo"]["id"])

    r = client.delete(f"/api/equipos/{escenario['otro_equipo']['id']}")
    assert r.status_code == 409, r.text
    assert "cobertura" in r.json()["detail"].lower()


def test_la_ficha_del_equipo_pregunta_quien_lo_cubre_hoy(client, escenario):
    """Lo consume la ficha para decir «cubierto por CPR-0001 hasta el 31-12».

    Sin cobertura devuelve **null con 200 y no un 404**: que una máquina no esté
    cubierta es una respuesta —de hecho es el estado de todo el parque hasta que
    se cargue el primer contrato—, no un error que la pantalla tenga que
    distinguir de un equipo inexistente.
    """
    sin = client.get(
        f"/api/contratos-proveedor/equipos/{escenario['equipo']['id']}/cobertura"
    )
    assert sin.status_code == 200, sin.text
    assert sin.json() is None

    c = _contrato(client, escenario, fecha_fin=_en(120)).json()
    _cubrir(client, c["id"], escenario["equipo"]["id"], fecha_alta=_dias(10))

    con = client.get(
        f"/api/contratos-proveedor/equipos/{escenario['equipo']['id']}/cobertura"
    ).json()
    assert con["numero"] == c["numero"]
    assert con["incluye_insumos"] is True
    # El control por el otro lado: la otra máquina del mismo cliente sigue sin
    # cubrir, así que el contrato no se le aplica a todo el parque.
    otra = client.get(
        f"/api/contratos-proveedor/equipos/{escenario['otro_equipo']['id']}/cobertura"
    )
    assert otra.json() is None


# ── El reporte ──────────────────────────────────────────────────────────────

def test_el_reporte_agrupa_por_equipo_y_pone_el_numero_en_el_encabezado(client, escenario):
    c = _contrato(client, escenario).json()
    _cubrir(client, c["id"], escenario["equipo"]["id"], fecha_alta=_dias(300))
    _insumo(client, escenario, fecha_pedido=_dias(60), fecha_entrega=_dias(58),
            fecha_colocacion=_dias(55), contador_copias=10000)
    _insumo(client, escenario, fecha_pedido=_dias(20), fecha_entrega=_dias(18),
            fecha_colocacion=_dias(15), contador_copias=17400)
    client.post("/api/insumos", json={
        "equipo_id": escenario["otro_equipo"]["id"],
        "insumo_item_id": escenario["negro"]["id"], "fecha_pedido": _dias(9),
    })

    vista = client.get(
        f"/api/reportes/insumos?desde={_dias(90)}&hasta={HOY.isoformat()}"
    ).json()
    assert vista["slug"] == "insumos"
    assert vista["cantidad_filas"] == 3
    # Dos máquinas, dos bloques: la cadena de contadores de una no se mezcla con
    # la de la otra, que es el punto de agrupar.
    assert len(vista["grupos"]) == 2
    etiquetas = [g["etiqueta"] for g in vista["grupos"]]
    assert any("4471" in e for e in etiquetas), etiquetas
    assert any("Laboratorio" in e for e in etiquetas), etiquetas


def test_el_reporte_muestra_el_rendimiento_y_la_demora_del_reclamo(client, escenario):
    _insumo(client, escenario, fecha_pedido=_dias(60), fecha_entrega=_dias(58),
            fecha_colocacion=_dias(55), contador_copias=10000)
    _insumo(client, escenario, fecha_pedido=_dias(20), fecha_entrega=_dias(18),
            fecha_colocacion=_dias(15), contador_copias=17400)
    _insumo(client, escenario, fecha_pedido=_dias(9))

    vista = client.get(
        f"/api/reportes/insumos?desde={_dias(90)}&hasta={HOY.isoformat()}"
    ).json()
    textos = [c["texto"] for g in vista["grupos"] for fila in g["filas"] for c in fila]
    assert "7400" in textos          # 17.400 − 10.000, lo que rindió el anterior
    assert "9 d" in textos           # lo que lleva esperando el pendiente
    # 🔑 Y **cuánto tardó lo que sí llegó**: 2 días entre el pedido y la
    # entrega. Sin esta mitad, un proveedor que entrega todo en veinte días
    # saldría con la columna vacía por el solo hecho de haber entregado, y el
    # reporte no serviría para discutir el cumplimiento.
    assert "2 d" in textos

    # Los totales son lo que se le lleva al proveedor: cuántos hay, cuántos
    # faltan y cuánto tarda en promedio.
    totales = [c["texto"] for c in vista["totales"]]
    assert "Total: 3" in totales
    assert "Pendientes: 1" in totales
    assert "2 d prom." in totales


def test_el_reporte_marca_el_contrato_que_no_cubre(client, escenario):
    c = _contrato(client, escenario, tipo="service", incluye_insumos=False).json()
    _cubrir(client, c["id"], escenario["equipo"]["id"], fecha_alta=_dias(300))
    _insumo(client, escenario, fecha_pedido=_dias(5))

    vista = client.get(
        f"/api/reportes/insumos?desde={_dias(90)}&hasta={HOY.isoformat()}"
    ).json()
    textos = [c["texto"] for g in vista["grupos"] for fila in g["filas"] for c in fila]
    assert f"{c['numero']} (no cubre)" in textos


def test_el_periodo_recorta_por_la_fecha_de_referencia_de_cada_fila(client, escenario):
    """El recorte usa la primera fecha que exista —pedido, entrega o
    colocación—, que es la misma con la que se mira el contrato. Una fila
    volcada de un cuaderno **sólo tiene colocación**, así que si el `WHERE`
    mirara nada más el pedido, esa fila no entraría en ningún período."""
    _insumo(client, escenario, fecha_colocacion=_dias(40), contador_copias=500)
    _insumo(client, escenario, fecha_pedido=_dias(200))

    dentro = client.get(
        f"/api/reportes/insumos?desde={_dias(60)}&hasta={HOY.isoformat()}"
    ).json()
    assert dentro["cantidad_filas"] == 1

    # El control: ampliando el rango entran las dos, así que el 1 de arriba es
    # el recorte y no una carga que falló.
    todo = client.get(
        f"/api/reportes/insumos?desde={_dias(300)}&hasta={HOY.isoformat()}"
    ).json()
    assert todo["cantidad_filas"] == 2


def test_el_reporte_se_baja_en_excel(client, escenario):
    _insumo(client, escenario, fecha_pedido=_dias(5))
    r = client.get(
        f"/api/reportes/insumos.xlsx?desde={_dias(90)}&hasta={HOY.isoformat()}"
    )
    assert r.status_code == 200, r.text
    # Un xlsx es un zip: los dos primeros bytes lo dicen. Sin esto, un 200 con
    # un HTML de error pasaría por bueno.
    assert r.content[:2] == b"PK"
    assert "insumos.xlsx" in r.headers["content-disposition"]
