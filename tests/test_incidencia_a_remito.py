"""De un reclamo cerrado al remito — el camino a facturación de un servicio.

LibraDesk manda a facturar **sólo remitos** (ver `app/routers/facturacion.py`),
así que sin esta conversión un trabajo por servicio no tenía cómo llegar a la
bandeja. Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que no se pueda facturar dos veces el mismo reclamo.** La conversión es
   idempotente y el vínculo queda guardado; sin eso, dos clicks son dos remitos
   y —desde que el envío debita en cuenta corriente— deuda de más para un
   cliente real.
2. 🔴 **Que el vínculo no se pierda editando el ticket.** El PUT de incidencias
   manda el objeto entero, y este producto ya perdió un dato así antes.
3. 🔴 **Que no se pueda borrar el remito por abajo** dejando al reclamo
   apuntando a un id que no existe. Acá no hay FK que lo ataje: `incidencias`
   es SQLAlchemy y `remitos` no.
4. Que sólo se convierta un ticket **cerrado**, que es donde el circuito real
   decide si va a facturación.
5. Que lo que entra en el remito sea el trabajo y los materiales que
   efectivamente se usaron, valorizados.
"""

import os
from datetime import datetime
from io import BytesIO

import pytest
from pypdf import PdfReader

from app.services import inventario, materiales

CUANDO = datetime(2026, 8, 13, 10, 0, 0)


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
    """Un cliente, un ticket abierto con horas, y una camioneta con 40 plugs.

    El plug tiene `precio` (de venta) distinto del `costo`: es lo que hace que
    el test note si el remito se valoriza con el precio equivocado.
    """
    cliente = client.post("/api/clientes", json={
        "nombre": "Medici Neumatec", "empresa": "NEUMYSER SRL",
        "cuit": "30-11111111-7", "ciudad": "Chivilcoy",
    }).json()
    incidencia = client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "titulo": "Central sin tono",
        "descripcion": "No hay tono en los internos",
        "horas_invertidas": 2,
    }).json()
    item = inventario.crear_item("Plug RJ45", costo=120.0, precio=500.0)
    camioneta = inventario.crear_deposito("Kangoo")
    inventario.ajustar(item["id"], camioneta["id"], 40, fecha=CUANDO)
    return client, cliente, incidencia, item, camioneta


def _cerrar(client, incidencia, **extra):
    """Cierra el ticket por el PUT real, que es como se cierra en la pantalla."""
    payload = {**incidencia, **extra, "estado": "cerrado"}
    r = client.put(f"/api/incidencias/{incidencia['id']}", json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _convertir(client, incidencia_id):
    return client.post(f"/api/incidencias/{incidencia_id}/convertir-en-remito")


def _convertir_lote(client, incidencia_ids):
    return client.post("/api/incidencias/convertir-en-remito",
                       json={"incidencia_ids": incidencia_ids})


def _descripciones(remito):
    return [i["description"] for i in remito["items"]]


# ── El circuito ──────────────────────────────────────────────────────────


def test_un_reclamo_cerrado_genera_el_remito_con_trabajo_y_materiales(escenario):
    client, cliente, incidencia, item, camioneta = escenario
    materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                      cuando=CUANDO)
    _cerrar(client, incidencia)

    r = _convertir(client, incidencia["id"])

    assert r.status_code == 201, r.text
    remito = r.json()
    assert remito["client_name"] == "NEUMYSER SRL"
    assert remito["client_cuit"] == "30-11111111-7"

    lineas = {i["description"]: i for i in remito["items"]}
    # La línea del trabajo: las horas van como cantidad y el precio queda en
    # cero porque no hay ningún servicio marcado como valor hora.
    trabajo = f"#{incidencia['id']} Central sin tono"
    assert lineas[trabajo]["qty"] == 2
    assert lineas[trabajo]["unit_price"] == 0
    # La del material, al precio de VENTA (500) y no al costo (120). El `\n`
    # parte la descripción en título y detalle al dibujar el PDF.
    material = f"Plug RJ45\nReclamo #{incidencia['id']}"
    assert lineas[material]["qty"] == 10
    assert lineas[material]["unit_price"] == 500


