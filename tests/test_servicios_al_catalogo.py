"""La mudanza del catálogo de servicios al catálogo del motor.

El catálogo propio de `servicios` nació el 2026-08-06 con el argumento de que
traer LibraCommerce sería *"19 tablas para un producto que no vende
productos"*. **Esa premisa venció el 2026-08-12**, cuando el producto adoptó
LibraCommerce, y el 13 cuando adoptó ventas y listas de precios.

Mientras el servicio siga afuera del motor, **las listas de precios no lo
alcanzan**: Lagrace tiene tres listas con 43 precios y su valor hora cotiza
igual para todos.

Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que la copia sea idempotente.** Corre en CADA arranque; si duplicara,
   cada reinicio del contenedor agregaría otro juego de servicios al catálogo.
2. 🔴 **Que no se pierda nada en el camino** — precio, alícuota, la marca de
   valor hora y el activo/inactivo.
3. 🔴 **Que no explote cuando no hay nada que mudar**: una instancia nueva no
   tiene la tabla `servicios`, y esto corre en su arranque igual.
4. Que el servicio migrado NO sea comprable: la mano de obra se vende.
"""

import json
import os

import pytest

from app.services import inventario, servicios_catalogo
from libracommerce.domain.catalog import CatalogItemType
from libracore.db import core as libracore_core


