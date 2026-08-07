"""Fase 4: el activo entra a la cadena de service.

Hasta la fase 3 un activo colocado que fallaba se pasaba a `en_reparacion` a
mano y sin ningún registro de a dónde se lo mandó — exactamente el hueco que el
bloque de service/RMA había cerrado para los equipos del cliente. Acá se cierra
para los propios, **reusando la misma cadena** en vez de duplicarla.

Los dos grupos que concentran el valor:

1. **Atomicidad.** Sacar el activo y registrar a dónde se lo mandó son el mismo
   hecho. Si el service falla, el retiro no puede haber ocurrido.
2. **Una sola cadena.** "Qué tengo hoy en service" tiene que contestar por los
   dos tipos de equipo a la vez; si hubiera dos tablas, la pregunta se
   contestaría a medias sin que se note.
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


INICIO = date(2026, 8, 1)
LUEGO = INICIO + timedelta(days=30)


def f(d: date) -> str:
    return d.isoformat()


@pytest.fixture
def escenario(client):
    """Un contrato con una central puesta, un activo de repuesto, un proveedor
    de service, y un equipo del cliente para probar que las dos familias
    conviven en la misma tabla."""
    cliente = client.post("/api/clientes", json={"nombre": "Estudio Sur"}).json()
    proveedor = client.post("/api/proveedores", json={"nombre": "Compu Service"}).json()
    central = client.post("/api/activos", json={
        "tipo": "Central telefónica", "marca": "Yeastar", "modelo": "S20",
        "serial": "YS-A123",
    }).json()
    repuesto = client.post("/api/activos", json={
        "tipo": "Central telefónica", "marca": "Yeastar", "modelo": "S20",
        "serial": "YS-B456",
    }).json()
    equipo = client.post("/api/equipos", json={
        "cliente_id": cliente["id"], "tipo": "Impresora", "marca": "HP",
    }).json()
    contrato = client.post("/api/contratos", json={
        "tipo_contrato": "alquiler", "cliente_id": cliente["id"],
        "fecha_inicio": f(INICIO), "estado": "activo", "importe": 45000,
    }).json()
    linea = client.post(f"/api/contratos/{contrato['id']}/equipos", json={
        "activo_id": central["id"], "fecha_instalacion": f(INICIO),
        "ubicacion": "Rack",
    }).json()
    return {
        "cliente": cliente, "proveedor": proveedor, "central": central,
        "repuesto": repuesto, "equipo": equipo, "contrato": contrato,
        "linea": linea,
    }


def _service(escenario, **extra):
    return {"proveedor_id": escenario["proveedor"]["id"], "fecha_envio": f(LUEGO), **extra}


# ── El retiro que manda a service ──────────────────────────────────────────

def test_retirar_a_service_abre_la_reparacion(client, escenario):
    r = client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/retirar", json={
        "fecha_retiro": f(LUEGO), "motivo_retiro": "reemplazo",
        "estado_activo": "en_reparacion",
        "service": _service(escenario, rma="RMA-991", en_garantia=True),
    })
    assert r.status_code == 200, r.text
    salida = r.json()

    assert salida["vigente"] is False
    assert salida["reparacion"]["abierta"] is True
    assert salida["reparacion"]["rma"] == "RMA-991"
    assert salida["reparacion"]["en_garantia"] is True
    # La reparación es del ACTIVO, no de un equipo del cliente.
    assert salida["reparacion"]["es_activo"] is True
    assert salida["reparacion"]["activo_id"] == escenario["central"]["id"]
    assert salida["reparacion"]["equipo_id"] is None

    activo = client.get(f"/api/activos/{escenario['central']['id']}").json()
    assert activo["estado"] == "en_reparacion"


def test_el_service_exige_que_el_activo_quede_en_reparacion(client, escenario):
    """Una reparación sobre un activo que vuelve a depósito describiría algo que
    no pasó. Se rechaza en vez de ignorarse en silencio: el llamador cargó esos
    datos creyendo que iban a alguna parte."""
    r = client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/retirar", json={
        "fecha_retiro": f(LUEGO), "motivo_retiro": "devolucion",
        "estado_activo": "retirado_a_revisar",
        "service": _service(escenario),
    })
    assert r.status_code == 409
    assert "en_reparacion" in r.json()["detail"]


def test_el_reemplazo_tambien_exige_que_el_que_sale_quede_en_reparacion(client, escenario):
    """La misma guarda que en el retiro, en el otro camino. Estaba escrita pero
    **sin test**: romperla no ponía nada en rojo porque el único test del
    reemplazo con service ya mandaba `en_reparacion`."""
    r = client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["repuesto"]["id"], "fecha": f(LUEGO),
        "estado_activo_retirado": "disponible",
        "service": _service(escenario),
    })
    assert r.status_code == 409
    assert "en_reparacion" in r.json()["detail"]

    # Y no dejó nada a medias: el activo sigue puesto.
    assert client.get(
        f"/api/activos/{escenario['central']['id']}"
    ).json()["estado"] == "colocado"


def test_si_el_service_falla_el_retiro_no_ocurre(client, escenario):
    """La prueba de que las dos escrituras son una sola transacción. Con un
    proveedor inexistente el retiro tiene que quedar **sin hacer** — si la línea
    quedara cerrada, el activo estaría fuera del contrato sin ninguna reparación
    que diga dónde está, que es justo el estado que esto viene a eliminar."""
    r = client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/retirar", json={
        "fecha_retiro": f(LUEGO), "motivo_retiro": "reemplazo",
        "estado_activo": "en_reparacion",
        "service": {"proveedor_id": 999, "fecha_envio": f(LUEGO)},
    })
    assert r.status_code == 404

    linea = client.get(f"/api/contratos/{escenario['contrato']['id']}/equipos").json()[0]
    assert linea["vigente"] is True, "la línea se cerró aunque el service falló"
    activo = client.get(f"/api/activos/{escenario['central']['id']}").json()
    assert activo["estado"] == "colocado"
    assert client.get(
        f"/api/reparaciones?activo_id={escenario['central']['id']}"
    ).json() == []


def test_un_activo_no_puede_tener_dos_reparaciones_abiertas(client, escenario):
    client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/retirar", json={
        "fecha_retiro": f(LUEGO), "motivo_retiro": "reemplazo",
        "estado_activo": "en_reparacion", "service": _service(escenario),
    })
    r = client.post("/api/reparaciones", json={
        "activo_id": escenario["central"]["id"],
        "proveedor_id": escenario["proveedor"]["id"], "fecha_envio": f(LUEGO),
    })
    assert r.status_code == 409
    assert "ya tiene una reparacion abierta" in r.json()["detail"]


# ── El reemplazo que manda a service, y la vuelta ──────────────────────────

def test_el_reemplazo_manda_a_service_al_que_sale(client, escenario):
    r = client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["repuesto"]["id"], "fecha": f(LUEGO),
        "estado_activo_retirado": "en_reparacion",
        "service": _service(escenario, remito_salida="0001-00000042"),
    })
    assert r.status_code == 200, r.text
    salida = r.json()

    assert salida["retirada"]["motivo_retiro"] == "reemplazo"
    assert salida["nueva"]["reemplaza_a_id"] == escenario["linea"]["id"]
    assert salida["reparacion"]["remito_salida"] == "0001-00000042"
    assert salida["reparacion"]["activo_id"] == escenario["central"]["id"]
    assert salida["reparacion_cerrada"] is None

    assert client.get(f"/api/activos/{escenario['central']['id']}").json()["estado"] == "en_reparacion"
    assert client.get(f"/api/activos/{escenario['repuesto']['id']}").json()["estado"] == "colocado"


def test_la_vuelta_del_service_es_el_mismo_reemplazo_al_reves(client, escenario):
    """El original vuelve entrando como sustituto y el repuesto sale. No hay
    una operación aparte para esto, igual que en `ReemplazoService`."""
    ida = client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["repuesto"]["id"], "fecha": f(LUEGO),
        "estado_activo_retirado": "en_reparacion", "service": _service(escenario),
    }).json()

    vuelta_el = LUEGO + timedelta(days=12)
    r = client.post(f"/api/contratos/equipos/{ida['nueva']['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["central"]["id"], "fecha": f(vuelta_el),
        "estado_activo_retirado": "disponible",
        "cierre_service": {
            "fecha_retorno": f(vuelta_el), "diagnostico": "Fuente cambiada",
            "costo": 32000,
        },
    })
    assert r.status_code == 200, r.text
    salida = r.json()

    assert salida["reparacion_cerrada"]["abierta"] is False
    assert salida["reparacion_cerrada"]["diagnostico"] == "Fuente cambiada"
    assert salida["reparacion_cerrada"]["costo"] == 32000
    assert salida["reparacion_cerrada"]["dias_afuera"] == 12

    assert client.get(f"/api/activos/{escenario['central']['id']}").json()["estado"] == "colocado"
    assert client.get(f"/api/activos/{escenario['repuesto']['id']}").json()["estado"] == "disponible"


def test_un_activo_en_reparacion_no_se_coloca_salvo_que_vuelva(client, escenario):
    """🔴 La guarda no puede ser fija. `en_reparacion` normalmente impide
    colocar —el equipo está afuera—, pero cuando la misma operación **cierra su
    reparación** ese es justo el estado del que se lo está sacando. Con la
    guarda fija, un activo que volvía de reparar no se podía reinstalar nunca y
    `cierre_service` quedaba inalcanzable."""
    client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/retirar", json={
        "fecha_retiro": f(LUEGO), "motivo_retiro": "devolucion",
        "estado_activo": "en_reparacion", "service": _service(escenario),
    })
    vuelve_el = LUEGO + timedelta(days=9)

    # Sin cerrar el service: no se puede colocar.
    sin_cierre = client.post(f"/api/contratos/{escenario['contrato']['id']}/equipos", json={
        "activo_id": escenario["central"]["id"], "fecha_instalacion": f(vuelve_el),
    })
    assert sin_cierre.status_code == 409
    assert "en_reparacion" in sin_cierre.json()["detail"]

    # Cerrándolo en el mismo gesto: sí.
    con_cierre = client.post(f"/api/contratos/{escenario['contrato']['id']}/equipos", json={
        "activo_id": escenario["central"]["id"], "fecha_instalacion": f(vuelve_el),
        "cierre_service": {"fecha_retorno": f(vuelve_el), "costo": 18000},
    })
    assert con_cierre.status_code == 201, con_cierre.text
    assert con_cierre.json()["reparacion_cerrada"]["abierta"] is False
    assert con_cierre.json()["reparacion_cerrada"]["costo"] == 18000
    assert client.get(f"/api/activos/{escenario['central']['id']}").json()["estado"] == "colocado"


def test_cerrar_service_sin_reparacion_abierta(client, escenario):
    r = client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["repuesto"]["id"], "fecha": f(LUEGO),
        "estado_activo_retirado": "disponible",
        "cierre_service": {"fecha_retorno": f(LUEGO)},
    })
    assert r.status_code == 409
    assert "ninguna reparación abierta" in r.json()["detail"]


def test_el_contrato_conserva_las_dos_lineas_y_el_paso_por_service(client, escenario):
    """La historia completa después de la ida y la vuelta: tres líneas, y el
    activo original vuelve a estar puesto sin haber perdido su paso por
    service."""
    ida = client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["repuesto"]["id"], "fecha": f(LUEGO),
        "estado_activo_retirado": "en_reparacion", "service": _service(escenario),
    }).json()
    vuelta_el = LUEGO + timedelta(days=12)
    client.post(f"/api/contratos/equipos/{ida['nueva']['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["central"]["id"], "fecha": f(vuelta_el),
        "estado_activo_retirado": "disponible",
        "cierre_service": {"fecha_retorno": f(vuelta_el)},
    })

    lineas = client.get(f"/api/contratos/{escenario['contrato']['id']}/equipos").json()
    assert len(lineas) == 3
    vigentes = [le for le in lineas if le["vigente"]]
    assert len(vigentes) == 1
    assert vigentes[0]["activo_serial"] == "YS-A123"

    reparaciones = client.get(
        f"/api/reparaciones?activo_id={escenario['central']['id']}"
    ).json()
    assert len(reparaciones) == 1
    assert reparaciones[0]["abierta"] is False


# ── Una sola cadena para las dos familias ──────────────────────────────────

def test_la_lista_de_service_trae_las_dos_familias_juntas(client, escenario):
    """El punto de la tabla unificada: "qué tengo hoy en service" no distingue
    de quién es el aparato. Con dos tablas esta pregunta se contestaría a medias
    sin que se note."""
    client.post("/api/reparaciones", json={
        "equipo_id": escenario["equipo"]["id"],
        "proveedor_id": escenario["proveedor"]["id"], "fecha_envio": f(LUEGO),
    })
    client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/retirar", json={
        "fecha_retiro": f(LUEGO), "motivo_retiro": "reemplazo",
        "estado_activo": "en_reparacion", "service": _service(escenario),
    })

    todas = client.get("/api/reparaciones?abiertas=true").json()
    assert len(todas) == 2
    assert {r["es_activo"] for r in todas} == {True, False}

    assert [r["es_activo"] for r in client.get(
        "/api/reparaciones?abiertas=true&solo_activos=true").json()] == [True]
    assert [r["es_activo"] for r in client.get(
        "/api/reparaciones?abiertas=true&solo_activos=false").json()] == [False]


def test_filtrar_service_por_cliente_incluye_los_activos_alquilados(client, escenario):
    """El cliente de un activo sale del contrato donde está colocado, no del
    aparato. Un `JOIN` contra `equipos` —que es como estaba— dejaría afuera
    todas las reparaciones de activos, en silencio."""
    client.post("/api/reparaciones", json={
        "equipo_id": escenario["equipo"]["id"],
        "proveedor_id": escenario["proveedor"]["id"], "fecha_envio": f(LUEGO),
    })
    client.post("/api/reparaciones", json={
        "activo_id": escenario["central"]["id"],
        "proveedor_id": escenario["proveedor"]["id"], "fecha_envio": f(LUEGO),
    })

    del_cliente = client.get(
        f"/api/reparaciones?cliente_id={escenario['cliente']['id']}"
    ).json()
    assert len(del_cliente) == 2, "se perdieron las reparaciones de activos"

    otro = client.post("/api/clientes", json={"nombre": "Otro"}).json()
    assert client.get(f"/api/reparaciones?cliente_id={otro['id']}").json() == []


def test_una_reparacion_es_de_un_equipo_o_de_un_activo(client, escenario):
    """El XOR, validado en la capa de servicio para que el error se entienda. La
    base además lo garantiza con un CHECK — ver la revisión 0006."""
    base = {"proveedor_id": escenario["proveedor"]["id"], "fecha_envio": f(LUEGO)}

    ninguno = client.post("/api/reparaciones", json=base)
    assert ninguno.status_code == 409
    assert "exactamente uno" in ninguno.json()["detail"]

    los_dos = client.post("/api/reparaciones", json={
        **base, "equipo_id": escenario["equipo"]["id"],
        "activo_id": escenario["central"]["id"],
    })
    assert los_dos.status_code == 409


# ── El historial del activo ────────────────────────────────────────────────

def test_colocar_y_retirar_dejan_movimientos(client, escenario):
    """`contratos_equipos` cuenta en qué contratos estuvo; los movimientos
    cuentan qué le pasó **entre** dos contratos. Sin esto el recorrido tiene
    agujeros."""
    client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/retirar", json={
        "fecha_retiro": f(LUEGO), "motivo_retiro": "devolucion",
        "estado_activo": "retirado_a_revisar",
    })

    tl = client.get(f"/api/activos/{escenario['central']['id']}/linea-de-tiempo").json()
    movimientos = [i for i in tl if i["clase"] == "movimiento"]
    assert len(movimientos) == 2
    # Más reciente primero.
    assert "Retirado" in movimientos[0]["titulo"]
    assert "Instalado" in movimientos[1]["titulo"]


def test_la_linea_de_tiempo_une_contrato_movimiento_y_service(client, escenario):
    """El recorrido que pedían los lineamientos: depósito → cliente → service →
    de vuelta. Las tres fuentes en una sola secuencia."""
    client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["repuesto"]["id"], "fecha": f(LUEGO),
        "estado_activo_retirado": "en_reparacion", "service": _service(escenario),
    })

    tl = client.get(f"/api/activos/{escenario['central']['id']}/linea-de-tiempo").json()
    clases = {i["clase"] for i in tl}
    assert clases == {"contrato", "movimiento", "service"}

    # Ordenada de más reciente a más vieja.
    fechas = [i["fecha"] for i in tl if i["fecha"]]
    assert fechas == sorted(fechas, reverse=True)

    service = next(i for i in tl if i["clase"] == "service")
    assert service["abierta"] is True
    assert service["detalle"] == "Compu Service"


def test_la_linea_de_tiempo_404(client):
    assert client.get("/api/activos/999/linea-de-tiempo").status_code == 404


# ── El ticket puede señalar un activo ──────────────────────────────────────

def test_una_incidencia_puede_apuntar_a_un_activo(client, escenario):
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"],
        "activo_id": escenario["central"]["id"],
        "titulo": "La central se reinicia sola",
    })
    assert ticket.status_code == 201, ticket.text
    assert ticket.json()["activo_id"] == escenario["central"]["id"]

    porque = client.get(
        f"/api/incidencias?activo_id={escenario['central']['id']}"
    ).json()
    assert [i["id"] for i in porque] == [ticket.json()["id"]]


def test_un_ticket_puede_tocar_el_equipo_del_cliente_y_un_activo(client, escenario):
    """No son excluyentes, a diferencia del historial: "el teléfono alquilado no
    registra en la PC del cliente" toca legítimamente las dos cosas."""
    r = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"],
        "equipo_id": escenario["equipo"]["id"],
        "activo_id": escenario["central"]["id"],
        "titulo": "No se comunican",
    })
    assert r.status_code == 201
    assert r.json()["equipo_id"] is not None
    assert r.json()["activo_id"] is not None


