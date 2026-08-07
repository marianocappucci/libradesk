"""Alquiler y cesión de equipos, fase 1 — contratos, activos y precios.

Los dos bloques que concentran el valor del módulo, y por eso los que más
tests tienen:

1. **El reemplazo no borra el equipo anterior.** El contrato tiene que poder
   decir "del 01/08 al 14/09 la serie A123, desde el 14/09 la B456".
2. **El precio nunca se sobreescribe.** Una liquidación de agosto rehecha en
   noviembre tiene que dar el importe de agosto.

Lo demás son las invariantes que sostienen esas dos: que un activo no esté en
dos contratos a la vez, que su estado no se pueda contradecir con las líneas, y
que un contrato sin cuota no acepte precios.
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


def _fecha(d: date) -> str:
    return d.isoformat()


@pytest.fixture
def escenario(client):
    """Un cliente, una central y dos teléfonos IP — el ejemplo de los
    lineamientos: contrato con central Yeastar y terminales Grandstream."""
    cliente = client.post("/api/clientes", json={"nombre": "Estudio Contable Sur"}).json()
    central = client.post("/api/activos", json={
        "tipo": "Central telefónica", "marca": "Yeastar", "modelo": "S20",
        "serial": "YS-A123", "codigo_interno": "PAT-0001",
        "costo_compra": 180000, "valor_reposicion": 250000,
    }).json()
    tel_a = client.post("/api/activos", json={
        "tipo": "Teléfono IP", "marca": "Grandstream", "modelo": "GXP1625",
        "serial": "GS-A123",
    }).json()
    tel_b = client.post("/api/activos", json={
        "tipo": "Teléfono IP", "marca": "Grandstream", "modelo": "GXP1625",
        "serial": "GS-B456",
    }).json()
    return {"cliente": cliente, "central": central, "tel_a": tel_a, "tel_b": tel_b}


def _contrato(client, escenario, **extra):
    body = {
        "tipo_contrato": "alquiler",
        "cliente_id": escenario["cliente"]["id"],
        "fecha_inicio": _fecha(INICIO),
        "estado": "activo",
        "importe": 45000,
        **extra,
    }
    r = client.post("/api/contratos", json=body)
    assert r.status_code == 201, r.text
    return r.json()


# ── El alta ────────────────────────────────────────────────────────────────

def test_el_alta_crea_el_contrato_con_su_primer_precio(client, escenario):
    """El importe viaja en el alta a propósito: separarlos admite un alquiler
    activo sin ningún precio, del que no se puede derivar cuánto cobrar."""
    c = _contrato(client, escenario)

    assert c["numero"] == "CTR-00000001"
    assert c["importe_vigente"] == 45000
    assert c["precio_vigente_desde"] == _fecha(INICIO)
    assert c["lleva_cuota"] is True

    precios = client.get(f"/api/contratos/{c['id']}/precios").json()
    assert len(precios) == 1
    assert precios[0]["motivo"] == "alta"
    assert precios[0]["vigente"] is True


def test_la_numeracion_es_correlativa(client, escenario):
    numeros = [_contrato(client, escenario)["numero"] for _ in range(3)]
    assert numeros == ["CTR-00000001", "CTR-00000002", "CTR-00000003"]


def test_un_comodato_no_acepta_importe(client, escenario):
    """Comodato, préstamo e incluido-en-servicio se entregan sin cobrar por el
    equipo. Un importe ahí no significa nada, así que se rechaza en vez de
    guardarse y no usarse nunca."""
    r = client.post("/api/contratos", json={
        "tipo_contrato": "comodato", "cliente_id": escenario["cliente"]["id"],
        "fecha_inicio": _fecha(INICIO), "importe": 45000,
    })
    assert r.status_code == 409
    assert "no lleva cuota" in r.json()["detail"]


def test_un_comodato_sin_importe_se_crea_igual(client, escenario):
    c = _contrato(client, escenario, tipo_contrato="comodato", importe=None)
    assert c["lleva_cuota"] is False
    assert c["importe_vigente"] is None


def test_tipo_de_contrato_invalido(client, escenario):
    r = client.post("/api/contratos", json={
        "tipo_contrato": "canje", "cliente_id": escenario["cliente"]["id"],
        "fecha_inicio": _fecha(INICIO),
    })
    assert r.status_code == 409


def test_la_fecha_de_fin_no_puede_preceder_al_inicio(client, escenario):
    r = client.post("/api/contratos", json={
        "tipo_contrato": "alquiler", "cliente_id": escenario["cliente"]["id"],
        "fecha_inicio": _fecha(INICIO), "fecha_fin": _fecha(INICIO - timedelta(days=1)),
    })
    assert r.status_code == 409


# ── Los equipos del contrato ───────────────────────────────────────────────

def _colocar(client, contrato, activo, fecha=INICIO, **extra):
    r = client.post(f"/api/contratos/{contrato['id']}/equipos", json={
        "activo_id": activo["id"], "fecha_instalacion": _fecha(fecha), **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_colocar_deja_el_activo_colocado_y_la_linea_vigente(client, escenario):
    c = _contrato(client, escenario)
    linea = _colocar(client, c, escenario["central"], ubicacion="Rack sala servidores")

    assert linea["vigente"] is True
    assert linea["fecha_retiro"] is None
    assert linea["activo_serial"] == "YS-A123"

    activo = client.get(f"/api/activos/{escenario['central']['id']}").json()
    assert activo["estado"] == "colocado"
    # Resuelto para la lista, sin pedir un endpoint más por fila.
    assert activo["contrato_numero"] == c["numero"]
    assert activo["cliente_nombre"] == "Estudio Contable Sur"


def test_un_activo_no_puede_estar_en_dos_contratos(client, escenario):
    c1 = _contrato(client, escenario)
    c2 = _contrato(client, escenario)
    _colocar(client, c1, escenario["central"])

    r = client.post(f"/api/contratos/{c2['id']}/equipos", json={
        "activo_id": escenario["central"]["id"], "fecha_instalacion": _fecha(INICIO),
    })
    assert r.status_code == 409
    # Lo frena la guarda por ESTADO, que dispara primero. La otra —por línea
    # abierta— la cubre el test de abajo.
    assert "'colocado'" in r.json()["detail"]


def test_la_guarda_por_linea_abierta_no_es_codigo_muerto(client, escenario):
    """La segunda red de `colocar()`, la que consulta las líneas en vez del
    estado, **nunca se ejercita por el camino normal**: la guarda por estado
    dispara antes. Este test la alcanza desincronizando el estado a mano, que es
    justo el escenario para el que existe — un arreglo directo en la base que
    deja al activo diciendo `disponible` con una línea todavía abierta.

    Sin este test la rama quedaría sin cubrir y su comentario sería una promesa
    que nadie verificó.
    """
    from app.services.activos import Activo

    c1 = _contrato(client, escenario)
    c2 = _contrato(client, escenario)
    _colocar(client, c1, escenario["central"])

    sessions = client.app.state.activos.session_factory
    with sessions() as s:
        s.get(Activo, escenario["central"]["id"]).estado = "disponible"
        s.commit()

    r = client.post(f"/api/contratos/{c2['id']}/equipos", json={
        "activo_id": escenario["central"]["id"], "fecha_instalacion": _fecha(INICIO),
    })
    assert r.status_code == 409
    assert "ya está colocado" in r.json()["detail"]


def test_no_se_coloca_en_un_contrato_finalizado(client, escenario):
    c = _contrato(client, escenario, estado="finalizado")
    r = client.post(f"/api/contratos/{c['id']}/equipos", json={
        "activo_id": escenario["central"]["id"], "fecha_instalacion": _fecha(INICIO),
    })
    assert r.status_code == 409


def test_la_instalacion_no_puede_preceder_al_contrato(client, escenario):
    c = _contrato(client, escenario)
    r = client.post(f"/api/contratos/{c['id']}/equipos", json={
        "activo_id": escenario["central"]["id"],
        "fecha_instalacion": _fecha(INICIO - timedelta(days=1)),
    })
    assert r.status_code == 409


def test_retirar_deja_el_activo_a_revisar_y_no_disponible(client, escenario):
    """Por defecto vuelve `retirado_a_revisar`, no `disponible`: un equipo que
    vuelve de un cliente no está listo para salir de nuevo hasta que alguien lo
    mire. Ponerlo directo en disponible haría que el selector ofrezca equipos
    que nadie revisó."""
    c = _contrato(client, escenario)
    linea = _colocar(client, c, escenario["central"])

    r = client.post(f"/api/contratos/equipos/{linea['id']}/retirar", json={
        "fecha_retiro": _fecha(INICIO + timedelta(days=30)), "motivo_retiro": "devolucion",
    })
    assert r.status_code == 200, r.text
    assert r.json()["vigente"] is False

    activo = client.get(f"/api/activos/{escenario['central']['id']}").json()
    assert activo["estado"] == "retirado_a_revisar"
    assert activo["contrato_id"] is None


def test_no_se_retira_dos_veces(client, escenario):
    c = _contrato(client, escenario)
    linea = _colocar(client, c, escenario["central"])
    cuerpo = {"fecha_retiro": _fecha(INICIO + timedelta(days=5)), "motivo_retiro": "devolucion"}
    assert client.post(f"/api/contratos/equipos/{linea['id']}/retirar", json=cuerpo).status_code == 200
    r = client.post(f"/api/contratos/equipos/{linea['id']}/retirar", json=cuerpo)
    assert r.status_code == 409


def test_el_retiro_no_puede_preceder_a_la_instalacion(client, escenario):
    c = _contrato(client, escenario)
    linea = _colocar(client, c, escenario["central"], fecha=INICIO + timedelta(days=10))
    r = client.post(f"/api/contratos/equipos/{linea['id']}/retirar", json={
        "fecha_retiro": _fecha(INICIO), "motivo_retiro": "devolucion",
    })
    assert r.status_code == 409


# ── El reemplazo: lo que NO tiene que pasar es que el anterior desaparezca ──

def test_el_reemplazo_conserva_la_linea_anterior(client, escenario):
    """El caso textual de los lineamientos: del 01/08 al 14/09 la serie A123,
    desde el 14/09 la B456 por reemplazo técnico. Las DOS tienen que quedar."""
    c = _contrato(client, escenario)
    linea = _colocar(client, c, escenario["tel_a"], ubicacion="Recepción")
    cambio = date(2026, 9, 14)

    r = client.post(f"/api/contratos/equipos/{linea['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["tel_b"]["id"], "fecha": _fecha(cambio),
    })
    assert r.status_code == 200, r.text
    resultado = r.json()

    assert resultado["retirada"]["id"] == linea["id"]
    assert resultado["retirada"]["fecha_retiro"] == _fecha(cambio)
    assert resultado["retirada"]["motivo_retiro"] == "reemplazo"
    assert resultado["nueva"]["reemplaza_a_id"] == linea["id"]
    # Hereda la ubicación: el equipo nuevo va donde estaba el viejo.
    assert resultado["nueva"]["ubicacion"] == "Recepción"

    # Y el contrato sigue contando las dos, no una.
    lineas = client.get(f"/api/contratos/{c['id']}/equipos").json()
    assert len(lineas) == 2
    seriales = {le["activo_serial"]: le["vigente"] for le in lineas}
    assert seriales == {"GS-A123": False, "GS-B456": True}


def test_el_reemplazo_mueve_los_dos_activos(client, escenario):
    c = _contrato(client, escenario)
    linea = _colocar(client, c, escenario["tel_a"])
    client.post(f"/api/contratos/equipos/{linea['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["tel_b"]["id"], "fecha": _fecha(INICIO + timedelta(days=44)),
    })

    viejo = client.get(f"/api/activos/{escenario['tel_a']['id']}").json()
    nuevo = client.get(f"/api/activos/{escenario['tel_b']['id']}").json()
    assert viejo["estado"] == "retirado_a_revisar"
    assert nuevo["estado"] == "colocado"
    assert nuevo["contrato_numero"] == c["numero"]


def test_no_se_reemplaza_por_el_mismo_activo(client, escenario):
    c = _contrato(client, escenario)
    linea = _colocar(client, c, escenario["tel_a"])
    r = client.post(f"/api/contratos/equipos/{linea['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["tel_a"]["id"], "fecha": _fecha(INICIO + timedelta(days=5)),
    })
    assert r.status_code == 409


def test_no_se_reemplaza_por_uno_ya_colocado(client, escenario):
    c = _contrato(client, escenario)
    puesta = _colocar(client, c, escenario["tel_a"])
    _colocar(client, c, escenario["tel_b"])

    r = client.post(f"/api/contratos/equipos/{puesta['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["tel_b"]["id"], "fecha": _fecha(INICIO + timedelta(days=5)),
    })
    assert r.status_code == 409


def test_el_historial_del_activo_recorre_sus_contratos(client, escenario):
    """"Depósito → cliente A → retirado → cliente B", que es la vista que
    justifica registrar todo esto."""
    c1 = _contrato(client, escenario)
    linea = _colocar(client, c1, escenario["central"])
    client.post(f"/api/contratos/equipos/{linea['id']}/retirar", json={
        "fecha_retiro": _fecha(INICIO + timedelta(days=60)), "motivo_retiro": "devolucion",
    })
    client.put(f"/api/activos/{escenario['central']['id']}", json={"estado": "disponible"})
    c2 = _contrato(client, escenario)
    _colocar(client, c2, escenario["central"], fecha=INICIO + timedelta(days=90))

    historial = client.get(f"/api/activos/{escenario['central']['id']}/historial").json()
    assert len(historial) == 2
    # Más reciente primero.
    assert historial[0]["contrato_numero"] == c2["numero"]
    assert historial[0]["vigente"] is True
    assert historial[1]["contrato_numero"] == c1["numero"]
    assert historial[1]["vigente"] is False


# ── Precios: el histórico es el punto ──────────────────────────────────────

def test_actualizar_precio_cierra_el_anterior_sin_pisarlo(client, escenario):
    c = _contrato(client, escenario)
    desde = date(2026, 11, 1)

    r = client.post(f"/api/contratos/{c['id']}/precios", json={
        "importe": 55000, "vigencia_desde": _fecha(desde), "motivo": "porcentaje",
    })
    assert r.status_code == 201, r.text

    precios = client.get(f"/api/contratos/{c['id']}/precios").json()
    assert len(precios) == 2
    nuevo, viejo = precios  # ordenados por vigencia descendente
    assert nuevo["importe"] == 55000 and nuevo["vigente"] is True
    # El viejo conserva su importe y se le pone fecha de fin: el día ANTERIOR,
    # para que las dos vigencias sean contiguas y no dejen un día sin precio.
    assert viejo["importe"] == 45000
    assert viejo["vigencia_hasta"] == _fecha(desde - timedelta(days=1))
    assert viejo["vigente"] is False


def test_rehacer_una_liquidacion_vieja_da_el_precio_viejo(client, escenario):
    """La consulta que justifica toda la tabla. Sin histórico, pedir el precio
    de agosto en noviembre devolvería el de noviembre y la factura rehecha
    saldría con otro número."""
    c = _contrato(client, escenario)
    client.post(f"/api/contratos/{c['id']}/precios", json={
        "importe": 55000, "vigencia_desde": "2026-11-01",
    })

    agosto = client.get(f"/api/contratos/{c['id']}/precio-en/2026-08-15").json()
    octubre = client.get(f"/api/contratos/{c['id']}/precio-en/2026-10-31").json()
    noviembre = client.get(f"/api/contratos/{c['id']}/precio-en/2026-11-01").json()

    assert agosto["importe"] == 45000
    assert octubre["importe"] == 45000
    assert noviembre["importe"] == 55000


def test_sin_precio_en_una_fecha_anterior_al_contrato(client, escenario):
    c = _contrato(client, escenario)
    r = client.get(f"/api/contratos/{c['id']}/precio-en/2026-07-01")
    assert r.status_code == 404


def test_el_precio_nuevo_no_puede_arrancar_antes_que_el_vigente(client, escenario):
    c = _contrato(client, escenario)
    r = client.post(f"/api/contratos/{c['id']}/precios", json={
        "importe": 55000, "vigencia_desde": _fecha(INICIO),
    })
    assert r.status_code == 409
    assert "tiene que empezar después" in r.json()["detail"]


def test_un_contrato_sin_cuota_no_acepta_precios(client, escenario):
    c = _contrato(client, escenario, tipo_contrato="prestamo", importe=None)
    r = client.post(f"/api/contratos/{c['id']}/precios", json={
        "importe": 1000, "vigencia_desde": _fecha(INICIO),
    })
    assert r.status_code == 409


def test_el_importe_no_se_edita_por_el_put_del_contrato(client, escenario):
    """Corregir un dato de la ficha y cambiar cuánto se cobra son cosas
    distintas. Si el PUT aceptara `importe` sobreescribiría el histórico, que
    es justo lo que la tabla de precios viene a impedir."""
    c = _contrato(client, escenario)
    r = client.put(f"/api/contratos/{c['id']}", json={"importe": 99999})
    # Pydantic lo descarta por no estar en el modelo, así que el importe no se
    # mueve. Lo que importa es el resultado, no qué capa lo frenó.
    assert r.status_code == 200
    assert client.get(f"/api/contratos/{c['id']}").json()["importe_vigente"] == 45000


def test_no_se_pasa_a_un_tipo_sin_cuota_teniendo_precio(client, escenario):
    c = _contrato(client, escenario)
    r = client.put(f"/api/contratos/{c['id']}", json={"tipo_contrato": "comodato"})
    assert r.status_code == 409


# ── El estado del activo no se puede contradecir con las líneas ────────────

def test_colocado_no_se_setea_a_mano(client, escenario):
    """`colocado` significa "tiene una línea abierta". Si se pudiera setear por
    los dos lados, un activo podría decir que está puesto sin ninguna línea que
    diga dónde."""
    r = client.put(f"/api/activos/{escenario['central']['id']}", json={"estado": "colocado"})
    assert r.status_code == 409
    assert "no se setea a mano" in r.json()["detail"]


def test_no_se_cambia_el_estado_de_un_activo_colocado(client, escenario):
    c = _contrato(client, escenario)
    _colocar(client, c, escenario["central"])
    r = client.put(f"/api/activos/{escenario['central']['id']}", json={"estado": "baja"})
    assert r.status_code == 409
    assert c["numero"] in r.json()["detail"]


def test_un_activo_de_baja_no_se_puede_colocar(client, escenario):
    client.put(f"/api/activos/{escenario['central']['id']}", json={"estado": "baja"})
    c = _contrato(client, escenario)
    r = client.post(f"/api/contratos/{c['id']}/equipos", json={
        "activo_id": escenario["central"]["id"], "fecha_instalacion": _fecha(INICIO),
    })
    assert r.status_code == 409


def test_la_invariante_estado_vs_lineas(client, escenario):
    """El chequeo que cierra el modelo: **ningún** activo `colocado` sin línea
    abierta, y **ninguna** línea abierta con su activo en otro estado.

    Se afirma sobre el juego completo después de ejercitar colocar, retirar y
    reemplazar, que son los tres caminos que tocan las dos cosas a la vez. Es la
    guarda que hace seguro haber guardado el estado en vez de derivarlo.
    """
    c = _contrato(client, escenario)
    _colocar(client, c, escenario["central"])
    linea = _colocar(client, c, escenario["tel_a"])
    client.post(f"/api/contratos/equipos/{linea['id']}/reemplazar", json={
        "activo_nuevo_id": escenario["tel_b"]["id"], "fecha": _fecha(INICIO + timedelta(days=20)),
    })
    otra = _colocar(client, _contrato(client, escenario), escenario["tel_a"],
                    fecha=INICIO + timedelta(days=30))
    client.post(f"/api/contratos/equipos/{otra['id']}/retirar", json={
        "fecha_retiro": _fecha(INICIO + timedelta(days=40)), "motivo_retiro": "devolucion",
    })

    activos = client.get("/api/activos").json()
    assert len(activos) == 3
    for a in activos:
        colocado_por_estado = a["estado"] == "colocado"
        colocado_por_linea = a["contrato_id"] is not None
        assert colocado_por_estado == colocado_por_linea, a


# ── Disponibilidad y resumen ───────────────────────────────────────────────

def test_disponibles_no_incluye_los_colocados(client, escenario):
    c = _contrato(client, escenario)
    _colocar(client, c, escenario["central"])

    disponibles = client.get("/api/activos?disponibles=true").json()
    seriales = {a["serial"] for a in disponibles}
    assert seriales == {"GS-A123", "GS-B456"}


def test_disponibles_tampoco_incluye_los_retirados_a_revisar(client, escenario):
    """`retirado_a_revisar` no está puesto en ningún lado pero tampoco se puede
    ofrecer: es exactamente la distinción que motivó ese estado."""
    c = _contrato(client, escenario)
    linea = _colocar(client, c, escenario["central"])
    client.post(f"/api/contratos/equipos/{linea['id']}/retirar", json={
        "fecha_retiro": _fecha(INICIO + timedelta(days=5)), "motivo_retiro": "devolucion",
    })

    disponibles = client.get("/api/activos?disponibles=true").json()
    assert escenario["central"]["serial"] not in {a["serial"] for a in disponibles}


def test_el_resumen_cuenta_por_estado(client, escenario):
    c = _contrato(client, escenario)
    _colocar(client, c, escenario["central"])

    resumen = client.get("/api/activos/resumen").json()
    assert resumen["total"] == 3
    assert resumen["por_estado"]["colocado"] == 1
    assert resumen["por_estado"]["disponible"] == 2
    assert resumen["por_estado"]["perdido"] == 0


def test_filtrar_activos_por_cliente(client, escenario):
    c = _contrato(client, escenario)
    _colocar(client, c, escenario["central"])
    otro = client.post("/api/clientes", json={"nombre": "Otro"}).json()

    del_cliente = client.get(f"/api/activos?cliente_id={escenario['cliente']['id']}").json()
    del_otro = client.get(f"/api/activos?cliente_id={otro['id']}").json()
    assert [a["serial"] for a in del_cliente] == ["YS-A123"]
    assert del_otro == []


# ── Identidad del activo ───────────────────────────────────────────────────

def test_serial_repetido(client, escenario):
    r = client.post("/api/activos", json={"tipo": "Router", "serial": "YS-A123"})
    assert r.status_code == 409
    assert "serial" in r.json()["detail"]


def test_codigo_interno_repetido(client, escenario):
    r = client.post("/api/activos", json={"tipo": "Router", "codigo_interno": "PAT-0001"})
    assert r.status_code == 409


def test_varios_activos_sin_serial_conviven(client):
    """Dos NULL no chocan en SQLite, que es lo que se quiere: muchos activos
    pueden no tener serial cargado. La cadena vacía del formulario web entra
    como NULL — si entrara como "" el segundo alta chocaría contra el UNIQUE."""
    for _ in range(3):
        assert client.post("/api/activos", json={
            "tipo": "Switch", "serial": "", "codigo_interno": "",
        }).status_code == 201
    assert len(client.get("/api/activos").json()) == 3


def test_estado_de_alta_invalido(client):
    r = client.post("/api/activos", json={"tipo": "Router", "estado": "prestado"})
    assert r.status_code == 409


# ── Borrado: lo que tiene historia no se borra ─────────────────────────────

def test_no_se_borra_un_activo_con_historial(client, escenario):
    c = _contrato(client, escenario)
    linea = _colocar(client, c, escenario["central"])
    client.post(f"/api/contratos/equipos/{linea['id']}/retirar", json={
        "fecha_retiro": _fecha(INICIO + timedelta(days=5)), "motivo_retiro": "devolucion",
    })
    assert client.delete(f"/api/activos/{escenario['central']['id']}").status_code == 409


def test_se_borra_un_activo_cargado_por_error(client, escenario):
    assert client.delete(f"/api/activos/{escenario['tel_b']['id']}").status_code == 204
    assert client.get(f"/api/activos/{escenario['tel_b']['id']}").status_code == 404


def test_no_se_borra_un_contrato_activo(client, escenario):
    c = _contrato(client, escenario)
    r = client.delete(f"/api/contratos/{c['id']}")
    assert r.status_code == 409
    assert "borrador" in r.json()["detail"]


def test_no_se_borra_un_borrador_con_equipos(client, escenario):
    c = _contrato(client, escenario, estado="borrador")
    _colocar(client, c, escenario["central"])
    assert client.delete(f"/api/contratos/{c['id']}").status_code == 409


def test_se_borra_un_borrador_vacio(client, escenario):
    c = _contrato(client, escenario, estado="borrador")
    assert client.delete(f"/api/contratos/{c['id']}").status_code == 204
    assert client.get(f"/api/contratos/{c['id']}").status_code == 404


# ── Filtros y 404 ──────────────────────────────────────────────────────────

def test_filtrar_contratos(client, escenario):
    alquiler = _contrato(client, escenario)
    comodato = _contrato(client, escenario, tipo_contrato="comodato", importe=None)

    por_tipo = client.get("/api/contratos?tipo_contrato=comodato").json()
    assert [c["id"] for c in por_tipo] == [comodato["id"]]

    _colocar(client, alquiler, escenario["central"])
    por_activo = client.get(
        f"/api/contratos?activo_id={escenario['central']['id']}"
    ).json()
    assert [c["id"] for c in por_activo] == [alquiler["id"]]


def test_la_ficha_trae_lineas_y_precios(client, escenario):
    """El listado no los trae y la ficha sí: la lista de contratos con el
    histórico completo de cada uno sería N+1 consultas para mostrar una tabla."""
    c = _contrato(client, escenario)
    _colocar(client, c, escenario["central"])

    ficha = client.get(f"/api/contratos/{c['id']}").json()
    assert len(ficha["lineas"]) == 1
    assert len(ficha["precios"]) == 1
    assert ficha["equipos_vigentes"] == 1

    listado = client.get("/api/contratos").json()
    assert "lineas" not in listado[0]
    assert listado[0]["equipos_vigentes"] == 1


def test_404_de_los_recursos(client, escenario):
    assert client.get("/api/contratos/999").status_code == 404
    assert client.get("/api/activos/999").status_code == 404
    assert client.get("/api/activos/999/historial").status_code == 404
    assert client.get("/api/contratos/999/equipos").status_code == 404
    c = _contrato(client, escenario)
    r = client.post(f"/api/contratos/{c['id']}/equipos", json={
        "activo_id": 999, "fecha_instalacion": _fecha(INICIO),
    })
    assert r.status_code == 404
    assert r.json()["detail"] == "activo not found"
