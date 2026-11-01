"""Las altas, ediciones y bajas de `catalog_items` quedan en la auditoria (ADR-020).

`catalog_items` es del catalogo de LibraCommerce y no de un modelo ORM de este producto, asi que el
listener de `flush` de `libraauth` no lo ve. Se audita por el repositorio de LibraCommerce envuelto en
`RepositorioAuditado` (`services/inventario._repo`). Los tres caminos de escritura del catalogo --
consumibles (`/api/consumibles`), servicios (`/api/servicios`) y el valor hora-- pasan por ese
repositorio; el guard de abajo cuida que nadie lo construya desnudo.
"""
import re
from pathlib import Path

import pytest


@pytest.fixture
def client(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return client


def _log(client, entidad="producto"):
    datos = client.get("/api/logs", params={"entidad": entidad}).json()
    return list(reversed(datos["actividad"]))


def test_el_alta_de_un_consumible_queda_en_el_log(client):
    r = client.post("/api/consumibles", json={"nombre": "Toner X", "precio": 100})
    assert r.status_code == 201, r.text
    filas = _log(client)
    assert [(f["accion"], f["usuario"], f["entidad"]) for f in filas] == [("crear", "admin", "producto")]
    assert "Toner X" in filas[0]["descripcion"]


def test_la_edicion_registra_el_precio_que_cambio(client):
    cid = client.post("/api/consumibles", json={"nombre": "Toner X", "precio": 100}).json()["id"]
    r = client.put(f"/api/consumibles/{cid}", json={"nombre": "Toner X", "precio": 250})
    assert r.status_code in (200, 204), r.text
    edicion = [f for f in _log(client) if f["accion"] == "editar"]
    assert len(edicion) == 1
    cambios = edicion[0]["cambios"]
    assert [float(v) for v in cambios["default_sale_price"]] == [100.0, 250.0]


def test_la_baja_de_un_consumible_queda_como_edicion_de_activo(client):
    cid = client.post("/api/consumibles", json={"nombre": "Toner X"}).json()["id"]
    assert client.delete(f"/api/consumibles/{cid}").status_code == 204
    ultima = _log(client)[-1]
    assert ultima["accion"] == "editar"
    assert "active" in ultima["cambios"]


def test_el_alta_edicion_y_baja_de_un_servicio_quedan_en_el_log(client):
    s = client.post("/api/servicios", json={"nombre": "Hora tecnica", "precio": 1000}).json()
    r = client.put(f"/api/servicios/{s['id']}", json={
        "nombre": "Hora tecnica", "descripcion": "", "precio": 1500, "activo": True,
    })
    assert r.status_code == 200, r.text
    assert client.delete(f"/api/servicios/{s['id']}").status_code == 204
    assert [f["accion"] for f in _log(client)] == ["crear", "editar", "editar"]


def test_el_filtro_de_entidades_ofrece_producto(client):
    assert "producto" in client.get("/api/logs").json()["entidades"]


def test_el_catalogo_no_se_construye_desnudo():
    """Un `SqliteCommerceRepository(conn)` fuera de `inventario._repo` que llame a
    `save_catalog_item` escribiria el catalogo sin dejar fila, y un log incompleto se ve igual
    que uno completo."""
    raiz = Path(__file__).resolve().parent.parent / "app"
    desnudos = []
    for py in raiz.rglob("*.py"):
        if py.name == "inventario.py" and py.parent.name == "services":
            continue
        texto = py.read_text(encoding="utf-8")
        if "save_catalog_item(" in texto and re.search(r"SqliteCommerceRepository\(", texto):
            desnudos.append(str(py.relative_to(raiz)))
    assert not desnudos, f"escriben `catalog_items` con el repositorio desnudo: {desnudos}"
