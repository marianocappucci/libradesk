"""Informe de servicio para el cliente — `GET /api/informes/cliente/{id}.pdf`.

Lo que estos tests fijan, en orden de lo que puede romperse sin que se note:

1. Que el informe diga **lo que era cierto al cierre del período**, no lo que
   es cierto hoy. Es la decisión de diseño de la que cuelga todo lo demás: un
   informe de enero regenerado en agosto tiene que dar lo mismo. Cuatro tests
   atacan esto desde distintos lados (tickets, garantías, service).
2. Que **no se filtre nada interno** al documento que ve el cliente: costos de
   reparación, estado de cobro, técnico asignado.
3. Que el PDF diga de verdad lo que el resumen calculó — leyendo el texto de
   vuelta con pypdf, no mirando el `Content-Type`. Un PDF vacío pasa igual el
   chequeo de la firma `%PDF-`.
4. Que el contrato con los helpers de maquetado de LibraCore siga en pie.

**Todo el escenario vive en enero de 2026**, un período cerrado y pasado. Es a
propósito: con fechas relativas a hoy, los tests del ancla temporal no podrían
distinguir "contado desde el fin del período" de "contado desde hoy", que es
justo lo que tienen que distinguir.
"""
import sys
from datetime import datetime
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader

RUTA = "/api/informes/cliente/{cliente_id}.pdf"

DESDE = "2026-01-01"
HASTA = "2026-01-31"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    from app.asgi import app
    return TestClient(app, base_url="https://testserver")


def _login(client) -> None:
    assert client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    ).status_code == 200


def _fechar(client, incidencia_id: int, creacion: str, cierre: str | None) -> None:
    """`fecha_creacion` y `fecha_cierre` las pone el servidor (`now()` y el
    cambio de estado), así que no hay forma de crear por API un ticket con
    fechas de enero. Se corrigen por la sesión, que es lo mismo que hizo el
    backdating del juego de datos de dev."""
    from app.services.incidencias import Incidencia

    sessions = client.app.state.informes.session_factory
    with sessions() as session:
        i = session.get(Incidencia, incidencia_id)
        i.fecha_creacion = datetime.fromisoformat(creacion)
        i.fecha_cierre = datetime.fromisoformat(cierre) if cierre else None
        session.commit()


def _informe(client, cliente_id: int, desde: str = DESDE, hasta: str = HASTA) -> dict:
    """El dict del service, que es lo que el PDF renderiza. Los tests de
    números van contra esto; los de presentación, contra el PDF."""
    return client.app.state.informes.cliente(cliente_id, desde, hasta)


def _texto_pdf(contenido: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)


