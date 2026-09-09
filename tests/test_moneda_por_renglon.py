"""Renglones en pesos y en dólares en el mismo comprobante (2026-09-09).

**El circuito que esto modela**, contado por Lagrace: se arma una
**pre-factura** donde conviven renglones al 10,5 y al 21 de IVA *y* renglones
en pesos y en dólares, y **la factura sale unificada en pesos**.

## Por qué los importes se afirman en pesos y no en dólares

Porque `unit_price` **sigue siendo el importe en pesos** después de convertir, y
ése es el diseño entero: los totales, el PDF, la cuenta corriente y el adaptador
de SOS leen ese campo y no se enteran de que existen los dólares. El de SOS
además no tendría dónde poner la moneda — su `PUT /venta` manda números pelados.

## Los dos tests que hay que mirar primero

`test_editar_no_reconvierte` y `test_convertir_conserva_la_cotizacion_congelada`.
Los dos custodian la **idempotencia** de `_normalizar_items`, que es lo más
fácil de romper acá: un ítem guardado vuelve con `moneda: USD` y su `unit_price`
**ya en pesos**, así que una segunda pasada ingenua lo multiplica por la
cotización otra vez — y el comprobante sale por mil veces su valor **sin que
nada falle**.
"""
import os
from datetime import date, timedelta

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


@pytest.fixture
def cliente(client):
    return client.post("/api/clientes", json={
        "nombre": "Metalmax Soluciones", "cuit": "30-71234567-9",
    }).json()


def crear_remito(client, cliente, items, cotizacion=None, **extra):
    cuerpo = {"client_id": cliente["id"], "items": items, **extra}
    if cotizacion is not None:
        cuerpo["cotizacion"] = cotizacion
    return client.post("/api/remitos", json=cuerpo)


# ── La conversión ───────────────────────────────────────────────────────────

def test_un_renglon_en_dolares_se_guarda_convertido_a_pesos(client, cliente):
    """**El test central.** Lo que queda guardado es el importe en pesos.

    Y al lado, lo que hace falta para volver a mostrarlo en dólares: el precio
    de origen y la cotización que se usó.
    """
    r = crear_remito(client, cliente, [
        {"description": "Central HIPATH", "qty": 2, "unit_price": 100.0, "moneda": "USD"},
    ], cotizacion=1450.5)
    assert r.status_code == 201, r.text

    item = r.json()["items"][0]
    assert item["unit_price"] == 145050.0
    assert item["subtotal"] == 290100.0
    assert item["moneda"] == "USD"
    assert item["unit_price_origen"] == 100.0
    assert item["cotizacion"] == 1450.5


def test_pesos_y_dolares_en_el_mismo_comprobante(client, cliente):
    """El «sistema híbrido» del pedido: se cargan ítems en las dos monedas y el
    total sale unificado en pesos."""
    r = crear_remito(client, cliente, [
        {"description": "Mano de obra", "qty": 3, "unit_price": 21100.0},
        {"description": "Central importada", "qty": 1, "unit_price": 100.0, "moneda": "USD"},
    ], cotizacion=1000.0)
    assert r.status_code == 201, r.text

    remito = r.json()
    assert remito["items"][0]["unit_price"] == 21100.0
    assert remito["items"][1]["unit_price"] == 100000.0
    # 63.300 + 100.000, en pesos
    assert remito["subtotal"] == pytest.approx(163300.0)


def test_dos_alicuotas_y_dos_monedas_a_la_vez(client, cliente):
    """El caso exacto que describieron: *"puedo poner items con IVA al 10,5 y
    otros con IVA al 21, puedo poner items en pesos e items en dólares"*.

    Las dos mitades son independientes y por eso se prueban juntas: el IVA se
    calcula sobre el importe **ya convertido**, no sobre el dólar.
    """
    r = crear_remito(client, cliente, [
        {"description": "Servicio al 10,5", "qty": 1, "unit_price": 1000.0,
         "tax_rate": 0.105},
        {"description": "Equipo al 21 en USD", "qty": 1, "unit_price": 10.0,
         "moneda": "USD", "tax_rate": 0.21},
    ], cotizacion=100.0)
    assert r.status_code == 201, r.text

    remito = r.json()
    assert remito["subtotal"] == pytest.approx(2000.0)          # 1000 + 1000
    # 105 del primero + 210 del segundo. Si el IVA se calculara sobre los 10
    # dólares en vez de sobre los 1000 pesos, darían 2,10.
    assert remito["tax_amount"] == pytest.approx(315.0)


