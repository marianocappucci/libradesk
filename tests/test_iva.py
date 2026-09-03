"""IVA por ítem y condición del receptor — ítem 2 de los pendientes de Libra.

> *"El iva se tiene que calcular segun el tipo de condicion de iva que tenga el
> cliente."*

El pedido decía "como en Contalibra" y eso no describía lo que Contalibra hace.
Se resolvió con el humano el 2026-08-05: **la alícuota es del servicio**, y de
la condición del receptor depende el tipo de comprobante y si el IVA se
discrimina. Como LibraDesk no factura, sobre este producto aplica sólo lo
segundo. El razonamiento completo está en `app/services/iva.py`.

Lo que fijan estos tests, en orden de lo que se rompe sin que se note:

1. 🔴 **Que un comprobante con alícuotas mezcladas sume bien.** Es el caso que
   motivó el pedido y el único que el cálculo viejo (`subtotal * tax_rate`)
   daba mal. Un presupuesto con una línea exenta cobraba IVA sobre ella.
2. 🔴 **Que la alícuota guardada en el comprobante sea la efectiva, no la que
   vino del formulario.** Si mezclan no hay una sola que lo describa, y guardar
   la del formulario hace que el listado muestre "21%" sobre un documento que
   tiene líneas al 0%.
3. 🔴 **Que un comprobante viejo, sin alícuota por línea, siga dando el mismo
   total.** Los que ya están guardados se editan, y el payload manda la clave
   `tax_rate` **presente y en `None`** — no ausente.
4. Que la lista de alícuotas sea cerrada: un 13% cargado a mano se declararía
   como 21% ante ARCA sin ningún aviso (ver `libracore.arca_wsfe._iva_id`).
5. Que un Monotributista **no** discrimine. Es el error más común del tema.
"""
import pytest
from fastapi.testclient import TestClient

from app.services import iva

# --- Las reglas puras, sin HTTP ----------------------------------------------

def test_las_cuatro_alicuotas_de_arca_son_validas():
    for rate in (0, 0.105, 0.21, 0.27):
        assert float(iva.validar(rate)) == pytest.approx(rate)


def test_una_alicuota_inventada_no_pasa_y_el_error_dice_cuales_valen():
    """El 13% es el caso real: `libracore.arca_wsfe._iva_id()` cae al 21% ante
    un porcentaje que no conoce, así que sin esta validación se declararía como
    21% en silencio."""
    with pytest.raises(iva.AlicuotaInvalida) as e:
        iva.validar(0.13)
    # Los porcentajes se leen como los escribiria una persona: "10.5%", no
    # "10.500%" — que es lo que sale al formatear el `Decimal` directo.
    assert "13%" in str(e.value)
    assert "10.5%" in str(e.value) and "21%" in str(e.value)


def test_solo_el_responsable_inscripto_discrimina():
    assert iva.discrimina("Responsable Inscripto") is True
    # 🔴 El Monotributista tiene CUIT pero NO computa crédito fiscal.
    assert iva.discrimina("Monotributista") is False
    assert iva.discrimina("Consumidor Final") is False


def test_una_condicion_vacia_o_desconocida_cae_a_precio_final():
    """Los clientes que ya existen no la tienen cargada: el default no puede
    cambiarles el comprobante de golpe."""
    assert iva.discrimina(None) is False
    assert iva.discrimina("") is False
    assert iva.discrimina("Sujeto Exterior") is False


def test_el_iva_se_calcula_por_linea_y_no_sobre_el_subtotal():
    """El caso que el cálculo viejo daba mal: una línea al 21% y otra exenta.

    Viejo: (10000 + 5000) * 0.21 = 3150 — le cobraba IVA a lo exento.
    """
    items = [
        {"qty": 1, "unit_price": 10000, "tax_rate": 0.21},
        {"qty": 1, "unit_price": 5000, "tax_rate": 0},
    ]
    subtotal, impuesto, total = iva.totales(items)
    assert subtotal == 15000
    assert impuesto == 2100
    assert total == 17100


def test_el_redondeo_es_por_linea_para_que_el_total_cierre_con_la_columna():
    """Tres líneas cuyo IVA individual redondea hacia arriba.

    33.33 * 0.21 = 6.9993 → 7.00 por línea, 21.00 en total. Redondeando al
    final darían 20.99 y la caja de totales no coincidiría con la suma de los
    importes que el cliente ve.
    """
    items = [{"qty": 1, "unit_price": 33.33, "tax_rate": 0.21}] * 3
    _, impuesto, _ = iva.totales(items)
    assert impuesto == 21.00


def test_la_alicuota_del_documento_es_la_comun_cuando_no_mezclan():
    items = [{"qty": 1, "unit_price": 100, "tax_rate": 0.105}] * 2
    assert iva.alicuota_del_documento(items) == 0.105


def test_la_alicuota_del_documento_es_cero_cuando_mezclan():
    """Cualquier otra sería falsa para parte del comprobante."""
    items = [
        {"qty": 1, "unit_price": 100, "tax_rate": 0.21},
        {"qty": 1, "unit_price": 100, "tax_rate": 0},
    ]
    assert iva.alicuota_del_documento(items) == 0.0