@pytest.fixture
def escenario(client):
    """Un cliente con historia repartida a los dos lados del período, y **un
    segundo cliente** con lo suyo — sin ese segundo, un `where cliente_id` que
    faltara pasaría inadvertido."""
    _login(client)

    cliente_id = client.post("/api/clientes", json={
        "nombre": "Ana Gómez", "empresa": "Compulibra SRL",
        "email": "c@test.com", "cuit": "30-11111111-2", "ciudad": "Suipacha",
    }).json()["id"]
    otro_id = client.post("/api/clientes", json={
        "nombre": "Cliente Ajeno", "email": "o@test.com",
    }).json()["id"]

    tecnico_id = client.post(
        "/api/tecnicos", json={"nombre": "Mariano Técnico"}).json()["id"]

    def equipo(cliente, tipo, **extra):
        return client.post("/api/equipos", json={
            "cliente_id": cliente, "tipo": tipo, **extra,
        }).json()["id"]

    equipos = {
        # Garantías, todas medidas contra el 31/01/2026 (fin del período):
        "g_por_vencer": equipo(cliente_id, "Notebook", marca="Lenovo",
                               serial="NB-1", garantia_vence="2026-03-15"),
        "g_vencida": equipo(cliente_id, "Impresora", marca="HP",
                            serial="IMP-1", garantia_vence="2025-12-20"),
        # 90 días después del cierre: fuera de la ventana de 60. Desde HOY ya
        # está vencida, así que si el cálculo se anclara a hoy, aparecería.
        "g_lejana": equipo(cliente_id, "Monitor", serial="MON-1",
                           garantia_vence="2026-05-01"),
        "g_baja": equipo(cliente_id, "Scanner", serial="SCN-1", estado="baja",
                         garantia_vence="2026-02-01"),
        "service_devuelto": equipo(cliente_id, "Router", serial="RTR-1"),
        "service_abierto": equipo(cliente_id, "Switch", serial="SW-1"),
        "service_tardio": equipo(cliente_id, "NAS", serial="NAS-1"),
        "service_viejo": equipo(cliente_id, "UPS", serial="UPS-1"),
        "ajeno": equipo(otro_id, "Notebook", serial="AJENO-1",
                        garantia_vence="2026-02-10"),
    }

    def ticket(cliente, titulo, creacion, cierre, **extra):
        tid = client.post("/api/incidencias", json={
            "cliente_id": cliente, "titulo": titulo, **extra,
        }).json()["id"]
        _fechar(client, tid, creacion, cierre)
        return tid

    tickets = {
        # (creada, cerrada)                          en el período:
        # 05/01, 08/01 → recibida Y resuelta
        "del_periodo": ticket(cliente_id, "Impresora no imprime",
                              "2026-01-05T09:00:00", "2026-01-08T15:00:00",
                              tecnico_id=tecnico_id, horas_invertidas=2.5),
        # 20/01, abierta → recibida y pendiente al cierre
        "abierta": ticket(cliente_id, "Red lenta en Admisión",
                          "2026-01-20T10:00:00", None, horas_invertidas=1),
        # 10/12, 03/01 → resuelta en el período pero NO recibida en él
        "vieja_cerrada": ticket(cliente_id, "Backup desactualizado",
                                "2025-12-10T08:00:00", "2026-01-03T12:00:00"),
        # 01/11, abierta → pendiente al cierre, fuera del detalle
        "vieja_abierta": ticket(cliente_id, "Cámara sin señal",
                                "2025-11-01T08:00:00", None),
        # 25/01, cerrada el 02/02 → al 31/01 seguía PENDIENTE
        "cierre_tardio": ticket(cliente_id, "Disco con errores",
                                "2026-01-25T11:00:00", "2026-02-02T09:00:00"),
        # Febrero entero → fuera de todo
        "posterior": ticket(cliente_id, "Ticket de febrero",
                            "2026-02-10T09:00:00", None),
        "ajeno": ticket(otro_id, "Incidencia del cliente ajeno",
                        "2026-01-15T09:00:00", None),
    }

    proveedor_id = client.post(
        "/api/proveedores", json={"nombre": "Compu Service SRL"}).json()["id"]

    def reparacion(equipo_key, envio, retorno, **cierre):
        rid = client.post("/api/reparaciones", json={
            "equipo_id": equipos[equipo_key], "proveedor_id": proveedor_id,
            "fecha_envio": envio, "rma": f"RMA-{equipo_key}",
        }).json()["id"]
        if retorno:
            client.post(f"/api/reparaciones/{rid}/cerrar",
                        json={"fecha_retorno": retorno, **cierre})
        return rid

    # Volvió dentro del período, con un costo real que NO tiene que salir en
    # el informe del cliente.
    reparacion("service_devuelto", "2026-01-10", "2026-01-20",
               costo=45000, diagnostico="Fuente reemplazada")
    # Sigue afuera.
    reparacion("service_abierto", "2026-01-15", None)
    # Volvió DESPUÉS del cierre: al 31/01 seguía en service.
    reparacion("service_tardio", "2026-01-05", "2026-02-20", costo=12000)
    # Entera fuera del período.
    reparacion("service_viejo", "2025-11-01", "2025-11-10")

    return {"cliente_id": cliente_id, "otro_id": otro_id,
            "equipos": equipos, "tickets": tickets}


# ── La ruta ────────────────────────────────────────────────────────