def test_sin_horas_cargadas_el_trabajo_va_como_una_visita(escenario):
    """`qty` 1 y no 0: un `qty` en 0 daría un remito que no cobra el trabajo
    aunque después le pongan precio a la línea."""
    client, _, incidencia, _, _ = escenario
    sin_horas = client.put(f"/api/incidencias/{incidencia['id']}", json={
        **incidencia, "horas_invertidas": None, "estado": "cerrado",
    }).json()
    assert sin_horas["horas_invertidas"] is None

    remito = _convertir(client, incidencia["id"]).json()

    assert remito["items"][0]["qty"] == 1


def test_el_material_devuelto_no_entra_en_el_remito(escenario):
    """Lo que volvió al depósito no se usó, y cobrarlo sería cobrar de más."""
    client, _, incidencia, item, camioneta = escenario
    cargado = materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                                cuando=CUANDO)
    materiales.quitar(cargado["id"], cuando=CUANDO)
    _cerrar(client, incidencia)

    remito = _convertir(client, incidencia["id"]).json()

    assert _descripciones(remito) == [f"#{incidencia['id']} Central sin tono"]


def test_el_numero_del_papel_firmado_encabeza_la_linea_del_trabajo(escenario):
    """El `N° CDS` es lo único que ata la conformidad firmada con el ticket, y
    quien concilia después busca por ese número.

    Va **en la línea**, no sólo en las observaciones: con varios reclamos en el
    mismo remito, un CDS al pie no dice cuál de los renglones es cuál. Y el PDF
    del remito imprime descripción y cantidad —`show_prices=False`—, así que la
    descripción es el único lugar del papel donde puede leerse.
    """
    client, _, incidencia, _, _ = escenario
    _cerrar(client, incidencia, nro_cds="0001-00041996")

    remito = _convertir(client, incidencia["id"]).json()

    assert _descripciones(remito) == [
        f"CDS 0001-00041996 — #{incidencia['id']} Central sin tono"
    ]
    # Y sigue estando en el resumen del pie, que es de dónde salió.
    assert "0001-00041996" in remito["observations"]


# ── Que no se facture dos veces ──────────────────────────────────────────


def test_convertir_dos_veces_devuelve_el_mismo_remito(escenario):
    client, _, incidencia, _, _ = escenario
    _cerrar(client, incidencia)

    primero = _convertir(client, incidencia["id"])
    segundo = _convertir(client, incidencia["id"])

    assert primero.status_code == segundo.status_code == 201
    assert primero.json()["id"] == segundo.json()["id"]
    # Y no quedó un segundo remito emitido por el mismo trabajo.
    assert len(client.get("/api/remitos").json()) == 1


def test_el_reclamo_queda_linkeado_al_remito(escenario):
    client, _, incidencia, _, _ = escenario
    _cerrar(client, incidencia)

    remito = _convertir(client, incidencia["id"]).json()

    ticket = client.get(f"/api/incidencias/{incidencia['id']}").json()
    assert ticket["remito_id"] == remito["id"]


def test_editar_el_ticket_no_borra_el_vinculo_con_el_remito(escenario):
    """El PUT de incidencias manda el objeto entero y lo que no viaja vuelve a
    `null`. Este producto ya perdió el `nro_cds` así una vez; `remito_id` es el
    mismo tipo de dato caro, y el que decide si un trabajo ya se facturó."""
    client, _, incidencia, _, _ = escenario
    _cerrar(client, incidencia)
    remito = _convertir(client, incidencia["id"]).json()

    editado = client.put(f"/api/incidencias/{incidencia['id']}", json={
        **incidencia, "estado": "cerrado", "prioridad": "alta",
    })

    assert editado.status_code == 200, editado.text
    assert editado.json()["remito_id"] == remito["id"]


def test_no_se_puede_borrar_el_remito_que_genero_un_reclamo(escenario):
    """Sin esto el reclamo queda diciendo "ya se remitió" apuntando a nada, y
    el trabajo no se puede facturar nunca. Acá **no hay FK que lo ataje**:
    `incidencias` es SQLAlchemy y `remitos` no."""
    client, _, incidencia, _, _ = escenario
    _cerrar(client, incidencia)
    remito = _convertir(client, incidencia["id"]).json()

    r = client.delete(f"/api/remitos/{remito['id']}")

    assert r.status_code == 409, r.text
    assert "reclamo" in r.json()["detail"]
    assert client.get(f"/api/remitos/{remito['id']}").status_code == 200


# ── Sólo un ticket cerrado ───────────────────────────────────────────────


