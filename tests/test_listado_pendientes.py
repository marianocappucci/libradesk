"""El listado de reclamos pendientes: el papel con el que se arma el día.

**Qué se afirma acá y por qué se lee el PDF de vuelta.** Todo lo que esta
funcionalidad agrega termina *impreso*: el teléfono de contacto, el reclamante,
la descripción larga, el domicilio y el casillero para repartir. Un test que
mirara sólo el `Content-Type` o el JSON pasaría con el papel vacío, que es el
modo de falla que importa — el circuito de Lagrace empieza con esta hoja, así
que una hoja sin teléfonos no sirve aunque el endpoint devuelva 200.

Mismo criterio que `test_hoja_ruta.py`, y por el mismo motivo.

**Y la diferencia con esa hoja es lo que más se testea acá**: un reclamo **sin
agendar** —sin cuadrilla y sin fecha programada— tiene que salir en este papel,
porque es exactamente el que la hoja de ruta no puede mostrar.
"""
import os
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


def texto_pdf(contenido: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)


@pytest.fixture
def escenario(client):
    """Tres clientes con datos distintos a propósito.

    `metalmax` está completo; `sin_datos` no tiene ni domicilio ni teléfono —es
    el caso que el papel tiene que *decir* en vez de callar—; `otra_localidad`
    existe para probar el filtro y el orden por localidad.
    """
    metalmax = client.post("/api/clientes", json={
        "nombre": "Metalmax Soluciones",
        "domicilio": "Av. San Martín 1240",
        "ciudad": "Suipacha",
        "telefono": "2324401234",
    }).json()
    sin_datos = client.post("/api/clientes", json={
        "nombre": "Panadería La Nueva",
    }).json()
    otra_localidad = client.post("/api/clientes", json={
        "nombre": "Frigorífico del Oeste",
        "domicilio": "Ruta 5 km 118",
        "ciudad": "Chivilcoy",
        "telefono": "2346551122",
    }).json()
    return {
        "metalmax": metalmax,
        "sin_datos": sin_datos,
        "otra_localidad": otra_localidad,
    }


def reclamo(client, cliente, titulo, **extra):
    cuerpo = {"cliente_id": cliente["id"], "titulo": titulo, **extra}
    r = client.post("/api/incidencias", json=cuerpo)
    assert r.status_code == 201, r.text
    return r.json()


def pedir(client, **params):
    query = "&".join(f"{k}={v}" for k, v in params.items())
    return client.get(f"/api/incidencias/pendientes.pdf{'?' + query if query else ''}")


# ── Lo que el listado tiene que decir ───────────────────────────────────────

def test_lleva_telefono_reclamante_domicilio_y_descripcion(client, escenario):
    """**El test central.** Son los cuatro datos que el pedido nombró.

    El teléfono va *"por si llegan y está cerrado"* y el reclamante es a quién
    preguntarle al llegar; ninguno de los dos salía impreso en ningún papel del
    producto antes de esto. La hoja de ruta lleva domicilio y no lleva estos dos.
    """
    reclamo(
        client, escenario["metalmax"], "Central sin tono",
        descripcion="No da tono en los internos 5 y 7 desde el corte de luz.",
        reclamante="FACUNDO",
    )

    r = pedir(client)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    texto = texto_pdf(r.content)

    assert "Metalmax Soluciones" in texto
    assert "Av. San Martín 1240" in texto
    assert "2324401234" in texto
    assert "FACUNDO" in texto
    assert "Central sin tono" in texto
    assert "internos 5 y 7" in texto


def test_un_reclamo_sin_agendar_igual_sale(client, escenario):
    """🔑 **Es la razón de existir de este papel.**

    Un reclamo sin `equipo_trabajo_id` y sin `fecha_programada` **no aparece en
    ninguna hoja de ruta**, porque aquélla es `equipo × día`. Y es justo el que
    hay que mirar para armar el día: el que todavía nadie asignó.
    """
    creado = reclamo(client, escenario["metalmax"], "Cableado nuevo en depósito")
    assert creado["equipo_trabajo_id"] is None
    assert creado["fecha_programada"] is None

    assert "Cableado nuevo en depósito" in texto_pdf(pedir(client).content)