def test_la_ruta_devuelve_un_pdf_que_se_puede_abrir(client, escenario):
    r = client.get(RUTA.format(cliente_id=escenario["cliente_id"]),
                   params={"desde": DESDE, "hasta": HASTA})

    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    # La firma sola no alcanza: un PDF de cero páginas la tiene igual. Que
    # pypdf lo abra y tenga páginas es lo que prueba que se generó algo.
    assert r.content.startswith(b"%PDF-")
    assert len(PdfReader(BytesIO(r.content)).pages) >= 1
    assert "informe-compulibra-srl-2026-01-01-2026-01-31.pdf" in \
        r.headers["content-disposition"]


def test_cliente_inexistente_da_404(client, escenario):
    r = client.get(RUTA.format(cliente_id=9999),
                   params={"desde": DESDE, "hasta": HASTA})
    assert r.status_code == 404


@pytest.mark.parametrize("desde,hasta", [
    ("no-es-fecha", HASTA),
    (DESDE, "2026-13-45"),
    ("2026-01-31", "2026-01-01"),   # rango invertido
])
def test_rango_invalido_da_422(client, escenario, desde, hasta):
    r = client.get(RUTA.format(cliente_id=escenario["cliente_id"]),
                   params={"desde": desde, "hasta": hasta})
    assert r.status_code == 422


def test_sin_sesion_no_se_emite_un_informe(client, escenario):
    client.post("/auth/logout")
    r = client.get(RUTA.format(cliente_id=escenario["cliente_id"]),
                   params={"desde": DESDE, "hasta": HASTA})
    assert r.status_code == 401


# ── Los números del período ────────────────────────────────────────

def test_el_resumen_separa_recibidas_resueltas_y_pendientes(client, escenario):
    resumen = _informe(client, escenario["cliente_id"])["resumen"]

    # Creadas en enero: del_periodo, abierta, cierre_tardio.
    assert resumen["recibidas"] == 3
    # Cerradas en enero: del_periodo y vieja_cerrada (abierta en diciembre).
    assert resumen["resueltas"] == 2
    # Al 31/01 seguían abiertas: abierta, vieja_abierta y cierre_tardio.
    assert resumen["pendientes"] == 3
    assert resumen["horas"] == 3.5


def test_entra_el_ticket_viejo_que_se_cerro_en_el_periodo(client, escenario):
    """La unión "creadas o cerradas" es el motivo de que este ticket exista:
    se abrió en diciembre, así que un filtro por fecha de creación lo dejaría
    afuera de todos los informes, pese a ser trabajo entregado en enero."""
    ids = [i["id"] for i in _informe(client, escenario["cliente_id"])["incidencias"]]

    assert escenario["tickets"]["vieja_cerrada"] in ids
    # Y la que sigue abierta desde noviembre NO entra al detalle: no pasó nada
    # con ella en el período. Igual cuenta como pendiente, ver el test de
    # arriba — que es la razón de que ese conteo no salga de esta lista.
    assert escenario["tickets"]["vieja_abierta"] not in ids
    assert escenario["tickets"]["posterior"] not in ids


def test_un_cierre_posterior_al_periodo_se_informa_como_pendiente(client, escenario):
    """El corazón del diseño. El ticket está cerrado HOY, pero al 31/01 no lo
    estaba: el informe de enero tiene que decir "Pendiente" para siempre. Si
    esto se derivara de la columna `estado`, el mismo informe cambiaría de
    contenido cada vez que se lo regenera."""
    informe = _informe(client, escenario["cliente_id"])
    fila = next(i for i in informe["incidencias"]
                if i["id"] == escenario["tickets"]["cierre_tardio"])

    assert fila["cerrada"] is False
    assert fila["resuelta_en_periodo"] is False
    assert fila["fecha_cierre"] is None

    texto = _texto_pdf(client.get(
        RUTA.format(cliente_id=escenario["cliente_id"]),
        params={"desde": DESDE, "hasta": HASTA}).content)
    assert "Disco con errores" in texto
    # Y en el PDF no puede aparecer la fecha de cierre de febrero.
    assert "02/02/2026" not in texto


