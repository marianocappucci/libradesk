"""Actas de entrega y devolución — fase 3 del módulo de alquiler.

Lo que este archivo defiende, en orden de importancia:

1. **El acta documenta un hecho físico y no se puede contradecir con el
   sistema.** No se documenta la devolución de un equipo que el contrato tiene
   instalado, ni se entrega dos veces el mismo, ni entra un equipo de otro
   contrato.
2. **Lo que el acta cobra, se cobra.** Una devolución con faltantes emite su
   cuota de reposición en la misma transacción; sin eso `cargo_reposicion`
   sería un número que el sistema conoce y nunca factura.
3. **Anular libera, borrar no existe.** Y no se anula un acta cuyo cargo ya
   salió en un remito que el cliente tiene en la mano.
"""
import os
from datetime import date
from io import BytesIO

import pytest
from pypdf import PdfReader

INICIO = date(2026, 8, 1)
ENTREGA = date(2026, 8, 3)
DEVOLUCION = date(2026, 8, 20)


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
    """Un contrato de alquiler con dos equipos puestos — el caso de los
    lineamientos: una central y un teléfono IP en el mismo cliente."""
    cliente = client.post("/api/clientes", json={
        "nombre": "Estudio Contable Sur", "cuit": "30-71234567-9",
        "domicilio": "Belgrano 450, Suipacha",
    }).json()
    central = client.post("/api/activos", json={
        "tipo": "Central telefónica", "marca": "Yeastar", "modelo": "S20",
        "serial": "YS-A123", "codigo_interno": "PAT-0001",
        "valor_reposicion": 250000,
    }).json()
    telefono = client.post("/api/activos", json={
        "tipo": "Teléfono IP", "marca": "Grandstream", "modelo": "GXP1625",
        "serial": "GS-A123", "codigo_interno": "PAT-0002",
    }).json()

    contrato = client.post("/api/contratos", json={
        "tipo_contrato": "alquiler", "cliente_id": cliente["id"],
        "fecha_inicio": INICIO.isoformat(), "estado": "activo",
        "importe": 45000, "dia_vencimiento": 10,
        "domicilio_instalacion": "Belgrano 450, Suipacha",
    }).json()

    lineas = []
    for activo in (central, telefono):
        r = client.post(f"/api/contratos/{contrato['id']}/equipos", json={
            "activo_id": activo["id"],
            "fecha_instalacion": INICIO.isoformat(),
            "ubicacion": "Administración",
        })
        assert r.status_code == 201, r.text
        lineas.append(r.json()["id"])

    return {
        "cliente": cliente, "contrato": contrato,
        "central": central, "telefono": telefono,
        "linea_central": lineas[0], "linea_telefono": lineas[1],
    }


def _emitir(client, contrato_id, **body):
    body.setdefault("tipo", "entrega")
    body.setdefault("fecha", ENTREGA.isoformat())
    return client.post(f"/api/contratos/{contrato_id}/actas", json=body)


def _retirar(client, linea_id, **extra):
    body = {
        "fecha_retiro": DEVOLUCION.isoformat(),
        "motivo_retiro": "devolucion",
        **extra,
    }
    r = client.post(f"/api/contratos/equipos/{linea_id}/retirar", json=body)
    assert r.status_code == 200, r.text
    return r.json()


# ── La entrega ─────────────────────────────────────────────────────────────

def test_el_acta_numera_y_guarda_una_linea_por_equipo(client, escenario):
    """El estado físico y los accesorios son **de cada equipo**, no del acta.

    Es la corrección 1 al diseño del 2026-08-04, que los ponía en el
    encabezado: un acta que cubre dos equipos no puede contestar con un solo
    `estado_fisico` por los dos, y acá se ve — la central va con sus fuentes y
    el teléfono con las suyas.
    """
    r = _emitir(client, escenario["contrato"]["id"],
                entrega_nombre="Rubén Ferreyra", recibe_nombre="Marta Ojeda",
                lineas=[
                    {"contrato_equipo_id": escenario["linea_central"],
                     "estado_fisico": "Impecable, sin marcas",
                     "accesorios": "Fuente 12V, dos patch cord"},
                    {"contrato_equipo_id": escenario["linea_telefono"],
                     "estado_fisico": "Usado, raya en la base",
                     "accesorios": "Fuente, auricular, base"},
                ])
    assert r.status_code == 201, r.text
    acta = r.json()

    assert acta["numero"] == "ACT-00000001"
    assert acta["tipo"] == "entrega"
    assert acta["estado"] == "emitida"
    assert acta["equipos"] == 2
    assert acta["cargo_total"] == 0.0
    assert acta["cuota_id"] is None
    # Las aclaraciones son texto tipeado, no una firma: ver el docstring del
    # servicio y la revisión `0023`.
    assert (acta["entrega_nombre"], acta["recibe_nombre"]) == (
        "Rubén Ferreyra", "Marta Ojeda")

    por_serie = {le["activo_serial"]: le for le in acta["lineas"]}
    assert por_serie["YS-A123"]["accesorios"] == "Fuente 12V, dos patch cord"
    assert por_serie["GS-A123"]["estado_fisico"] == "Usado, raya en la base"
    # Resuelto para que la ficha no pida un endpoint por fila.
    assert "Yeastar" in por_serie["YS-A123"]["activo_descripcion"]

    listado = client.get(f"/api/contratos/{escenario['contrato']['id']}/actas").json()
    assert [a["numero"] for a in listado] == ["ACT-00000001"]


