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


def test_usuario_duplicado_devuelve_409(client):
    """Bug latente que estuvo vivo desde el dia 1 y no tenia test.

    Un username repetido tiene que dar 409, no 500. Con el pin viejo de
    libraauth (`v0.1.0`) el duplicado propagaba el `IntegrityError` de
    SQLAlchemy; desde `v0.1.1` levanta `UsernameTaken`, que **no hereda de
    ValueError**, asi que el `except ValueError` del router tampoco lo
    agarraba: bumpear el pin solo no arreglaba nada. Ver
    wiki/entities/libraauth.md.
    """
    _login(client)
    alta = {"username": "repetido", "name": "Repetido", "password": "secreta123",
            "role": "admin"}
    assert client.post("/api/usuarios", json=alta).status_code == 201
    assert client.post("/api/usuarios", json=alta).status_code == 409


def test_usuario_con_rol_invalido_devuelve_422(client):
    """El otro camino del mismo `try`: que el `except UsernameTaken` nuevo no
    se coma el 422 que ya existia."""
    _login(client)
    r = client.post("/api/usuarios", json={
        "username": "rolmalo", "name": "Rol Malo", "password": "secreta123",
        "role": "rol-que-no-existe"})
    assert r.status_code == 422


def test_export_xlsx(client):
    _login(client)
    client.post("/api/clientes", json={"nombre": "Cliente XLSX"})
    r = client.get("/api/reportes/clientes.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"] == XLSX_MIME


XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _equipo_de_prueba(client, **extra) -> int:
    cliente_id = client.post("/api/clientes", json={"nombre": "Cliente Mov"}).json()["id"]
    body = {"cliente_id": cliente_id, "tipo": "Notebook", "marca": "Lenovo",
            "sector": "Administracion", "ubicacion_oficina": "Piso 2",
            "estado": "activo"}
    body.update(extra)
    return client.post("/api/equipos", json=body).json()["id"]


def test_alta_de_equipo_registra_movimiento(client):
    _login(client)
    equipo_id = _equipo_de_prueba(client)

    movs = client.get(f"/api/equipos/{equipo_id}/movimientos").json()
    assert len(movs) == 1
    assert movs[0]["tipo"] == "alta"
    assert movs[0]["descripcion"] == "Alta: Notebook Lenovo"
    assert movs[0]["sector_destino"] == "Administracion"
    assert movs[0]["ubicacion_destino"] == "Piso 2"
    # El actor queda registrado, no "Sistema".
    assert movs[0]["usuario"] == "admin"


def test_traslado_registra_origen_y_destino(client):
    _login(client)
    equipo_id = _equipo_de_prueba(client)

    client.put(f"/api/equipos/{equipo_id}", json={
        "cliente_id": 1, "tipo": "Notebook", "marca": "Lenovo",
        "sector": "Deposito", "ubicacion_oficina": "Subsuelo",
        "estado": "activo", "motivo": "Reubicacion por obra",
    })

    movs = client.get(f"/api/equipos/{equipo_id}/movimientos").json()
    traslado = next(m for m in movs if m["tipo"] == "traslado")
    assert traslado["sector_origen"] == "Administracion"
    assert traslado["sector_destino"] == "Deposito"
    assert traslado["ubicacion_origen"] == "Piso 2"
    assert traslado["ubicacion_destino"] == "Subsuelo"
    assert traslado["motivo"] == "Reubicacion por obra"
    assert traslado["descripcion"] == "Traslado → Deposito"