def test_las_garantias_se_miden_desde_el_cierre_del_periodo(client, escenario):
    """Anclar a `hasta` y no a `date.today()`. `g_lejana` vence el 01/05/2026:
    a 90 días del cierre —fuera de la ventana de 60— pero ya vencida hoy, así
    que un cálculo anclado al presente la incluiría."""
    garantias = _informe(client, escenario["cliente_id"])["garantias"]
    seriales = {g["serial"] for g in garantias}

    assert seriales == {"IMP-1", "NB-1"}
    assert "MON-1" not in seriales           # fuera de ventana desde el cierre
    assert "SCN-1" not in seriales           # dada de baja
    assert "AJENO-1" not in seriales         # de otro cliente

    por_serial = {g["serial"]: g["dias_restantes"] for g in garantias}
    # 31/01 → 15/03 son 43 días; 31/01 → 20/12/2025 son 42 para atrás. Los dos
    # números son fijos: dependen del período, no del día en que se corra.
    assert por_serial["NB-1"] == 43
    assert por_serial["IMP-1"] == -42


def test_una_reparacion_que_volvio_despues_del_cierre_figura_abierta(client, escenario):
    """Mismo criterio que los tickets: al 31/01 el NAS seguía en service, y eso
    es lo que el informe de enero tiene que decir aunque hoy ya haya vuelto."""
    service = {s["serial"]: s for s in _informe(client, escenario["cliente_id"])["service"]}

    assert set(service) == {"RTR-1", "SW-1", "NAS-1"}
    assert "UPS-1" not in service            # entera fuera del período

    assert service["RTR-1"]["abierta"] is False
    assert service["RTR-1"]["dias_afuera"] == 10

    assert service["SW-1"]["abierta"] is True
    assert service["SW-1"]["dias_afuera"] == 16      # 15/01 → 31/01

    assert service["NAS-1"]["abierta"] is True       # volvió el 20/02
    assert service["NAS-1"]["fecha_retorno"] is None
    assert service["NAS-1"]["dias_afuera"] == 26     # 05/01 → 31/01


def test_el_parque_excluye_las_bajas_y_las_cuenta_aparte(client, escenario):
    parque = _informe(client, escenario["cliente_id"])["parque"]

    assert "baja" not in parque["por_estado"]
    assert parque["bajas"] == 1
    assert parque["total"] == 7              # 8 equipos del cliente menos la baja
    assert sum(n for _, n in parque["por_tipo"]) == 7


def test_no_se_mezcla_nada_del_otro_cliente(client, escenario):
    informe = _informe(client, escenario["cliente_id"])

    assert escenario["tickets"]["ajeno"] not in [i["id"] for i in informe["incidencias"]]
    assert informe["parque"]["total"] == 7   # el equipo ajeno no suma

    texto = _texto_pdf(client.get(
        RUTA.format(cliente_id=escenario["cliente_id"]),
        params={"desde": DESDE, "hasta": HASTA}).content)
    assert "Cliente Ajeno" not in texto
    assert "AJENO-1" not in texto


# ── Lo que el PDF muestra y lo que no ──────────────────────────────

def test_el_pdf_dice_lo_mismo_que_el_resumen(client, escenario):
    texto = _texto_pdf(client.get(
        RUTA.format(cliente_id=escenario["cliente_id"]),
        params={"desde": DESDE, "hasta": HASTA}).content)

    assert "Compulibra SRL" in texto
    assert "01/01/2026" in texto and "31/01/2026" in texto
    # Los cuatro títulos de sección, que son el índice implícito del informe.
    for seccion in ("Resumen del período", "Detalle de incidencias",
                    "Parque de equipos", "Garantías", "Equipos en service"):
        assert seccion in texto, f"falta la sección {seccion!r}"
    # Y los asuntos de los tickets del período.
    assert "Impresora no imprime" in texto
    assert "Backup desactualizado" in texto
    assert "Ticket de febrero" not in texto