def test_las_dos_actas_comparten_la_numeracion(client, escenario):
    """Una serie para los dos tipos, con `tipo` como columna — mismo criterio
    que `contratos.tipo_contrato`."""
    primera = _emitir(client, escenario["contrato"]["id"], lineas=[
        {"contrato_equipo_id": escenario["linea_central"]},
    ]).json()
    _retirar(client, escenario["linea_telefono"])
    segunda = _emitir(
        client, escenario["contrato"]["id"], tipo="devolucion",
        fecha=DEVOLUCION.isoformat(),
        lineas=[{"contrato_equipo_id": escenario["linea_telefono"]}],
    ).json()

    assert (primera["numero"], segunda["numero"]) == (
        "ACT-00000001", "ACT-00000002")


def test_un_acta_sin_equipos_no_documenta_nada(client, escenario):
    r = _emitir(client, escenario["contrato"]["id"], lineas=[])
    assert r.status_code == 409
    assert "al menos uno" in r.json()["detail"]


def test_la_entrega_no_lleva_faltantes_ni_cargo(client, escenario):
    """El equipo sale de casa: no hay nada que falte ni a quién cobrarle.

    Aceptarlos dejaría actas que describen algo que no pasó, y el PDF de la
    entrega ni siquiera imprime esas secciones.
    """
    r = _emitir(client, escenario["contrato"]["id"], lineas=[
        {"contrato_equipo_id": escenario["linea_central"],
         "faltantes": "Falta el cargador", "cargo_reposicion": 15000},
    ])
    assert r.status_code == 409
    assert "acta de entrega no lleva" in r.json()["detail"]


def test_un_equipo_de_otro_contrato_no_entra_al_acta(client, escenario):
    otro = client.post("/api/contratos", json={
        "tipo_contrato": "comodato", "cliente_id": escenario["cliente"]["id"],
        "fecha_inicio": INICIO.isoformat(), "estado": "activo",
    }).json()
    r = _emitir(client, otro["id"], lineas=[
        {"contrato_equipo_id": escenario["linea_central"]},
    ])
    assert r.status_code == 409
    assert "no es de este contrato" in r.json()["detail"]


def test_el_mismo_equipo_no_se_entrega_dos_veces(client, escenario):
    """Y el error dice **cuál** acta lo documentó: sin el número, quien lo lee
    no sabe si buscar un papel que ya existe o si el sistema se equivocó."""
    _emitir(client, escenario["contrato"]["id"], lineas=[
        {"contrato_equipo_id": escenario["linea_central"]},
    ])
    r = _emitir(client, escenario["contrato"]["id"], lineas=[
        {"contrato_equipo_id": escenario["linea_central"]},
    ])
    assert r.status_code == 409
    assert "ACT-00000001" in r.json()["detail"]


def test_el_mismo_equipo_repetido_dentro_del_acta(client, escenario):
    r = _emitir(client, escenario["contrato"]["id"], lineas=[
        {"contrato_equipo_id": escenario["linea_central"]},
        {"contrato_equipo_id": escenario["linea_central"]},
    ])
    assert r.status_code == 409
    assert "repetido" in r.json()["detail"]


# ── La devolución ──────────────────────────────────────────────────────────

def test_no_se_documenta_la_devolucion_de_un_equipo_instalado(client, escenario):
    """La invariante que hace que el papel y el sistema no se contradigan.

    Sin esto se podía firmar la devolución de un equipo que el contrato sigue
    facturando como puesto — y el error manda a «Retirar equipo», que es lo que
    de verdad registra que volvió.
    """
    r = _emitir(client, escenario["contrato"]["id"], tipo="devolucion",
                fecha=DEVOLUCION.isoformat(),
                lineas=[{"contrato_equipo_id": escenario["linea_central"]}])
    assert r.status_code == 409
    assert "Retirar equipo" in r.json()["detail"]


