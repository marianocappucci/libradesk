"""Smoke tests de la API real (auth + un flujo CRUD por dominio +
dashboard). No es cobertura exhaustiva de los 5 dominios — verifica que
el wiring completo (libraauth + SQLAlchemy + routers) funciona de punta
a punta contra una SQLite temporal."""
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Reimportar limpio: app.database/app.main tienen estado de modulo
    # (engine/session_factory globales) que no debe pisarse entre tests.
    import sys
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    from app.asgi import app
    # base_url https: la cookie de sesion se crea con secure=True (ver
    # libraauth/session_auth.py) — sobre http:// el cliente la descarta y
    # cualquier request post-login vuelve 401, mismo gotcha que ya
    # documentan los tests de libraauth.
    return TestClient(app, base_url="https://testserver")


def _login(client) -> None:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200


def test_health(client):
    assert client.get("/api/health").status_code == 200


def test_login_and_me(client):
    _login(client)
    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["role"] == "admin"


def test_cliente_equipo_incidencia_flow(client):
    _login(client)

    r = client.post("/api/clientes", json={"nombre": "Cliente Test", "email": "t@test.com"})
    assert r.status_code == 201
    cliente_id = r.json()["id"]

    r = client.post("/api/equipos", json={"cliente_id": cliente_id, "tipo": "Notebook"})
    assert r.status_code == 201
    equipo_id = r.json()["id"]

    r = client.post("/api/tecnicos", json={"nombre": "Tecnico Test"})
    assert r.status_code == 201
    tecnico_id = r.json()["id"]

    r = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "equipo_id": equipo_id, "tecnico_id": tecnico_id,
        "titulo": "No enciende", "prioridad": "alta",
    })
    assert r.status_code == 201
    incidencia_id = r.json()["id"]
    assert r.json()["estado"] == "abierto"

    r = client.put(f"/api/incidencias/{incidencia_id}", json={
        "cliente_id": cliente_id, "equipo_id": equipo_id, "tecnico_id": tecnico_id,
        "titulo": "No enciende", "prioridad": "alta", "estado": "resuelta",
        "resolucion": "Fuente cambiada",
    })
    assert r.status_code == 200
    assert r.json()["fecha_cierre"] is not None

    log = client.get(f"/api/incidencias/{incidencia_id}/estados").json()
    assert len(log) == 2
    assert log[0]["estado_nuevo"] == "resuelta"

    dash = client.get("/api/dashboard").json()
    assert dash["incidencias_por_estado"].get("resuelta") == 1
    assert dash["total_clientes_activos"] == 1


def test_incidencias_requires_auth(client):
    r = client.get("/api/incidencias")
    assert r.status_code == 401


def test_usuarios_requires_admin(client):
    _login(client)
    r = client.get("/api/usuarios")
    assert r.status_code == 200  # admin logueado


def test_export_xlsx(client):
    _login(client)
    client.post("/api/clientes", json={"nombre": "Cliente XLSX"})
    r = client.get("/api/reportes/clientes.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"] == XLSX_MIME


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _armar_datos_para_reportes(client) -> dict:
    """Un cliente por_servicio con equipo (garantia vencida), incidencia
    cerrada, actividad y movimiento — toca las 6 consultas analiticas."""
    cliente_id = client.post("/api/clientes", json={
        "nombre": "Reportes SA", "empresa": "Reportes SA",
        "tipo_facturacion": "por_servicio",
    }).json()["id"]
    equipo_id = client.post("/api/equipos", json={
        "cliente_id": cliente_id, "tipo": "Notebook", "marca": "Lenovo",
        "garantia_vence": "2020-01-01", "estado": "activo",
    }).json()["id"]
    tecnico_id = client.post("/api/tecnicos", json={"nombre": "Tec Reportes"}).json()["id"]
    incidencia_id = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "equipo_id": equipo_id, "tecnico_id": tecnico_id,
        "titulo": "Falla de fuente", "prioridad": "alta",
    }).json()["id"]
    client.post(f"/api/incidencias/{incidencia_id}/actividades",
                json={"descripcion": "Diagnostico inicial"})
    client.put(f"/api/incidencias/{incidencia_id}", json={
        "cliente_id": cliente_id, "equipo_id": equipo_id, "tecnico_id": tecnico_id,
        "titulo": "Falla de fuente", "prioridad": "alta", "estado": "cerrado",
    })
    return {"cliente_id": cliente_id, "equipo_id": equipo_id}


