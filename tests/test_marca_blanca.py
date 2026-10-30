"""La marca blanca está cableada: la instancia puede tener nombre, color y logo del revendedor (libracore ADR-092).

Lo que se mide acá es el **cableado** del producto, no el motor: que las rutas estén montadas, que escribirlas lo gatee el
rol del producto, que el manifest le gane al catch-all de la SPA y que el mail de recuperación salga con el nombre de la
marca. El comportamiento de la marca lo prueba `libracore`.
"""
import os

import pytest

pytestmark = pytest.mark.usefixtures("_marca_aislada")

MARCA = {"nombre": "Mesa de Ayuda Modelo", "nombre_corto": "Modelo", "color": "#c0392b"}


@pytest.fixture
def sin_sesion(client):
    """El `client` de conftest.py, sin loguear: es como llega el público (el login también lleva la marca)."""
    return client


@pytest.fixture
def admin(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


def test_sin_marca_la_instancia_es_la_del_producto(sin_sesion):
    r = sin_sesion.get("/api/marca")
    assert r.status_code == 200
    assert r.json()["propia"] is False
    assert r.json()["terminos_propios"] is False


def test_el_admin_carga_la_marca_y_cualquiera_la_lee(admin):
    assert admin.put("/api/marca", json=MARCA).status_code == 200
    admin.cookies.clear()  # sin sesión: el login también lleva la marca
    leida = admin.get("/api/marca").json()
    assert leida["propia"] is True
    assert leida["nombre"] == "Mesa de Ayuda Modelo"
    assert leida["color"] == "#c0392b"


@pytest.mark.parametrize("metodo", ["put", "delete"])
def test_sin_sesion_no_se_escribe_la_marca(sin_sesion, metodo):
    r = sin_sesion.request(metodo, "/api/marca", json=MARCA if metodo == "put" else None)
    assert r.status_code in (401, 403)


def test_sin_sesion_no_se_escriben_los_terminos_propios(sin_sesion):
    r = sin_sesion.put("/api/marca/terminos", json={"version": "r-1.0", "vigente_desde": "01-01-2026", "texto": "x"})
    assert r.status_code in (401, 403)


def test_el_manifest_es_el_de_la_marca_y_no_el_index_de_la_spa(admin):
    admin.put("/api/marca", json=MARCA)
    r = admin.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")
    assert r.json()["name"] == "Mesa de Ayuda Modelo"


def test_el_mail_de_recuperacion_sale_con_el_nombre_de_la_marca(admin):
    reset = admin.app.state.password_reset
    assert reset.product_name == "LibraDesk"
    admin.put("/api/marca", json=MARCA)
    assert reset.product_name == "Mesa de Ayuda Modelo"
    admin.delete("/api/marca")
    assert reset.product_name == "LibraDesk"


def test_el_manifest_le_gana_al_catch_all_de_la_spa(data_dir, url_de_base, tmp_path_factory, monkeypatch):
    """🔴 Con un build, la SPA contesta `index.html` a cualquier ruta que no conozca. Si la marca se montara después,
    el navegador leería HTML como manifest. Arma la app como `app.asgi` (create_app y después montar_spa) con un build de juguete."""
    from fastapi.testclient import TestClient

    import app.main as principal
    from app.spa import montar_spa
    from tests.conftest import construir_app

    dist = tmp_path_factory.mktemp("dist")
    (dist / "assets").mkdir()
    (dist / "index.html").write_text("<html>spa-de-prueba</html>", encoding="utf-8")
    (dist / "manifest.webmanifest").write_text('{"name": "LibraDesk", "icons": []}', encoding="utf-8")
    monkeypatch.setattr(principal, "frontend_dist", lambda: dist)

    app = construir_app(data_dir, url_de_base)
    montar_spa(app, dist)
    with TestClient(app, base_url="https://testserver") as c:
        r = c.get("/manifest.webmanifest")
        assert r.status_code == 200 and r.json()["name"] == "LibraDesk", r.text
        assert "manifest" in r.headers["content-type"]
        assert c.get("/ruta-del-cliente").text.startswith("<html>spa-de-prueba")
