"""La barra de estado del pie (libracore ADR-075, libra-ui ADR-083): `GET /api/estado-del-sistema` está montada, pide
sesión, y para el admin trae el respaldo. La sucursal la pone el frontend (el selector vive en el navegador)."""
import os


def test_sin_sesion_no_contesta(client):
    assert client.get("/api/estado-del-sistema").status_code == 401


def test_el_admin_ve_respaldo_y_version_del_motor(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    datos = client.get("/api/estado-del-sistema").json()
    assert datos["usuario"]["rol"] == "admin" and datos["libraedge"] is None
    assert datos["respaldo"] is not None and datos["version"]["motor"]
