"""Fase 2: el devengado de un contrato.

Hasta hoy el sistema sabía **cuánto** vale el alquiler de agosto pero nunca decía
que agosto se devengó. Estos tests fijan las cuatro decisiones que el humano tomó
el 2026-08-15 y las tres formas en que esto se puede romper sin que se note.

Lo que concentra el valor, en orden:

1. **La idempotencia.** Generar agosto dos veces no puede cobrar agosto dos
   veces. Es lo único acá que, si falla, le llega al cliente como un cobro de
   más.
2. **El prorrateo por días.** Un contrato que arranca el 20 cobra 12/31, y el
   divisor es el mes real y no 30 fijos.
3. **La aritmética de los meses cortos**, que es donde una fecha revienta una vez
   al año y en producción.
"""
import os
from datetime import date

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


def f(d: date) -> str:
    return d.isoformat()


@pytest.fixture
def cliente(client):
    return client.post("/api/clientes", json={"nombre": "Estudio Sur"}).json()


def _contrato(client, cliente, **extra):
    datos = {
        "tipo_contrato": "alquiler", "cliente_id": cliente["id"],
        "fecha_inicio": f(date(2026, 8, 1)), "estado": "activo", "importe": 31000,
        **extra,
    }
    r = client.post("/api/contratos", json=datos)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _generar(client, ancla: date, **extra):
    r = client.post("/api/cuotas/generar", json={"ancla": f(ancla), **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ── Lo básico: que devengue ────────────────────────────────────────────────

def test_genera_la_cuota_del_mes_con_el_precio_vigente(client, cliente):
    contrato = _contrato(client, cliente)

    salida = _generar(client, date(2026, 8, 15))

    assert len(salida["generadas"]) == 1
    cuota = salida["generadas"][0]
    assert cuota["contrato_id"] == contrato["id"]
    assert cuota["periodo_desde"] == "2026-08-01"
    assert cuota["periodo_hasta"] == "2026-08-31"
    assert cuota["tipo_cargo"] == "alquiler"
    assert cuota["importe_total"] == 31000
    assert cuota["estado"] == "pendiente"
    # ADELANTADO: se emite el primer día del período, no al terminarlo.
    assert cuota["fecha_emision"] == "2026-08-01"


def test_el_ancla_es_una_fecha_cualquiera_del_periodo(client, cliente):
    """El parámetro no es "el mes": es un día que cae adentro. El período lo
    define el contrato, no el calendario."""
    _contrato(client, cliente)

    for dia in (1, 15, 31):
        salida = client.get(
            "/api/cuotas/previsualizar", params={"ancla": f(date(2026, 8, dia))},
        ).json()
        assert len(salida["a_generar"]) == 1
        assert salida["a_generar"][0]["periodo_desde"] == "2026-08-01"


def test_el_importe_queda_congelado_aunque_el_precio_suba_despues(client, cliente):
    """La razón de ser de `contratos_precios`, verificada de punta a punta.

    Si esto fallara, rehacer en diciembre la liquidación de agosto daría el
    precio de diciembre — y el cliente recibiría un número que nunca se le
    cobró.
    """
    contrato = _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 10))["generadas"][0]

    client.post(f"/api/contratos/{contrato['id']}/precios", json={
        "importe": 99000, "vigencia_desde": f(date(2026, 9, 1)),
    })

    assert client.get(f"/api/cuotas/{cuota['id']}").json()["importe_total"] == 31000


# ── La idempotencia, que es lo único que le llega al cliente ────────────────

def test_generar_dos_veces_el_mismo_mes_no_cobra_dos_veces(client, cliente):
    _contrato(client, cliente)

    primera = _generar(client, date(2026, 8, 15))
    segunda = _generar(client, date(2026, 8, 15))

    assert len(primera["generadas"]) == 1
    assert segunda["generadas"] == []
    # No se esconde: la segunda vuelta dice que ya estaba, que es lo que contesta
    # "¿esto ya se emitió?".
    assert len(segunda["ya_generadas"]) == 1

    todas = client.get("/api/cuotas").json()
    assert len(todas) == 1


