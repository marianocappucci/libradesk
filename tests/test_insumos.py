"""Insumos por equipo y referencias ajenas — fase 1 (2026-08-24).

El caso que hay que poder contestar, y que hasta hoy vivía en un cuaderno: el
cliente le alquila fotocopiadoras a un tercero, el tercero le provee los tóner,
y para pedir uno hay que darle **su** número de máquina.

Los tests siguen ese circuito y no el CRUD: qué número le paso, qué me deben,
cuándo se cambió y cuánto rindió.

⚠️ El gate del módulo **no** se prueba acá: vive en `test_modulos_y_planes.py`,
donde `/api/insumos` entró al diccionario `RUTAS` que recorren los cinco tests
de planes. Duplicarlo acá daría dos lugares que se pueden desincronizar.
"""
import os
from datetime import date, timedelta

import pytest


HOY = date.today()


def _dias(n: int) -> str:
    return (HOY - timedelta(days=n)).isoformat()


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
    """El hospital, su proveedor de fotocopiadoras, dos máquinas y dos tóner."""
    hospital = client.post("/api/clientes", json={
        "nombre": "Hospital Municipal Esteban Iribarne",
    }).json()
    junin = client.post("/api/proveedores", json={"nombre": "Sistemas Junín"}).json()

    laboratorio = client.post("/api/equipos", json={
        "cliente_id": hospital["id"], "tipo": "Fotocopiadora", "marca": "Kyocera",
        "modelo": "M2540", "sector": "Laboratorio", "proveedor_id": junin["id"],
    })
    assert laboratorio.status_code == 201, laboratorio.text
    admision = client.post("/api/equipos", json={
        "cliente_id": hospital["id"], "tipo": "Fotocopiadora", "marca": "Kyocera",
        "modelo": "M2540", "sector": "Admisión", "proveedor_id": junin["id"],
    }).json()

    negro = client.post("/api/consumibles", json={"nombre": "Tóner TK-1170 negro"})
    assert negro.status_code == 201, negro.text
    cyan = client.post("/api/consumibles", json={"nombre": "Tóner TK-5240 cyan"}).json()

    return {
        "cliente": hospital, "proveedor": junin,
        "equipo": laboratorio.json(), "otro_equipo": admision,
        "negro": negro.json(), "cyan": cyan,
    }


def _referencia(client, equipo_id: int, **payload):
    return client.post(f"/api/equipos/{equipo_id}/referencias", json=payload)


def _cargar(client, esc, **payload):
    """Un insumo, con los campos que este caso no distingue ya puestos."""
    cuerpo = {"equipo_id": esc["equipo"]["id"], "insumo_item_id": esc["negro"]["id"]}
    cuerpo.update(payload)
    return client.post("/api/insumos", json=cuerpo)


# ── El número con el que lo llama el proveedor ──────────────────────────────

def test_el_numero_interno_del_proveedor_viaja_con_el_equipo(client, escenario):
    """Es el dato que motiva todo: sin esto, pedir un tóner obliga a buscar el
    número en un papel."""
    r = _referencia(
        client, escenario["equipo"]["id"],
        etiqueta="N° interno", valor="4471",
        proveedor_id=escenario["proveedor"]["id"],
    )
    assert r.status_code == 201, r.text
    assert r.json()["proveedor_nombre"] == "Sistemas Junín"

    ficha = client.get(f"/api/equipos/{escenario['equipo']['id']}").json()
    assert [(x["etiqueta"], x["valor"]) for x in ficha["referencias"]] == [
        ("N° interno", "4471"),
    ]
    # Y el equipo dice de quién es, que es la otra mitad de la misma pregunta.
    assert ficha["proveedor_nombre"] == "Sistemas Junín"


def test_un_equipo_lleva_varios_identificadores_a_la_vez(client, escenario):
    """El del proveedor y el patrimonial del hospital son dos números distintos
    para la misma máquina. Es el caso que una columna `codigo_interno` no podía
    cubrir, y la razón por la que esto es una tabla."""
    _referencia(client, escenario["equipo"]["id"], etiqueta="N° interno",
                valor="4471", proveedor_id=escenario["proveedor"]["id"])
    _referencia(client, escenario["equipo"]["id"], etiqueta="Patrimonial",
                valor="INV-0092")

    ficha = client.get(f"/api/equipos/{escenario['equipo']['id']}").json()
    assert {x["valor"] for x in ficha["referencias"]} == {"4471", "INV-0092"}
    # El patrimonial no es de nadie más que del cliente.
    patrimonial = next(x for x in ficha["referencias"] if x["valor"] == "INV-0092")
    assert patrimonial["proveedor_id"] is None