def test_un_reclamo_ya_agendado_sale_y_lo_dice(client, escenario):
    """Sigue pendiente hasta que se haga, así que no se lo saca del listado —
    pero se avisa, para que nadie lo planifique dos veces.
    """
    reclamo(
        client, escenario["metalmax"], "Revisión de UPS",
        fecha_programada="2026-09-10T09:30:00",
    )
    texto = texto_pdf(pedir(client).content)
    assert "Revisión de UPS" in texto
    assert "10-09-2026 09:30" in texto


def test_un_cliente_sin_domicilio_ni_telefono_lo_dice(client, escenario):
    """Los dos huecos se dicen con todas las letras y no se omiten.

    🔑 **El del teléfono es el que importa.** Un renglón que lo omitiera en
    silencio se lee igual que uno con el teléfono cargado más abajo, y quien
    intenta llamar antes de salir no tiene cómo saber que no hay a quién.
    """
    reclamo(client, escenario["sin_datos"], "No enciende la central")
    texto = texto_pdf(pedir(client).content)
    assert "sin domicilio cargado" in texto
    assert "sin teléfono cargado" in texto


def test_la_ciudad_no_se_repite_si_ya_esta_en_el_domicilio(client):
    """La regla se reusa de `hoja_ruta_pdf.direccion()`, no se reescribe.

    Es el defecto que apareció con los datos reales de la demo: los clientes
    cargan la ciudad **dentro** del domicilio y además en su campo, así que
    pegar los dos daba `Av. Pueyrredón 1640, CABA, CABA`.
    """
    cliente = client.post("/api/clientes", json={
        "nombre": "Estudio Pueyrredón",
        "domicilio": "Av. Pueyrredón 1640, CABA",
        "ciudad": "CABA",
    }).json()
    reclamo(client, cliente, "Router colgado")

    texto = texto_pdf(pedir(client).content)
    assert "Av. Pueyrredón 1640, CABA" in texto
    assert "CABA, CABA" not in texto


def test_la_descripcion_larga_se_corta_y_avisa(client, escenario):
    """Hay tope aunque el pedido diga "descripción larga", y se ve que hubo corte.

    Sin tope, una descripción pegada de un mail se lleva la carilla entera y
    empuja los otros reclamos abajo de todo — que es lo que este papel viene a
    evitar. El `[…]` es lo que distingue "esto es todo" de "hay más en la ficha".
    """
    from app.services.pendientes_pdf import _MAX_LINEAS_DESCRIPCION

    # Palabras largas y distintas para forzar el envoltorio en muchos renglones.
    larga = " ".join(f"renglon{n:03d}" for n in range(400))
    reclamo(client, escenario["metalmax"], "Relevamiento", descripcion=larga)

    texto = texto_pdf(pedir(client).content)
    assert "[…]" in texto
    assert "renglon000" in texto
    # El corte es real: el final de una descripción de 400 palabras no llega.
    assert "renglon399" not in texto
    assert _MAX_LINEAS_DESCRIPCION == 10


# ── Qué entra y qué no ──────────────────────────────────────────────────────

@pytest.mark.parametrize("estado,esta", [
    ("abierto", True),
    ("en_progreso", True),
    ("resuelta", False),
    ("cerrado", False),
])
def test_solo_los_estados_que_todavia_hay_que_ir_a_hacer(
    client, escenario, estado, esta,
):
    """🔑 **`resuelta` NO es pendiente, y es la decisión del listado.**

    En este producto `resuelta` es "el técnico ya terminó" y lo que falta es el
    control de oficina contra el CDS. Mandarlo al papel manda a la cuadrilla a
    un domicilio donde no hay nada que hacer.
    """
    creado = reclamo(client, escenario["metalmax"], f"Trabajo {estado}")
    r = client.put(f"/api/incidencias/{creado['id']}", json={
        "cliente_id": escenario["metalmax"]["id"],
        "titulo": f"Trabajo {estado}",
        "estado": estado,
    })
    assert r.status_code == 200, r.text

    texto = texto_pdf(pedir(client).content)
    assert (f"Trabajo {estado}" in texto) is esta