def test_generar_con_otro_dia_del_mismo_mes_tampoco_duplica(client, cliente):
    """La idempotencia es por PERÍODO, no por el día que se mandó.

    Sin esto, correrlo el 1 y volver a correrlo el 20 daría dos cuotas de agosto
    — y las dos serían "correctas" mirando cada una por separado.
    """
    _contrato(client, cliente)
    _generar(client, date(2026, 8, 1))

    assert _generar(client, date(2026, 8, 20))["generadas"] == []
    assert len(client.get("/api/cuotas").json()) == 1


def test_una_cuota_anulada_deja_volver_a_generar_el_periodo(client, cliente):
    """Anular tiene que destrabar el mes: si no, un error de carga lo bloquea
    para siempre y hay que arreglarlo a mano en la base."""
    _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]

    client.post(f"/api/cuotas/{cuota['id']}/anular", json={"motivo": "mal cargada"})

    salida = _generar(client, date(2026, 8, 15))
    assert len(salida["generadas"]) == 1
    # La anulada sigue estando, no se borró: el devengado no queda con agujeros.
    estados = sorted(c["estado"] for c in client.get("/api/cuotas").json())
    assert estados == ["anulada", "pendiente"]


def test_el_unico_de_la_base_tambien_lo_impide(client, cliente):
    """El control de que la idempotencia NO depende sólo del `if` de Python.

    `generar()` chequea antes de insertar, así que los tests de arriba pasarían
    igual sin el índice. Esto va contra la base directamente: dos cargos
    recurrentes del mismo período tienen que ser imposibles, aunque el camino de
    arriba se rompa.
    """
    from sqlalchemy.exc import IntegrityError

    from app.services.cuotas import ContratoCuota

    contrato = _contrato(client, cliente)
    _generar(client, date(2026, 8, 15))

    sessions = client.app.state.cuotas.session_factory
    with sessions() as session:
        session.add(ContratoCuota(
            contrato_id=contrato["id"],
            periodo_desde=date(2026, 8, 1), periodo_hasta=date(2026, 8, 31),
            concepto="Duplicada a mano", tipo_cargo="alquiler",
            fecha_emision=date(2026, 8, 1),
            importe_base=1, importe_total=1, bonificacion=0, impuestos=0,
            interes_mora=0, moneda="ARS", estado="pendiente",
        ))
        with pytest.raises(IntegrityError):
            session.commit()


def test_un_alquiler_y_un_proporcional_del_mismo_mes_tampoco_conviven(client, cliente):
    """El defecto que tenía el índice propuesto en el diseño del 2026-08-04.

    Con el único sobre `(contrato_id, tipo_cargo, periodo_desde)`, estas dos
    filas no chocaban —tienen distinto `tipo_cargo`— y son el mismo mes cobrado
    dos veces, una entera y otra a medias.
    """
    from sqlalchemy.exc import IntegrityError

    from app.services.cuotas import ContratoCuota

    contrato = _contrato(client, cliente)
    _generar(client, date(2026, 8, 15))  # deja el 'alquiler' de agosto

    sessions = client.app.state.cuotas.session_factory
    with sessions() as session:
        session.add(ContratoCuota(
            contrato_id=contrato["id"],
            periodo_desde=date(2026, 8, 1), periodo_hasta=date(2026, 8, 31),
            concepto="Proporcional del mismo mes", tipo_cargo="proporcional",
            fecha_emision=date(2026, 8, 1),
            importe_base=1, importe_total=1, bonificacion=0, impuestos=0,
            interes_mora=0, moneda="ARS", estado="pendiente",
        ))
        with pytest.raises(IntegrityError):
            session.commit()


def test_dos_reparaciones_en_el_mismo_mes_SI_conviven(client, cliente):
    """La otra mitad de por qué el índice es parcial.

    Un único sobre todos los cargos habría prohibido esto, que es legítimo y
    pasa seguido: dos reparaciones facturables en el mismo mes.
    """
    contrato = _contrato(client, cliente)

    for concepto in ("Cambio de fuente", "Cambio de placa"):
        r = client.post(f"/api/cuotas/contrato/{contrato['id']}/cargo", json={
            "tipo_cargo": "reparacion", "concepto": concepto,
            "importe": 8000, "fecha": f(date(2026, 8, 10)),
        })
        assert r.status_code == 201, r.text

    cargos = [c for c in client.get("/api/cuotas").json()
              if c["tipo_cargo"] == "reparacion"]
    assert len(cargos) == 2