# --- El recorrido completo, por HTTP -----------------------------------------

@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin."""
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return client


def _cliente(client, **extra):
    r = client.post("/api/clientes", json={"nombre": "Compulibra", **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _presupuesto(client, items, **extra):
    cliente = _cliente(client)
    r = client.post("/api/presupuestos", json={
        "client_id": cliente["id"], "items": items, **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_un_presupuesto_con_alicuotas_mezcladas_suma_bien(client):
    """El caso del pedido, de punta a punta."""
    p = _presupuesto(client, [
        {"description": "Soporte mensual", "qty": 1, "unit_price": 10000, "tax_rate": 0.21},
        {"description": "Libro de instructivos", "qty": 1, "unit_price": 5000, "tax_rate": 0},
    ])
    assert p["subtotal"] == 15000
    assert p["tax_amount"] == 2100
    assert p["total"] == 17100


def test_un_presupuesto_con_alicuotas_mezcladas_guarda_tax_rate_en_cero(client):
    """La columna del comprobante no puede mentir sobre parte de sus líneas."""
    p = _presupuesto(client, [
        {"description": "A", "qty": 1, "unit_price": 100, "tax_rate": 0.21},
        {"description": "B", "qty": 1, "unit_price": 100, "tax_rate": 0},
    ])
    assert p["tax_rate"] == 0.0


def test_un_presupuesto_de_una_sola_alicuota_la_guarda(client):
    p = _presupuesto(client, [
        {"description": "A", "qty": 1, "unit_price": 100, "tax_rate": 0.105},
        {"description": "B", "qty": 2, "unit_price": 50, "tax_rate": 0.105},
    ])
    assert p["tax_rate"] == 0.105
    assert p["tax_amount"] == 21.0


def test_un_presupuesto_sin_alicuota_por_linea_usa_la_del_documento(client):
    """🔴 Un comprobante guardado antes de este cambio, al editarse, manda la
    clave `tax_rate` **presente y en `None`** — no ausente. Con un
    `item.get("tax_rate", defecto)` el default nunca se aplicaría y el IVA
    daría 0."""
    p = _presupuesto(
        client,
        [{"description": "Soporte", "qty": 1, "unit_price": 10000}],
        tax_rate=0.21,
    )
    assert p["tax_amount"] == 2100
    assert p["tax_rate"] == 0.21


def test_cada_item_guarda_su_alicuota_para_que_el_pdf_la_muestre(client):
    """El PDF de LibraCore v1.12.0 decide el rótulo mirando las líneas, no la
    columna del documento: si el ítem no la lleva, la columna "IVA" del PDF
    sale en 0 para todo."""
    p = _presupuesto(client, [
        {"description": "A", "qty": 1, "unit_price": 100, "tax_rate": 0.21},
        {"description": "B", "qty": 1, "unit_price": 100, "tax_rate": 0},
    ])
    assert [i["iva_pct"] for i in p["items"]] == [21.0, 0.0]


def test_un_remito_con_alicuotas_mezcladas_suma_igual_que_un_presupuesto(client):
    """Los dos comprobantes comparten el cálculo; si uno se actualizara y el
    otro no, la diferencia aparecería recién al comparar dos documentos."""
    cliente = _cliente(client)
    r = client.post("/api/remitos", json={"client_id": cliente["id"], "items": [
        {"description": "A", "qty": 1, "unit_price": 10000, "tax_rate": 0.21},
        {"description": "B", "qty": 1, "unit_price": 5000, "tax_rate": 0},
    ]})
    assert r.status_code == 201, r.text
    assert r.json()["tax_amount"] == 2100


# --- El catálogo y el cliente ------------------------------------------------

def test_un_servicio_nuevo_arranca_al_21(client):
    r = client.post("/api/servicios", json={"nombre": "Soporte", "precio": 1000})
    assert r.status_code == 201, r.text
    assert r.json()["iva_rate"] == 0.21


def test_un_servicio_puede_ser_exento(client):
    r = client.post("/api/servicios", json={
        "nombre": "Capacitación", "precio": 1000, "iva_rate": 0,
    })
    assert r.status_code == 201, r.text
    assert r.json()["iva_rate"] == 0


def test_el_catalogo_rechaza_una_alicuota_inventada(client):
    r = client.post("/api/servicios", json={
        "nombre": "Raro", "precio": 1000, "iva_rate": 0.13,
    })
    assert r.status_code == 422, r.text
    assert "13%" in r.json()["detail"]


def test_actualizar_un_servicio_tambien_valida_la_alicuota(client):
    """La validación en el alta no alcanza: la edición es otro camino a la
    misma columna."""
    s = client.post("/api/servicios", json={"nombre": "Soporte", "precio": 1000}).json()
    r = client.put(f"/api/servicios/{s['id']}", json={
        "nombre": "Soporte", "precio": 1000, "iva_rate": 0.13, "activo": True,
    })
    assert r.status_code == 422, r.text


def test_la_pantalla_lee_las_alicuotas_del_backend(client):
    """Una sola lista: si el frontend las hardcodeara, agregar una acá dejaría
    el catálogo aceptando por API algo que nadie puede elegir."""
    r = client.get("/api/servicios/alicuotas")
    assert r.status_code == 200, r.text
    assert r.json() == [0.0, 0.105, 0.21, 0.27]


def test_el_cliente_guarda_su_condicion_de_iva(client):
    c = _cliente(client, condicion_iva="Responsable Inscripto")
    assert c["condicion_iva"] == "Responsable Inscripto"
    assert client.get(f"/api/clientes/{c['id']}").json()["condicion_iva"] == "Responsable Inscripto"


def test_un_cliente_viejo_sin_condicion_sigue_funcionando(client):
    """Las 9 filas reales de `compulibra` vienen de la migración del Node.js
    viejo y no la tienen."""
    c = _cliente(client)
    assert c["condicion_iva"] is None
    assert c["iva_discriminado"] is False


def test_la_regla_de_quien_discrimina_la_calcula_el_backend(client):
    """🔴 La pantalla **no** compara contra «Responsable Inscripto»: recibe el
    booleano ya resuelto. Si lo reprodujera, agregar una condición que
    discrimine cambiaría el PDF y no el aviso que se lee al cargarla."""
    ri = _cliente(client, condicion_iva="Responsable Inscripto")
    assert ri["iva_discriminado"] is True

    mono = client.post("/api/clientes", json={
        "nombre": "Otro", "condicion_iva": "Monotributista",
    }).json()
    assert mono["iva_discriminado"] is False


def test_la_pantalla_lee_las_condiciones_con_su_efecto(client):
    r = client.get("/api/clientes/condiciones-iva")
    assert r.status_code == 200, r.text
    condiciones = {c["nombre"]: c["discrimina"] for c in r.json()}
    assert condiciones["Responsable Inscripto"] is True
    assert condiciones["Consumidor Final"] is False


# --- El PDF, que es donde la condición se vuelve visible ---------------------

def _texto_pdf(respuesta) -> str:
    from io import BytesIO

    from pypdf import PdfReader

    lector = PdfReader(BytesIO(respuesta.content))
    return "\n".join(p.extract_text() or "" for p in lector.pages)


def _presupuesto_de(client, cliente_id, items, **extra):
    r = client.post("/api/presupuestos", json={
        "client_id": cliente_id, "items": items, **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_el_pdf_de_un_responsable_inscripto_discrimina_el_iva(client):
    c = _cliente(client, condicion_iva="Responsable Inscripto")
    p = _presupuesto_de(client, c["id"], [
        {"description": "Soporte", "qty": 1, "unit_price": 10000, "tax_rate": 0.21},
    ])
    r = client.get(f"/api/presupuestos/{p['id']}/pdf")
    assert r.status_code == 200, r.text
    texto = _texto_pdf(r)

    assert "Subtotal" in texto
    assert "IVA 21%" in texto


def test_el_pdf_de_un_consumidor_final_muestra_el_precio_final(client):
    """🔴 La otra mitad del pedido. Sin esto la condición se guardaba y no
    cambiaba nada — el dato estaría cargado y sería decorativo."""
    c = _cliente(client, condicion_iva="Consumidor Final")
    p = _presupuesto_de(client, c["id"], [
        {"description": "Soporte", "qty": 1, "unit_price": 10000, "tax_rate": 0.21},
    ])
    texto = _texto_pdf(client.get(f"/api/presupuestos/{p['id']}/pdf"))

    assert "Subtotal" not in texto
    assert "IVA incluido" in texto
    # 12.100 = 10.000 + 21%, y el neto no aparece en ninguna parte.
    assert "12.100,00" in texto
    assert "10.000,00" not in texto


def test_el_pdf_de_un_cliente_sin_condicion_cae_a_precio_final(client):
    """El default de los clientes que ya existían."""
    c = _cliente(client)
    p = _presupuesto_de(client, c["id"], [
        {"description": "Soporte", "qty": 1, "unit_price": 10000, "tax_rate": 0.21},
    ])
    texto = _texto_pdf(client.get(f"/api/presupuestos/{p['id']}/pdf"))

    assert "Subtotal" not in texto


def test_cambiar_la_condicion_cambia_el_pdf_del_presupuesto_ya_emitido(client):
    """🔴 La condición se lee del cliente **al generar el PDF**, no se copia al
    comprobante: si estaba mal cargada, corregirla tiene que arreglar el PDF
    sin tener que rehacer los presupuestos."""
    c = _cliente(client, condicion_iva="Consumidor Final")
    p = _presupuesto_de(client, c["id"], [
        {"description": "Soporte", "qty": 1, "unit_price": 10000, "tax_rate": 0.21},
    ])
    assert "Subtotal" not in _texto_pdf(client.get(f"/api/presupuestos/{p['id']}/pdf"))

    r = client.put(f"/api/clientes/{c['id']}", json={
        "nombre": c["nombre"], "condicion_iva": "Responsable Inscripto",
    })
    assert r.status_code == 200, r.text

    assert "Subtotal" in _texto_pdf(client.get(f"/api/presupuestos/{p['id']}/pdf"))