def test_el_mismo_numero_del_mismo_proveedor_en_dos_equipos_se_rechaza(client, escenario):
    """Es como llega el tóner a la máquina equivocada. El 409 además dice **con
    cuál** chocó: sin eso el operador no sabe qué corregir."""
    _referencia(client, escenario["equipo"]["id"], etiqueta="N° interno",
                valor="4471", proveedor_id=escenario["proveedor"]["id"])

    r = _referencia(client, escenario["otro_equipo"]["id"], etiqueta="N° interno",
                    valor="4471", proveedor_id=escenario["proveedor"]["id"])
    assert r.status_code == 409, r.text
    assert str(escenario["equipo"]["id"]) in r.json()["detail"]


def test_dos_proveedores_pueden_usar_el_mismo_numero(client, escenario):
    """El control de la guarda de arriba: la unicidad es **por destinatario**.

    Sin este test, una constraint global sobre `valor` pasaría los mismos
    verdes, y el día que entre un segundo proveedor que numera desde 1 el alta
    se rechazaría sin motivo.
    """
    otro = client.post("/api/proveedores", json={"nombre": "Copias del Centro"}).json()
    _referencia(client, escenario["equipo"]["id"], etiqueta="N° interno",
                valor="4471", proveedor_id=escenario["proveedor"]["id"])

    r = _referencia(client, escenario["otro_equipo"]["id"], etiqueta="N° interno",
                    valor="4471", proveedor_id=otro["id"])
    assert r.status_code == 201, r.text


def test_el_patrimonial_es_unico_dentro_del_cliente_y_no_mas_alla(client, escenario):
    """Dos clientes numeran su inventario desde 1 sin que eso sea un error; el
    mismo cliente repitiendo un número sí lo es. Es la única regla que la base
    no puede sostener sola — ver `EquipoRepository._duplicado`."""
    _referencia(client, escenario["equipo"]["id"], etiqueta="Patrimonial", valor="1")

    choca = _referencia(client, escenario["otro_equipo"]["id"],
                        etiqueta="Patrimonial", valor="1")
    assert choca.status_code == 409, choca.text

    otro_cliente = client.post("/api/clientes", json={"nombre": "Clínica San Luis"}).json()
    equipo_ajeno = client.post("/api/equipos", json={
        "cliente_id": otro_cliente["id"], "tipo": "Impresora",
    }).json()
    convive = _referencia(client, equipo_ajeno["id"], etiqueta="Patrimonial", valor="1")
    assert convive.status_code == 201, convive.text


def test_editar_el_equipo_no_le_borra_el_dueno_tercero(client, escenario):
    """El `PUT` reemplaza el equipo entero, así que un formulario al que le
    falte el campo lo manda en `null` y **cada edición borra el dato**.

    No es hipotético: es exactamente lo que pasó con `garantia_vence`, que
    durante semanas se borraba al editar y sacaba al equipo del reporte de
    Garantías sin que nadie lo notara. Este test es la guarda para que no vuelva
    a pasar con el proveedor, que es de quién es la máquina.
    """
    equipo = escenario["equipo"]
    r = client.put(f"/api/equipos/{equipo['id']}", json={
        **{k: equipo[k] for k in (
            "cliente_id", "tipo", "marca", "modelo", "serial",
            "ubicacion_oficina", "sector", "deposito_id", "estado",
            "proveedor_id", "garantia_vence", "observaciones",
        )},
        "sector": "Guardia",
    })
    assert r.status_code == 200, r.text
    assert r.json()["proveedor_id"] == escenario["proveedor"]["id"]
    assert r.json()["proveedor_nombre"] == "Sistemas Junín"