def test_el_pdf_no_le_muestra_al_cliente_datos_internos(client, escenario):
    """El informe es lo único que sale de LibraDesk hacia afuera. Costos de
    service, estado de cobro y técnico asignado son datos de la operación
    interna: aparecen en los seis reportes de `/reportes`, no acá."""
    texto = _texto_pdf(client.get(
        RUTA.format(cliente_id=escenario["cliente_id"]),
        params={"desde": DESDE, "hasta": HASTA}).content)

    assert "45000" not in texto and "45.000" not in texto
    assert "12000" not in texto and "12.000" not in texto
    assert "Mariano Técnico" not in texto
    for palabra in ("cobro", "Cobro", "Facturación", "facturar", "Costo", "costo"):
        assert palabra not in texto, f"el informe menciona {palabra!r}"


def test_un_cliente_sin_movimiento_igual_produce_un_informe(client, escenario):
    """El caso que rompe una tabla mal escrita: sin filas, `_tabla` tiene que
    poner la leyenda de vacío y no un encabezado colgando."""
    r = client.get(RUTA.format(cliente_id=escenario["otro_id"]),
                   params={"desde": "2020-01-01", "hasta": "2020-01-31"})

    assert r.status_code == 200
    texto = _texto_pdf(r.content)
    assert "Sin incidencias registradas en el período." in texto
    assert "Sin garantías próximas a vencer." in texto
    assert "Ningún equipo pasó por service en el período." in texto


def test_el_texto_cargado_por_el_usuario_no_rompe_el_pdf(client):
    """Todo lo que se imprime —título del ticket, nombre del cliente, marca del
    equipo— lo escribe una persona, y basta pegar desde Word para traerse
    comillas tipográficas y una raya. Con las fuentes core de fpdf2 en su
    codificación por defecto eso es un **500**, no un renglón feo.

    Desde `libracore` v1.8.0 la base `_TextoSeguroPDF` usa cp1252, así que
    estos caracteres ya no se degradan: **se dibujan tal como se escribieron**.
    Antes este mismo test afirmaba que la raya salía como guión.
    """
    _login(client)
    cliente_id = client.post("/api/clientes", json={
        "nombre": "Piñeiro — “Integrales”", "email": "u@test.com",
        "domicilio": "Av. Güemes 1234 – piso 2º",
    }).json()["id"]
    equipo_id = client.post("/api/equipos", json={
        # La flecha no está en cp1252: es el caso que sí necesita traducirse.
        "cliente_id": cliente_id, "tipo": "Notebook", "marca": "Aspire→5",
    }).json()["id"]
    # Con `equipo_id`, para que la marca llegue al detalle del informe: sin el
    # vínculo la columna EQUIPO va vacía y el test no probaría nada.
    tid = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "titulo": "Pantalla “azul” — reinicia",
        "equipo_id": equipo_id,
    }).json()["id"]
    _fechar(client, tid, "2026-01-10T09:00:00", None)

    r = client.get(RUTA.format(cliente_id=cliente_id),
                   params={"desde": DESDE, "hasta": HASTA})

    assert r.status_code == 200
    texto = _texto_pdf(r.content)
    # Tal cual se escribieron: cp1252 tiene la raya y las comillas curvas.
    assert "Pantalla “azul” — reinicia" in texto
    assert "Piñeiro — “Integrales”" in texto
    # Y lo que no entra ni en cp1252 se translitera en vez de tumbar la
    # request: la marca del equipo entra por el detalle del ticket.
    assert "→" not in texto
    assert "Aspire->5" in texto