def test_el_cargo_del_periodo_no_se_puede_cargar_a_mano(client, cliente):
    """Cargar un `alquiler` a mano dejaría dos cobros del mismo mes: uno hecho a
    mano y otro que va a generar la tanda. Se rechaza con un texto que dice qué
    hacer, no con un IntegrityError."""
    contrato = _contrato(client, cliente)

    r = client.post(f"/api/cuotas/contrato/{contrato['id']}/cargo", json={
        "tipo_cargo": "alquiler", "concepto": "A mano", "importe": 1000,
        "fecha": f(date(2026, 8, 10)),
    })
    assert r.status_code == 422
    assert "Generar cuotas" in r.json()["detail"]


# ── El prorrateo ───────────────────────────────────────────────────────────

def test_el_primer_mes_se_prorratea_por_dias(client, cliente):
    """Arranca el 20 de agosto: cobra del 20 al 31, o sea 12 de 31 días."""
    _contrato(client, cliente, fecha_inicio=f(date(2026, 8, 20)), importe=31000)

    cuota = _generar(client, date(2026, 8, 25))["generadas"][0]

    assert cuota["tipo_cargo"] == "proporcional"
    assert cuota["periodo_desde"] == "2026-08-20"
    assert cuota["periodo_hasta"] == "2026-08-31"
    # 31000 * 12 / 31 = 12000 exacto.
    assert cuota["importe_total"] == 12000
    # El período va en la descripción: es lo único que viaja al remito, porque el
    # PDF sólo imprime descripción y cantidad.
    assert "proporcional 20-08-2026 al 31-08-2026" in cuota["concepto"]


def test_el_ultimo_mes_tambien_se_prorratea(client, cliente):
    """La decisión del humano fue "las dos puntas". Un contrato que termina el 10
    cobra 10 de 31, no el mes entero."""
    _contrato(
        client, cliente,
        fecha_inicio=f(date(2026, 1, 1)), fecha_fin=f(date(2026, 8, 10)),
        importe=31000,
    )

    cuota = _generar(client, date(2026, 8, 5))["generadas"][0]

    assert cuota["tipo_cargo"] == "proporcional"
    assert cuota["periodo_hasta"] == "2026-08-10"
    assert cuota["importe_total"] == 10000  # 31000 * 10 / 31


def test_el_divisor_es_el_mes_real_y_no_30(client, cliente):
    """Febrero tiene 28 días y vale lo mismo que marzo, así que el día de
    febrero vale MÁS. Dividir siempre por 30 le cobraría de menos a febrero.

    Con 28000 y arranque el 15 de febrero de 2026: 14 de 28 días = la mitad
    exacta, 14000. Con divisor 30 daría 13066,67.
    """
    _contrato(
        client, cliente, fecha_inicio=f(date(2026, 2, 15)), importe=28000,
    )

    cuota = _generar(client, date(2026, 2, 20))["generadas"][0]
    assert cuota["importe_total"] == 14000


def test_un_mes_entero_no_se_marca_como_proporcional(client, cliente):
    """El control del prorrateo. Sin esto, un cálculo que marcara TODO como
    proporcional pasaría los dos tests de arriba."""
    _contrato(client, cliente, fecha_inicio=f(date(2026, 1, 1)))

    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]
    assert cuota["tipo_cargo"] == "alquiler"
    assert cuota["importe_total"] == 31000
    assert "proporcional" not in cuota["concepto"]


def test_la_previa_explica_por_que_un_mes_sale_menos(client, cliente):
    _contrato(client, cliente, fecha_inicio=f(date(2026, 8, 20)))

    fila = client.get(
        "/api/cuotas/previsualizar", params={"ancla": f(date(2026, 8, 25))},
    ).json()["a_generar"][0]

    assert fila["prorrateada"] is True
    assert fila["dias_cubiertos"] == 12
    assert fila["dias_del_periodo"] == 31


