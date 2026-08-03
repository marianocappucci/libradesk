"""
Ficha del cliente — `GET /api/dashboard/cliente/{id}` (2026-08-02, pendiente 24).

Lo que estos tests fijan, en orden de lo que puede romperse sin que se note:

1. Que la ruta **exista de verdad** y no sea el fallback de la SPA.
2. Que los agregados sean **de ese cliente y de nadie más**.
3. Que la lista de garantías incluya las **ya vencidas** (con días negativos)
   y excluya las bajas, que es donde la ficha se diferencia de un simple
   "vence dentro de N días".
"""
import sys
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

RUTA = "/api/dashboard/cliente/{cliente_id}"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    from app.asgi import app
    return TestClient(app, base_url="https://testserver")


def _login(client) -> None:
    assert client.post("/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200


def _iso(dias: int) -> str:
    return (date.today() + timedelta(days=dias)).isoformat()


@pytest.fixture
def escenario(client):
    """Un cliente con parque, tickets y garantías, y **un segundo cliente**
    con lo suyo — sin ese segundo, un `where cliente_id` que faltara pasaría
    inadvertido."""
    _login(client)

    cliente_id = client.post("/api/clientes", json={
        "nombre": "Compulibra", "empresa": "Compulibra SRL", "email": "c@test.com",
    }).json()["id"]
    otro_id = client.post("/api/clientes", json={
        "nombre": "Otro", "email": "o@test.com",
    }).json()["id"]

    tecnico_id = client.post("/api/tecnicos", json={"nombre": "Mariano"}).json()["id"]
    client.post("/api/sectores", json={"cliente_id": cliente_id, "nombre": "Admisión"})
    client.post("/api/sectores", json={"cliente_id": cliente_id, "nombre": "Depósito"})
    client.post("/api/sectores", json={"cliente_id": otro_id, "nombre": "Ajeno"})

    equipos = {
        # (clave)            estado            garantía
        "vencida":          ("activo",         _iso(-12)),
        "por_vencer":       ("activo",         _iso(30)),
        "lejana":           ("activo",         _iso(400)),
        "sin_garantia":     ("activo",         None),
        "baja_vencida":     ("baja",           _iso(-5)),
        "reparacion":       ("en_reparacion",  None),
    }
    ids = {}
    for clave, (estado, garantia) in equipos.items():
        ids[clave] = client.post("/api/equipos", json={
            "cliente_id": cliente_id, "tipo": "Impresora", "marca": "HP",
            "modelo": clave, "serial": f"S-{clave}", "sector": "Admisión",
            "estado": estado, "garantia_vence": garantia,
        }).json()["id"]

    # Del otro cliente: mismo perfil, para que aparezca si el filtro falla.
    client.post("/api/equipos", json={
        "cliente_id": otro_id, "tipo": "Notebook", "garantia_vence": _iso(1),
    })

    # Dos abiertas (una con equipo y técnico, una pelada) y una cerrada.
    abierta_con_equipo = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "equipo_id": ids["vencida"], "tecnico_id": tecnico_id,
        "titulo": "Hace ruido", "prioridad": "alta",
    }).json()["id"]
    client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "titulo": "Sin asignar", "prioridad": "baja",
    })
    cerrada = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "titulo": "Ya resuelta", "prioridad": "media",
    }).json()["id"]
    client.put(f"/api/incidencias/{cerrada}", json={
        "cliente_id": cliente_id, "titulo": "Ya resuelta", "prioridad": "media",
        "estado": "cerrado", "horas_invertidas": 2.5,
    })
    client.post("/api/incidencias", json={
        "cliente_id": otro_id, "titulo": "Del otro cliente", "prioridad": "alta",
    })

    return {"cliente_id": cliente_id, "otro_id": otro_id, "equipos": ids,
            "abierta_con_equipo": abierta_con_equipo}


# ── Que la ruta exista ──────────────────────────────────────────────────────

def test_la_ruta_existe_de_verdad(client):
    """`asgi.py` sirve la SPA en `/{full_path:path}`, así que una ruta
    inventada devuelve 200 con HTML. Sin este chequeo, todo el archivo podría
    estar midiendo el fallback — el falso verde que ya pasó una vez acá
    (ver tests/test_modulos_y_planes.py)."""
    assert RUTA in client.app.openapi()["paths"]


