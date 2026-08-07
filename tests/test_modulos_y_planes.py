"""
Módulos y planes (2026-08-02).

LibraDesk era el único de los seis productos sin planes, sin módulos y sin
provisioning, y por eso el único que el backoffice compartido no podía
administrar igual que al resto. Estos tests fijan las dos cosas que importan de
ese cambio:

1. **Las instancias que ya existen no se enteran.** Sin plan asignado todo
   queda habilitado, así que `compulibra` y `dev` siguen funcionando igual.
2. El core de tickets no se gatea ni aunque alguien lo intente.
"""

import pytest

from plans import PLAN_MODULOS, PLANES, TODOS_LOS_MODULOS, modulos_de_plan


# `client` sale de conftest.py.


def _login(client) -> None:
    assert client.post("/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200


# Rutas REALES de cada router gateado. Que existan no es un detalle: `asgi.py`
# monta un fallback de SPA (`/{full_path:path}` → index.html), así que
# **cualquier ruta inventada devuelve 200 con HTML**. Un test que apunte al
# path equivocado pasa en verde sin haber ejercitado el gating — pasó
# escribiendo estos mismos tests, con `/api/dashboard/resumen`, que no existe.
RUTAS = {
    "dashboard":    "/api/dashboard",
    "reportes":     "/api/reportes/clientes.xlsx",
    "remitos":      "/api/remitos",
    "presupuestos": "/api/presupuestos",
    "alquileres":   "/api/contratos",
}

# El módulo `alquileres` monta DOS routers y el de arriba cubre uno solo. Éste
# se chequea aparte para que el segundo no quede sin cubrir: un gateo a medias
# le mostraría el stock propio a quien no puede entregarlo bajo contrato.
RUTA_ACTIVOS = "/api/activos"


def _existe_de_verdad(client, ruta: str) -> bool:
    """Que la ruta la sirva un router y no el fallback de la SPA.

    Se consulta el schema de OpenAPI y no `app.routes`: esta versión de FastAPI
    envuelve los routers incluidos en `_IncludedRouter` y ahí los paths hoja no
    aparecen, así que recorrer `app.routes` diría que ninguna ruta existe.
    """
    return ruta in client.app.openapi()["paths"]


# ── El catálogo de planes ───────────────────────────────────────────────────

def test_los_planes_son_crecientes():
    """Cada plan incluye todo lo del anterior. Un plan más caro que quita algo
    es un bug de catálogo que nadie mira hasta que un cliente lo reclama."""
    anterior: set[str] = set()
    for plan in PLANES:
        actual = modulos_de_plan(plan)
        assert anterior <= actual, f"{plan} no incluye todo lo del plan anterior"
        anterior = actual


def test_el_core_de_tickets_no_es_gateable():
    """Clientes, equipos, incidencias, técnicos, sectores y categorías definen
    el producto. `categorias` se sumó el 2026-08-02 con el catálogo de tipos:
    clasificar un ticket no es una feature de plan."""
    core = {"clientes", "equipos", "incidencias", "tecnicos", "sectores", "categorias"}
    assert core & TODOS_LOS_MODULOS == set()


def test_todos_los_modulos_es_el_plan_mas_alto():
    assert TODOS_LOS_MODULOS == PLAN_MODULOS["premium"]


def test_plan_desconocido_no_habilita_nada():
    assert modulos_de_plan("enterprise") == set()


# ── Comportamiento por defecto (las dos instancias que ya existen) ──────────

def test_las_rutas_gateadas_existen(client):
    """Guarda contra el falso verde: si alguien renombra un endpoint, el resto
    de los tests de este archivo empezarían a medir el fallback de la SPA."""
    for modulo, ruta in RUTAS.items():
        assert _existe_de_verdad(client, ruta), f"{modulo}: {ruta} ya no existe"


def test_sin_plan_asignado_todo_queda_habilitado(client):
    """La garantía de adopción: agregar módulos no le cambia nada a una
    instancia existente hasta que alguien le asigne un plan."""
    _login(client)
    for modulo, ruta in RUTAS.items():
        assert client.get(ruta).status_code != 403, modulo


# ── Con un plan aplicado ────────────────────────────────────────────────────

def test_plan_basico_deja_el_core_y_corta_el_resto(client, tmp_path):
    from plans import aplicar_plan_en_db

    aplicar_plan_en_db(str(tmp_path / "libradesk.db"), "basico")
    _login(client)

    # El core sigue entero.
    assert client.get("/api/clientes").status_code == 200
    assert client.get("/api/incidencias").status_code == 200
    # Lo que se vende por nivel, no.
    for modulo, ruta in RUTAS.items():
        assert client.get(ruta).status_code == 403, modulo


def test_plan_estandar_suma_dashboard_y_reportes(client, tmp_path):
    from plans import aplicar_plan_en_db

    aplicar_plan_en_db(str(tmp_path / "libradesk.db"), "estandar")
    _login(client)

    assert client.get(RUTAS["dashboard"]).status_code == 200
    assert client.get(RUTAS["reportes"]).status_code == 200
    assert client.get(RUTAS["remitos"]).status_code == 403
    assert client.get(RUTAS["presupuestos"]).status_code == 403


def test_plan_premium_habilita_todo(client, tmp_path):
    from plans import aplicar_plan_en_db

    aplicar_plan_en_db(str(tmp_path / "libradesk.db"), "premium")
    _login(client)

    for modulo, ruta in RUTAS.items():
        assert client.get(ruta).status_code == 200, modulo


def test_los_dos_routers_de_alquileres_van_juntos(client, tmp_path):
    """Activos y contratos cuelgan del mismo módulo, así que se habilitan y se
    cortan a la vez. Sin este test, gatear uno solo pasaría desapercibido:
    `RUTAS` cubre `/api/contratos` y nadie miraría `/api/activos`."""
    from plans import aplicar_plan_en_db

    assert _existe_de_verdad(client, RUTA_ACTIVOS), f"{RUTA_ACTIVOS} ya no existe"

    aplicar_plan_en_db(str(tmp_path / "libradesk.db"), "estandar")
    _login(client)
    assert client.get(RUTA_ACTIVOS).status_code == 403
    assert client.get(RUTAS["alquileres"]).status_code == 403

    aplicar_plan_en_db(str(tmp_path / "libradesk.db"), "premium")
    assert client.get(RUTA_ACTIVOS).status_code == 200
    assert client.get(RUTAS["alquileres"]).status_code == 200


def test_aplicar_un_plan_inexistente_falla_fuerte(tmp_path):
    from plans import aplicar_plan_en_db

    with pytest.raises(ValueError, match="enterprise"):
        aplicar_plan_en_db(str(tmp_path / "libradesk.db"), "enterprise")