# ── Meses cortos y aritmética de fechas ────────────────────────────────────

def test_un_contrato_que_arranca_el_31_de_enero(client, cliente):
    """Enero le sale de un día, y febrero entero.

    Con períodos de calendario, un contrato que arranca el 31 cubre **un** día
    de enero —1/31 del importe— y desde febrero cobra el mes completo.
    """
    _contrato(client, cliente, fecha_inicio=f(date(2026, 1, 31)), importe=31000)

    enero = _generar(client, date(2026, 1, 15))["generadas"][0]
    assert enero["periodo_desde"] == "2026-01-31"
    assert enero["periodo_hasta"] == "2026-01-31"
    assert enero["tipo_cargo"] == "proporcional"
    assert enero["importe_total"] == 1000  # 31000 * 1 / 31

    febrero = _generar(client, date(2026, 2, 15))["generadas"][0]
    assert febrero["periodo_desde"] == "2026-02-01"
    assert febrero["periodo_hasta"] == "2026-02-28"
    assert febrero["tipo_cargo"] == "alquiler"
    assert febrero["importe_total"] == 31000


def test_el_paso_de_mes_no_revienta_en_los_meses_cortos(client, cliente):
    """`31 de enero + 1 mes` no existe. Sin el recorte al último día del mes
    destino, `_sumar_meses` es un `ValueError: day is out of range` que sale una
    vez al año y en producción.

    Se ejerce por el cierre del período: el 1 de febrero + 1 mes − 1 día, y un
    trimestral que cierra el 30 de abril.
    """
    _contrato(client, cliente, fecha_inicio=f(date(2026, 1, 1)))

    febrero = _generar(client, date(2026, 2, 10))["generadas"][0]
    assert febrero["periodo_hasta"] == "2026-02-28"


def test_el_vencimiento_se_recorta_al_ultimo_dia_del_mes(client, cliente):
    """Un contrato con vencimiento el 31 no puede vencer el 31 de febrero."""
    _contrato(
        client, cliente, fecha_inicio=f(date(2026, 1, 1)), dia_vencimiento=31,
    )

    cuota = _generar(client, date(2026, 2, 10))["generadas"][0]
    assert cuota["fecha_vencimiento"] == "2026-02-28"


def test_sin_dia_de_vencimiento_no_se_inventa_ninguno(client, cliente):
    _contrato(client, cliente)
    assert _generar(client, date(2026, 8, 15))["generadas"][0]["fecha_vencimiento"] is None


def test_un_trimestral_se_alinea_al_calendario_y_prorratea_el_primero(client, cliente):
    """🔴 El caso que destapó la premisa equivocada del primer intento.

    Los períodos se alinean al **año**, no al arranque del contrato: un
    trimestral devenga ene-mar, abr-jun, jul-sep, oct-dic. Uno que arranca el 1
    de febrero cubre 59 de los 90 días del primer trimestre, y desde abril cobra
    el trimestre entero.

    Anclarlos a `fecha_inicio` —que es lo que hacía el primer intento— habría
    dado feb-abr completo, o sea **sin prorratear nunca**, que contradice la
    decisión del humano.
    """
    _contrato(
        client, cliente, fecha_inicio=f(date(2026, 2, 1)),
        periodicidad="trimestral", importe=90000,
    )

    primero = _generar(client, date(2026, 3, 15))["generadas"][0]
    assert primero["periodo_desde"] == "2026-02-01"   # recortado por el contrato
    assert primero["periodo_hasta"] == "2026-03-31"   # fin del trimestre calendario
    assert primero["tipo_cargo"] == "proporcional"
    assert primero["importe_total"] == 59000          # 90000 * 59 / 90

    segundo = _generar(client, date(2026, 5, 15))["generadas"][0]
    assert segundo["periodo_desde"] == "2026-04-01"
    assert segundo["periodo_hasta"] == "2026-06-30"
    assert segundo["tipo_cargo"] == "alquiler"
    assert segundo["importe_total"] == 90000


# ── Qué contratos entran, y cuáles no ──────────────────────────────────────

