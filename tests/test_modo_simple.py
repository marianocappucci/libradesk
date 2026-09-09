"""El add-on `modo_simple`: un LibraDesk reducido que vive adentro de LibraDesk.

Sale del pedido del humano del 2026-09-09:

> *"Sigo pensando que tenemos que hacer un LibraDesk resumido para Lagrace que
> viva dentro de LibraDesk pero que sea particular para ellos, porque puede
> haber otras empresas que sí se adapten a un flujo más correcto."*

## Por qué es un ADD-ON y no un módulo de plan

🔴 Porque `ensure_seeded()` inserta toda entrada nueva de `TODOS_LOS_MODULOS`
**con `habilitado=True` en todas las instancias** en el próximo arranque. Ya
pasó con `alquileres`, que le hizo aparecer una entrada de menú a un cliente que
no la había pedido. Un add-on queda afuera de ese superset: nace apagado en
todos lados y se prende sólo donde se quiere, **y sobrevive a subir o bajar de
plan**. Mismo patrón que `mayorista` en Contalibra.

## Y el defecto que este trabajo destapó

`require_module` gateaba ocho routers, pero **el frontend nunca recibía los
módulos**: LibraDesk no pasaba `get_extras` a libraauth ni `hasModule` a su
`Layout`. O sea que apagar un módulo dejaba su entrada en el menú y el click
daba 403. Los tests de `/auth/me` de acá abajo son la mitad backend de ese
arreglo, que **alcanza a todas las instancias**, no sólo a la del modo simple.
"""
import pytest


def _login(client) -> None:
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text


# ── El catálogo ────────────────────────────────────────────────────────────

def test_modo_simple_es_un_addon_y_no_esta_en_ningun_plan():
    """Si estuviera en un plan, `ensure_seeded()` lo prendería en todas las
    instancias en el próximo arranque."""
    import plans

    assert "modo_simple" in plans.ADDONS
    for plan, modulos in plans.PLAN_MODULOS.items():
        assert "modo_simple" not in modulos, plan
    assert "modo_simple" not in plans.TODOS_LOS_MODULOS


def test_el_core_de_tickets_sigue_sin_gatearse():
    """🔑 `modo_simple` **no apaga las incidencias**: elige cómo se dibujan.

    Un LibraDesk sin incidencias no es un plan más barato, es otra cosa — y esa
    regla no la cambia el add-on.
    """
    import plans

    for modulos in plans.PLAN_MODULOS.values():
        assert "incidencias" not in modulos
    assert "incidencias" not in plans.ADDONS


@pytest.mark.parametrize("plan", ["basico", "estandar", "premium"])
def test_aplicar_un_plan_no_apaga_el_addon(client, destino_base, plan):
    """🔑 **Lo que se paga aparte no se apaga al cambiar de plan.**

    Es la propiedad que hace del add-on la herramienta correcta: si `modo_simple`
    fuera un módulo de plan, subir a premium se lo prendería a todo el mundo y
    bajar a básico se lo apagaría a Lagrace sin que nadie lo pidiera.
    """
    from libracore.db.modulos import get_modulos

    from plans import aplicar_plan_en_db

    _prender(client, "modo_simple")
    aplicar_plan_en_db(destino_base, plan)

    assert get_modulos().get("modo_simple") is True


def _prender(client, modulo: str) -> None:
    """Prende un módulo en la base de la instancia del test.

    Por SQL y no por un endpoint porque no hay: los módulos los administra el
    backoffice contra la base, que es justamente el circuito que se prueba.
    """
    from sqlalchemy import text

    from app import database

    with database.get_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO modulos (modulo, habilitado, plan) VALUES "
                 "(:m, true, 'addon') ON CONFLICT (modulo) DO UPDATE "
                 "SET habilitado = true"),
            {"m": modulo},
        )


# ── Los módulos llegan al frontend ─────────────────────────────────────────

def test_la_sesion_devuelve_los_modulos_habilitados(client):
    """🔴 **Sin esto el menú mentía.** El backend gateaba y la UI no se
    enteraba: la entrada quedaba en el sidebar y el click daba 403."""
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    assert "modulos" in r.json()
    assert isinstance(r.json()["modulos"], list)


def test_los_modulos_tambien_vienen_en_me(client):
    """En `/me` y en el login: si sólo estuviera en `/me`, el sidebar cambiaría
    de forma después de recargar y no después de loguear."""
    _login(client)
    r = client.get("/auth/me")
    assert r.status_code == 200, r.text
    assert "modulos" in r.json()


def test_el_addon_apagado_no_aparece_en_la_sesion(client):
    """Nace apagado en todos lados: es lo que hace que las otras instancias no
    vean nada distinto."""
    _login(client)
    assert "modo_simple" not in client.get("/auth/me").json()["modulos"]


def test_prendido_aparece(client):
    _prender(client, "modo_simple")
    _login(client)
    assert "modo_simple" in client.get("/auth/me").json()["modulos"]


def test_solo_vienen_los_habilitados(client):
    """La lista es de los prendidos, no el catálogo entero: el frontend
    pregunta `modulos.includes(m)` y un catálogo completo le diría que sí a
    todo."""
    from sqlalchemy import text

    from app import database

    _prender(client, "modo_simple")
    with database.get_engine().begin() as conn:
        conn.execute(text("UPDATE modulos SET habilitado = false WHERE modulo = 'dashboard'"))

    _login(client)
    modulos = client.get("/auth/me").json()["modulos"]
    assert "modo_simple" in modulos
    assert "dashboard" not in modulos
