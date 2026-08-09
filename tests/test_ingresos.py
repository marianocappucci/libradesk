"""Comprobante de recepción y de entrega de equipo (pedido 43).

Lo que estos tests fijan, en orden de qué duele más si se rompe:

1. **Los datos del equipo quedan congelados en el comprobante.** Si se leyeran
   por FK, corregir el modelo en el inventario cambiaría retroactivamente un
   papel que el cliente ya firmó.
2. **No se puede entregar dos veces**, ni borrar algo ya entregado: el segundo
   número diría algo que no pasó, y el papel está en manos del cliente.
3. **`fecha_entrega IS NULL` es "está en el taller"** y no puede mentir.
4. Los correlativos son dos y no se pisan.
"""
import os
from datetime import datetime

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
def escenario(client):
    cliente = client.post("/api/clientes", json={
        "nombre": "Estudio Sur", "cuit": "30-11111111-1",
        "domicilio": "Suipacha 123", "telefono": "3514567890",
    }).json()
    equipo = client.post("/api/equipos", json={
        "cliente_id": cliente["id"], "tipo": "Notebook", "marca": "Lenovo",
        "modelo": "ThinkPad T14", "serial": "LN-0001",
    }).json()
    tecnico = client.post("/api/tecnicos", json={
        "nombre": "Sofía Núñez", "es_tecnico": True,
    }).json()
    recep = client.post("/api/tecnicos", json={
        "nombre": "Lucía Fernández", "es_recepcionista": True,
    }).json()
    return {"cliente": cliente, "equipo": equipo, "tecnico": tecnico,
            "recepcionista": recep}


def _recibir(client, escenario, **extra):
    cuerpo = {
        "cliente_id": escenario["cliente"]["id"],
        "equipo_id": escenario["equipo"]["id"],
        "contacto": "Marta Ríos",
        "accesorios": "Cargador original, funda negra",
        "estado_fisico": "Tapa rayada en la esquina inferior derecha",
        "falla_declarada": "No enciende. Dice que se mojó.",
        "observaciones": "Faltan dos tornillos de la base (preexistente)",
        "tecnico_id": escenario["recepcionista"]["id"],
        "entregado_por": "Marta Ríos",
    }
    cuerpo.update(extra)
    return client.post("/api/ingresos-reparacion", json=cuerpo)


# ── Recibir ────────────────────────────────────────────────────────────────

def test_recibir_emite_el_comprobante_con_todo_lo_que_pidio_el_pedido(client, escenario):
    r = _recibir(client, escenario)
    assert r.status_code == 201, r.text
    i = r.json()

    assert i["numero"] == "REC-00000001"
    assert i["fecha_recepcion"] is not None
    assert i["cliente_nombre"] == "Estudio Sur"
    assert i["contacto"] == "Marta Ríos"
    assert (i["equipo_tipo"], i["equipo_marca"], i["equipo_modelo"], i["equipo_serial"]) \
        == ("Notebook", "Lenovo", "ThinkPad T14", "LN-0001")
    assert i["accesorios"].startswith("Cargador original")
    assert i["estado_fisico"].startswith("Tapa rayada")
    assert i["falla_declarada"].startswith("No enciende")
    assert i["observaciones"].startswith("Faltan dos tornillos")
    assert i["tecnico_nombre"] == "Lucía Fernández"
    assert i["entregado_por"] == "Marta Ríos"
    # Y lo derivado: todavía no se entregó.
    assert i["en_taller"] is True
    assert i["numero_entrega"] is None


def test_los_correlativos_avanzan_de_a_uno(client, escenario):
    assert _recibir(client, escenario).json()["numero"] == "REC-00000001"
    assert _recibir(client, escenario).json()["numero"] == "REC-00000002"


def test_un_equipo_de_mostrador_no_necesita_estar_en_el_inventario(client, escenario):
    """El caso que hace que `equipo_id` sea opcional: alguien trae una notebook
    que no es parte del parque que le administramos."""
    r = client.post("/api/ingresos-reparacion", json={
        "cliente_id": escenario["cliente"]["id"],
        "equipo_tipo": "Impresora", "equipo_marca": "HP",
        "equipo_modelo": "M404", "equipo_serial": "HP-9999",
        "falla_declarada": "Atasca el papel",
    })
    assert r.status_code == 201, r.text
    assert r.json()["equipo_id"] is None
    assert r.json()["equipo_descripcion"] == "Impresora HP M404"