def test_un_parque_grande_no_desborda_la_paginacion(client):
    """🔴 Regresión de un defecto real, encontrado mirando el PDF y no los
    tests: `_lista_conteos` llevaba su propio cursor `y` y no contemplaba el
    salto de página. Cuando la lista pasaba el margen, fpdf abría página nueva
    —arriba— pero el cursor seguía abajo, así que **cada renglón siguiente
    forzaba otra página**. Un informe de 7 incidencias salía de 27 páginas y
    20 KB, y todos los tests estaban en verde: ninguno miraba cuántas páginas
    tenía el documento.

    **El escenario es un parque grande con POCAS incidencias**, y eso no es
    casual: medido, el desborde aparece justo ahí. Con 3 a 7 incidencias el
    detalle empuja el título del parque más allá del margen, `_titulo_seccion`
    abre página nueva y el bloque entra por casualidad. Con 1 o 2 arranca a
    media página y desborda. Una primera versión de este test usaba 12 y
    **pasaba con el defecto puesto**: caía en la zona sana.

    Por eso la aserción no es sólo el total de páginas sino que **ninguna
    página quede casi vacía**. Ese es el síntoma directo —una fila por
    carilla— y no depende de acertar un número de incidencias.
    """
    _login(client)
    cliente_id = client.post("/api/clientes", json={
        "nombre": "Parque Grande SA", "email": "pg@test.com",
    }).json()["id"]

    # 20 equipos repartidos en 10 sectores y 8 tipos: las tres listas del
    # bloque del parque quedan en su tope, que es su alto máximo.
    for n in range(20):
        client.post("/api/equipos", json={
            "cliente_id": cliente_id, "tipo": f"Tipo {n % 8}",
            "marca": "Marca", "modelo": f"M{n}", "serial": f"S-{n}",
            "sector": f"Sector {n % 10}",
        })
    for n in range(2):
        tid = client.post("/api/incidencias", json={
            "cliente_id": cliente_id,
            "titulo": f"Incidencia {n} con un asunto largo que ocupa dos renglones",
        }).json()["id"]
        _fechar(client, tid, f"2026-01-{n + 1:02d}T09:00:00", None)

    r = client.get(RUTA.format(cliente_id=cliente_id),
                   params={"desde": DESDE, "hasta": HASTA})

    assert r.status_code == 200
    paginas = [p.extract_text().strip() for p in PdfReader(BytesIO(r.content)).pages]
    assert len(paginas) <= 3, f"el informe salió de {len(paginas)} páginas"
    # Una página sana de este informe trae 700 caracteres o más; una del
    # desborde traía 80 (el encabezado, el pie y una sola fila). La última
    # queda afuera: es normal que cierre con poco.
    for numero, texto in enumerate(paginas[:-1], start=1):
        assert len(texto) > 300, (
            f"la página {numero} quedó casi vacía ({len(texto)} caracteres): "
            "la paginación se desbordó"
        )


def test_una_fila_de_dos_renglones_ocupa_el_alto_de_dos(client):
    """El alto de la fila se calcula **antes** de dibujarla, y de eso dependen
    dos cosas: que el corte de página sea exacto y que un asunto de dos
    renglones no se dibuje encima de la fila siguiente.

    Se mide la separación vertical real entre filas en el PDF, porque el
    síntoma de calcularlo mal es **superposición**, no páginas de más: el texto
    sigue estando y se extrae igual, así que ni el conteo de páginas ni la
    búsqueda de una frase lo delatan. Medido: 34,3 pt con dos renglones contra
    21,3 con uno.
    """
    _login(client)
    cliente_id = client.post("/api/clientes", json={
        "nombre": "Envuelve SA", "email": "e@test.com",
    }).json()["id"]
    for n in range(5):
        tid = client.post("/api/incidencias", json={
            "cliente_id": cliente_id,
            "titulo": f"Titulo {n} suficientemente largo como para ocupar dos renglones",
        }).json()["id"]
        _fechar(client, tid, f"2026-01-0{n + 1}T09:00:00", None)

    r = client.get(RUTA.format(cliente_id=cliente_id),
                   params={"desde": DESDE, "hasta": HASTA})
    assert r.status_code == 200

    filas: list[float] = []

    def visitor(text, cm, tm, font_dict, font_size):
        limpio = text.strip()
        if limpio.startswith("#") and limpio[1:].isdigit():
            filas.append(tm[5])

    PdfReader(BytesIO(r.content)).pages[0].extract_text(visitor_text=visitor)

    assert len(filas) == 5, f"se ubicaron {len(filas)} filas en la página 1"
    for anterior, siguiente in zip(filas, filas[1:]):
        separacion = anterior - siguiente
        assert separacion > 28, (
            f"las filas quedaron a {separacion:.1f} pt: el asunto de dos "
            "renglones se dibuja encima de la fila siguiente"
        )


