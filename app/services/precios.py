"""Cuánto vale un ítem para un cliente. **Una sola definición.**

## Qué problema resuelve

Lagrace tiene tres listas de precios —«Lista general», «Resellers» y
«Mostrador»— con **43 precios cargados**, y hasta el 2026-08-16 **ningún
circuito las aplicaba**: ni ventas, ni remitos, ni presupuestos, ni los
materiales de un reclamo. Todo cotizaba por `catalog_items.default_sale_price`.

Alguien cargó 43 precios diferenciados creyendo que servían, y no cambiaban nada
en ninguna pantalla. El mecanismo estaba construido y desenchufado; esto es el
enchufe.

## La precedencia, que es la decisión del humano (2026-08-16)

> *"La lista se tiene que poder elegir por cliente o por operación."*

Y ante el empate, **gana la de la operación**:

1. **La lista que la operación eligió**, si eligió una. Es la excepción
   justificada: este presupuesto puntual va a precio de reseller.
2. **La lista del cliente** (`clients.price_list_id`). Es el acuerdo.
3. **La lista por defecto** (`is_default`), que resuelve el motor solo.
4. **El precio del catálogo** (`default_sale_price`), si nada de lo anterior
   tiene precio para ese ítem.

El paso 4 no es un descarte: es lo que hace que **enchufar esto no cambie ningún
precio hoy**. Una lista que no tiene cargado el ítem devuelve `None`, y ahí el
producto sigue cotizando como cotizaba. La adopción es por ítem y por lista, no
un interruptor que mueve todo de golpe.

## Por qué un módulo y no una función suelta en cada circuito

Porque son cuatro circuitos —ventas, remitos, presupuestos y los materiales de
un reclamo— y con la regla copiada en cada uno, el día que cambie la precedencia
va a cambiar en tres. Es el mismo motivo por el que el saldo de la cuenta
corriente se calcula en el servicio y no en la pantalla, y por el que el margen
vive en `listas_precio.py`.
"""
from __future__ import annotations

from decimal import Decimal

from libracore.db import core as libracore_core

from .inventario import _repo


def lista_del_cliente(conn, cliente_id: int | None) -> int | None:
    """La lista asignada al cliente, o `None`.

    `None` **no es un error**: es un cliente que cotiza por la lista por
    defecto, que es como cotizan todos hasta que alguien les asigne una.
    """
    if not cliente_id:
        return None
    fila = conn.execute(
        "SELECT price_list_id FROM clients WHERE id = ?", (int(cliente_id),)
    ).fetchone()
    return fila["price_list_id"] if fila else None


def lista_efectiva(conn, *, cliente_id: int | None = None,
                   lista_id: int | None = None) -> int | None:
    """Qué lista se aplica. La de la operación pisa a la del cliente.

    Devuelve `None` cuando no hay ninguna elegida ni asignada, y eso significa
    "que el motor use la lista por defecto" — no "sin lista".
    """
    if lista_id:
        return int(lista_id)
    return lista_del_cliente(conn, cliente_id)


def precio_de(item_id: int, *, cliente_id: int | None = None,
              lista_id: int | None = None, sucursal_id: int | None = None,
              cantidad: float = 1.0) -> float:
    """El precio efectivo de un ítem. Nunca devuelve `None`.

    Cae al `default_sale_price` del catálogo cuando ninguna lista tiene ese
    ítem, que es lo que hace que enchufar las listas no mueva ningún precio
    hasta que alguien cargue uno. Ver el docstring del módulo.

    ⚠️ **Devuelve 0.0 para un ítem que no existe**, igual que
    `materiales.valorizados()`: inventar un precio sería peor, y la bandeja de
    facturación ya se niega a mandar un comprobante con total 0.
    """
    with libracore_core.get_connection() as conn:
        return _precio_con(conn, item_id, cliente_id=cliente_id,
                           lista_id=lista_id, sucursal_id=sucursal_id,
                           cantidad=cantidad)


def _precio_con(conn, item_id: int, *, cliente_id=None, lista_id=None,
                sucursal_id=None, cantidad=1.0) -> float:
    """El cálculo, sobre una conexión ya abierta.

    Existe separado para que un circuito que ya tiene la conexión —y que va a
    resolver N precios de un comprobante— no abra una por ítem.
    """
    repo = _repo(conn)
    efectiva = lista_efectiva(conn, cliente_id=cliente_id, lista_id=lista_id)
    resuelto = repo.resolve_price(
        int(item_id),
        price_list_id=efectiva,
        quantity=Decimal(str(cantidad)),
        branch_id=sucursal_id,
    )
    if resuelto is not None:
        return float(resuelto)

    item = repo.get_catalog_item(int(item_id))
    return float(item.default_sale_price) if item is not None else 0.0


def precios_de(item_ids, *, cliente_id: int | None = None,
               lista_id: int | None = None, sucursal_id: int | None = None) -> dict:
    """`{item_id: precio}` para varios ítems, en **una sola** conexión.

    Es lo que usan los circuitos que arman un comprobante entero: un remito de
    doce líneas abriría doce conexiones llamando a `precio_de()` una por una.
    """
    unicos = {int(i) for i in item_ids if i}
    if not unicos:
        return {}
    with libracore_core.get_connection() as conn:
        return {
            i: _precio_con(conn, i, cliente_id=cliente_id, lista_id=lista_id,
                           sucursal_id=sucursal_id)
            for i in unicos
        }