def test_el_reemplazo_por_ticket_queda_trazado(client, escenario):
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"],
        "activo_id": escenario["central"]["id"], "titulo": "Se colgó",
    }).json()

    r = client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["repuesto"]["id"], "fecha": f(LUEGO),
        "estado_activo_retirado": "en_reparacion",
        "incidencia_id": ticket["id"], "service": _service(escenario),
    }).json()

    assert r["nueva"]["incidencia_id"] == ticket["id"]
    assert r["retirada"]["incidencia_id"] == ticket["id"]
    assert r["reparacion"]["incidencia_id"] == ticket["id"]


def test_borrar_el_ticket_no_borra_la_historia(client, escenario):
    """El equipo se reemplazó de verdad ese día, y eso le sobrevive al ticket:
    las filas quedan, sólo pierden el link. Mismo criterio que ya tenían los
    movimientos y las reparaciones de equipos."""
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "Se colgó",
    }).json()
    client.post(f"/api/contratos/equipos/{escenario['linea']['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["repuesto"]["id"], "fecha": f(LUEGO),
        "estado_activo_retirado": "en_reparacion",
        "incidencia_id": ticket["id"], "service": _service(escenario),
    })

    assert client.delete(f"/api/incidencias/{ticket['id']}").status_code == 204

    lineas = client.get(f"/api/contratos/{escenario['contrato']['id']}/equipos").json()
    assert len(lineas) == 2
    assert all(le["incidencia_id"] is None for le in lineas)

    reparaciones = client.get(
        f"/api/reparaciones?activo_id={escenario['central']['id']}"
    ).json()
    assert len(reparaciones) == 1
    assert reparaciones[0]["incidencia_id"] is None