@pytest.fixture
def client(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def servicios(client):
    """Tres servicios **en la tabla vieja**: el valor hora, uno normal y uno de baja.

    Los tres juntos son el punto: con uno solo no se ve si la marca de valor
    hora viaja al que corresponde ni si el inactivo se conserva inactivo.

    🔑 **Se escriben por SQL directo y no por `POST /api/servicios`**, y eso es
    la segunda release del expand/contract: desde el 2026-08-16 la API escribe
    en el **catálogo**, así que crear por ahí ya no deja nada que migrar — el
    test pasaba a medir cero.

    Escribir la tabla vieja a mano es además lo más fiel a lo que esto prueba:
    una instancia que **viene de antes** y arranca con el código nuevo. Es el
    único escenario en que la mudanza tiene algo que hacer.
    """
    filas = [
        ("Hora de servicio técnico", "", 15000, "0.21", True, True),
        ("Instalación de central", "Incluye pruebas", 80000, "0.105", False, True),
        ("Servicio discontinuado", "", 500, "0.21", False, False),
    ]
    with libracore_core.get_connection() as conn:
        for nombre, desc, precio, alic, es_hora, activo in filas:
            conn.execute(
                "INSERT INTO servicios (nombre, descripcion, precio, iva_rate, "
                "es_valor_hora, activo) VALUES (?,?,?,?,?,?)",
                (nombre, desc, precio, alic, es_hora, activo),
            )
    return filas


def _del_catalogo() -> list[dict]:
    """Los servicios que hay en el catálogo del motor, con su metadata."""
    with libracore_core.get_connection() as conn:
        filas = conn.execute(
            "SELECT id, name, description, default_sale_price, tax_profile, "
            "active, purchasable, metadata_json FROM catalog_items "
            "WHERE item_type = ?",
            (str(CatalogItemType.SERVICE),),
        ).fetchall()
    return [
        {
            "id": f["id"], "nombre": f["name"], "descripcion": f["description"],
            "precio": float(f["default_sale_price"] or 0),
            "iva": f["tax_profile"], "activo": bool(f["active"]),
            "comprable": bool(f["purchasable"]),
            "meta": json.loads(f["metadata_json"] or "{}"),
        }
        for f in filas
    ]


def _migrar() -> dict:
    return servicios_catalogo.migrar(inventario._repo)


# ── 1. Idempotencia ──────────────────────────────────────────────────────


def test_migrar_dos_veces_no_duplica(servicios):
    """🔴 Corre en CADA arranque. Si duplicara, cada reinicio del contenedor
    agregaría otro juego completo de servicios al catálogo."""
    primera = _migrar()
    assert primera["copiados"] == 3

    segunda = _migrar()
    assert segunda["copiados"] == 0
    assert segunda["ya_estaban"] == 3

    assert len(_del_catalogo()) == 3, "en el catálogo tiene que haber tres, no seis"


def test_se_reconoce_por_el_origen_y_no_por_el_nombre(servicios, client):
    """Renombrar el ítem del lado del catálogo no puede hacer que la copia lo
    vuelva a crear: por eso el vínculo va en la metadata y no en el nombre.

    🔴 **Este test encontró un defecto distinto del que buscaba.** Editar el
    ítem lo volvía a copiar, pero no porque el vínculo fallara: `editar_item`
    tenía `CatalogItemType.PRODUCT` cableado, así que **editar un servicio lo
    convertía en producto** — desaparecía de los `SERVICE` y la mudanza lo
    volvía a crear. Ver el comentario en `inventario.editar_item()`.
    """
    _migrar()
    item = next(i for i in _del_catalogo() if i["nombre"] == "Instalación de central")

    inventario.editar_item(item["id"], nombre="Instalación (renombrada)",
                           precio=80000.0)

    assert _migrar()["copiados"] == 0, (
        "renombrarlo no puede hacer que se copie de nuevo"
    )


def test_editar_un_servicio_no_lo_convierte_en_producto(servicios):
    """La mitad que importa del test de arriba, dicha directamente.

    Sin esto, la regresión volvería disfrazada de "la mudanza duplica" y
    costaría el mismo rato entender de dónde sale.
    """
    _migrar()
    item = next(i for i in _del_catalogo() if i["nombre"] == "Instalación de central")

    inventario.editar_item(item["id"], nombre="Instalación (renombrada)",
                           precio=80000.0)

    sigue = [i for i in _del_catalogo() if i["id"] == item["id"]]
    assert sigue, "editarlo no puede sacarlo de los servicios del catálogo"
    assert item["id"] not in [p["id"] for p in inventario.listar_items()], (
        "y tampoco puede aparecer en el listado de consumibles"
    )


# ── 2. Que no se pierda nada ─────────────────────────────────────────────


def test_viajan_precio_alicuota_y_texto(servicios):
    _migrar()
    inst = next(i for i in _del_catalogo() if i["nombre"] == "Instalación de central")

    assert inst["precio"] == pytest.approx(80000.0)
    assert float(inst["iva"]) == pytest.approx(0.105), (
        "la alícuota va al mismo lugar donde el resto del sistema ya la busca"
    )
    assert inst["descripcion"] == "Incluye pruebas"


def test_la_marca_de_valor_hora_viaja_al_que_corresponde(servicios):
    """La contraprueba está adentro: se afirma cuál lo tiene **y** que los
    otros dos no. Sin eso, marcar todos pasaría el test."""
    _migrar()
    catalogo = _del_catalogo()

    con_marca = [i["nombre"] for i in catalogo
                 if i["meta"].get(servicios_catalogo.CLAVE_VALOR_HORA) == "1"]
    assert con_marca == ["Hora de servicio técnico"]


def test_un_servicio_de_baja_llega_de_baja(servicios):
    _migrar()
    viejo = next(i for i in _del_catalogo() if i["nombre"] == "Servicio discontinuado")
    assert viejo["activo"] is False


def test_la_mano_de_obra_no_es_comprable(servicios):
    """Se vende, no se compra. Sin esto aparecería en las órdenes de compra al
    lado de los consumibles."""
    _migrar()
    assert all(not i["comprable"] for i in _del_catalogo())


# ── 3. Que no explote cuando no hay nada que mudar ───────────────────────


def test_sin_servicios_cargados_no_hace_nada(client):
    """La tabla existe y está vacía."""
    assert _migrar() == {"copiados": 0, "ya_estaban": 0}


def test_sin_la_tabla_servicios_no_explota(client):
    """🔴 El caso de una instancia nueva: nace con el catálogo del motor y sin
    la tabla vieja. Esto corre en su arranque igual, y no puede tumbarlo."""
    with libracore_core.get_connection() as conn:
        conn.execute("DROP TABLE IF EXISTS servicios")

    assert _migrar() == {"copiados": 0, "ya_estaban": 0}