def test_se_busca_el_equipo_por_el_numero_que_dicta_el_proveedor(client, escenario):
    """La pregunta del teléfono: *"es la 4471"*, ¿cuál es?"""
    _referencia(client, escenario["equipo"]["id"], etiqueta="N° interno",
                valor="4471", proveedor_id=escenario["proveedor"]["id"])

    encontrados = client.get("/api/equipos?referencia=4471").json()
    assert [e["id"] for e in encontrados] == [escenario["equipo"]["id"]]

    # El control: sin esto, un filtro roto que devuelve TODO también pasaría la
    # aserción de arriba cuando hay un solo equipo con referencia.
    assert client.get("/api/equipos?referencia=9999").json() == []
    assert len(client.get("/api/equipos").json()) > 1


def test_la_referencia_se_va_con_el_equipo(client, escenario):
    """Si sobreviviera, seguiría ocupando el `UNIQUE` y el número no se podría
    cargar en la máquina que lo reemplaza. El pragma de FKs está apagado, así
    que el CASCADE declarado no alcanza."""
    equipo = client.post("/api/equipos", json={
        "cliente_id": escenario["cliente"]["id"], "tipo": "Impresora",
    }).json()
    _referencia(client, equipo["id"], etiqueta="N° interno", valor="7788",
                proveedor_id=escenario["proveedor"]["id"])

    assert client.delete(f"/api/equipos/{equipo['id']}").status_code == 204

    reusa = _referencia(client, escenario["equipo"]["id"], etiqueta="N° interno",
                        valor="7788", proveedor_id=escenario["proveedor"]["id"])
    assert reusa.status_code == 201, reusa.text


# ── El ciclo del tóner ──────────────────────────────────────────────────────

def test_el_ciclo_completo_pedir_recibir_colocar(client, escenario):
    pedido = _cargar(client, escenario, fecha_pedido=_dias(5))
    assert pedido.status_code == 201, pedido.text
    fila = pedido.json()[0]
    assert fila["estado"] == "pendiente"
    assert fila["dias_esperando"] == 5
    # Se hereda del equipo: nadie vuelve a escribir a quién se le pide.
    assert fila["proveedor_nombre"] == "Sistemas Junín"
    # Y el nombre queda copiado, no referenciado.
    assert fila["insumo_nombre"] == "Tóner TK-1170 negro"

    entrega = client.post(f"/api/insumos/{fila['id']}/entrega", json={
        "fecha_entrega": _dias(3), "remito_proveedor": "R-8891",
    })
    assert entrega.status_code == 200, entrega.text
    assert entrega.json()["estado"] == "en_poder"
    # Ya no se está esperando: el contador de demora deja de tener sentido.
    assert entrega.json()["dias_esperando"] is None

    colocacion = client.post(f"/api/insumos/{fila['id']}/colocacion", json={
        "fecha_colocacion": _dias(1), "contador_copias": 48200,
    })
    assert colocacion.status_code == 200, colocacion.text
    assert colocacion.json()["estado"] == "colocado"
    assert colocacion.json()["contador_copias"] == 48200


def test_la_bandeja_de_pendientes_es_lo_que_hay_que_reclamar(client, escenario):
    """`estado=pendiente` es la pantalla entera: lo pedido que no llegó."""
    pendiente = _cargar(client, escenario, fecha_pedido=_dias(9)).json()[0]
    entregado = _cargar(client, escenario, fecha_pedido=_dias(9),
                        fecha_entrega=_dias(2)).json()[0]

    ids = [i["id"] for i in client.get("/api/insumos?estado=pendiente").json()]
    assert ids == [pendiente["id"]]
    # El control por el otro lado: el entregado existe y sale sin filtro, así
    # que el vacío de arriba no puede ser "no se cargó nada".
    assert entregado["id"] in [i["id"] for i in client.get("/api/insumos").json()]


def test_un_cambio_ya_hecho_se_registra_sin_inventar_un_pedido(client, escenario):
    """La primera carga vuelca un cuaderno: hay fecha de colocación y nunca
    hubo pedido. Obligar a completar los tres momentos empujaría a cargar datos
    falsos."""
    r = _cargar(client, escenario, fecha_colocacion=_dias(40), contador_copias=12000)
    assert r.status_code == 201, r.text
    assert r.json()[0]["estado"] == "colocado"
    assert r.json()[0]["fecha_pedido"] is None


