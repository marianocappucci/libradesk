"""Cuenta corriente por cliente. Dominio entero de LibraCore.

Este archivo es casi todo declaracion: lo unico propio de LibraDesk es **de que
tabla salen las ventas**. Viven en `sales` de LibraCommerce, no en la tabla
`ventas` de LibraCore, asi que se le pasa el origen `VENTAS_LIBRACOMMERCE` --el
mismo que usa Contalibra desde su migracion P7--.

Sin ese parametro, `get_cc_saldo()` leeria la tabla `ventas`, que en esta base
**existe y esta vacia** (la crea el schema del motor). No fallaria: devolveria
saldo cero para todos los clientes. Es el mismo pozo que documenta
`app/db_recibos.py` de Contalibra.

## Que suma y que no

El saldo son cuatro terminos: debitos por venta en cuenta corriente, debitos por
factura, debitos directos, menos los abonos.

> 🔴 **La pata de facturas siempre da cero en LibraDesk, y es una decision de
> producto pendiente.** Sale de `caja_movimientos` + `facturas`, dos tablas que
> este producto crea vacias porque **no factura**: los comprobantes fiscales los
> emite SOS Contador. O sea que hoy la cuenta corriente refleja **lo que
> LibraDesk emite** y no lo que el cliente realmente debe.
>
> La salida es registrar un `cc_debito` al mandar el comprobante a SOS --el
> puente ya existe, `app/services/facturacion_externa.py`-- y es lo que hace
> que `cc_debitos` exista en el motor. **No esta cableado todavia**: hay que
> decidirlo con el cliente, porque cambia que significa el saldo. Ver la fase 5
> de `wiki/analyses/libradesk-modulo-comercial-plan.md`.
"""

from __future__ import annotations

from functools import partial

from libracore.db import cuenta_corriente as _cc

# Estas no dependen del origen de las ventas: se reexportan tal cual.
from libracore.db.cuenta_corriente import (  # noqa: F401
    VENTAS_LIBRACOMMERCE,
    create_cc_debito,
    create_cc_pago,
    delete_cc_debito,
    delete_cc_pago,
    get_cc_pago,
)

saldo = partial(_cc.get_cc_saldo, origen=VENTAS_LIBRACOMMERCE)
movimientos = partial(_cc.get_cc_movimientos, origen=VENTAS_LIBRACOMMERCE)
movimientos_periodo = partial(
    _cc.get_cc_movimientos_periodo, origen=VENTAS_LIBRACOMMERCE
)


def clientes_con_saldo() -> list[dict]:
    """Los clientes con movimientos, con los nombres de campo de ESTE producto.

    ⚠️ El motor devuelve las columnas crudas de `clients` --`id`, `name`,
    `cuit_dni`-- y el contrato de `/api/clientes` de LibraDesk usa `cliente_id`
    y `nombre`. Traducir aca y no en la pantalla es lo que evita que cada vista
    invente su propio mapeo.

    🔴 No es teorico: la primera version de la pantalla de cuenta corriente leia
    `cliente_id` y `nombre` directo de esta respuesta y **renderizaba filas en
    blanco con saldo correcto**. No fallaba, no avisaba: mostraba una tabla de
    deudores sin nombre. Lo destapo `test_comercial_api.py`.
    """
    return [
        {"cliente_id": c["id"], "nombre": c["name"],
         "cuit": c.get("cuit_dni") or "", "saldo": float(c["saldo"])}
        for c in _cc.get_clientes_con_saldo_cc(origen=VENTAS_LIBRACOMMERCE)
    ]


def resumen() -> dict:
    """Las tres cifras del encabezado de la pantalla.

    Se calculan aca y no en el front por el mismo motivo de siempre: si la
    pantalla las derivara, otra pantalla podria derivarlas distinto.
    """
    clientes = clientes_con_saldo()
    deudores = [c for c in clientes if float(c.get("saldo", 0)) > 0]
    return {
        "clientes_con_saldo": len(deudores),
        "total_adeudado": round(sum(float(c["saldo"]) for c in deudores), 2),
        "saldo_mayor": round(
            max((float(c["saldo"]) for c in deudores), default=0.0), 2
        ),
    }