def test_sin_tipo_de_equipo_no_hay_comprobante(client, escenario):
    """Un comprobante que no dice qué se recibió no sirve para nada."""
    r = client.post("/api/ingresos-reparacion", json={
        "cliente_id": escenario["cliente"]["id"], "falla_declarada": "Algo",
    })
    assert r.status_code == 422
    assert "qué se recibió" in r.json()["detail"]


def test_los_datos_del_equipo_se_pueden_pisar_a_mano(client, escenario):
    """El inventario dice una cosa y el mostrador ve otra —una etiqueta de serie
    distinta de la cargada—. Manda lo que se ve, porque es lo que se firma."""
    r = _recibir(client, escenario, equipo_serial="LN-CORREGIDO")
    assert r.json()["equipo_serial"] == "LN-CORREGIDO"
    # Y lo que no se pisó igual salió del inventario.
    assert r.json()["equipo_marca"] == "Lenovo"


# ── 🔴 Lo congelado ────────────────────────────────────────────────────────

def test_corregir_el_equipo_en_el_inventario_NO_cambia_el_comprobante(client, escenario):
    """El corazón del diseño. Si esto falla, un papel firmado cambia solo."""
    i = _recibir(client, escenario).json()

    client.put(f"/api/equipos/{escenario['equipo']['id']}", json={
        "cliente_id": escenario["cliente"]["id"], "tipo": "Notebook",
        "marca": "Lenovo", "modelo": "ThinkPad T14 GEN 3",
        "serial": "LN-OTRO-SERIAL",
    })

    despues = client.get(f"/api/ingresos-reparacion/{i['id']}").json()
    assert despues["equipo_modelo"] == "ThinkPad T14"
    assert despues["equipo_serial"] == "LN-0001"


def test_un_equipo_con_comprobante_no_se_borra(client, escenario):
    """El comprobante dice qué se recibió, que es su única razón de existir, y
    el equipo no se lo lleva puesto.

    🔴 Este test decía otra cosa hasta el 2026-08-09: borraba el equipo, veía
    que el comprobante seguía respondiendo 200 y lo daba por bueno. **El
    comprobante quedaba apuntando a un equipo inexistente**, y sólo se leía
    bien porque guarda el serial desnormalizado. Pasaba porque el pragma
    `foreign_keys` está apagado en SQLite; contra PostgreSQL el DELETE muere
    con `ForeignKeyViolation`.

    Ahora un equipo con papeles no se borra —para sacarlo de circulación está
    el estado `baja`— y se asiertan las dos mitades: que el borrado se rechaza
    y que el comprobante sigue completo.
    """
    i = _recibir(client, escenario).json()

    r = client.delete(f"/api/equipos/{escenario['equipo']['id']}")
    assert r.status_code == 409, r.text
    assert "comprobantes_de_ingreso" in r.text

    despues = client.get(f"/api/ingresos-reparacion/{i['id']}")
    assert despues.status_code == 200
    assert despues.json()["equipo_serial"] == "LN-0001"
    # Y el equipo sigue estando: el rechazo no lo dejó a medio borrar.
    assert client.get(f"/api/equipos/{escenario['equipo']['id']}").status_code == 200


def test_un_equipo_sin_papeles_se_sigue_borrando(client, escenario):
    """Contraprueba de la guarda de arriba.

    Sin esto, un `delete` que devolviera 409 SIEMPRE —por un bug en el conteo
    de dependencias— dejaría verde al test anterior, y nadie podría borrar un
    equipo cargado por error.
    """
    r = client.delete(f"/api/equipos/{escenario['equipo']['id']}")
    assert r.status_code == 204, r.text
    assert client.get(f"/api/equipos/{escenario['equipo']['id']}").status_code == 404


