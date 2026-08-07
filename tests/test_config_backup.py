"""Datos de empresa con logo, y Datos / Backup — ítems 1 y 4.

El mecanismo es de `libracore` (`config_router.py` + `respaldo.py`) y tiene sus
propios tests ahí, incluida la validación del ZIP y el rechazo de un backup
ajeno. Lo que se prueba **acá** es lo que sólo este producto puede verificar:

1. 🔴 Que la `Instancia` esté bien armada — que el backup contenga **la base de
   este producto** y sus logos. Mal armada no falla: da un ZIP que se
   descarga, pesa poco y no sirve para restaurar. Un backup incompleto se ve
   igual que uno completo.
2. Que los gates sean los de LibraDesk: la lectura abierta al staff (el
   generador de PDF la usa), la escritura y el backup sólo admin.
"""
import zipfile

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import sys
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    from app.asgi import app
    c = TestClient(app, base_url="https://testserver")
    c.data_dir = tmp_path
    return c


def _login(client, usuario="admin", clave="admin") -> None:
    r = client.post("/auth/login", json={"username": usuario, "password": clave})
    assert r.status_code == 200, r.text


def _staff(client) -> TestClient:
    """Un segundo cliente logueado como staff, sobre la misma app."""
    r = client.post("/api/usuarios", json={
        "username": "tecnico-1", "name": "Técnico", "password": "tecnico-pass", "role": "staff",
    })
    assert r.status_code in (200, 201), r.text
    otro = TestClient(client.app, base_url="https://testserver")
    _login(otro, "tecnico-1", "tecnico-pass")
    return otro


def _png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"0" * 40


# ── 🔴 Que el backup contenga lo de este producto ─────────────────────────

def test_el_backup_trae_la_base_y_el_logo_de_esta_instancia(client):
    """Si la `Instancia` apuntara a la base equivocada —o a ninguna— el
    endpoint devolvería un ZIP igual, sólo que sin nada adentro que sirva. No
    hay forma de notarlo desde la pantalla."""
    _login(client)
    client.post("/api/clientes", json={"nombre": "Cliente que tiene que estar en el backup"})
    client.post("/api/config/empresa/logo", files={"logo": ("l.png", _png(), "image/png")})

    r = client.get("/api/config/backup-ahora")
    assert r.status_code == 200, r.text

    import io
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        dentro = z.namelist()
        assert "bases/libradesk.db" in dentro, dentro
        assert "datos/logos/logo.png" in dentro, dentro
        # Y que la base traiga los datos de verdad, no un archivo vacío.
        z.extract("bases/libradesk.db", client.data_dir / "verificacion")

    import sqlite3
    conn = sqlite3.connect(str(client.data_dir / "verificacion" / "bases" / "libradesk.db"))
    try:
        nombres = [f[0] for f in conn.execute("SELECT nombre FROM clientes").fetchall()]
    finally:
        conn.close()
    assert "Cliente que tiene que estar en el backup" in nombres


def test_crear_listar_y_restaurar(client):
    _login(client)
    client.post("/api/clientes", json={"nombre": "Antes del backup"})

    creado = client.post("/api/config/backups")
    assert creado.status_code == 200, creado.text
    nombre = creado.json()["filename"]
    assert [f["filename"] for f in client.get("/api/config/backups").json()] == [nombre]

    client.post("/api/clientes", json={"nombre": "Después del backup"})

    zip_bytes = client.get(f"/api/config/backups/{nombre}").content
    r = client.post("/api/config/restore",
                    files={"backup_file": ("b.zip", zip_bytes, "application/zip")})
    assert r.status_code == 200, r.text

    nombres = [c["nombre"] for c in client.get("/api/clientes").json()]
    assert "Antes del backup" in nombres
    assert "Después del backup" not in nombres


# ── Empresa y logo ────────────────────────────────────────────────────────

def test_los_datos_de_empresa_siguen_funcionando_en_la_ruta_nueva(client):
    """La ruta cambió de `/api/config-empresa` a `/api/config/empresa` al pasar
    al router del motor. El comportamiento tiene que ser el mismo."""
    _login(client)
    r = client.put("/api/config/empresa", json={
        "empresa_nombre": "Compulibra", "empresa_cuit": "20-12345678-9",
    })
    assert r.status_code == 200, r.text
    assert client.get("/api/config/empresa").json()["empresa_cuit"] == "20-12345678-9"


def test_subir_el_logo_y_que_el_pdf_lo_encuentre(client):
    """El generador de PDF de LibraCore ya buscaba el logo en `LOGO_DIR`; lo
    que no existía era el modo de ponerlo ahí sin entrar al volumen. Este test
    cierra ese hueco end-to-end: se sube por HTTP y `resolve_logo_path` lo ve."""
    _login(client)
    r = client.post("/api/config/empresa/logo", files={"logo": ("l.png", _png(), "image/png")})
    assert r.status_code == 200, r.text

    from libracore import config_manager
    assert config_manager.resolve_logo_path().endswith("logo.png")
    assert client.get("/api/config/empresa/logo").content == _png()


# ── Gates ─────────────────────────────────────────────────────────────────

def test_el_staff_lee_los_datos_de_empresa(client):
    """No es admin-only a propósito: el generador de PDF los usa, y cerrarlo
    rompería la previsualización de un remito para cualquiera que no sea
    admin."""
    _login(client)
    assert _staff(client).get("/api/config/empresa").status_code == 200


def test_el_staff_no_los_edita(client):
    _login(client)
    r = _staff(client).put("/api/config/empresa", json={"empresa_nombre": "Pirata"})
    assert r.status_code == 403


def test_el_staff_no_sube_el_logo(client):
    _login(client)
    r = _staff(client).post(
        "/api/config/empresa/logo", files={"logo": ("l.png", _png(), "image/png")},
    )
    assert r.status_code == 403


def test_el_staff_no_toca_los_backups(client):
    """Un backup es una copia completa de los datos del cliente, con los
    usuarios adentro: quien lo baje se lleva todo."""
    _login(client)
    staff = _staff(client)
    assert staff.get("/api/config/backups").status_code == 403
    assert staff.get("/api/config/backup-ahora").status_code == 403
    assert staff.post("/api/config/backups").status_code == 403
    assert staff.post(
        "/api/config/restore", files={"backup_file": ("b.zip", b"x", "application/zip")},
    ).status_code == 403
