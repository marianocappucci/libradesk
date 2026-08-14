"""La hoja de ruta del equipo (el papel que faltaba del circuito).

**Qué se afirma acá y por qué se lee el PDF de vuelta.** Todo lo que esta
funcionalidad agrega termina *impreso*: el domicilio de cada parada, el orden,
la patente, los renglones en blanco para completar en la calle. Un test que
mirara sólo el `Content-Type` o el JSON pasaría con el papel vacío, que es
exactamente el modo de falla que importa — el circuito de Lagrace controla el
parte **contra esta hoja**, así que una hoja sin domicilios no sirve aunque el
endpoint devuelva 200.

Por eso casi todos leen el texto extraído con `pypdf`. Es el mismo criterio que
`test_cds_y_materiales.py` ya usa para los N° CDS del remito, y por el mismo
motivo.
"""
import os
from datetime import datetime
from io import BytesIO

import pytest
from pypdf import PdfReader


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin."""
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


MARTES = "2026-08-11"
MIERCOLES = "2026-08-12"


def texto_pdf(contenido: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)


@pytest.fixture
def escenario(client):
    """Una cuadrilla con responsable, un integrante, una Kangoo y dos clientes.

    El segundo cliente va **sin domicilio** a propósito: es el caso que la hoja
    tiene que decir en vez de callar.
    """
    metalmax = client.post("/api/clientes", json={
        "nombre": "Metalmax Soluciones",
        "domicilio": "Av. San Martín 1240",
        "ciudad": "Suipacha",
    }).json()
    sin_domicilio = client.post("/api/clientes", json={
        "nombre": "Panadería La Nueva",
    }).json()
    jefe = client.post("/api/tecnicos", json={
        "nombre": "Rubén Actis", "es_tecnico": True, "es_responsable": True,
    }).json()
    peon = client.post("/api/tecnicos", json={
        "nombre": "Nadia Ferreyra", "es_tecnico": True,
    }).json()
    # Los integrantes van en el alta del equipo, no por un endpoint propio: la
    # lista entera se reemplaza en cada escritura para no dejar fantasmas al
    # sacar dos personas a la vez (ver `routers/equipos_trabajo.py`).
    r_norte = client.post("/api/equipos-trabajo", json={
        "nombre": "Cuadrilla Norte", "responsable_id": jefe["id"],
        "integrantes": [peon["id"]],
    })
    assert r_norte.status_code == 201, r_norte.text
    norte = r_norte.json()
    kangoo = client.post("/api/equipos-trabajo/vehiculos", json={
        "patente": "AB123CD", "marca": "Renault", "modelo": "Kangoo",
    }).json()
    client.post(f"/api/equipos-trabajo/vehiculos/{kangoo['id']}/asignar",
                json={"equipo_id": norte["id"]})
    return {
        "metalmax": metalmax, "sin_domicilio": sin_domicilio,
        "jefe": jefe, "peon": peon, "norte": norte, "kangoo": kangoo,
    }


def agendar(client, escenario, *, cliente, hora, titulo, minutos=60,
            modalidad=None, equipo=None):
    cuerpo = {
        "cliente_id": cliente["id"],
        "titulo": titulo,
        "fecha_programada": hora,
        "duracion_minutos": minutos,
        "equipo_trabajo_id": (equipo or escenario["norte"])["id"],
    }
    if modalidad:
        cuerpo["modalidad"] = modalidad
    r = client.post("/api/incidencias", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


def pedir_hoja(client, escenario, dia=MARTES, equipo=None):
    equipo_id = (equipo or escenario["norte"])["id"]
    return client.get(f"/api/agenda/equipo/{equipo_id}/hoja-de-ruta?dia={dia}")


# ── Lo que la hoja tiene que decir ──────────────────────────────────────────

def test_la_hoja_lleva_el_domicilio_de_cada_parada(client, escenario):
    """**El test central.** Es lo que separa una agenda de una hoja de ruta.

    Antes de esto `agenda_del_equipo()` devolvía el nombre del cliente y no su
    dirección, así que la lista decía a quién visitar y no dónde queda.
    """
    agendar(client, escenario, cliente=escenario["metalmax"],
            hora=f"{MARTES}T08:30", titulo="Central sin tono")

    r = pedir_hoja(client, escenario)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"

    texto = texto_pdf(r.content)
    assert "Av. San Martín 1240" in texto
    assert "Suipacha" in texto


def test_un_cliente_sin_domicilio_lo_dice_en_la_hoja(client, escenario):
    """Un renglón en blanco se lee como un error de impresión."""
    agendar(client, escenario, cliente=escenario["sin_domicilio"],
            hora=f"{MARTES}T09:00", titulo="Cambio de router")

    texto = texto_pdf(pedir_hoja(client, escenario).content)
    assert "sin domicilio cargado" in texto


def test_las_paradas_salen_en_orden_de_hora(client, escenario):
    """Se cargan al revés a propósito: si el orden saliera del alta y no de la
    hora agendada, este test lo agarra y ningún otro lo haría.
    """
    agendar(client, escenario, cliente=escenario["sin_domicilio"],
            hora=f"{MARTES}T15:00", titulo="Trabajo de la tarde")
    agendar(client, escenario, cliente=escenario["metalmax"],
            hora=f"{MARTES}T08:30", titulo="Trabajo de la mañana")

    texto = texto_pdf(pedir_hoja(client, escenario).content)
    assert texto.index("Trabajo de la mañana") < texto.index("Trabajo de la tarde")


def test_lleva_el_vehiculo_el_responsable_y_los_integrantes(client, escenario):
    """Los tres contestan «quién sale y en qué», que es la cabecera del papel."""
    agendar(client, escenario, cliente=escenario["metalmax"],
            hora=f"{MARTES}T08:30", titulo="Central sin tono")

    texto = texto_pdf(pedir_hoja(client, escenario).content)
    assert "AB123CD" in texto
    assert "Kangoo" in texto
    assert "Rubén Actis" in texto
    assert "Nadia Ferreyra" in texto


def test_lleva_los_renglones_que_se_completan_en_la_calle(client, escenario):
    """El kilometraje y las horas reales son el insumo del control de María
    contra el satelital. Sin ellos la hoja es una lista de tareas, no un parte.
    """
    agendar(client, escenario, cliente=escenario["metalmax"],
            hora=f"{MARTES}T08:30", titulo="Central sin tono")

    texto = texto_pdf(pedir_hoja(client, escenario).content)
    assert "LLEGADA" in texto
    assert "SALIDA" in texto
    assert "Km al salir" in texto
    assert "Km al regresar" in texto
    assert "Firma del responsable del equipo" in texto


# ── Lo que la hoja tiene que dejar afuera ───────────────────────────────────

def test_un_trabajo_remoto_no_es_una_parada(client, escenario):
    """Ocupa la agenda del equipo pero no es una parada de la camioneta.

    Si entrara, el control contra el satelital tendría una fila que no puede
    cerrar nunca: no hubo viaje.
    """
    agendar(client, escenario, cliente=escenario["metalmax"],
            hora=f"{MARTES}T08:30", titulo="Central sin tono")
    agendar(client, escenario, cliente=escenario["sin_domicilio"],
            hora=f"{MARTES}T11:00", titulo="Reseteo por acceso remoto",
            modalidad="remoto")

    texto = texto_pdf(pedir_hoja(client, escenario).content)
    assert "Central sin tono" in texto
    assert "Reseteo por acceso remoto" not in texto
    assert "Paradas: 1" in texto.replace("\n", " ")


def test_la_hoja_es_de_un_solo_dia(client, escenario):
    agendar(client, escenario, cliente=escenario["metalmax"],
            hora=f"{MARTES}T08:30", titulo="Trabajo del martes")
    agendar(client, escenario, cliente=escenario["metalmax"],
            hora=f"{MIERCOLES}T08:30", titulo="Trabajo del miércoles")

    texto = texto_pdf(pedir_hoja(client, escenario, dia=MARTES).content)
    assert "Trabajo del martes" in texto
    assert "Trabajo del miércoles" not in texto


def test_el_trabajo_de_otro_equipo_no_entra(client, escenario):
    sur = client.post("/api/equipos-trabajo", json={"nombre": "Cuadrilla Sur"}).json()
    agendar(client, escenario, cliente=escenario["metalmax"],
            hora=f"{MARTES}T08:30", titulo="Trabajo del Sur", equipo=sur)

    texto = texto_pdf(pedir_hoja(client, escenario).content)
    assert "Trabajo del Sur" not in texto


# ── Los bordes del endpoint ─────────────────────────────────────────────────

def test_un_equipo_sin_trabajos_ese_dia_igual_da_una_hoja(client, escenario):
    """Devolver 404 obligaría a la pantalla a distinguir «no hay equipo» de «no
    hay trabajos», que son dos cosas distintas con la misma cara.
    """
    r = pedir_hoja(client, escenario)
    assert r.status_code == 200, r.text
    assert "Sin trabajos agendados" in texto_pdf(r.content)


def test_un_equipo_que_no_existe_da_404(client):
    r = client.get("/api/agenda/equipo/99999/hoja-de-ruta?dia=" + MARTES)
    assert r.status_code == 404


def test_una_fecha_invalida_da_422(client, escenario):
    equipo_id = escenario["norte"]["id"]
    r = client.get(f"/api/agenda/equipo/{equipo_id}/hoja-de-ruta?dia=11-08-2026")
    assert r.status_code == 422


def test_sin_dia_no_se_adivina_hoy(client, escenario):
    """`dia` es obligatorio. Un default a hoy haría que un click distraído
    imprimiera la hoja equivocada sin decir nada.
    """
    equipo_id = escenario["norte"]["id"]
    assert client.get(f"/api/agenda/equipo/{equipo_id}/hoja-de-ruta").status_code == 422


# ── La agenda de pantalla, que ahora también trae el domicilio ──────────────

def test_la_agenda_en_pantalla_tambien_devuelve_el_domicilio(client, escenario):
    """El recorrido se decide mirando la agenda del día, no el PDF. Decidirlo
    sin ver dónde queda cada trabajo es la misma carencia con otra ropa.
    """
    agendar(client, escenario, cliente=escenario["metalmax"],
            hora=f"{MARTES}T08:30", titulo="Central sin tono")

    equipo_id = escenario["norte"]["id"]
    r = client.get(f"/api/agenda/equipo/{equipo_id}?desde={MARTES}&dias=1")
    assert r.status_code == 200, r.text
    fila = r.json()[0]
    assert fila["cliente_domicilio"] == "Av. San Martín 1240"
    assert fila["cliente_ciudad"] == "Suipacha"