def test_la_devolucion_con_faltantes_emite_su_cuota_de_reposicion(client, escenario):
    """Lo que el acta cobra, se cobra: el cargo no se queda en el papel.

    Una cuota `reposicion` por el acta entera —no una por equipo—, con el
    número del acta en el concepto para poder cruzarlas.
    """
    _retirar(client, escenario["linea_central"])
    _retirar(client, escenario["linea_telefono"])

    acta = _emitir(
        client, escenario["contrato"]["id"], tipo="devolucion",
        fecha=DEVOLUCION.isoformat(),
        lineas=[
            {"contrato_equipo_id": escenario["linea_central"],
             "estado_fisico": "Golpeada en el frente",
             "faltantes": "Sin fuente", "danios": "Frente rajado",
             "cargo_reposicion": 18000},
            {"contrato_equipo_id": escenario["linea_telefono"],
             "faltantes": "Sin auricular", "cargo_reposicion": 7500.50},
        ],
    ).json()

    assert acta["cargo_total"] == 25500.50
    assert acta["cuota_id"] is not None

    cuota = client.get(f"/api/cuotas/{acta['cuota_id']}").json()
    assert cuota["tipo_cargo"] == "reposicion"
    assert cuota["importe_total"] == 25500.50
    assert acta["numero"] in cuota["concepto"]
    # El vencimiento sale del `dia_vencimiento` del contrato, con la misma
    # aritmética que las cuotas del período: `vencimiento_de` es una sola.
    assert cuota["fecha_vencimiento"] == "2026-08-10"


def test_una_devolucion_sin_cargo_no_emite_cuota(client, escenario):
    """El equipo vuelve completo: no hay nada que facturar, y una cuota en cero
    ensuciaría el devengado con una línea que nadie va a cobrar."""
    _retirar(client, escenario["linea_central"])
    acta = _emitir(
        client, escenario["contrato"]["id"], tipo="devolucion",
        fecha=DEVOLUCION.isoformat(),
        lineas=[{"contrato_equipo_id": escenario["linea_central"],
                 "estado_fisico": "Impecable", "accesorios": "Todo completo"}],
    ).json()

    assert acta["cuota_id"] is None
    cuotas = client.get(
        f"/api/cuotas?contrato_id={escenario['contrato']['id']}").json()
    assert [c for c in cuotas if c["tipo_cargo"] == "reposicion"] == []


def test_el_cargo_negativo_se_rechaza(client, escenario):
    _retirar(client, escenario["linea_central"])
    r = _emitir(client, escenario["contrato"]["id"], tipo="devolucion",
                fecha=DEVOLUCION.isoformat(),
                lineas=[{"contrato_equipo_id": escenario["linea_central"],
                         "cargo_reposicion": -100}])
    assert r.status_code == 409
    assert "negativo" in r.json()["detail"]


# ── Anular ─────────────────────────────────────────────────────────────────

def test_anular_libera_la_colocacion(client, escenario):
    """Es lo que permite rehacer un acta que salió mal, y el motivo por el que
    la unicidad vive en Python y no en un índice: el estado que hay que excluir
    está en el encabezado y la clave, en la línea."""
    primera = _emitir(client, escenario["contrato"]["id"], lineas=[
        {"contrato_equipo_id": escenario["linea_central"]},
    ]).json()

    r = client.post(f"/api/contratos/actas/{primera['id']}/anular",
                    json={"motivo": "Se cargó el equipo equivocado"})
    assert r.status_code == 200, r.text
    assert r.json()["anulada"] is True
    assert "Se cargó el equipo equivocado" in r.json()["observaciones"]

    segunda = _emitir(client, escenario["contrato"]["id"], lineas=[
        {"contrato_equipo_id": escenario["linea_central"]},
    ])
    assert segunda.status_code == 201, segunda.text
    assert segunda.json()["numero"] == "ACT-00000002"


def test_anular_dos_veces_no(client, escenario):
    acta = _emitir(client, escenario["contrato"]["id"], lineas=[
        {"contrato_equipo_id": escenario["linea_central"]},
    ]).json()
    client.post(f"/api/contratos/actas/{acta['id']}/anular", json={})
    r = client.post(f"/api/contratos/actas/{acta['id']}/anular", json={})
    assert r.status_code == 409