# ── Entregar ───────────────────────────────────────────────────────────────

def test_entregar_emite_el_segundo_comprobante_y_cierra_el_ingreso(client, escenario):
    i = _recibir(client, escenario).json()
    r = client.post(f"/api/ingresos-reparacion/{i['id']}/entregar", json={
        "retirado_por": "Marta Ríos",
        "trabajo_realizado": "Se limpió la placa y se cambió el teclado.",
        "tecnico_entrega_id": escenario["tecnico"]["id"],
    })
    assert r.status_code == 200, r.text
    e = r.json()

    assert e["numero_entrega"] == "ENT-00000001"
    # El de recepción NO cambia: los dos papeles se cruzan por él.
    assert e["numero"] == i["numero"]
    assert e["fecha_entrega"] is not None
    assert e["retirado_por"] == "Marta Ríos"
    assert e["tecnico_entrega_nombre"] == "Sofía Núñez"
    assert e["en_taller"] is False


def test_no_se_puede_entregar_dos_veces(client, escenario):
    """El segundo comprobante diría algo que no pasó, y llevaría un número
    correlativo gastado."""
    i = _recibir(client, escenario).json()
    client.post(f"/api/ingresos-reparacion/{i['id']}/entregar", json={})

    r = client.post(f"/api/ingresos-reparacion/{i['id']}/entregar", json={})
    assert r.status_code == 409
    assert "ya se entregó" in r.json()["detail"]


def test_corregir_la_recepcion_no_puede_fabricar_una_entrega(client, escenario):
    """`PUT` es para arreglar lo que se tipeó mal en el mostrador. Si aceptara
    los campos de la entrega, se podría cerrar un ingreso **sin emitir el
    comprobante**, que es justo lo que el cliente se lleva."""
    i = _recibir(client, escenario).json()
    r = client.put(f"/api/ingresos-reparacion/{i['id']}", json={
        "cliente_id": escenario["cliente"]["id"],
        "equipo_tipo": "Notebook",
        "accesorios": "Cargador original (sin funda, se la llevó)",
        # Esto tiene que ser ignorado.
        "fecha_entrega": datetime(2026, 8, 5, 12, 0).isoformat(),
        "numero_entrega": "ENT-99999999",
        "retirado_por": "Alguien",
    })
    assert r.status_code == 200, r.text
    assert r.json()["accesorios"].endswith("se la llevó)")
    assert r.json()["fecha_entrega"] is None
    assert r.json()["numero_entrega"] is None
    assert r.json()["en_taller"] is True
    # Y el número de recepción tampoco se puede reescribir: ya se imprimió.
    assert r.json()["numero"] == "REC-00000001"


def test_el_service_es_quien_impide_fabricar_una_entrega(client, escenario):
    """El mismo invariante, pero **contra el repositorio y no contra la API**.

    Por la API la protección la da `IngresoIn`, que ni siquiera declara los
    campos de la entrega: Pydantic los descarta antes de llegar acá. O sea que
    el test del router pasa aunque la guarda del service no exista — se
    comprobó forzando el fallo, y quedó verde.

    Eso convertiría la guarda en código muerto, salvo que se la pruebe donde
    manda. Y tiene que existir, porque el invariante es del dominio, no de una
    forma de request: cualquier otro llamador —un script, un seed, un router
    futuro que reuse el modelo— pasaría por acá.
    """
    # `client.app` y no `app.asgi.app`: la app la arma la fixture, y `app.asgi`
    # construiria una SEGUNDA instancia, con su propio engine.
    repo = client.app.state.ingresos
    i = _recibir(client, escenario).json()

    r = repo.update(
        i["id"],
        cliente_id=escenario["cliente"]["id"],
        accesorios="Sólo el cargador",
        numero_entrega="ENT-99999999",
        fecha_entrega=datetime(2026, 8, 5, 12, 0),
        retirado_por="Alguien",
        trabajo_realizado="Nada",
    )
    assert r["accesorios"] == "Sólo el cargador"
    assert r["numero_entrega"] is None
    assert r["fecha_entrega"] is None
    assert r["en_taller"] is True