def test_cambio_de_estado_registra_movimiento_con_ese_tipo(client):
    """El `tipo` del movimiento es el estado nuevo: asi el reporte lo
    etiqueta 'Reparación'/'Baja'/'Reactivado' via MOV_LABEL."""
    _login(client)
    equipo_id = _equipo_de_prueba(client)

    base = {"cliente_id": 1, "tipo": "Notebook", "marca": "Lenovo",
            "sector": "Administracion", "ubicacion_oficina": "Piso 2"}
    client.put(f"/api/equipos/{equipo_id}", json={**base, "estado": "en_reparacion",
                                                 "motivo": "No enciende"})

    movs = client.get(f"/api/equipos/{equipo_id}/movimientos").json()
    cambio = next(m for m in movs if m["tipo"] == "en_reparacion")
    assert cambio["descripcion"] == "Estado cambiado a: en_reparacion"
    assert cambio["motivo"] == "No enciende"


def test_un_update_sin_cambios_relevantes_no_ensucia_el_historial(client):
    """Corregir el serial no es un movimiento: si cada PUT generara una
    fila, el historial se volveria inservible."""
    _login(client)
    equipo_id = _equipo_de_prueba(client)
    antes = len(client.get(f"/api/equipos/{equipo_id}/movimientos").json())

    client.put(f"/api/equipos/{equipo_id}", json={
        "cliente_id": 1, "tipo": "Notebook", "marca": "Lenovo",
        "sector": "Administracion", "ubicacion_oficina": "Piso 2",
        "estado": "activo", "serial": "CORREGIDO-123",
    })

    despues = client.get(f"/api/equipos/{equipo_id}/movimientos").json()
    assert len(despues) == antes


def test_traslado_y_cambio_de_estado_juntos_generan_dos_movimientos(client):
    """Un equipo que vuelve del service Y cambia de sector son dos hechos
    distintos, y el historial tiene que reflejar los dos."""
    _login(client)
    equipo_id = _equipo_de_prueba(client, estado="en_reparacion")

    client.put(f"/api/equipos/{equipo_id}", json={
        "cliente_id": 1, "tipo": "Notebook", "marca": "Lenovo",
        "sector": "Consultorios", "ubicacion_oficina": "Consultorio 4",
        "estado": "activo",
    })

    movs = client.get(f"/api/equipos/{equipo_id}/movimientos").json()
    tipos = [m["tipo"] for m in movs]
    assert "traslado" in tipos
    assert "activo" in tipos
    assert len(movs) == 3  # alta + traslado + reactivacion


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


# ─── Remitos y presupuestos (dominio reusado de libracore) ──────────────

def _cliente_para_comprobantes(client) -> int:
    return client.post("/api/clientes", json={
        "nombre": "Juan Perez", "empresa": "Compulibra SRL",
        "email": "facturacion@compulibra.com.ar", "telefono": "3514567890",
        "ciudad": "Cordoba",
    }).json()["id"]


_ITEMS = [
    {"description": "Reparacion de notebook", "qty": 2, "unit_price": 15000},
    {"description": "Cambio de disco SSD 480GB", "qty": 1, "unit_price": 45000},
]


def test_remito_con_client_id_real_se_inserta(client):
    """El test que justifica el diseno del schema: el DDL de LibraCore declara
    `client_id REFERENCES clients(id)` y LibraDesk no tiene `clients`. Como
    `libracore.db.core.get_connection()` corre `PRAGMA foreign_keys = ON` en
    toda conexion, dejar esa FK haria fallar TODO insert con `no such table:
    main.clients` — incluso con client_id NULL. Si alguien "restaura" la FK
    copiando el DDL original, este test se pone rojo."""
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)

    r = client.post("/api/remitos", json={"client_id": cliente_id, "items": _ITEMS})
    assert r.status_code == 201, r.text
    remito = r.json()

    assert remito["client_id"] == cliente_id
    assert remito["client_name"] == "Compulibra SRL"   # empresa, no nombre
    assert remito["client_email"] == "facturacion@compulibra.com.ar"
    assert remito["client_address"] == "Cordoba"
    assert remito["number"].startswith("0001-")
    assert len(remito["items"]) == 2