@pytest.mark.parametrize("estado", ["abierto", "en_progreso", "resuelta"])
def test_un_reclamo_que_no_esta_cerrado_no_genera_remito(escenario, estado):
    """`resuelta` está en la lista a propósito: el técnico ya terminó, pero en
    el circuito real todavía falta el control del comprobante contra la hoja de
    ruta, y es al cerrar cuando se decide si va a facturación."""
    client, _, incidencia, _, _ = escenario
    client.put(f"/api/incidencias/{incidencia['id']}",
               json={**incidencia, "estado": estado})

    r = _convertir(client, incidencia["id"])

    assert r.status_code == 409, r.text
    assert client.get("/api/remitos").json() == []


def test_un_reclamo_que_no_existe_da_404(client):
    assert _convertir(client, 9999).status_code == 404


# ── Varios reclamos, un solo remito ──────────────────────────────────────
#
# El caso que motivó todo esto: a un cliente se le hicieron tres visitas en el
# mes y se le emite **una** factura. Sin esto había que emitir tres remitos y
# facturarlos por separado, que no es lo que se acordó con el cliente.


def _nuevo_reclamo(client, cliente_id, titulo, *, horas=1, nro_cds=None):
    r = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "titulo": titulo,
        "horas_invertidas": horas, "nro_cds": nro_cds,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _marcar_valor_hora(client, precio, *, nombre="Hora de servicio técnico",
                       iva_rate=0.21):
    r = client.post("/api/servicios", json={
        "nombre": nombre, "precio": precio, "iva_rate": iva_rate,
        "es_valor_hora": True,
    })
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def tres_reclamos(escenario):
    """Tres reclamos cerrados del mismo cliente, dos con comprobante en papel.

    El del medio queda **sin** `nro_cds` a propósito: es el reclamo que se
    resolvió en remoto, no tiene papel que numerar, y tiene que entrar al remito
    igual que los otros dos.
    """
    client, cliente, primero, item, camioneta = escenario
    _cerrar(client, primero, nro_cds="0001-00041996")
    segundo = _nuevo_reclamo(client, cliente["id"], "Sin acceso al correo", horas=1)
    _cerrar(client, segundo)
    tercero = _nuevo_reclamo(client, cliente["id"], "Cambio de switch", horas=3,
                             nro_cds="0001-00041998")
    _cerrar(client, tercero)
    return client, cliente, [primero, segundo, tercero], item, camioneta


def test_tres_reclamos_dan_un_remito_con_los_tres_cds(tres_reclamos):
    """Lo que el humano pidió: un remito por los tres, con los CDS a la vista."""
    client, _, reclamos, _, _ = tres_reclamos
    ids = [r["id"] for r in reclamos]

    r = _convertir_lote(client, ids)

    assert r.status_code == 201, r.text
    remito = r.json()
    assert _descripciones(remito) == [
        f"CDS 0001-00041996 — #{ids[0]} Central sin tono",
        f"#{ids[1]} Sin acceso al correo",
        f"CDS 0001-00041998 — #{ids[2]} Cambio de switch",
    ]
    # Un solo remito por los tres, no tres.
    assert len(client.get("/api/remitos").json()) == 1


def test_los_materiales_van_debajo_del_reclamo_del_que_salieron(tres_reclamos):
    """Agrupado por ticket y no todo el trabajo primero: quien concilia contra
    los papeles va bajando de a un CDS por vez."""
    client, _, reclamos, item, camioneta = tres_reclamos
    ids = [r["id"] for r in reclamos]
    materiales.cargar(ids[0], item["id"], camioneta["id"], 10, cuando=CUANDO)
    materiales.cargar(ids[2], item["id"], camioneta["id"], 4, cuando=CUANDO)

    remito = _convertir_lote(client, ids).json()

    assert _descripciones(remito) == [
        f"CDS 0001-00041996 — #{ids[0]} Central sin tono",
        f"Plug RJ45\nReclamo #{ids[0]}",
        f"#{ids[1]} Sin acceso al correo",
        f"CDS 0001-00041998 — #{ids[2]} Cambio de switch",
        f"Plug RJ45\nReclamo #{ids[2]}",
    ]