def test_un_comodato_no_devenga(client, cliente):
    """Los tipos sin cuota se entregan sin cobrar por el equipo. Si devengaran,
    le llegaría una factura a alguien que no tiene que pagar nada."""
    _contrato(client, cliente, tipo_contrato="comodato", importe=None)

    assert _generar(client, date(2026, 8, 15))["generadas"] == []


def test_un_contrato_en_borrador_no_devenga(client, cliente):
    _contrato(client, cliente, estado="borrador")
    assert _generar(client, date(2026, 8, 15))["generadas"] == []


def test_un_contrato_que_todavia_no_arranco_no_devenga(client, cliente):
    _contrato(client, cliente, fecha_inicio=f(date(2026, 12, 1)))
    assert _generar(client, date(2026, 8, 15))["generadas"] == []


def test_un_contrato_ya_terminado_no_devenga(client, cliente):
    _contrato(
        client, cliente,
        fecha_inicio=f(date(2026, 1, 1)), fecha_fin=f(date(2026, 6, 30)),
    )
    assert _generar(client, date(2026, 8, 15))["generadas"] == []


def test_se_puede_devengar_un_contrato_solo(client, cliente):
    uno = _contrato(client, cliente)
    _contrato(client, cliente)

    salida = _generar(client, date(2026, 8, 15), contrato_id=uno["id"])

    assert len(salida["generadas"]) == 1
    assert salida["generadas"][0]["contrato_id"] == uno["id"]


# ── El abono de servicio, que es la decisión 1 del humano ──────────────────

def test_un_abono_sin_ningun_equipo_devenga_igual(client, cliente):
    """La brecha 11 de las de Lagrace: un abono de mantenimiento se cobra por
    atender, no por haber entregado algo. Hasta hoy no tenía dónde vivir."""
    contrato = _contrato(
        client, cliente, tipo_contrato="abono", importe=45000,
    )
    assert client.get(f"/api/contratos/{contrato['id']}").json()["equipos_vigentes"] == 0

    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]

    assert cuota["tipo_cargo"] == "mantenimiento"
    assert cuota["importe_total"] == 45000
    assert cuota["concepto"].startswith("Abono agosto 2026")


def test_el_abono_tambien_se_prorratea(client, cliente):
    _contrato(
        client, cliente, tipo_contrato="abono",
        fecha_inicio=f(date(2026, 8, 20)), importe=31000,
    )

    cuota = _generar(client, date(2026, 8, 25))["generadas"][0]
    assert cuota["tipo_cargo"] == "proporcional"
    assert cuota["importe_total"] == 12000


# ── La confirmación humana ─────────────────────────────────────────────────

def test_previsualizar_no_escribe_nada(client, cliente):
    """La mitad "confirmación humana" de la decisión del 2026-08-15. Si esto
    escribiera, el botón de mirar sería el botón de emitir."""
    _contrato(client, cliente)

    previa = client.get(
        "/api/cuotas/previsualizar", params={"ancla": f(date(2026, 8, 15))},
    ).json()
    assert len(previa["a_generar"]) == 1
    assert previa["total"] == 31000

    assert client.get("/api/cuotas").json() == []


def test_la_previa_y_lo_generado_dan_el_mismo_importe(client, cliente):
    """El cálculo es uno solo, compartido. Si fueran dos caminos, la pantalla
    podría mostrar un número y la base guardar otro — y nadie se enteraría hasta
    que un cliente reclamara la diferencia."""
    _contrato(client, cliente, fecha_inicio=f(date(2026, 8, 20)), importe=31000)

    previa = client.get(
        "/api/cuotas/previsualizar", params={"ancla": f(date(2026, 8, 25))},
    ).json()["a_generar"][0]
    generada = _generar(client, date(2026, 8, 25))["generadas"][0]

    assert previa["importe_total"] == generada["importe_total"]
    assert previa["periodo_desde"] == generada["periodo_desde"]
    assert previa["periodo_hasta"] == generada["periodo_hasta"]
    assert previa["concepto"] == generada["concepto"]