def test_remito_calcula_los_totales_en_el_servidor(client):
    """Los importes no se aceptan del front: 2*15000 + 1*45000 = 75000."""
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)

    remito = client.post("/api/remitos", json={
        "client_id": cliente_id, "items": _ITEMS, "tax_rate": 0.21,
    }).json()

    assert remito["subtotal"] == 75000
    assert remito["tax_amount"] == 15750
    assert remito["total"] == 90750
    assert remito["items"][0]["subtotal"] == 30000


def test_remito_de_cliente_inexistente_da_404(client):
    """La FK no existe, asi que la integridad la sostiene el router."""
    _login(client)
    r = client.post("/api/remitos", json={"client_id": 99999, "items": _ITEMS})
    assert r.status_code == 404


def test_remito_sin_items_es_rechazado(client):
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)
    r = client.post("/api/remitos", json={"client_id": cliente_id, "items": []})
    assert r.status_code == 422


def test_next_number_no_choca_con_la_ruta_de_detalle(client):
    """/next-number va declarada antes de /{remito_id}; al reves daria 422
    porque "next-number" no parsea como int."""
    _login(client)
    r = client.get("/api/remitos/next-number")
    assert r.status_code == 200
    assert r.json()["number"].startswith("0001-")


def test_remitos_exigen_autenticacion(client):
    """Los routers de dominio ya se habian olvidado la autenticacion una vez
    (solo /api/usuarios la tenia); se cubre explicitamente."""
    assert client.get("/api/remitos").status_code == 401
    assert client.get("/api/presupuestos").status_code == 401
    assert client.post("/api/remitos", json={"client_id": 1, "items": _ITEMS}).status_code == 401


def test_remito_pdf_es_un_pdf_real(client):
    """No alcanza con un 200: se verifica la firma del archivo y que el
    generador de LibraCore produjo algo con contenido."""
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)
    remito_id = client.post("/api/remitos", json={
        "client_id": cliente_id, "items": _ITEMS, "observations": "Retira el cliente",
    }).json()["id"]

    r = client.get(f"/api/remitos/{remito_id}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF")
    assert len(r.content) > 1000

    # El path queda guardado en la fila, como en Contalibra/Restolibra.
    assert client.get(f"/api/remitos/{remito_id}").json()["pdf_path"].endswith(".pdf")


def test_presupuesto_flujo_completo_y_conversion_a_remito(client):
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)

    p = client.post("/api/presupuestos", json={
        "client_id": cliente_id, "items": _ITEMS,
    })
    assert p.status_code == 201, p.text
    presupuesto = p.json()
    assert presupuesto["number"].startswith("PRES-")
    assert presupuesto["status"] == "borrador"
    assert presupuesto["total"] == 90750

    pid = presupuesto["id"]
    r = client.patch(f"/api/presupuestos/{pid}/estado", json={"status": "enviado"})
    assert r.status_code == 200
    assert r.json()["status"] == "enviado"

    r = client.post(f"/api/presupuestos/{pid}/convertir-en-remito")
    assert r.status_code == 201, r.text
    remito = r.json()
    assert remito["total"] == presupuesto["total"]
    assert presupuesto["number"] in remito["observations"]

    despues = client.get(f"/api/presupuestos/{pid}").json()
    assert despues["status"] == "aceptado"
    assert despues["remito_id"] == remito["id"]


def test_convertir_dos_veces_no_emite_un_segundo_remito(client):
    """Idempotente a proposito: dos clicks no facturan el trabajo dos veces."""
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)
    pid = client.post("/api/presupuestos", json={
        "client_id": cliente_id, "items": _ITEMS,
    }).json()["id"]

    primero = client.post(f"/api/presupuestos/{pid}/convertir-en-remito").json()
    segundo = client.post(f"/api/presupuestos/{pid}/convertir-en-remito").json()

    assert primero["id"] == segundo["id"]
    assert len(client.get("/api/remitos").json()) == 1


