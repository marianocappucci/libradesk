"""El detalle por ítem en remitos y presupuestos.

La aclaración corta que va DEBAJO del nombre de un ítem, opcional renglón por
renglón. No es `observations`, que es una sola y describe el comprobante
entero: ésta describe **un** ítem, y la mayoría de los ítems no la necesita.

El PDF lo dibuja LibraCore (`pdf_generator._draw_items_table`, en itálica más
chica y en el gris apagado). Lo que fijan estos tests es lo de este lado:

1. que el campo llegue entero del payload al JSON guardado;
2. que un detalle vacío **no** escriba la clave — un comprobante sin detalles
   queda igual que antes de que el campo existiera;
3. que la conversión presupuesto→remito lo lleve. En LibraDesk la conversión
   **recomputa** los totales con IVA por línea en vez de copiar verbatim, así
   que el detalle podría perderse ahí sin que se note en el presupuesto.
"""

import os

import pytest


@pytest.fixture
def client(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def cliente_id(client):
    return client.post("/api/clientes", json={"nombre": "Medici Neumatec"}).json()["id"]


def _presupuesto(cliente_id, items):
    return {"client_id": cliente_id, "date": "2026-09-08", "tax_rate": 0.21,
            "items": items}


def test_el_detalle_del_item_se_guarda(client, cliente_id):
    r = client.post("/api/presupuestos", json=_presupuesto(cliente_id, [
        {"description": "Cambio de cubierta", "qty": 4, "unit_price": 1000,
         "detalle": "rodado 15, incluye balanceo"},
    ]))
    assert r.status_code == 201, r.text
    item = r.json()["items"][0]
    assert item["detalle"] == "rodado 15, incluye balanceo"
    assert item["description"] == "Cambio de cubierta"   # el nombre no lo absorbe


def test_un_item_sin_detalle_no_escribe_la_clave(client, cliente_id):
    r = client.post("/api/presupuestos", json=_presupuesto(cliente_id, [
        {"description": "Con espacios", "qty": 1, "unit_price": 10, "detalle": "   "},
        {"description": "Sin campo", "qty": 1, "unit_price": 10},
    ]))
    assert r.status_code == 201, r.text
    con_espacios, sin_campo = r.json()["items"]
    assert "detalle" not in con_espacios
    assert "detalle" not in sin_campo


def test_editar_puede_borrar_el_detalle(client, cliente_id):
    creado = client.post("/api/presupuestos", json=_presupuesto(cliente_id, [
        {"description": "Item", "qty": 1, "unit_price": 10, "detalle": "aclaración"},
    ])).json()
    assert creado["items"][0]["detalle"] == "aclaración"

    r = client.put(f"/api/presupuestos/{creado['id']}", json=_presupuesto(cliente_id, [
        {"description": "Item", "qty": 1, "unit_price": 10, "detalle": ""},
    ]))
    assert r.status_code == 200, r.text
    assert "detalle" not in r.json()["items"][0]


def test_el_remito_tambien_lo_acepta(client, cliente_id):
    r = client.post("/api/remitos", json={
        "client_id": cliente_id, "date": "2026-09-08", "tax_rate": 0.21,
        "items": [{"description": "Cubierta 195/65", "qty": 4, "unit_price": 1000,
                   "detalle": "entregadas en el taller"}],
    })
    assert r.status_code == 201, r.text
    assert r.json()["items"][0]["detalle"] == "entregadas en el taller"


def test_convertir_a_remito_se_lleva_el_detalle(client, cliente_id):
    """🔴 La conversión de LibraDesk NO copia verbatim: recompone cada línea.

    Recompone para recalcular el IVA por línea, y en esa recomposición es donde
    un campo nuevo se cae sin que nada falle: el presupuesto sigue mostrando el
    detalle y el remito sale sin él.
    """
    creado = client.post("/api/presupuestos", json=_presupuesto(cliente_id, [
        {"description": "Service completo", "qty": 1, "unit_price": 5000,
         "detalle": "incluye filtros y aceite"},
    ])).json()

    r = client.post(f"/api/presupuestos/{creado['id']}/convertir-en-remito")
    assert r.status_code == 201, r.text
    assert r.json()["items"][0]["detalle"] == "incluye filtros y aceite"
