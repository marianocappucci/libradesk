"""Lo que el abono cubre no se factura, y lo que queda afuera sí.

Un cliente `tipo_facturacion='mensual'` paga un abono. Sus reclamos igual se
cargan —por trazabilidad— pero cobrarle el trabajo *y* el abono es cobrarle dos
veces. `reportes.facturacion()` ya aplicaba esa regla desde siempre (*"a los
`mensual` se les factura el abono, no la incidencia"*) y `convertir_a_remito()`
no la miraba: dos módulos del mismo producto con criterios opuestos sobre el
mismo cliente.

Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que no se le cobre lo que el abono cubre.** Es el defecto que esto vino
   a cerrar, y el caso más traicionero no es el reclamo entero cubierto sino la
   cobertura **parcial** que deja cero horas facturables: sin el corte, la línea
   caía en el "sin horas vale 1" y el remito cobraba una visita paga.
2. 🔴 **Que tampoco se deje de cobrar lo que cae afuera.** La guarda no puede
   ser "un cliente con abono no se remita": los materiales y las horas de
   excedente sí se facturan, y ese es medio pedido.
3. 🔴 **Que no se pueda emitir sin haber decidido.** `NULL` no es "se factura
   entero": es "nadie lo miró", y el remito se frena hasta que alguien elija.
4. Que el reclamo cubierto **quede igual vinculado** al remito y nombrado en las
   observaciones — si no, podría remitirse otra vez y ahí sí cobrarse.
5. Que editar el ticket no borre la decisión, que es como este producto ya
   perdió un campo antes.
6. Que un cliente sin abono se comporte **exactamente** como antes.
"""

import os
from datetime import datetime

import pytest

from app.services import inventario, materiales

CUANDO = datetime(2026, 8, 14, 10, 0, 0)


@pytest.fixture
def client(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def escenario(client):
    """Un cliente **con abono**, otro sin, y un item con precio de venta.

    Los dos clientes en el mismo escenario a propósito: casi todos los tests de
    abajo tienen que poder comparar contra el comportamiento de siempre, y con
    fixtures separadas la comparación se hace de memoria.
    """
    con_abono = client.post("/api/clientes", json={
        "nombre": "Medici Neumatec", "empresa": "NEUMYSER SRL",
        "cuit": "30-11111111-7", "ciudad": "Chivilcoy",
        "tipo_facturacion": "mensual",
    }).json()
    assert con_abono["tipo_facturacion"] == "mensual"
    sin_abono = client.post("/api/clientes", json={
        "nombre": "Otro", "empresa": "OTRO SA", "cuit": "30-22222222-8",
    }).json()
    item = inventario.crear_item("Plug RJ45", costo=120.0, precio=500.0)
    camioneta = inventario.crear_deposito("Kangoo")
    inventario.ajustar(item["id"], camioneta["id"], 40, fecha=CUANDO)
    return client, con_abono, sin_abono, item, camioneta


def _reclamo(client, cliente, horas=5, titulo="Central sin tono"):
    return client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "titulo": titulo,
        "horas_invertidas": horas,
    }).json()


def _guardar(client, incidencia, **extra):
    """Escribe por el PUT real, que es como guarda la pantalla."""
    payload = {**incidencia, **extra}
    r = client.put(f"/api/incidencias/{incidencia['id']}", json=payload)
    return r


def _cerrar(client, incidencia, **extra):
    r = _guardar(client, incidencia, estado="cerrado", **extra)
    assert r.status_code == 200, r.text
    return r.json()


def _convertir(client, ids):
    return client.post("/api/incidencias/convertir-en-remito",
                       json={"incidencia_ids": ids})


def _descripciones(remito):
    return [i["description"] for i in remito["items"]]


# ── Sin decidir no se emite ──────────────────────────────────────────────


def test_cliente_con_abono_sin_decidir_la_cobertura_no_genera_remito(escenario):
    """El corazón del arreglo: antes esto emitía el remito y le cobraba el
    trabajo a alguien que ya paga un abono."""
    client, con_abono, _, _, _ = escenario
    reclamo = _reclamo(client, con_abono)
    cerrado = _cerrar(client, reclamo)
    assert cerrado["cobertura_abono"] is None

    r = _convertir(client, [reclamo["id"]])

    assert r.status_code == 409, r.text
    # Que nombre CUÁL: con tres reclamos tildados, "falta decidir" sin decir
    # cuál obliga a abrirlos de a uno.
    assert f"#{reclamo['id']}" in r.json()["detail"]
    assert "abono" in r.json()["detail"].lower()