def test_dos_unidades_son_dos_filas(client, escenario):
    """Con una fila de cantidad 2 no se podría colocar una hoy y la otra en dos
    meses, que es exactamente lo que pasa."""
    r = _cargar(client, escenario, cantidad=2, fecha_pedido=_dias(2))
    assert r.status_code == 201, r.text
    assert len({f["id"] for f in r.json()}) == 2
    assert len(client.get("/api/insumos?estado=pendiente").json()) == 2


def test_una_fila_sin_ninguna_fecha_no_se_guarda(client, escenario):
    r = _cargar(client, escenario)
    assert r.status_code == 409, r.text


def test_las_fechas_no_pueden_ir_al_reves(client, escenario):
    r = _cargar(client, escenario, fecha_pedido=_dias(2), fecha_entrega=_dias(9))
    assert r.status_code == 409, r.text

    fila = _cargar(client, escenario, fecha_pedido=_dias(9),
                   fecha_entrega=_dias(5)).json()[0]
    tarde = client.post(f"/api/insumos/{fila['id']}/colocacion", json={
        "fecha_colocacion": _dias(7),
    })
    assert tarde.status_code == 409, tarde.text


def test_el_contador_sin_colocacion_se_rechaza(client, escenario):
    """Una lectura de display sin la máquina cargada no significa nada, y
    ensuciaría el cálculo de rendimiento del tramo siguiente."""
    r = _cargar(client, escenario, fecha_entrega=_dias(2), contador_copias=1000)
    assert r.status_code == 409, r.text


def test_un_insumo_que_no_esta_en_el_catalogo_no_se_carga(client, escenario):
    r = _cargar(client, escenario, insumo_item_id=99999, fecha_pedido=_dias(1))
    assert r.status_code == 404, r.text


def test_el_nombre_del_insumo_no_se_reescribe_al_renombrar_el_catalogo(client, escenario):
    """Mismo criterio que los materiales de un ticket: renombrar un producto no
    puede cambiar lo que dice un cambio de tóner de marzo."""
    fila = _cargar(client, escenario, fecha_colocacion=_dias(30),
                   contador_copias=100).json()[0]

    editado = client.put(f"/api/consumibles/{escenario['negro']['id']}", json={
        "nombre": "Tóner TK-1170 negro (genérico)",
    })
    assert editado.status_code == 200, editado.text

    assert client.get(f"/api/insumos/{fila['id']}").json()["insumo_nombre"] == (
        "Tóner TK-1170 negro"
    )


# ── El contador, que es lo que convierte el registro en control ─────────────

def test_el_rendimiento_sale_de_la_diferencia_entre_dos_colocaciones(client, escenario):
    """La pregunta que ninguna fila suelta contesta: cuánto duró el anterior."""
    _cargar(client, escenario, fecha_colocacion=_dias(60), contador_copias=10000)
    segundo = _cargar(client, escenario, fecha_colocacion=_dias(10),
                      contador_copias=17400).json()[0]

    assert segundo["copias_desde_el_anterior"] == 7400
    # El primero no tiene contra qué medirse, y eso no es cero.
    primero = client.get("/api/insumos?estado=colocado").json()[-1]
    assert primero["copias_desde_el_anterior"] is None


def test_un_contador_que_retrocede_no_inventa_un_rendimiento_negativo(client, escenario):
    """Pasa en uso normal —le cambian la placa a la máquina y vuelve a cero—,
    así que no se rechaza. Un negativo promediaría mal; el vacío dice la
    verdad."""
    _cargar(client, escenario, fecha_colocacion=_dias(60), contador_copias=98000)
    despues = _cargar(client, escenario, fecha_colocacion=_dias(10),
                      contador_copias=120).json()[0]

    assert despues["copias_desde_el_anterior"] is None


def _rendimiento(client, ruta: str) -> dict[int, int | None]:
    """`{id: copias_desde_el_anterior}` **leído del listado**.

    🔴 Y no de la respuesta del alta, que es como estaban escritos los dos tests
    de abajo y por eso no medían nada: el alta resuelve UNA fila, así que el
    `IN` de `_copias_previas` ya viene filtrado por ese equipo y ese insumo, y
    las cadenas quedan separadas aunque el agrupamiento esté roto. Se descubrió
    mutando el agrupamiento —los dos siguieron en verde—. En el listado, que es
    donde las cadenas conviven, la mutación sí sale.
    """
    return {i["id"]: i["copias_desde_el_anterior"] for i in client.get(ruta).json()}


