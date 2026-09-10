"""El contrato que el backoffice espera de `app.database`, y que faltaba.

El backoffice no habla con la app por HTTP para los add-ons: corre un snippet
DENTRO del contenedor de la instancia (`libracore.admin.services`), y ese
snippet hace

    from app.database import get_modulos   # para leer el estado
    from app.database import set_addon     # para prenderlo/apagarlo

LibraDesk declaró `ADDONS = {"modo_simple"}` el 2026-09-09 sin exportar ninguna
de las dos —`app/database.py` es la engine factory de SQLAlchemy—, así que el
`docker exec` moría con `ImportError`. Y como la lectura del backoffice traducía
cualquier error a `False`, el resultado no fue un error visible sino una mentira:
en `libradesk-lagrace`, con `modo_simple = true` en la base, la pantalla del
backoffice mostraba el add-on **destildado**.

Estos tests fijan el contrato. El que lo generaliza —y el único que habría
atajado el defecto el día que se declaró el add-on— es
`test_declarar_addons_obliga_a_exportar_el_contrato`.
"""
import pytest


def test_app_database_exporta_el_contrato_del_backoffice():
    """El import textual del snippet, tal cual lo escribe el backoffice."""
    from app.database import get_modulos, set_addon  # noqa: F401

    assert callable(get_modulos)
    assert callable(set_addon)


def test_declarar_addons_obliga_a_exportar_el_contrato():
    """🔑 El test que ata las dos mitades.

    Declarar `plans.ADDONS` sin el contrato es exactamente el defecto de este
    trabajo: se ve bien en el producto (el add-on funciona adentro de la app) y
    rompe en el backoffice, que es el único lugar desde donde se administra.

    Si algún día LibraDesk deja de tener add-ons, este test se vuelve trivial
    en vez de romperse — a propósito.
    """
    import plans

    if not getattr(plans, "ADDONS", set()):
        pytest.skip("el producto no declara add-ons")

    import app.database as database

    faltantes = [n for n in ("get_modulos", "set_addon") if not hasattr(database, n)]
    assert not faltantes, (
        f"plans.ADDONS = {sorted(plans.ADDONS)} pero app.database no exporta "
        f"{faltantes}: el backoffice no puede leer ni cambiar esos add-ons."
    )


def test_set_addon_prende_y_get_modulos_lo_ve(client):
    """El circuito completo contra la base de la instancia, como en producción."""
    from app.database import get_modulos, set_addon

    assert get_modulos().get("modo_simple", False) is False

    set_addon("modo_simple", True)
    assert get_modulos()["modo_simple"] is True

    set_addon("modo_simple", False)
    assert get_modulos()["modo_simple"] is False


def test_set_addon_crea_la_fila_si_falta(client):
    """Una instancia que nunca vio el add-on no tiene la fila.

    Sin el `INSERT` del motor, el `UPDATE` afectaría cero filas y la función
    saldría con éxito sin prender nada: el backoffice reportaría OK y el cliente
    seguiría sin el add-on.
    """
    from sqlalchemy import text

    from app import database
    from app.database import get_modulos, set_addon

    with database.get_engine().begin() as conn:
        conn.execute(text("DELETE FROM modulos WHERE modulo = 'modo_simple'"))
    assert "modo_simple" not in get_modulos()

    set_addon("modo_simple", True)
    assert get_modulos()["modo_simple"] is True


def test_lo_que_ve_el_shim_es_lo_que_ve_la_app(client):
    """Control: el shim no abre una base propia.

    Si `_asegurar_core_configurado()` apuntara a otro lado —el default de una
    variable de entorno, una base recién creada—, todos los tests de arriba
    pasarían igual contra esa base paralela y el backoffice seguiría mostrando
    otra cosa que la app. Se mide escribiendo por el shim y leyendo por el
    engine de la app.
    """
    from sqlalchemy import text

    from app import database
    from app.database import set_addon

    set_addon("modo_simple", True)

    with database.get_engine().begin() as conn:
        fila = conn.execute(
            text("SELECT habilitado FROM modulos WHERE modulo = 'modo_simple'")
        ).fetchone()

    assert fila is not None, "el shim escribió en una base que la app no ve"
    assert fila[0] is True