def test_la_previa_marca_lo_que_ya_estaba_emitido(client, cliente):
    """Se muestra en vez de esconderse: una pantalla que simplemente no lista un
    contrato ya emitido se lee como "este contrato no devenga"."""
    _contrato(client, cliente)
    _generar(client, date(2026, 8, 15))

    previa = client.get(
        "/api/cuotas/previsualizar", params={"ancla": f(date(2026, 8, 15))},
    ).json()

    assert previa["a_generar"] == []
    assert len(previa["ya_generadas"]) == 1
    assert previa["total"] == 0


# ── Anular ─────────────────────────────────────────────────────────────────

def test_no_se_puede_anular_una_cuota_cobrada(client, cliente):
    _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]

    sessions = client.app.state.cuotas.session_factory
    from app.services.cuotas import ContratoCuota
    with sessions() as session:
        session.get(ContratoCuota, cuota["id"]).estado = "cobrada"
        session.commit()

    r = client.post(f"/api/cuotas/{cuota['id']}/anular", json={})
    assert r.status_code == 422
    assert "cobrada" in r.json()["detail"]


def test_no_se_puede_anular_una_cuota_que_ya_salio_en_un_remito(client, cliente):
    """La guarda que protege a la pieza B: anular acá dejaría un comprobante
    entregado al cliente sin nada que lo respalde."""
    _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]

    sessions = client.app.state.cuotas.session_factory
    from app.services.cuotas import ContratoCuota
    with sessions() as session:
        session.get(ContratoCuota, cuota["id"]).remito_id = 77
        session.commit()

    r = client.post(f"/api/cuotas/{cuota['id']}/anular", json={})
    assert r.status_code == 422
    assert "remito" in r.json()["detail"]


# ── Pieza B: el remito a partir de una cuota ───────────────────────────────

def _remito_de(client, cuota_ids):
    return client.post("/api/cuotas/convertir-en-remito", json={"cuota_ids": cuota_ids})


def test_una_cuota_se_convierte_en_remito(client, cliente):
    """El destino de todo el devengado: el comprobante que sale hacia el
    cliente."""
    _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]

    r = _remito_de(client, [cuota["id"]])
    assert r.status_code == 201, r.text
    remito = r.json()

    assert len(remito["items"]) == 1
    # 🔑 El período viaja en la DESCRIPCIÓN: el PDF de un remito sólo imprime
    # descripción y cantidad, y `armar_payload` del puente manda los campos de
    # período en vacío. Si no está acá, no llega a ninguna parte.
    assert "Alquiler agosto 2026" in remito["items"][0]["description"]
    assert remito["items"][0]["unit_price"] == 31000
    assert remito["items"][0]["qty"] == 1


def test_la_cuota_queda_atada_al_remito(client, cliente):
    _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]

    remito = _remito_de(client, [cuota["id"]]).json()

    assert client.get(f"/api/cuotas/{cuota['id']}").json()["remito_id"] == remito["id"]


def test_varias_cuotas_del_mismo_cliente_van_en_UN_remito(client, cliente):
    """Un cliente con tres contratos recibe un remito por los tres: es una
    factura la que va a salir de ahí."""
    for _ in range(3):
        _contrato(client, cliente)
    cuotas = _generar(client, date(2026, 8, 15))["generadas"]
    assert len(cuotas) == 3

    remito = _remito_de(client, [c["id"] for c in cuotas]).json()

    assert len(remito["items"]) == 3
    assert sum(i["unit_price"] for i in remito["items"]) == 93000


def test_cuotas_de_dos_clientes_se_rechazan(client, cliente):
    """Un remito se emite a nombre de uno solo. El cliente sale del CONTRATO —
    la cuota no lo guarda."""
    otro = client.post("/api/clientes", json={"nombre": "Otro SRL"}).json()
    _contrato(client, cliente)
    _contrato(client, otro)
    cuotas = _generar(client, date(2026, 8, 15))["generadas"]

    r = _remito_de(client, [c["id"] for c in cuotas])
    assert r.status_code == 409
    assert "más de un cliente" in r.json()["detail"]


def test_convertir_dos_veces_devuelve_el_mismo_remito(client, cliente):
    """El doble click. Emitir un segundo remito por la misma cuota es cobrarla
    dos veces."""
    _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]

    primero = _remito_de(client, [cuota["id"]]).json()
    segundo = _remito_de(client, [cuota["id"]])

    assert segundo.status_code == 201
    assert segundo.json()["id"] == primero["id"]


