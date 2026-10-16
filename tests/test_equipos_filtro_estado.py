"""El filtro por estado de la lista de equipos (2026-10-16).

La pantalla de Equipos filtraba sólo por cliente; para ver "qué tengo en
reparación" había que ir al reporte de Equipamiento, que no se puede clickear.
El filtro lo resuelve el backend, igual que el de cliente, y se combina con él.
"""
import pytest

# `client` sale de conftest.py.


@pytest.fixture
def escenario(client):
    assert client.post(
        "/auth/login", json={"username": "admin", "password": "admin"}
    ).status_code == 200

    uno = client.post("/api/clientes", json={
        "nombre": "Cliente Uno", "empresa": "Empresa Uno SA", "email": "uno@test.com",
    }).json()["id"]
    dos = client.post("/api/clientes", json={
        "nombre": "Cliente Dos", "empresa": "Empresa Dos SA", "email": "dos@test.com",
    }).json()["id"]

    for cliente_id, tipo, estado in (
        (uno, "Notebook", "activo"),
        (uno, "Impresora", "en_reparacion"),
        (dos, "Monitor", "en_reparacion"),
        (dos, "PC", "baja"),
    ):
        assert client.post("/api/equipos", json={
            "cliente_id": cliente_id, "tipo": tipo, "estado": estado,
        }).status_code == 201

    return {"uno": uno, "dos": dos}


def _tipos(respuesta) -> set[str]:
    assert respuesta.status_code == 200
    return {e["tipo"] for e in respuesta.json()}


def test_filtra_por_estado(client, escenario):
    assert _tipos(client.get("/api/equipos?estado=en_reparacion")) == {"Impresora", "Monitor"}


def test_el_estado_se_combina_con_el_cliente(client, escenario):
    respuesta = client.get(f"/api/equipos?estado=en_reparacion&cliente_id={escenario['dos']}")
    assert _tipos(respuesta) == {"Monitor"}


def test_sin_filtro_trae_todos_incluida_la_baja(client, escenario):
    assert _tipos(client.get("/api/equipos")) == {"Notebook", "Impresora", "Monitor", "PC"}
