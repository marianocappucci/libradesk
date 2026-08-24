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
    "stock":        "/api/consumibles",
    # El consumo del parque del cliente (2026-08-24). Entra a este diccionario
    # y no a un test propio a propósito: los cinco tests de abajo lo recorren,
    # así que el gate del módulo nuevo queda cubierto el mismo día en vez de
    # "cuando alguien se acuerde de agregarle su test".
    "insumos":      "/api/insumos",
}

# El módulo `stock` monta UN router con dos familias de rutas: el inventario y
# los materiales de una incidencia. La de arriba cubre la primera; ésta la
# segunda, porque un gateo a medias dejaría un ticket anotando consumos contra
# un inventario que el cliente no contrató.
RUTA_MATERIALES = "/api/incidencias/{incidencia_id}/materiales"

# El módulo `alquileres` monta TRES routers y el de arriba cubre uno solo. Los
# otros dos se chequean aparte para que no queden sin cubrir: un gateo a medias
# le mostraría el stock propio a quien no puede entregarlo bajo contrato, o —
# peor — una bandeja de cobros de algo que no contrató.
RUTA_ACTIVOS = "/api/activos"
# El devengado (fase 2, 2026-08-15). Mismo módulo que los contratos: una cuota
# sin contrato no existe.
RUTA_CUOTAS = "/api/cuotas"


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

def test_plan_basico_deja_el_core_y_corta_el_resto(client, destino_base):
    from plans import aplicar_plan_en_db

    aplicar_plan_en_db(destino_base, "basico")
    _login(client)

    # El core sigue entero.
    assert client.get("/api/clientes").status_code == 200
    assert client.get("/api/incidencias").status_code == 200
    # Lo que se vende por nivel, no.
    for modulo, ruta in RUTAS.items():
        assert client.get(ruta).status_code == 403, modulo


def test_plan_estandar_suma_dashboard_y_reportes(client, destino_base):
    from plans import aplicar_plan_en_db

    aplicar_plan_en_db(destino_base, "estandar")
    _login(client)

    assert client.get(RUTAS["dashboard"]).status_code == 200
    assert client.get(RUTAS["reportes"]).status_code == 200
    assert client.get(RUTAS["remitos"]).status_code == 403
    assert client.get(RUTAS["presupuestos"]).status_code == 403


def test_plan_premium_habilita_todo(client, destino_base):
    from plans import aplicar_plan_en_db

    aplicar_plan_en_db(destino_base, "premium")
    _login(client)

    for modulo, ruta in RUTAS.items():
        assert client.get(ruta).status_code == 200, modulo


def test_los_tres_routers_de_alquileres_van_juntos(client, destino_base):
    """Activos, contratos y cuotas cuelgan del mismo módulo, así que se habilitan
    y se cortan a la vez. Sin este test, gatear uno solo pasaría desapercibido:
    `RUTAS` cubre `/api/contratos` y nadie miraría los otros dos."""
    from plans import aplicar_plan_en_db

    for ruta in (RUTA_ACTIVOS, RUTA_CUOTAS):
        assert _existe_de_verdad(client, ruta), f"{ruta} ya no existe"

    aplicar_plan_en_db(destino_base, "estandar")
    _login(client)
    assert client.get(RUTA_ACTIVOS).status_code == 403
    assert client.get(RUTA_CUOTAS).status_code == 403
    assert client.get(RUTAS["alquileres"]).status_code == 403

    aplicar_plan_en_db(destino_base, "premium")
    assert client.get(RUTA_ACTIVOS).status_code == 200
    assert client.get(RUTA_CUOTAS).status_code == 200
    assert client.get(RUTAS["alquileres"]).status_code == 200


def test_los_materiales_de_una_incidencia_van_con_el_stock(client, destino_base):
    """El inventario y el consumo en el ticket cuelgan del mismo módulo.

    Sin este test, gatear sólo el inventario pasaría desapercibido: `RUTAS`
    cubre `/api/consumibles` y nadie miraría los materiales — que es la mitad
    que le importa al técnico, y la que descuenta stock de verdad.
    """
    from plans import aplicar_plan_en_db

    assert _existe_de_verdad(client, RUTA_MATERIALES), f"{RUTA_MATERIALES} ya no existe"

    aplicar_plan_en_db(destino_base, "estandar")
    _login(client)
    assert client.get("/api/incidencias/1/materiales").status_code == 403
    assert client.get(RUTAS["stock"]).status_code == 403

    aplicar_plan_en_db(destino_base, "premium")
    assert client.get("/api/incidencias/1/materiales").status_code == 200
    assert client.get(RUTAS["stock"]).status_code == 200


def test_aplicar_un_plan_inexistente_falla_fuerte(tmp_path):
    """No necesita una base de verdad: el nombre del plan se valida antes de
    abrir ninguna conexión, y que sea así es parte de lo que se prueba."""
    from plans import aplicar_plan_en_db

    with pytest.raises(ValueError, match="enterprise"):
        aplicar_plan_en_db(str(tmp_path / "no-existe.db"), "enterprise")
