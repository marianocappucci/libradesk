"""Los cargos de mano de obra de un reclamo.

Hasta hoy el remito de un reclamo llevaba **una sola línea de trabajo**: las
`horas_invertidas` al único valor hora del sistema. Eso no alcanza para lo que
una cuadrilla que sale a la calle factura: una visita son dos horas **más** un
viático **más** el traslado, y el viático no reemplaza a las horas — se suma.

🔑 **El tipo de cargo es un ítem del catálogo, no un enum**, y esa es la
decisión que deja base para ampliar: agregar «hora nocturna» o «feriado» es
cargar un ítem, sin código ni migración. Estos tests lo prueban creando un tipo
que no existía.

Lo que fijan, en orden de lo que duele si se rompe:

1. 🔴 **Que un reclamo SIN cargos siga saliendo exactamente como antes.** Es lo
   que hace que ningún ticket existente cambie de precio. Si se rompe, cambia
   la plata de todo lo que ya está cargado.
2. 🔴 **Que con cargos salga una línea por cargo**, y que el viático no
   reemplace a las horas.
3. 🔴 **Que el precio salga de la lista del cliente**, no del catálogo pelado.
4. Que agregar un tipo nuevo no necesite tocar código.
"""

import os

import pytest

from app.services import inventario, listas_precio


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
    """Un cliente, el valor hora, y los tres tipos de cargo en el catálogo.

    ⚠️ **Los cargos son ítems del CATÁLOGO, no de `/api/servicios`.** Los dos
    espacios de id conviven mientras la mudanza está en su primera release, y
    confundirlos cotiza el ítem equivocado: la primera versión de este test
    usaba un `servicios.id` como `item_id` y el remito salió $29.000 en vez de
    $43.000, sin fallar nada.

    El `POST /api/servicios` de acá abajo es para la tabla vieja **a propósito**:
    es de donde sale el valor hora del camino sin cargos, que es el que tiene
    que seguir funcionando igual.
    """
    cliente = client.post("/api/clientes", json={"nombre": "Medici Neumatec"}).json()
    client.post("/api/servicios", json={
        "nombre": "Hora de servicio técnico", "precio": 15000, "iva_rate": 0.21,
        "es_valor_hora": True,
    })
    hora = inventario.crear_servicio("Hora de servicio técnico", precio=15000.0,
                                     iva_rate=0.21)
    viatico = inventario.crear_servicio("Viático", precio=8000.0, iva_rate=0.21)
    traslado = inventario.crear_servicio("Traslado", precio=5000.0, iva_rate=0.21)
    return client, cliente, hora, viatico, traslado


def _reclamo_cerrado(client, cliente, horas=2):
    inc = client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "titulo": "Central sin tono",
        "horas_invertidas": horas,
    }).json()
    ficha = client.get(f"/api/incidencias/{inc['id']}").json()
    client.put(f"/api/incidencias/{inc['id']}", json={**ficha, "estado": "cerrado"})
    return inc


def _remito(client, incidencia_id):
    r = client.post("/api/incidencias/convertir-en-remito",
                    json={"incidencia_ids": [incidencia_id]})
    assert r.status_code == 201, r.text
    return r.json()


# ── 1. Sin cargos, todo sigue igual ──────────────────────────────────────


def test_sin_cargos_el_remito_sale_como_antes(escenario):
    """🔴 Es lo que hace que ningún ticket existente cambie de precio."""
    client, cliente, _h, _v, _t = escenario
    inc = _reclamo_cerrado(client, cliente, horas=2)

    remito = _remito(client, inc["id"])

    assert len(remito["items"]) == 1, "una sola línea de trabajo, como antes"
    linea = remito["items"][0]
    assert float(linea["qty"]) == pytest.approx(2.0), "las horas invertidas"
    assert float(linea["unit_price"]) == pytest.approx(15000.0), "al valor hora"


# ── 2. Con cargos, una línea por cargo ───────────────────────────────────