def test_los_tres_cds_salen_impresos_en_el_pdf_del_remito(tres_reclamos):
    """🔴 El chequeo que de verdad cierra el pedido.

    Que el CDS esté en el JSON del remito no prueba que salga en el papel: el
    PDF del remito se dibuja con `show_prices=False`, así que las únicas
    columnas que llegan a la hoja son DESCRIPCIÓN y CANTIDAD. Si mañana alguien
    mueve el número a un campo propio del comprobante, el JSON sigue diciendo
    que está y el papel sale sin él.

    Por eso se lee el **texto extraído del PDF**, no el `Content-Type` ni la
    firma `%PDF-`.
    """
    client, _, reclamos, _, _ = tres_reclamos
    remito = _convertir_lote(client, [r["id"] for r in reclamos]).json()

    r = client.get(f"/api/remitos/{remito['id']}/pdf")

    assert r.status_code == 200, r.text
    texto = "\n".join(p.extract_text() for p in PdfReader(BytesIO(r.content)).pages)
    assert "0001-00041996" in texto
    assert "0001-00041998" in texto
    # Y el reclamo sin papel también salió, con su número de ticket.
    assert f"#{reclamos[1]['id']}" in texto


def test_los_tres_quedan_atados_al_mismo_remito(tres_reclamos):
    client, _, reclamos, _, _ = tres_reclamos
    ids = [r["id"] for r in reclamos]

    remito = _convertir_lote(client, ids).json()

    atados = [client.get(f"/api/incidencias/{x}").json()["remito_id"] for x in ids]
    assert atados == [remito["id"]] * 3


def test_el_mismo_lote_dos_veces_devuelve_el_mismo_remito(tres_reclamos):
    """El doble click, que es de donde sale la idempotencia."""
    client, _, reclamos, _, _ = tres_reclamos
    ids = [r["id"] for r in reclamos]

    primero = _convertir_lote(client, ids)
    segundo = _convertir_lote(client, ids)

    assert primero.status_code == segundo.status_code == 201
    assert primero.json()["id"] == segundo.json()["id"]
    assert len(client.get("/api/remitos").json()) == 1


def test_reclamos_de_dos_clientes_no_entran_al_mismo_remito(tres_reclamos):
    """Un remito se emite a nombre de UN cliente. Sin esto, el remito saldría a
    nombre del primero de la lista y los trabajos del otro se le facturarían a
    él — un error que recién se ve cuando el cliente recibe la factura."""
    client, _, reclamos, _, _ = tres_reclamos
    otro = client.post("/api/clientes", json={
        "nombre": "Otro", "empresa": "OTRA SRL", "ciudad": "Chivilcoy",
    }).json()
    ajeno = _nuevo_reclamo(client, otro["id"], "Nada que ver")
    _cerrar(client, ajeno)

    r = _convertir_lote(client, [reclamos[0]["id"], ajeno["id"]])

    assert r.status_code == 409, r.text
    assert "uno solo" in r.json()["detail"]
    assert client.get("/api/remitos").json() == []


def test_uno_no_cerrado_en_el_lote_lo_rechaza_entero(tres_reclamos):
    """Nombrando cuál, que es lo que hace falta para poder arreglarlo."""
    client, cliente, reclamos, _, _ = tres_reclamos
    abierto = _nuevo_reclamo(client, cliente["id"], "Todavía en curso")

    r = _convertir_lote(client, [reclamos[0]["id"], abierto["id"]])

    assert r.status_code == 409, r.text
    assert f"#{abierto['id']}" in r.json()["detail"]
    assert client.get("/api/remitos").json() == []


def test_uno_ya_remitado_en_el_lote_lo_rechaza_entero(tres_reclamos):
    """La mezcla de remitados y no remitados **no** es idempotencia.

    Devolver el remito viejo dejaría a los otros dos sin facturar, y en
    silencio: la pantalla mostraría un remito y el operador daría el trabajo por
    liquidado.
    """
    client, _, reclamos, _, _ = tres_reclamos
    ids = [r["id"] for r in reclamos]
    ya = _convertir(client, ids[0]).json()

    r = _convertir_lote(client, ids)

    assert r.status_code == 409, r.text
    assert f"#{ids[0]}" in r.json()["detail"]
    # Y los otros dos siguen libres: el rechazo no dejó nada a medio hacer.
    assert len(client.get("/api/remitos").json()) == 1
    sueltos = [client.get(f"/api/incidencias/{x}").json()["remito_id"] for x in ids[1:]]
    assert sueltos == [None, None]
    assert client.get(f"/api/incidencias/{ids[0]}").json()["remito_id"] == ya["id"]


def test_un_reclamo_del_lote_que_no_existe_da_404(tres_reclamos):
    client, _, reclamos, _, _ = tres_reclamos

    r = _convertir_lote(client, [reclamos[0]["id"], 9999])

    assert r.status_code == 404, r.text
    assert client.get("/api/remitos").json() == []