def test_un_reclamo_borrado_no_entra(client, escenario):
    """⚠️ **Esto NO prueba ningún filtro del listado**, y conviene decirlo.

    El `DELETE` de este producto borra la fila, así que el reclamo desaparece
    de cualquier consulta. La primera versión del listado traía un
    `.where(Incidencia.activo)` que este test parecía cubrir; mutarlo dejó el
    test en verde, y ahí se vio que la columna no la escribe nadie. El filtro
    se sacó. Lo que queda acá es una regresión del endpoint, no de una guarda.
    """
    creado = reclamo(client, escenario["metalmax"], "Alta por error")
    assert client.delete(f"/api/incidencias/{creado['id']}").status_code == 204

    assert "Alta por error" not in texto_pdf(pedir(client).content)


def test_la_bandeja_vacia_lo_dice(client, escenario):
    """Una grilla con encabezado y nada abajo se lee como que la consulta falló."""
    assert "Sin reclamos pendientes." in texto_pdf(pedir(client).content)


def test_la_bandeja_vacia_por_el_filtro_dice_cual(client, escenario):
    """Filtrar por una localidad mal escrita no puede dar el mismo papel que no
    tener nada pendiente: son dos cosas muy distintas de leer un lunes."""
    reclamo(client, escenario["metalmax"], "Central sin tono")

    texto = texto_pdf(pedir(client, ciudad="Mercedes").content)
    assert "Sin reclamos pendientes en Mercedes." in texto


# ── El orden y el filtro ────────────────────────────────────────────────────

def test_por_defecto_el_que_espera_hace_mas_manda(client, escenario):
    """El default es antigüedad: el reclamo más viejo primero.

    Se fuerza la fecha de creación por la base porque el alta la estampa el
    motor —`server_default=func.now()`— y los tres saldrían del mismo segundo.
    """
    viejo = reclamo(client, escenario["metalmax"], "Reclamo viejo")
    nuevo = reclamo(client, escenario["metalmax"], "Reclamo nuevo")
    _envejecer(client, viejo["id"], "2026-01-15 09:00:00")
    _envejecer(client, nuevo["id"], "2026-09-01 09:00:00")

    texto = texto_pdf(pedir(client).content)
    assert texto.index("Reclamo viejo") < texto.index("Reclamo nuevo")


def test_la_antiguedad_nunca_es_negativa(client, escenario):
    """🔴 **El reclamo más nuevo llegaba a imprimir `-1 d`.**

    `fecha_creacion` la estampa el motor y el "ahora" lo da el proceso: son dos
    relojes. Con el motor un segundo adelante, `.days` de un `timedelta`
    negativo chico es **-1**, no 0. Se descubrió con el PostgreSQL de prueba
    sin `TZ` —tres horas de diferencia—, pero alcanza un segundo de desfasaje
    para que pase en producción.

    Se prueba adelantando la fecha de ingreso a propósito, así el test no
    depende de la zona horaria del contenedor que corre la suite.
    """
    creado = reclamo(client, escenario["metalmax"], "Recién cargado")
    _envejecer(client, creado["id"], "2030-01-01 09:00:00")

    texto = texto_pdf(pedir(client).content)
    assert "(-1 d)" not in texto
    assert "(0 d)" in texto


def test_el_orden_por_localidad_agrupa_y_deja_los_sin_localidad_al_final(
    client, escenario,
):
    """`Chivilcoy` antes que `Suipacha`, y el cliente sin localidad **último**.

    Los sin localidad al final y no adelante: son los que hay que resolver a
    mano, no los primeros que se reparten.
    """
    reclamo(client, escenario["metalmax"], "Trabajo en Suipacha")
    reclamo(client, escenario["otra_localidad"], "Trabajo en Chivilcoy")
    reclamo(client, escenario["sin_datos"], "Trabajo sin localidad")

    texto = texto_pdf(pedir(client, orden="localidad").content)
    assert texto.index("Trabajo en Chivilcoy") < texto.index("Trabajo en Suipacha")
    assert texto.index("Trabajo en Suipacha") < texto.index("Trabajo sin localidad")