def test_reportes_analiticos_devuelven_xlsx(client):
    """Los 6 reportes reconstruidos responden 200 con un xlsx real. Se
    verifica la firma ZIP ('PK') y no solo el content-type: un 200 con
    cuerpo vacio pasaria el chequeo de header igual."""
    _login(client)
    _armar_datos_para_reportes(client)
    periodo = "desde=2020-01-01&hasta=2030-12-31"

    for url in [
        "/api/reportes/equipamiento.xlsx",
        f"/api/reportes/incidencias-periodo.xlsx?{periodo}",
        f"/api/reportes/facturacion.xlsx?{periodo}",
        "/api/reportes/garantias.xlsx?dias=60",
        f"/api/reportes/tecnico.xlsx?{periodo}",
        f"/api/reportes/movimientos.xlsx?{periodo}",
    ]:
        r = client.get(url)
        assert r.status_code == 200, f"{url} -> {r.status_code}"
        assert r.headers["content-type"] == XLSX_MIME, url
        assert r.content[:2] == b"PK", f"{url} no devolvio un xlsx real"


def test_reporte_periodo_exige_fechas(client):
    """`desde`/`hasta` son obligatorios: sin ellos el reporte no tiene
    sentido y el original respondia 400."""
    _login(client)
    assert client.get("/api/reportes/incidencias-periodo.xlsx").status_code == 422


def test_reportes_exigen_autenticacion(client):
    assert client.get("/api/reportes/garantias.xlsx").status_code == 401


def test_contenido_real_del_reporte_por_tecnico(client):
    """Lee el xlsx con openpyxl y confirma los numeros, no solo que baje:
    un reporte que devuelve un archivo vacio tambien daria 200."""
    from io import BytesIO

    from openpyxl import load_workbook

    _login(client)
    _armar_datos_para_reportes(client)
    r = client.get("/api/reportes/tecnico.xlsx?desde=2020-01-01&hasta=2030-12-31")
    ws = load_workbook(BytesIO(r.content)).active

    # Fila 4 = headers; 5 = primer tecnico; ultima = totales.
    assert ws.cell(row=4, column=1).value == "Técnico"
    assert ws.cell(row=5, column=1).value == "Tec Reportes"
    assert ws.cell(row=5, column=2).value == 1  # total
    assert ws.cell(row=5, column=5).value == 1  # cerradas
    assert ws.cell(row=5, column=6).value == "100%"  # % resolucion
    assert ws.cell(row=5, column=7).value == 1  # actividades
    assert ws.cell(row=6, column=1).value == "TOTAL"


def test_garantia_vencida_se_reporta_como_vencida(client):
    """El equipo del fixture vencio en 2020: la columna de dias tiene que
    decir 'Vencida hace Xd', no un numero de dias positivo."""
    from io import BytesIO

    from openpyxl import load_workbook

    _login(client)
    _armar_datos_para_reportes(client)
    r = client.get("/api/reportes/garantias.xlsx?dias=60")
    ws = load_workbook(BytesIO(r.content)).active
    assert str(ws.cell(row=5, column=9).value).startswith("Vencida hace")


def test_facturacion_solo_incluye_clientes_por_servicio(client):
    """Un cliente 'mensual' cobra abono, no incidencia: sus cerradas no
    deben aparecer en el reporte de facturacion."""
    from io import BytesIO

    from openpyxl import load_workbook

    _login(client)
    _armar_datos_para_reportes(client)  # por_servicio -> si aparece

    mensual_id = client.post("/api/clientes", json={
        "nombre": "Abono SA", "tipo_facturacion": "mensual",
    }).json()["id"]
    inc = client.post("/api/incidencias", json={
        "cliente_id": mensual_id, "titulo": "Incidencia de abono",
    }).json()["id"]
    client.put(f"/api/incidencias/{inc}", json={
        "cliente_id": mensual_id, "titulo": "Incidencia de abono", "estado": "cerrado",
    })

    r = client.get("/api/reportes/facturacion.xlsx?desde=2020-01-01&hasta=2030-12-31")
    ws = load_workbook(BytesIO(r.content)).active
    textos = [
        str(c.value) for fila in ws.iter_rows() for c in fila if c.value is not None
    ]
    assert any("Falla de fuente" in t for t in textos)
    assert not any("Incidencia de abono" in t for t in textos)