def test_el_lote_vacio_no_llega_al_servicio(client):
    """422 de pydantic: no es un estado de los reclamos, es un pedido mal
    formado."""
    assert _convertir_lote(client, []).status_code == 422


# ── El valor hora ────────────────────────────────────────────────────────


def test_el_valor_hora_del_catalogo_cotiza_el_trabajo(tres_reclamos):
    """Sin esto la mano de obra sale en cero y hay que tipear el importe en cada
    línea de cada remito — tres veces el mismo número, en este caso."""
    client, _, reclamos, _, _ = tres_reclamos
    _marcar_valor_hora(client, 15000, iva_rate=0.21)

    remito = _convertir_lote(client, [r["id"] for r in reclamos]).json()

    trabajos = [i for i in remito["items"] if "Plug" not in i["description"]]
    assert [i["unit_price"] for i in trabajos] == [15000, 15000, 15000]
    # Y las horas de cada uno, que es lo que multiplica.
    assert [i["qty"] for i in trabajos] == [2, 1, 3]
    assert remito["total"] > 0


def test_la_alicuota_sale_del_servicio_y_no_del_documento(tres_reclamos):
    """El valor hora es una línea del catálogo y trae la suya: en Argentina la
    alícuota sale de QUÉ se vende."""
    client, _, reclamos, _, _ = tres_reclamos
    _marcar_valor_hora(client, 10000, iva_rate=0.105)

    remito = _convertir_lote(client, [r["id"] for r in reclamos]).json()

    assert remito["items"][0]["tax_rate"] == 0.105


def test_sin_servicio_marcado_el_trabajo_sale_en_cero(tres_reclamos):
    """`None` y no un 0 inventado: una instancia que todavía no cargó su valor
    hora emite el remito igual, y la bandeja de facturación se niega a mandar un
    remito con total 0, así que el olvido no llega a facturarse."""
    client, _, reclamos, _, _ = tres_reclamos

    remito = _convertir_lote(client, [r["id"] for r in reclamos]).json()

    assert [i["unit_price"] for i in remito["items"]] == [0, 0, 0]
    assert remito["total"] == 0
    enviar = client.post("/api/facturacion/enviar",
                         json={"origen_tipo": "remito", "ids": [remito["id"]]})
    assert enviar.status_code == 409, enviar.text


def test_marcar_un_segundo_valor_hora_desmarca_al_primero(client):
    """Con dos marcados, el precio del trabajo pasaría a depender de cómo se
    llamen los servicios."""
    viejo = _marcar_valor_hora(client, 10000, nombre="Hora vieja")
    nuevo = _marcar_valor_hora(client, 15000, nombre="Hora nueva")

    marcados = [
        s for s in client.get("/api/servicios").json() if s["es_valor_hora"]
    ]

    assert [s["id"] for s in marcados] == [nuevo["id"]]
    assert client.get(f"/api/servicios/{viejo['id']}").json()["es_valor_hora"] is False


def test_un_valor_hora_desactivado_no_cotiza(tres_reclamos):
    """Dar de baja el servicio es cómo se dice que se dejó de usar; seguir
    cotizando con él sería usar un precio que la pantalla ya no muestra."""
    client, _, reclamos, _, _ = tres_reclamos
    servicio = _marcar_valor_hora(client, 15000)
    client.put(f"/api/servicios/{servicio['id']}", json={
        **servicio, "activo": False,
    })

    remito = _convertir_lote(client, [r["id"] for r in reclamos]).json()

    assert [i["unit_price"] for i in remito["items"]] == [0, 0, 0]


# ── Y de ahí a la bandeja ────────────────────────────────────────────────


def test_el_remito_generado_es_lo_que_llega_a_la_bandeja(escenario):
    """El circuito completo: reclamo cerrado → remito → pendientes.

    Y **una sola fila**: el reclamo no aparece por su cuenta.
    """
    client, _, incidencia, item, camioneta = escenario
    materiales.cargar(incidencia["id"], item["id"], camioneta["id"], 10,
                      cuando=CUANDO)
    _cerrar(client, incidencia)
    remito = _convertir(client, incidencia["id"]).json()

    items = client.get("/api/facturacion/pendientes").json()["items"]

    assert [(i["origen_tipo"], i["id"]) for i in items] == [("remito", remito["id"])]