def test_una_maquina_color_no_mezcla_las_cadenas_de_dos_toner(client, escenario):
    """El negro y el cyan son dos items del catálogo, o sea dos cadenas: el
    rendimiento de un cyan se mide contra el cyan anterior, no contra el negro
    que se puso en el medio. Sin esta separación, una color daría números que
    no significan nada."""
    _cargar(client, escenario, fecha_colocacion=_dias(90), contador_copias=5000)
    _cargar(client, escenario, insumo_item_id=escenario["cyan"]["id"],
            fecha_colocacion=_dias(60), contador_copias=6000)
    negro = _cargar(client, escenario, fecha_colocacion=_dias(30),
                    contador_copias=12000).json()[0]
    cyan = _cargar(client, escenario, insumo_item_id=escenario["cyan"]["id"],
                   fecha_colocacion=_dias(5), contador_copias=15000).json()[0]

    rinde = _rendimiento(client, f"/api/insumos?equipo_id={escenario['equipo']['id']}")
    assert rinde[negro["id"]] == 7000   # 12000 − 5000, no − 6000
    assert rinde[cyan["id"]] == 9000    # 15000 − 6000, no − 12000


def test_dos_equipos_no_se_miden_uno_contra_el_otro(client, escenario):
    """El par (equipo, insumo) define la cadena. Con dos máquinas del mismo
    modelo —que es lo normal en un parque— medir sólo por insumo daría el
    rendimiento cruzado de dos contadores que no tienen nada que ver.

    🔑 **El contador de la segunda máquina es MAYOR que el de la primera**, y es
    lo que hace que el test mida. Con uno menor, cruzar las cadenas daría
    `None` igual —por el guard del contador que retrocede— y la aserción se
    cumpliría por la razón equivocada: se comprobó mutando el agrupamiento.
    """
    _cargar(client, escenario, fecha_colocacion=_dias(50), contador_copias=80000)
    otro = client.post("/api/insumos", json={
        "equipo_id": escenario["otro_equipo"]["id"],
        "insumo_item_id": escenario["negro"]["id"],
        "fecha_colocacion": _dias(20), "contador_copias": 95000,
    }).json()[0]

    # Sin filtro: las dos máquinas en la misma lista, que es donde se cruzarían.
    assert _rendimiento(client, "/api/insumos")[otro["id"]] is None


# ── El historial es del equipo ──────────────────────────────────────────────

def test_los_insumos_de_un_equipo_se_filtran_por_equipo(client, escenario):
    _cargar(client, escenario, fecha_pedido=_dias(3))
    client.post("/api/insumos", json={
        "equipo_id": escenario["otro_equipo"]["id"],
        "insumo_item_id": escenario["negro"]["id"], "fecha_pedido": _dias(3),
    })

    del_equipo = client.get(
        f"/api/insumos?equipo_id={escenario['equipo']['id']}"
    ).json()
    assert len(del_equipo) == 1
    assert del_equipo[0]["equipo_id"] == escenario["equipo"]["id"]
    # Control: los dos existen, así que el 1 de arriba es un filtro y no una
    # carga que falló.
    assert len(client.get("/api/insumos").json()) == 2


def test_un_equipo_con_insumos_cargados_no_se_borra(client, escenario):
    """Cada fila dice que un proveedor entregó algo un día, con su remito: es un
    papel, igual que un comprobante de ingreso. Para sacar la máquina de
    circulación está el estado `baja`."""
    _cargar(client, escenario, fecha_entrega=_dias(1), remito_proveedor="R-1")

    r = client.delete(f"/api/equipos/{escenario['equipo']['id']}")
    assert r.status_code == 409, r.text
    assert "insumos" in r.json()["detail"]


def test_borrar_un_insumo_mal_cargado_lo_saca_de_la_cuenta(client, escenario):
    fila = _cargar(client, escenario, fecha_pedido=_dias(1)).json()[0]
    assert client.delete(f"/api/insumos/{fila['id']}").status_code == 204
    assert client.get("/api/insumos").json() == []
    assert client.get(f"/api/insumos/{fila['id']}").status_code == 404