def test_mezclar_una_ya_convertida_con_una_nueva_es_un_error(client, cliente):
    """🔴 No es idempotencia: devolver el remito viejo dejaría a la nueva sin
    facturar, y en silencio."""
    _contrato(client, cliente)
    _contrato(client, cliente)
    cuotas = _generar(client, date(2026, 8, 15))["generadas"]
    _remito_de(client, [cuotas[0]["id"]])

    r = _remito_de(client, [c["id"] for c in cuotas])
    assert r.status_code == 409
    assert "Ya salieron en un remito" in r.json()["detail"]

    # Y la que faltaba sigue sin remito: el error no dejó nada a medias.
    assert client.get(f"/api/cuotas/{cuotas[1]['id']}").json()["remito_id"] is None


def test_una_cuota_anulada_no_se_convierte(client, cliente):
    _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]
    client.post(f"/api/cuotas/{cuota['id']}/anular", json={})

    r = _remito_de(client, [cuota["id"]])
    assert r.status_code == 409
    assert "anulada" in r.json()["detail"]


def test_emitir_el_remito_NO_marca_la_cuota_como_facturada(client, cliente):
    """🔴 La factura la produce SOS Contador desde la bandeja, no este paso.

    Decir `facturada` acá sería afirmar algo que no pasó. Lo que dice que la
    cuota ya salió es `remito_id`, que es también lo que mira la guarda de
    anular.
    """
    _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]

    _remito_de(client, [cuota["id"]])

    ficha = client.get(f"/api/cuotas/{cuota['id']}").json()
    assert ficha["estado"] == "pendiente"
    assert ficha["remito_id"] is not None


def test_una_cuota_ya_remitada_no_se_puede_anular(client, cliente):
    """La guarda que escribió la fase 2, ahora ejercida por el camino real y no
    escribiendo `remito_id` a mano."""
    _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]
    _remito_de(client, [cuota["id"]])

    r = client.post(f"/api/cuotas/{cuota['id']}/anular", json={})
    assert r.status_code == 422
    assert "remito" in r.json()["detail"]


def test_el_remito_de_una_cuota_llega_a_la_bandeja_de_facturacion(client, cliente):
    """🔑 El punto de haberlo hecho como remito y no como un origen nuevo.

    `ORIGENES_ENVIABLES` es `(ORIGEN_REMITO,)`, así que esto tiene que aparecer
    en la bandeja **sin una línea nueva del lado del adaptador**. Si no
    apareciera, todo el diseño de la pieza B estaría mal.
    """
    _contrato(client, cliente)
    cuota = _generar(client, date(2026, 8, 15))["generadas"][0]
    remito = _remito_de(client, [cuota["id"]]).json()

    r = client.get("/api/facturacion/pendientes")
    assert r.status_code == 200, r.text
    # La bandeja devuelve `{configurado, destino, items}` y no una lista pelada.
    filas = {p["id"]: p for p in r.json()["items"] if p["origen_tipo"] == "remito"}

    assert remito["id"] in filas
    # El importe de la cuota llegó, y no en cero: un remito con total 0 la
    # bandeja se niega a mandarlo, así que un importe perdido en el camino se
    # vería justo acá.
    #
    # 🔑 **31.000 + 21 %.** El total del remito lleva IVA y el `importe_total` de
    # la cuota es NETO. No se le pasa `tax_rate` al ítem —un contrato no tiene
    # una línea de catálogo de la que sacarlo— así que rige el default de
    # LibraCore. Se afirma el número exacto a propósito: si algún día cambia ese
    # default, lo que cambia es cuánto se le cobra a un cliente por su alquiler,
    # y eso tiene que avisar.
    assert filas[remito["id"]]["total"] == 37510  # 31000 * 1.21


# El gate del módulo `alquileres` sobre esta bandeja se prueba en
# `test_modulos_y_planes.py`, junto a los otros dos routers del mismo módulo y
# con el arnés que ya distingue una ruta gateada del fallback de la SPA.