def test_al_anular_el_acta_se_anula_su_cargo(client, escenario):
    """Si el acta deja de valer, el cargo que emitió tampoco: quedaría una
    cuota de reposición sin ningún papel que la respalde."""
    _retirar(client, escenario["linea_central"])
    acta = _emitir(
        client, escenario["contrato"]["id"], tipo="devolucion",
        fecha=DEVOLUCION.isoformat(),
        lineas=[{"contrato_equipo_id": escenario["linea_central"],
                 "cargo_reposicion": 18000}],
    ).json()

    client.post(f"/api/contratos/actas/{acta['id']}/anular", json={})

    cuota = client.get(f"/api/cuotas/{acta['cuota_id']}").json()
    assert cuota["estado"] == "anulada"
    assert acta["numero"] in cuota["observaciones"]


def test_no_se_anula_el_acta_si_su_cargo_ya_salio_en_un_remito(client, escenario):
    """Y **ninguna de las dos** queda tocada: el remito lo tiene el cliente en
    la mano, y anular acá lo dejaría sin respaldo.

    Se comprueba el estado de las dos después del rechazo, no sólo el código:
    un rollback a medias —el acta anulada y la cuota viva— pasaría igual
    mirando nada más el 409.
    """
    _retirar(client, escenario["linea_central"])
    acta = _emitir(
        client, escenario["contrato"]["id"], tipo="devolucion",
        fecha=DEVOLUCION.isoformat(),
        lineas=[{"contrato_equipo_id": escenario["linea_central"],
                 "cargo_reposicion": 18000}],
    ).json()

    r = client.post("/api/cuotas/convertir-en-remito",
                    json={"cuota_ids": [acta["cuota_id"]]})
    assert r.status_code == 201, r.text

    r = client.post(f"/api/contratos/actas/{acta['id']}/anular", json={})
    assert r.status_code == 409
    assert "remito" in r.json()["detail"]

    assert client.get(f"/api/contratos/actas/{acta['id']}").json()["estado"] == "emitida"
    assert client.get(f"/api/cuotas/{acta['cuota_id']}").json()["estado"] != "anulada"


# ── El PDF ─────────────────────────────────────────────────────────────────

def _texto_del_pdf(contenido: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)


def test_el_pdf_del_acta_sale_con_su_numero(client, escenario):
    acta = _emitir(client, escenario["contrato"]["id"],
                   entrega_nombre="Rubén Ferreyra", recibe_nombre="Marta Ojeda",
                   lineas=[{"contrato_equipo_id": escenario["linea_central"],
                            "accesorios": "Fuente 12V, dos patch cord"}]).json()

    r = client.get(f"/api/contratos/actas/{acta['id']}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert acta["numero"] in r.headers["content-disposition"]
    assert r.content[:4] == b"%PDF"

    texto = _texto_del_pdf(r.content)
    # Las dos aclaraciones y el contrato: es lo que hace que el papel sirva
    # cuando aparece un reclamo.
    for esperado in ("Rubén Ferreyra", "Marta Ojeda",
                     escenario["contrato"]["numero"], "Fuente 12V"):
        assert esperado in texto, f"falta {esperado!r} en el PDF"
    # La entrega no imprime las secciones de la devolución.
    assert "FALTANTES" not in texto.upper()


def test_el_pdf_de_un_acta_anulada_lo_dice(client, escenario):
    """El estado vive en la pantalla; el papel que queda sobre el escritorio
    tiene que saberlo solo."""
    acta = _emitir(client, escenario["contrato"]["id"], lineas=[
        {"contrato_equipo_id": escenario["linea_central"]},
    ]).json()
    client.post(f"/api/contratos/actas/{acta['id']}/anular", json={})

    texto = _texto_del_pdf(
        client.get(f"/api/contratos/actas/{acta['id']}/pdf").content)
    assert "ANULADA" in texto


def test_el_pdf_de_la_devolucion_imprime_los_cargos(client, escenario):
    _retirar(client, escenario["linea_central"])
    acta = _emitir(
        client, escenario["contrato"]["id"], tipo="devolucion",
        fecha=DEVOLUCION.isoformat(),
        lineas=[{"contrato_equipo_id": escenario["linea_central"],
                 "faltantes": "Sin fuente", "cargo_reposicion": 18000}],
    ).json()

    texto = _texto_del_pdf(
        client.get(f"/api/contratos/actas/{acta['id']}/pdf").content)
    assert "Sin fuente" in texto
    # Con los separadores de acá: 18.000,00 y no 18,000.00.
    assert "18.000,00" in texto


def test_el_pdf_de_un_acta_que_no_existe(client):
    assert client.get("/api/contratos/actas/9999/pdf").status_code == 404