def test_corregir_no_puede_vaciar_las_columnas_que_no_admiten_nulo(client, escenario):
    """Semántica de objeto entero, con la excepción de las tres `NOT NULL`: ahí
    un `None` sólo puede querer decir "no lo mandé". Sin esta guarda, corregir
    los accesorios tumbaba la fila contra el `NOT NULL` de `fecha_recepcion`."""
    i = _recibir(client, escenario).json()
    r = client.put(f"/api/ingresos-reparacion/{i['id']}", json={
        "cliente_id": escenario["cliente"]["id"],
        "accesorios": "Sólo el cargador",
    })
    assert r.status_code == 200, r.text
    assert r.json()["fecha_recepcion"] == i["fecha_recepcion"]
    assert r.json()["equipo_tipo"] == "Notebook"
    assert r.json()["accesorios"] == "Sólo el cargador"


def test_no_se_borra_un_ingreso_ya_entregado(client, escenario):
    """El comprobante está en manos del cliente: borrar la fila dejaría ese
    número apuntando a la nada, y el próximo lo reusaría."""
    i = _recibir(client, escenario).json()
    client.post(f"/api/ingresos-reparacion/{i['id']}/entregar", json={})

    r = client.delete(f"/api/ingresos-reparacion/{i['id']}")
    assert r.status_code == 409
    assert "en manos del cliente" in r.json()["detail"]


def test_uno_sin_entregar_si_se_borra(client, escenario):
    """Cargarlo por error en el mostrador tiene que poder deshacerse."""
    i = _recibir(client, escenario).json()
    assert client.delete(f"/api/ingresos-reparacion/{i['id']}").status_code == 204
    assert client.get(f"/api/ingresos-reparacion/{i['id']}").status_code == 404


# ── "Qué tengo hoy en el taller" ───────────────────────────────────────────

def test_el_filtro_de_taller_sale_de_la_fecha_y_no_de_un_estado(client, escenario):
    a = _recibir(client, escenario).json()
    _recibir(client, escenario)
    client.post(f"/api/ingresos-reparacion/{a['id']}/entregar", json={})

    en_taller = client.get("/api/ingresos-reparacion?en_taller=true").json()
    entregados = client.get("/api/ingresos-reparacion?en_taller=false").json()
    todos = client.get("/api/ingresos-reparacion").json()

    assert [x["numero"] for x in en_taller] == ["REC-00000002"]
    assert [x["numero"] for x in entregados] == ["REC-00000001"]
    assert len(todos) == 2


def test_se_filtra_por_cliente_y_por_ticket(client, escenario):
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "Notebook mojada",
    }).json()
    _recibir(client, escenario, incidencia_id=ticket["id"])
    _recibir(client, escenario)

    del_ticket = client.get(
        f"/api/ingresos-reparacion?incidencia_id={ticket['id']}").json()
    assert [x["numero"] for x in del_ticket] == ["REC-00000001"]

    otro = client.post("/api/clientes", json={"nombre": "Otro"}).json()
    assert client.get(
        f"/api/ingresos-reparacion?cliente_id={otro['id']}").json() == []


def test_recibir_deja_el_movimiento_en_el_historial_del_equipo(client, escenario):
    """Lo que pidió el pedido: "asociar el comprobante a la incidencia y al
    movimiento del equipo"."""
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "Notebook mojada",
    }).json()
    i = _recibir(client, escenario, incidencia_id=ticket["id"]).json()

    movs = client.get(f"/api/incidencias/{ticket['id']}/movimientos").json()
    entrada = next(m for m in movs if m["tipo"] == "ingreso_reparacion")
    assert i["numero"] in entrada["descripcion"]

    client.post(f"/api/ingresos-reparacion/{i['id']}/entregar", json={})
    movs = client.get(f"/api/incidencias/{ticket['id']}/movimientos").json()
    salida = next(m for m in movs if m["tipo"] == "entrega_reparacion")
    assert "ENT-00000001" in salida["descripcion"]