def test_un_comprobante_solo_en_pesos_queda_como_antes(client, cliente):
    """🔑 Un renglón sin moneda **no escribe ninguna de las tres claves**.

    Misma convención que `detalle`. Es lo que hace que los comprobantes que ya
    existen y los que se emitan sin dólares queden idénticos a como eran antes
    de que la moneda existiera — nada que migrar y nada que cambie de forma.
    """
    r = crear_remito(client, cliente, [
        {"description": "Mano de obra", "qty": 1, "unit_price": 5000.0},
    ])
    assert r.status_code == 201, r.text

    item = r.json()["items"][0]
    assert "moneda" not in item
    assert "unit_price_origen" not in item
    assert "cotizacion" not in item


# ── Lo que tiene que fallar ─────────────────────────────────────────────────

def test_dolares_sin_cotizacion_es_422(client, cliente):
    """🔴 **Caer a `x1` sería el modo de falla más caro de todo esto.**

    Un renglón de USD 100 saldría facturado en $100 — una fracción de lo que
    vale— y el comprobante se emitiría sin que nada falle.
    """
    r = crear_remito(client, cliente, [
        {"description": "Central", "qty": 1, "unit_price": 100.0, "moneda": "USD"},
    ])
    assert r.status_code == 422, r.text
    assert "cotizacion" in r.text


def test_una_moneda_que_no_existe_es_422(client, cliente):
    """La lista es cerrada por el mismo motivo que la de alícuotas: lo que salga
    de acá termina en un comprobante fiscal."""
    r = crear_remito(client, cliente, [
        {"description": "Algo", "qty": 1, "unit_price": 100.0, "moneda": "EUR"},
    ], cotizacion=1000.0)
    assert r.status_code == 422, r.text
    assert "EUR" in r.text


# ── La idempotencia, que es lo que se rompe solo ────────────────────────────

def test_editar_no_reconvierte(client, cliente):
    """🔴 **Guardar de nuevo un comprobante NO puede volver a convertir.**

    El ítem guardado vuelve del servidor con `moneda: USD` y su `unit_price`
    **ya en pesos**. Una segunda pasada ingenua lo multiplica otra vez: de
    $145.050 pasaría a $210 millones, y el remito se guardaría contento.
    """
    r = crear_remito(client, cliente, [
        {"description": "Central", "qty": 1, "unit_price": 100.0, "moneda": "USD"},
    ], cotizacion=1450.5)
    remito = r.json()
    assert remito["items"][0]["unit_price"] == 145050.0

    # Se reenvía tal cual vino, que es lo que hace la pantalla al editar.
    r2 = client.put(f"/api/remitos/{remito['id']}", json={
        "client_id": cliente["id"],
        "items": remito["items"],
        "observations": "editado",
    })
    assert r2.status_code == 200, r2.text
    assert r2.json()["items"][0]["unit_price"] == 145050.0
    assert r2.json()["total"] == remito["total"]


def test_convertir_conserva_la_cotizacion_congelada(client, cliente):
    """🔑 **El presupuesto convertido en remito conserva SU tipo de cambio.**

    `convertir_a_remito()` le pasa los ítems guardados a `RemitoService.create`
    y **no le pasa ninguna cotización**. Si la conversión tomara "la de hoy", un
    presupuesto de agosto convertido en diciembre saldría a otro precio que el
    que el cliente aceptó.
    """
    p = client.post("/api/presupuestos", json={
        "client_id": cliente["id"],
        "items": [{"description": "Central", "qty": 1, "unit_price": 100.0,
                   "moneda": "USD"}],
        "cotizacion": 1000.0,
    })
    assert p.status_code == 201, p.text
    presupuesto = p.json()
    assert presupuesto["items"][0]["unit_price"] == 100000.0

    r = client.post(f"/api/presupuestos/{presupuesto['id']}/convertir-en-remito")
    assert r.status_code == 201, r.text

    # `convertir_presupuesto_a_remito` devuelve **el remito**, no un id.
    item = r.json()["items"][0]
    assert item["cotizacion"] == 1000.0
    assert item["unit_price"] == 100000.0
    assert item["unit_price_origen"] == 100.0


# ── Lo que sale impreso ─────────────────────────────────────────────────────

def test_el_pdf_muestra_de_donde_salio_el_importe(client, cliente):
    """*"Muestra los valores unificados en pesos con sus respectivos cálculos."*

    Los importes del papel son los pesos; lo que se agrega es de dónde salieron.
    Se lee el **texto extraído del PDF**, no el `Content-Type`: un test que
    mirara el status pasaría con la conversión ausente, que es el modo de falla
    que importa.
    """
    from io import BytesIO

    from pypdf import PdfReader

    remito = crear_remito(client, cliente, [
        {"description": "Central", "qty": 1, "unit_price": 100.0, "moneda": "USD"},
    ], cotizacion=1450.5).json()

    r = client.get(f"/api/remitos/{remito['id']}/pdf")
    assert r.status_code == 200, r.text
    texto = "\n".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages)

    assert "USD 100,00" in texto
    assert "1.450,50" in texto