def test_el_viatico_se_suma_a_las_horas_y_no_las_reemplaza(escenario):
    """🔴 La razón de ser del cambio. Con un selector de "qué tarifa aplica"
    sólo se podría cobrar una de las tres cosas."""
    client, cliente, hora, viatico, traslado = escenario
    inc = _reclamo_cerrado(client, cliente, horas=2)

    for item_id, cantidad in ((hora["id"], 2), (viatico["id"], 1), (traslado["id"], 1)):
        r = client.post(f"/api/incidencias/{inc['id']}/cargos",
                        json={"item_id": item_id, "cantidad": cantidad})
        assert r.status_code == 201, r.text

    remito = _remito(client, inc["id"])

    assert len(remito["items"]) == 3, "tres cargos son tres líneas"
    total = sum(float(i["qty"]) * float(i["unit_price"]) for i in remito["items"])
    assert total == pytest.approx(2 * 15000 + 8000 + 5000), (
        "las dos horas MÁS el viático MÁS el traslado"
    )


def test_cada_linea_dice_de_que_reclamo_es(escenario):
    """Con tres cargos en el remito hay que poder leer renglón por renglón a qué
    visita corresponde cada uno, igual que con los materiales."""
    client, cliente, _hora, viatico, _t = escenario
    inc = _reclamo_cerrado(client, cliente)
    client.post(f"/api/incidencias/{inc['id']}/cargos",
                json={"item_id": viatico["id"], "cantidad": 1})

    remito = _remito(client, inc["id"])
    assert "Viático" in remito["items"][0]["description"]
    assert str(inc["id"]) in remito["items"][0]["description"]


def test_un_cargo_en_cero_no_es_un_cargo(escenario):
    client, cliente, _hora, viatico, _t = escenario
    inc = _reclamo_cerrado(client, cliente)

    r = client.post(f"/api/incidencias/{inc['id']}/cargos",
                    json={"item_id": viatico["id"], "cantidad": 0})
    assert r.status_code == 422


def test_quitar_un_cargo_lo_saca_del_remito(escenario):
    client, cliente, _hora, viatico, _t = escenario
    inc = _reclamo_cerrado(client, cliente, horas=2)
    cargo = client.post(f"/api/incidencias/{inc['id']}/cargos",
                        json={"item_id": viatico["id"], "cantidad": 1}).json()

    client.delete(f"/api/incidencias/{inc['id']}/cargos/{cargo['id']}")

    # Sin cargos vuelve al camino de siempre: las horas al valor hora.
    remito = _remito(client, inc["id"])
    assert len(remito["items"]) == 1
    assert float(remito["items"][0]["unit_price"]) == pytest.approx(15000.0)


# ── 3. El precio sale de la lista del cliente ────────────────────────────


def test_el_cargo_cotiza_por_la_lista_del_cliente(escenario):
    """🔴 Es lo que hace que un reseller tenga otro viático que un mostrador."""
    client, cliente, _hora, viatico, _t = escenario
    reseller = listas_precio.crear("Resellers")
    listas_precio.fijar_precio(reseller["id"], viatico["id"], 6000.0)
    ficha = client.get(f"/api/clientes/{cliente['id']}").json()
    client.put(f"/api/clientes/{cliente['id']}",
               json={**ficha, "price_list_id": reseller["id"]})

    inc = _reclamo_cerrado(client, cliente)
    client.post(f"/api/incidencias/{inc['id']}/cargos",
                json={"item_id": viatico["id"], "cantidad": 1})

    # La ficha del reclamo tiene que mostrar el mismo precio que el remito.
    cargos = client.get(f"/api/incidencias/{inc['id']}/cargos").json()
    assert cargos[0]["precio"] == pytest.approx(6000.0)

    remito = _remito(client, inc["id"])
    assert float(remito["items"][0]["unit_price"]) == pytest.approx(6000.0)


# ── 4. Ampliar no toca código ────────────────────────────────────────────


def test_un_tipo_de_cargo_nuevo_no_necesita_tocar_nada(escenario):
    """🔑 La prueba de que el tipo es un dato y no un enum.

    «Hora nocturna» no existe en ninguna constante del producto. Se carga como
    ítem y se cobra igual que los otros: si mañana hiciera falta «feriado» o
    «especialista senior», es lo mismo.
    """
    client, cliente, _h, _v, _t = escenario
    nocturna = inventario.crear_servicio("Hora nocturna", precio=22000.0, iva_rate=0.21)

    inc = _reclamo_cerrado(client, cliente)
    r = client.post(f"/api/incidencias/{inc['id']}/cargos",
                    json={"item_id": nocturna["id"], "cantidad": 3})
    assert r.status_code == 201, r.text

    remito = _remito(client, inc["id"])
    assert float(remito["items"][0]["unit_price"]) == pytest.approx(22000.0)
    assert float(remito["items"][0]["qty"]) == pytest.approx(3.0)