def test_cliente_sin_abono_no_necesita_decidir_nada(escenario):
    """El comportamiento de siempre, intacto. Si este test se pone en rojo, la
    guarda se comió a todos los clientes que se facturan por servicio."""
    client, _, sin_abono, _, _ = escenario
    reclamo = _reclamo(client, sin_abono, horas=2)
    _cerrar(client, reclamo)

    r = _convertir(client, [reclamo["id"]])

    assert r.status_code == 201, r.text
    remito = r.json()
    assert remito["items"][0]["qty"] == 2


# ── Cubierto entero ──────────────────────────────────────────────────────


def test_todo_dentro_del_abono_y_es_el_unico_no_hay_remito(escenario):
    client, con_abono, _, _, _ = escenario
    reclamo = _reclamo(client, con_abono)
    _cerrar(client, reclamo, cobertura_abono="total")

    r = _convertir(client, [reclamo["id"]])

    assert r.status_code == 409, r.text
    assert "no hay" in r.json()["detail"].lower()


def test_el_cubierto_no_aporta_lineas_pero_queda_vinculado_y_nombrado(escenario):
    """Mezcla: uno cubierto y uno que se factura.

    Las dos mitades importan. Que el cubierto **no** genere línea es no
    cobrarlo; que igual quede atado al remito es que no pueda volver a
    remitirse después —esa segunda vez sí lo cobraría—.
    """
    client, con_abono, _, _, _ = escenario
    cubierto = _reclamo(client, con_abono, titulo="Revisión mensual")
    afuera = _reclamo(client, con_abono, horas=3, titulo="Cambio de central")
    _cerrar(client, cubierto, cobertura_abono="total")
    _cerrar(client, afuera, cobertura_abono="fuera")

    r = _convertir(client, [cubierto["id"], afuera["id"]])

    assert r.status_code == 201, r.text
    remito = r.json()
    descripciones = " ".join(_descripciones(remito))
    assert "Revisión mensual" not in descripciones
    assert "Cambio de central" in descripciones
    # Nombrado en el papel: es lo que hace verificable que no se lo cobró por
    # error y no por olvido.
    assert f"#{cubierto['id']}" in remito["observations"]
    assert "sin cargo" in remito["observations"]
    # Y vinculado: el reclamo cubierto ya no se puede volver a remitir.
    ficha = client.get(f"/api/incidencias/{cubierto['id']}").json()
    assert ficha["remito_id"] == remito["id"]


# ── Cobertura parcial ────────────────────────────────────────────────────


def test_parcial_por_horas_factura_solo_el_excedente(escenario):
    client, con_abono, _, _, _ = escenario
    reclamo = _reclamo(client, con_abono, horas=5)
    _cerrar(client, reclamo, cobertura_abono="parcial",
            abono_horas_cubiertas=2, abono_materiales_incluidos=False)

    remito = _convertir(client, [reclamo["id"]]).json()

    trabajo = next(i for i in remito["items"] if "Central sin tono" in i["description"])
    assert trabajo["qty"] == 3


def test_parcial_con_todas_las_horas_cubiertas_no_cobra_la_visita(escenario):
    """El caso traicionero. Sin el corte explícito, cero horas facturables
    caían en el "sin horas cargadas vale 1" y el remito cobraba una visita que
    el abono ya paga. Los materiales sí se cobran: son lo único que quedó
    afuera."""
    client, con_abono, _, item, camioneta = escenario
    reclamo = _reclamo(client, con_abono, horas=4)
    materiales.cargar(reclamo["id"], item["id"], camioneta["id"], 10,
                      cuando=CUANDO)
    _cerrar(client, reclamo, cobertura_abono="parcial",
            abono_horas_cubiertas=4, abono_materiales_incluidos=False)

    remito = _convertir(client, [reclamo["id"]]).json()

    descripciones = _descripciones(remito)
    assert not any("Central sin tono" in d for d in descripciones), descripciones
    assert any("Plug RJ45" in d for d in descripciones), descripciones
    # Y lo que se cobra es el material, al precio de venta.
    assert remito["items"][0]["qty"] == 10
    assert remito["items"][0]["unit_price"] == 500


def test_parcial_con_los_materiales_dentro_del_abono_no_los_cobra(escenario):
    client, con_abono, _, item, camioneta = escenario
    reclamo = _reclamo(client, con_abono, horas=5)
    materiales.cargar(reclamo["id"], item["id"], camioneta["id"], 10,
                      cuando=CUANDO)
    _cerrar(client, reclamo, cobertura_abono="parcial",
            abono_horas_cubiertas=2, abono_materiales_incluidos=True)

    remito = _convertir(client, [reclamo["id"]]).json()

    descripciones = _descripciones(remito)
    assert not any("Plug RJ45" in d for d in descripciones), descripciones
    assert len(remito["items"]) == 1
    assert remito["items"][0]["qty"] == 3


