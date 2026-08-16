"""La mudanza del catálogo de servicios al catálogo del motor.

## Por qué se muda

`servicios.py` es una tabla propia de LibraDesk, y su docstring explica por qué
no se usó el catálogo de LibraCommerce:

> *"traerlo a LibraDesk sería importar catálogo, inventario, compras, ventas y
> POS —19 tablas— para un producto que no vende productos."*

**Esa premisa venció seis días después de escribirse**, y las fechas lo dicen
solas:

| | |
|---|---|
| Nace `servicios.py`, con ese argumento | 2026-08-06 |
| Se adopta LibraCommerce: catálogo, inventario, compras | 2026-08-12 |
| Se adopta ventas y listas de precios | 2026-08-13 |

LibraDesk hoy tiene exactamente esas 19 tablas y **sí vende productos**. El
catálogo paralelo quedó como remanente de una restricción que ya no existe, y
mientras siga afuera del motor **las listas de precios no lo alcanzan**: hoy
Lagrace tiene tres listas —general, resellers y mostrador— con 43 precios
cargados, y el valor hora del servicio técnico cotiza igual para todos.

Que la mano de obra sea un ítem del catálogo es además el estándar de la
industria: se le aplican las mismas listas, alícuotas y comprobantes que a
cualquier otra línea, sin tratamiento especial.

## 🔴 Por qué esto NO es una migración de Alembic

Porque la tabla destino todavía no existe cuando Alembic corre.

En `app/main.py`, `schema.ensure_schema()` —la cadena de migraciones— corre en
la **línea 93**, e `inventario.ensure_schema()` —que es quien crea
`catalog_items` con el `init_schema()` del motor— corre en la **111**.

Una migración que insertara en `catalog_items` andaría perfecto en Lagrace, en
la demo y en dev —donde la tabla ya está de antes— y **fallaría en la primera
instancia nueva** con `relation "catalog_items" does not exist`. Es el peor tipo
de defecto: verde en todo lo que mirás, rojo en lo que todavía no existe.

Así que la copia vive acá, como **paso de arranque idempotente** que corre
después de que los dos esquemas existen. Mismo patrón que
`comercial.sincronizar_parties()`.

## Expand/contract: esta release copia, la próxima dropea

La tabla `servicios` **queda intacta**. No se dropea en la misma release que
copia, por dos motivos:

1. Alembic corre antes que este paso, así que un `drop_table` en la cadena se
   llevaría los datos **antes** de que hubiera oportunidad de copiarlos.
2. Aunque el orden diera, dropear y copiar en el mismo despliegue deja sin red:
   si la copia sale mal, el origen ya no está.

Queda como tabla muerta —nadie la lee después de este cambio— y se dropea en una
revisión posterior, con las instancias ya verificadas.
"""
from __future__ import annotations

import json
import logging
from decimal import Decimal

from libracommerce.domain.catalog import CatalogItem, CatalogItemType
from libracore.db import core as libracore_core

logger = logging.getLogger(__name__)

#: La clave de `metadata_json` que marca cuál de los servicios es la hora de
#: trabajo. Mismo mecanismo que `es_equipo` en los productos: la bolsa de
#: atributos del consumidor que el motor ofrece y que nadie más usa.
CLAVE_VALOR_HORA = "es_valor_hora"

#: Marca de dónde vino el ítem, para que la copia sea idempotente sin depender
#: del nombre —que se puede editar— ni de un id que no se conserva.
CLAVE_ORIGEN = "servicio_migrado_id"


def _existe_tabla(conn, nombre: str) -> bool:
    """Si la tabla existe, en los dos motores.

    🔴 **No se puede preguntar por `sqlite_master`**: en PostgreSQL no existe y
    el adaptador de LibraCore no la emula. Es la misma trampa que documenta
    `comercial._existe_tabla()`, y por eso se pregunta por `information_schema`
    con el fallback del otro motor.
    """
    try:
        fila = conn.execute(
            "SELECT 1 FROM information_schema.tables WHERE table_name = ?",
            (nombre,),
        ).fetchone()
        return fila is not None
    except Exception:
        try:
            fila = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
                (nombre,),
            ).fetchone()
            return fila is not None
        except Exception:
            return False