def _informe_sintetico(n_incidencias: int, n_garantias: int, n_service: int) -> dict:
    """Un informe armado a mano, para barrer tamaños sin pagar el costo de
    crear todo por la API."""
    return {
        "cliente": {"id": 1, "nombre": "Prueba SA", "contacto": None,
                    "cuit": None, "domicilio": None, "ciudad": None,
                    "email": None, "telefono": None},
        "periodo": {"desde": DESDE, "hasta": HASTA, "emitido": "2026-02-01"},
        "resumen": {"recibidas": n_incidencias, "resueltas": 0,
                    "pendientes": n_incidencias, "horas": 0.0, "actividades": 0,
                    "promedio_resolucion_horas": None, "por_categoria": []},
        "incidencias": [
            {"id": i, "titulo": f"Incidencia {i} con un asunto de dos renglones",
             "categoria": None, "equipo": "PC de escritorio Lenovo ThinkCentre",
             "sector": None, "fecha_creacion": datetime(2026, 1, 5, 9),
             "fecha_cierre": None, "cerrada": False, "resuelta_en_periodo": False,
             "creada_en_periodo": True, "horas": 0.0, "actividades": 0,
             "resolucion": None}
            for i in range(n_incidencias)],
        "parque": {"por_estado": {"activo": 8}, "total": 8, "bajas": 0,
                   "por_sector": [("Sector A", 8)], "por_tipo": [("PC", 8)]},
        "garantias": [
            {"equipo": f"Equipo con nombre largo {i}", "serial": f"S-{i}",
             "sector": "Administración",
             "garantia_vence": datetime(2026, 3, 1).date(), "dias_restantes": 29}
            for i in range(n_garantias)],
        "service": [
            {"equipo": f"Equipo en service {i}", "serial": f"SVC-{i}",
             "proveedor": "Compu Service", "fecha_envio": datetime(2026, 1, 10).date(),
             "fecha_retorno": None, "abierta": True, "dias_afuera": 9,
             "rma": None, "diagnostico": None}
            for i in range(n_service)],
        "dias_garantia": 60,
    }


def test_la_ultima_seccion_y_el_aviso_nunca_quedan_partidos():
    """🔴 Regresión de dos defectos encontrados mirando el PDF desplegado.

    1. El aviso de "documento no válido como factura" se dibujaba **a caballo**
       entre dos carillas: `_draw_no_fiscal_notice` traza las cuatro líneas
       punteadas y recién después escribe el texto, así que el salto automático
       dejaba el recuadro en una página y su contenido en la otra. Medido: en
       **2 de 3** informes reales de dev.
    2. Al reservarle lugar, apareció el otro: la sección de service quedaba con
       su título y su encabezado de columnas al pie de una carilla y las filas
       en la siguiente.

    **Barre el espacio en vez de apostar a un punto.** El defecto aparece sólo
    cuando la última sección cae cerca del pie, y acertar ese borde a mano ya
    falló antes en este mismo archivo: un test de paginación se escribió con 12
    incidencias y pasaba con el defecto puesto porque caía en la zona sana.
    Acá se prueban todas las combinaciones del rango, así que no hay borde que
    errar.
    """
    from app.services.informe_pdf import generar

    # El rango de `service` llega hasta 14 a propósito: con pocos, la reserva
    # del **título** ya alcanza para que todo entre, y la de la **tabla** —que
    # es la que importa cuando las filas obligan a cortar— quedaría sin
    # ejercitar. Se verificó forzando el fallo: con el tope en 3, revertirla no
    # ponía nada en rojo.
    for n_inc in range(0, 13):
        for n_gar in (0, 3, 6, 9):
            for n_svc in (0, 1, 3, 14):
                informe = _informe_sintetico(n_inc, n_gar, n_svc)
                paginas = [p.extract_text()
                           for p in PdfReader(BytesIO(generar(informe))).pages]
                caso = f"{n_inc} incidencias, {n_gar} garantías, {n_svc} service"

                def pagina_con(texto, _p=paginas):
                    return next((i for i, t in enumerate(_p) if texto in t), None)

                titulo = pagina_con("Equipos en service")
                aviso = pagina_con("NO VÁLIDO COMO FACTURA")
                assert titulo is not None, f"falta la sección de service ({caso})"

                # El aviso va con el FINAL de la sección, no con su título: si
                # la tabla se parte en dos carillas —cosa legítima— el título
                # queda arriba y el cierre abajo. Exigir que coincidieran con
                # el título era una aserción mal escrita, y el barrido la
                # delató con 14 filas de service.
                ultima = pagina_con(f"SVC-{n_svc - 1}") if n_svc else titulo
                assert aviso == ultima, (
                    f"el aviso quedó en la página {aviso} y la última fila de "
                    f"service en la {ultima} ({caso})")

                if n_svc:
                    primera = pagina_con("SVC-0")
                    assert primera == titulo, (
                        f"el título de service quedó en la página {titulo} y "
                        f"sus filas arrancan en la {primera} ({caso})")