def test_si_el_abono_cubre_todo_lo_del_parcial_no_sale_un_remito_vacio(escenario):
    """Un `parcial` que cubre las horas **y** los materiales es un `total`
    escrito de otra forma. Sin esta guarda saldría un comprobante sin una sola
    línea, que la bandeja recién rechazaría mucho más lejos, por total 0."""
    client, con_abono, _, item, camioneta = escenario
    reclamo = _reclamo(client, con_abono, horas=4)
    materiales.cargar(reclamo["id"], item["id"], camioneta["id"], 10,
                      cuando=CUANDO)
    _cerrar(client, reclamo, cobertura_abono="parcial",
            abono_horas_cubiertas=4, abono_materiales_incluidos=True)

    r = _convertir(client, [reclamo["id"]])

    assert r.status_code == 409, r.text
    assert "sin una sola linea" in r.json()["detail"]


# ── Lo que no se acepta guardar ──────────────────────────────────────────


def test_no_se_pueden_cubrir_mas_horas_de_las_trabajadas(escenario):
    """Cubrir 8 de 5 no es un caso raro: es un número mal tipeado, y sin esto
    el remito saldría con una cantidad negativa."""
    client, con_abono, _, _, _ = escenario
    reclamo = _reclamo(client, con_abono, horas=5)

    r = _guardar(client, reclamo, estado="cerrado", cobertura_abono="parcial",
                 abono_horas_cubiertas=8)

    assert r.status_code == 409, r.text
    assert "8" in r.json()["detail"] and "5" in r.json()["detail"]


def test_parcial_tiene_que_decir_que_cubre(escenario):
    client, con_abono, _, _, _ = escenario
    reclamo = _reclamo(client, con_abono)

    r = _guardar(client, reclamo, cobertura_abono="parcial")

    assert r.status_code == 409, r.text
    assert "qué cubre" in r.json()["detail"]


def test_un_cliente_sin_abono_no_puede_tener_cobertura(escenario):
    client, _, sin_abono, _, _ = escenario
    reclamo = _reclamo(client, sin_abono)

    r = _guardar(client, reclamo, cobertura_abono="total")

    assert r.status_code == 409, r.text
    assert "no tiene abono" in r.json()["detail"]


def test_cobertura_invalida_se_rechaza(escenario):
    client, con_abono, _, _, _ = escenario
    reclamo = _reclamo(client, con_abono)

    r = _guardar(client, reclamo, cobertura_abono="a_medias")

    assert r.status_code == 409, r.text


# ── Normalización y persistencia ─────────────────────────────────────────


def test_pasar_de_parcial_a_total_limpia_el_detalle(escenario):
    """Se limpia en vez de rechazarse: la pantalla guarda sola al salir de cada
    campo y manda el objeto entero, así que el detalle viejo viaja junto con la
    cobertura nueva sin que el usuario haya hecho nada raro. Una guarda que
    salta en uso normal es la guarda equivocada."""
    client, con_abono, _, _, _ = escenario
    reclamo = _reclamo(client, con_abono, horas=5)
    parcial = _cerrar(client, reclamo, cobertura_abono="parcial",
                      abono_horas_cubiertas=2, abono_materiales_incluidos=True)
    assert parcial["abono_horas_cubiertas"] == 2

    total = _cerrar(client, parcial, cobertura_abono="total")

    assert total["cobertura_abono"] == "total"
    assert total["abono_horas_cubiertas"] is None
    assert total["abono_materiales_incluidos"] is None


def test_editar_otro_campo_no_borra_la_cobertura(escenario):
    """El PUT manda el objeto entero: si la pantalla no reenvía estos campos,
    tocarle la prioridad a un ticket le borra la decisión y el remito vuelve a
    quedar frenado. Es exactamente como este producto perdió el `nro_cds` una
    vez."""
    client, con_abono, _, _, _ = escenario
    reclamo = _reclamo(client, con_abono, horas=5)
    guardado = _cerrar(client, reclamo, cobertura_abono="parcial",
                       abono_horas_cubiertas=2, abono_materiales_incluidos=False)

    despues = _cerrar(client, guardado, prioridad="alta")

    assert despues["prioridad"] == "alta"
    assert despues["cobertura_abono"] == "parcial"
    assert despues["abono_horas_cubiertas"] == 2
    assert despues["abono_materiales_incluidos"] is False