def _ya_migrados(conn) -> set[int]:
    """Los `servicios.id` que ya tienen su ítem en el catálogo.

    Se leen de la metadata y no del nombre: el nombre se puede editar del lado
    del catálogo, y entonces la copia lo volvería a crear en cada arranque.
    """
    filas = conn.execute(
        "SELECT metadata_json FROM catalog_items WHERE item_type = ?",
        (str(CatalogItemType.SERVICE),),
    ).fetchall()
    vistos = set()
    for f in filas:
        try:
            meta = json.loads(f["metadata_json"] or "{}")
        except (ValueError, TypeError):
            continue
        origen = meta.get(CLAVE_ORIGEN)
        if origen is not None:
            try:
                vistos.add(int(origen))
            except (TypeError, ValueError):
                continue
    return vistos


def migrar(repo_factory) -> dict:
    """Copia los servicios que falten al catálogo. Idempotente.

    `repo_factory` recibe la conexión y devuelve el repositorio del motor — se
    inyecta para no importar `inventario` y armar un ciclo (`inventario` no
    importa esto, pero `main` los ordena a los dos).

    Devuelve cuántos copió y cuántos ya estaban.
    """
    salida = {"copiados": 0, "ya_estaban": 0}
    with libracore_core.get_connection() as conn:
        # Sin `servicios` no hay nada que mudar: es una instancia nueva, que
        # nace directamente con el catálogo del motor.
        if not _existe_tabla(conn, "servicios"):
            return salida
        if not _existe_tabla(conn, "catalog_items"):
            # No debería pasar —esto corre después de `inventario.ensure_schema()`—
            # pero si el orden de arranque cambia, es mejor no hacer nada que
            # explotar en el arranque de todas las instancias.
            logger.warning(
                "servicios_catalogo.migrar: catalog_items todavia no existe, "
                "se saltea. Revisar el orden de arranque en main.py."
            )
            return salida

        migrados = _ya_migrados(conn)
        filas = conn.execute(
            "SELECT id, nombre, descripcion, precio, iva_rate, es_valor_hora, "
            "activo FROM servicios"
        ).fetchall()

        repo = repo_factory(conn)
        for s in filas:
            if s["id"] in migrados:
                salida["ya_estaban"] += 1
                continue
            repo.save_catalog_item(
                CatalogItem(
                    None,
                    CatalogItemType.SERVICE,
                    s["nombre"],
                    _unidad_hora(),
                    description=s["descripcion"] or "",
                    active=bool(s["activo"]),
                    # La mano de obra no se compra: se vende. Sin esto aparecería
                    # en las órdenes de compra al lado de los consumibles.
                    purchasable=False,
                    default_sale_price=Decimal(str(s["precio"] or 0)),
                    # La alícuota va al mismo lugar que la de los productos, que
                    # es donde el resto del sistema ya la busca.
                    tax_profile=str(s["iva_rate"]) if s["iva_rate"] is not None else None,
                    metadata={
                        CLAVE_ORIGEN: str(s["id"]),
                        **({CLAVE_VALOR_HORA: "1"} if s["es_valor_hora"] else {}),
                    },
                )
            )
            salida["copiados"] += 1

    if salida["copiados"]:
        logger.info(
            "servicios_catalogo: %s servicio(s) copiados al catalogo del motor",
            salida["copiados"],
        )
    return salida


def _unidad_hora():
    """La unidad de los servicios migrados.

    Se importa acá y no arriba para que este módulo no dependa del orden en que
    `inventario` registra las unidades.
    """
    from .inventario import _unidad
    return _unidad("u")