def test_borrar_el_ticket_no_borra_el_comprobante(client, escenario):
    """El pragma de FK está apagado, así que hay que mirarlo. Y acá pesa más que
    en el resto: el papel que quedó en manos del cliente nombra ese número."""
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "Notebook mojada",
    }).json()
    i = _recibir(client, escenario, incidencia_id=ticket["id"]).json()

    client.delete(f"/api/incidencias/{ticket['id']}")

    despues = client.get(f"/api/ingresos-reparacion/{i['id']}")
    assert despues.status_code == 200
    assert despues.json()["numero"] == "REC-00000001"
    assert despues.json()["incidencia_id"] is None


# ── Los PDF ────────────────────────────────────────────────────────────────

def test_el_pdf_de_recepcion_sale(client, escenario):
    i = _recibir(client, escenario).json()
    r = client.get(f"/api/ingresos-reparacion/{i['id']}/pdf/recepcion")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    assert "REC-00000001.pdf" in r.headers["content-disposition"]


def test_el_pdf_de_entrega_no_existe_antes_de_entregar(client, escenario):
    """Imprimir un comprobante de entrega de algo que sigue en el taller sería
    darle al cliente un papel que dice que se llevó lo que no se llevó."""
    i = _recibir(client, escenario).json()
    r = client.get(f"/api/ingresos-reparacion/{i['id']}/pdf/entrega")
    assert r.status_code == 409
    assert "Todavía no se entregó" in r.json()["detail"]


def test_el_pdf_de_entrega_sale_despues(client, escenario):
    i = _recibir(client, escenario).json()
    client.post(f"/api/ingresos-reparacion/{i['id']}/entregar", json={
        "retirado_por": "Marta Ríos", "trabajo_realizado": "Cambio de teclado",
    })
    r = client.get(f"/api/ingresos-reparacion/{i['id']}/pdf/entrega")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
    assert "ENT-00000001.pdf" in r.headers["content-disposition"]


def test_los_dos_pdf_llevan_el_texto_del_pedido(client, escenario):
    """Se afirma sobre `datos_para_pdf`, no sobre el binario: es lo que hace
    testeable el contenido sin parsear un PDF. El binario ya se probó arriba."""
    from app.services.ingresos import IngresoRepository  # noqa: PLC0415

    i = _recibir(client, escenario).json()
    client.post(f"/api/ingresos-reparacion/{i['id']}/entregar", json={
        "retirado_por": "Marta Ríos", "trabajo_realizado": "Cambio de teclado",
    })
    repo: IngresoRepository = client.app.state.ingresos
    rec = repo.datos_para_pdf(i["id"], tipo="recepcion")
    ent = repo.datos_para_pdf(i["id"], tipo="entrega")

    # El de recepción lleva lo que se discute en un reclamo.
    assert rec["accesorios"] and rec["estado_fisico"] and rec["falla_declarada"]
    assert rec["cliente"]["cuit"] == "30-11111111-1"
    assert rec["cliente"]["domicilio"] == "Suipacha 123"
    # El de entrega lleva el número de recepción: es por donde se cruzan.
    assert ent["numero"] == "REC-00000001"
    assert ent["numero_entrega"] == "ENT-00000001"
    assert ent["trabajo_realizado"] == "Cambio de teclado"
    assert ent["dias_en_taller"] == 0


def test_un_tipo_de_comprobante_inventado_no_imprime_nada(client, escenario):
    i = _recibir(client, escenario).json()
    assert client.get(
        f"/api/ingresos-reparacion/{i['id']}/pdf/factura").status_code == 404


def test_el_pdf_aguanta_un_guion_largo_pegado_de_word(client, escenario):
    """`_TextoSeguroPDF` primero en el MRO. Sin eso esto es un 500, y no es
    hipotético: el mostrador tipea con el cliente enfrente y pega de WhatsApp."""
    i = _recibir(client, escenario, falla_declarada=(
        "No enciende —dice que se mojó— y hace un ruido “raro”… al arrancar"
    )).json()
    r = client.get(f"/api/ingresos-reparacion/{i['id']}/pdf/recepcion")
    assert r.status_code == 200, r.text
    assert r.content[:4] == b"%PDF"