def test_el_pdf_no_pisa_el_detalle_que_escribio_la_persona(client, cliente):
    """Se appendea, no se reemplaza. Y lo guardado no cambia: reimprimir dos
    veces no puede ir acumulando la conversión adentro del detalle."""
    from io import BytesIO

    from pypdf import PdfReader

    remito = crear_remito(client, cliente, [
        {"description": "Central", "qty": 1, "unit_price": 100.0, "moneda": "USD",
         "detalle": "Modelo HIPATH 1120"},
    ], cotizacion=1000.0).json()

    client.get(f"/api/remitos/{remito['id']}/pdf")
    r = client.get(f"/api/remitos/{remito['id']}/pdf")
    texto = "\n".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages)
    assert "Modelo HIPATH 1120" in texto
    assert texto.count("USD 100,00") == 1

    # Y lo GUARDADO quedó intacto.
    assert client.get(f"/api/remitos/{remito['id']}").json()[
        "items"][0]["detalle"] == "Modelo HIPATH 1120"


# ── La tabla de cotizaciones ────────────────────────────────────────────────

def test_cargar_dos_veces_el_mismo_dia_corrige_y_no_duplica(client):
    hoy = date.today().isoformat()
    client.put("/api/cotizaciones", json={"fecha": hoy, "valor": 1400.0})
    r = client.put("/api/cotizaciones", json={"fecha": hoy, "valor": 1455.75})
    assert r.status_code == 200, r.text
    assert r.json()["valor"] == 1455.75

    listado = client.get("/api/cotizaciones").json()
    assert len([c for c in listado if c["fecha"] == hoy]) == 1


def test_la_vigente_es_la_ultima_anterior_y_dice_de_que_dia_es(client):
    """🔴 **Devuelve la fecha, no sólo el número.**

    Si al 15 la última cargada es del 3, la pantalla tiene que poder decir
    *"cotización del 03-09"*. Contestar el número solo presentaría un tipo de
    cambio de doce días como si fuera el de hoy.
    """
    viejo = (date.today() - timedelta(days=12)).isoformat()
    client.put("/api/cotizaciones", json={"fecha": viejo, "valor": 1300.0})

    r = client.get("/api/cotizaciones/vigente")
    assert r.status_code == 200, r.text
    assert r.json()["valor"] == 1300.0
    assert r.json()["fecha"] == viejo


def test_sin_ninguna_cargada_la_vigente_es_null_y_no_uno(client):
    """No cae a 1: un dólar a un peso convertiría los renglones a su valor
    nominal y el comprobante saldría por una fracción de lo que vale."""
    r = client.get("/api/cotizaciones/vigente")
    assert r.status_code == 200, r.text
    assert r.json() is None


def test_una_cotizacion_futura_no_es_la_vigente_de_hoy(client):
    """`vigente_a` mira `fecha <= objetivo`. Cargar la de mañana —que pasa, se
    tipea mal la fecha— no puede cambiar lo que se factura hoy."""
    manana = (date.today() + timedelta(days=1)).isoformat()
    client.put("/api/cotizaciones", json={"fecha": manana, "valor": 9999.0})

    assert client.get("/api/cotizaciones/vigente").json() is None


def test_corregir_la_cotizacion_no_le_mueve_el_total_a_lo_ya_emitido(client, cliente):
    """🔑 **La razón de ser de congelarla por renglón.**

    Si el importe en pesos se derivara al leer, corregir el dólar de hoy —o
    reimprimir en diciembre— le cambiaría el total a un comprobante ya emitido.
    Es la misma regla que gobierna `contratos_precios`.
    """
    hoy = date.today().isoformat()
    client.put("/api/cotizaciones", json={"fecha": hoy, "valor": 1000.0})
    remito = crear_remito(client, cliente, [
        {"description": "Central", "qty": 1, "unit_price": 100.0, "moneda": "USD"},
    ], cotizacion=1000.0).json()

    client.put("/api/cotizaciones", json={"fecha": hoy, "valor": 2000.0})

    de_nuevo = client.get(f"/api/remitos/{remito['id']}").json()
    assert de_nuevo["items"][0]["unit_price"] == 100000.0
    assert de_nuevo["total"] == remito["total"]


def test_un_valor_no_positivo_es_422(client):
    r = client.put("/api/cotizaciones", json={
        "fecha": date.today().isoformat(), "valor": 0,
    })
    assert r.status_code == 422, r.text