def test_el_informe_hereda_la_base_segura_de_libracore():
    """`InformePDF` extiende `_TextoSeguroPDF`, y de ahí sale que ningún
    carácter pueda tumbar la generación.

    **Esto reemplazó a un saneo propio de este módulo.** Cuando el informe se
    escribió, `libracore` estaba pineado en v1.6.0, cuyas fuentes core
    codificaban en latin-1 y levantaban `UnicodeEncodeError` ante un guión
    largo; había acá un `_latin1()` que degradaba `—` a `-` y `…` a `...`. La
    v1.8.0 trae la base con `cp1252`, que los **dibuja**, así que heredar es
    menos código y además mejor resultado.

    Lo que este test fija es justamente eso: que la herencia siga en pie. Si
    alguien vuelve a poner `FPDF` como base, un guión largo en el título de un
    ticket devuelve 500 otra vez.
    """
    from libracore.pdf_generator import _TextoSeguroPDF

    from app.services.informe_pdf import InformePDF

    assert issubclass(InformePDF, _TextoSeguroPDF)

    pdf = InformePDF({"nombre": "X"}, {"desde": DESDE, "hasta": HASTA,
                                       "emitido": DESDE})
    pdf.add_page()

    # Se dibujan tal cual: cp1252 los tiene. (El `™` también, en 0x99 — lo que
    # uno cree que es "raro" a menudo entra; por eso el caso de abajo usa una
    # flecha, que de verdad no está.)
    assert pdf.normalize_text("raya — y elipsis …") == "raya \x97 y elipsis \x85"
    assert pdf.normalize_text("marca ™") == "marca \x99"
    # Y lo que no entra ni en cp1252 se translitera en vez de romper.
    assert pdf.normalize_text("flecha →") == "flecha ->"
    assert pdf.normalize_text("vocal ā") == "vocal a"


# ── El contrato con LibraCore ──────────────────────────────────────

def test_el_membrete_de_libracore_sigue_exponiendo_lo_que_usamos():
    """`informe_pdf` importa nombres privados de `libracore.pdf_generator` —
    el mismo patrón que el shim de Contalibra. El pin es exacto, así que no
    puede cambiar solo; este test hace que un bump que se lleve puesto alguno
    falle acá, en el CI, y no la primera vez que alguien pida un informe."""
    from libracore import pdf_generator

    for nombre in ("_draw_header_block", "_draw_emisor_cliente",
                   "_draw_no_fiscal_notice", "_empresa", "_rrect", "_wrap_text",
                   "_LX", "_RX", "_CW", "_INK", "_MUTED", "_LINE",
                   "_ACCENT_SOFT", "_ACCENT_DARK"):
        assert hasattr(pdf_generator, nombre), \
            f"libracore ya no expone {nombre!r}: revisar app/services/informe_pdf.py"