def test_el_orden_por_prioridad_no_es_alfabetico(client, escenario):
    """`alta, media, baja`. Un `ORDER BY` alfabético daría `alta, baja, media`,
    que pone lo menos urgente en el medio — y ése es el error que este test mata.
    """
    for prioridad in ("baja", "alta", "media"):
        creado = reclamo(client, escenario["metalmax"], f"Trabajo {prioridad}")
        client.put(f"/api/incidencias/{creado['id']}", json={
            "cliente_id": escenario["metalmax"]["id"],
            "titulo": f"Trabajo {prioridad}",
            "prioridad": prioridad,
        })

    texto = texto_pdf(pedir(client, orden="prioridad").content)
    assert texto.index("Trabajo alta") < texto.index("Trabajo media")
    assert texto.index("Trabajo media") < texto.index("Trabajo baja")


def test_el_filtro_por_localidad_deja_afuera_al_resto(client, escenario):
    reclamo(client, escenario["metalmax"], "Trabajo en Suipacha")
    reclamo(client, escenario["otra_localidad"], "Trabajo en Chivilcoy")

    texto = texto_pdf(pedir(client, ciudad="Chivilcoy").content)
    assert "Trabajo en Chivilcoy" in texto
    assert "Trabajo en Suipacha" not in texto


def test_el_filtro_por_localidad_no_distingue_mayusculas(client, escenario):
    """`clients.ciudad` es texto libre: en los datos reales conviven `Chivilcoy`
    y `CHIVILCOY`, y un filtro exacto imprime media localidad."""
    otro = client.post("/api/clientes", json={
        "nombre": "Taller CHIVILCOY", "ciudad": "CHIVILCOY",
    }).json()
    reclamo(client, escenario["otra_localidad"], "Trabajo en Chivilcoy")
    reclamo(client, otro, "Trabajo en CHIVILCOY")

    texto = texto_pdf(pedir(client, ciudad="chivilcoy").content)
    assert "Trabajo en Chivilcoy" in texto
    assert "Trabajo en CHIVILCOY" in texto


def test_un_orden_invalido_da_422_y_dice_cuales_valen(client, escenario):
    r = pedir(client, orden="por_color")
    assert r.status_code == 422
    assert "antiguedad" in r.text


# ── El membrete ─────────────────────────────────────────────────────────────

def test_el_membrete_dice_cuantos_son_y_como_estan_ordenados(client, escenario):
    """Sin esto, dos impresiones del mismo día con órdenes distintos son dos
    papeles idénticos de mirar y distintos de leer."""
    reclamo(client, escenario["metalmax"], "Central sin tono")
    reclamo(client, escenario["otra_localidad"], "Cambio de switch")

    texto = texto_pdf(pedir(client, orden="localidad", ciudad="Chivilcoy").content)
    assert "Localidad" in texto
    assert "Chivilcoy" in texto


def _envejecer(client, incidencia_id: int, cuando: str) -> None:
    """Le mueve la `fecha_creacion` a un reclamo, por SQL.

    No hay endpoint que lo permita —y está bien que no lo haya: la fecha de
    ingreso la estampa el motor—, pero el orden por antigüedad no se puede
    probar con dos reclamos creados en el mismo segundo.

    Va por el engine de la app y no por `sqlite3.connect(ruta)`, mismo motivo
    que `test_dashboard_operativo.py`: la suite corre contra PostgreSQL, donde
    no hay archivo que abrir.
    """
    from sqlalchemy import text

    from app import database

    with database.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE incidencias SET fecha_creacion = :cuando WHERE id = :id"),
            {"cuando": cuando, "id": incidencia_id},
        )