def test_sin_sesion_no_se_ve(client):
    assert client.get(RUTA.format(cliente_id=1)).status_code == 401


def test_cliente_inexistente_es_404(client):
    _login(client)
    r = client.get(RUTA.format(cliente_id=9999))
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/json")


# ── Los agregados ───────────────────────────────────────────────────────────

def test_el_parque_es_solo_del_cliente(client, escenario):
    ficha = client.get(RUTA.format(cliente_id=escenario["cliente_id"])).json()

    assert ficha["cliente"]["nombre"] == "Compulibra"
    assert ficha["total_equipos"] == 6
    assert ficha["equipos_por_estado"] == {"activo": 4, "baja": 1, "en_reparacion": 1}
    assert ficha["total_sectores"] == 2

    # El otro cliente tiene lo suyo y nada de lo de éste.
    otra = client.get(RUTA.format(cliente_id=escenario["otro_id"])).json()
    assert otra["total_equipos"] == 1
    assert otra["total_sectores"] == 1


def test_incidencias_por_estado_y_horas(client, escenario):
    ficha = client.get(RUTA.format(cliente_id=escenario["cliente_id"])).json()

    assert ficha["total_incidencias"] == 3
    assert ficha["incidencias_por_estado"] == {"abierto": 2, "cerrado": 1}
    # Las horas salen de la incidencia cerrada; las abiertas no tienen.
    assert ficha["horas_invertidas"] == 2.5


def test_las_abiertas_traen_equipo_y_tecnico_resueltos(client, escenario):
    ficha = client.get(RUTA.format(cliente_id=escenario["cliente_id"])).json()
    abiertas = ficha["incidencias_abiertas"]

    assert len(abiertas) == 2
    assert {i["titulo"] for i in abiertas} == {"Hace ruido", "Sin asignar"}

    con_equipo = next(i for i in abiertas if i["id"] == escenario["abierta_con_equipo"])
    assert con_equipo["equipo"] == "Impresora HP vencida"
    assert con_equipo["tecnico"] == "Mariano"
    assert con_equipo["prioridad"] == "alta"

    # La pelada no rompe: los dos outerjoin devuelven None, no una fila menos.
    pelada = next(i for i in abiertas if i["titulo"] == "Sin asignar")
    assert pelada["equipo"] is None
    assert pelada["tecnico"] is None


# ── Garantías ───────────────────────────────────────────────────────────────

def test_garantias_incluye_las_vencidas_y_excluye_las_bajas(client, escenario):
    ficha = client.get(RUTA.format(cliente_id=escenario["cliente_id"])).json()
    por_modelo = {g["descripcion"]: g for g in ficha["garantias"]}

    # Dentro de la ventana de 60 días: la vencida y la que vence en 30.
    assert set(por_modelo) == {"Impresora HP vencida", "Impresora HP por_vencer"}
    assert ficha["dias_garantia"] == 60

    # La vencida va primero (orden por fecha ascendente) y con días negativos:
    # es el dato que la ficha pinta en rojo.
    assert ficha["garantias"][0]["descripcion"] == "Impresora HP vencida"
    assert por_modelo["Impresora HP vencida"]["dias_restantes"] == -12
    assert por_modelo["Impresora HP por_vencer"]["dias_restantes"] == 30

    # `garantia_vence` viaja como fecha sola, que es lo que el frontend parsea
    # a mano para no correrse un día por zona horaria.
    assert por_modelo["Impresora HP vencida"]["garantia_vence"] == _iso(-12)


def test_dias_garantia_ensancha_la_ventana(client, escenario):
    ruta = RUTA.format(cliente_id=escenario["cliente_id"])

    corta = client.get(f"{ruta}?dias_garantia=7").json()
    assert [g["descripcion"] for g in corta["garantias"]] == ["Impresora HP vencida"]
    assert corta["dias_garantia"] == 7

    ancha = client.get(f"{ruta}?dias_garantia=500").json()
    # Entra la lejana; la de baja sigue afuera por más que se agrande.
    assert len(ancha["garantias"]) == 3
    assert "Impresora HP baja_vencida" not in {g["descripcion"] for g in ancha["garantias"]}