def test_presupuesto_enviado_y_expirado_aparece_vencido_solo(client):
    """El vencimiento lo corre LibraCore al leer, sin tarea programada: un
    `enviado` con valid_until pasado sale `vencido` del listado."""
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)

    pid = client.post("/api/presupuestos", json={
        "client_id": cliente_id, "items": _ITEMS,
        "valid_until": "2020-01-01", "status": "enviado",
    }).json()["id"]

    # El detalle no dispara el vencimiento; el listado si.
    assert client.get(f"/api/presupuestos/{pid}").json()["status"] == "enviado"
    listado = client.get("/api/presupuestos").json()
    assert next(p for p in listado if p["id"] == pid)["status"] == "vencido"
    assert client.get("/api/presupuestos/resumen").json()["vencido"] == 1


def test_convertir_un_presupuesto_vencido_da_409(client):
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)
    pid = client.post("/api/presupuestos", json={
        "client_id": cliente_id, "items": _ITEMS,
        "valid_until": "2020-01-01", "status": "enviado",
    }).json()["id"]
    client.get("/api/presupuestos")  # dispara el vencimiento

    r = client.post(f"/api/presupuestos/{pid}/convertir-en-remito")
    assert r.status_code == 409


def test_solo_se_borra_un_presupuesto_en_borrador(client):
    """Regla de LibraCore, no propia: en cualquier otro estado levanta
    ValueError, que el router traduce a 409."""
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)

    borrador = client.post("/api/presupuestos", json={
        "client_id": cliente_id, "items": _ITEMS,
    }).json()["id"]
    assert client.delete(f"/api/presupuestos/{borrador}").status_code == 204

    enviado = client.post("/api/presupuestos", json={
        "client_id": cliente_id, "items": _ITEMS, "status": "enviado",
    }).json()["id"]
    assert client.delete(f"/api/presupuestos/{enviado}").status_code == 409
    assert client.get(f"/api/presupuestos/{enviado}").status_code == 200


def test_estado_invalido_es_rechazado(client):
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)
    pid = client.post("/api/presupuestos", json={
        "client_id": cliente_id, "items": _ITEMS,
    }).json()["id"]
    assert client.patch(f"/api/presupuestos/{pid}/estado",
                        json={"status": "pagado"}).status_code == 422


def test_presupuesto_pdf_es_un_pdf_real(client):
    _login(client)
    cliente_id = _cliente_para_comprobantes(client)
    pid = client.post("/api/presupuestos", json={
        "client_id": cliente_id, "items": _ITEMS,
    }).json()["id"]

    r = client.get(f"/api/presupuestos/{pid}/pdf")
    assert r.status_code == 200
    assert r.content.startswith(b"%PDF")
    assert len(r.content) > 1000


def test_config_empresa_ida_y_vuelta(client):
    """El encabezado de los PDF. Sin esto salen con la empresa en blanco."""
    _login(client)
    assert client.get("/api/config-empresa").json()["empresa_nombre"] == ""

    r = client.put("/api/config-empresa", json={
        "empresa_nombre": "Compulibra", "empresa_cuit": "20-12345678-9",
        "empresa_direccion": "Suipacha 123", "empresa_email": "info@compulibra.com.ar",
    })
    assert r.status_code == 200
    assert r.json()["empresa_nombre"] == "Compulibra"
    assert client.get("/api/config-empresa").json()["empresa_cuit"] == "20-12345678-9"


def test_config_empresa_no_expone_ni_pisa_secretos(client):
    """config.json es compartido con MercadoPago/SMTP en la familia: esta API
    solo toca las claves empresa_*, y no devuelve las otras."""
    from libracore import config_manager
    _login(client)

    cfg = config_manager.load()
    cfg["mp_access_token"] = "TOKEN-QUE-NO-SE-DEBE-PERDER"
    config_manager.save(cfg)

    r = client.get("/api/config-empresa")
    assert "mp_access_token" not in r.json()

    client.put("/api/config-empresa", json={"empresa_nombre": "Compulibra"})
    assert config_manager.load()["mp_access_token"] == "TOKEN-QUE-NO-SE-DEBE-PERDER"
