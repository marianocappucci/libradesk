"""La hora de Argentina, en un solo lugar.

**Regla del proyecto** (`wiki/concepts/estandares-desarrollo.md`, seccion "Fecha
y hora"): todo sistema nuevo trabaja en **UTC-3 fijo, sin horario de verano**.
No es una preferencia estetica: los contenedores corren en UTC, asi que
`datetime.now()` adentro de uno devuelve la hora de Londres.

🔴 **Y no es teorico.** Una venta cargada a las 21:00 del 12 en Chivilcoy se
guardaba con fecha **13** --se vio en la prueba de este modulo, contra
PostgreSQL: el movimiento de cuenta corriente aparecio un dia adelantado del
comprobante que lo origino--. Con eso, un cierre de mes deja operaciones del
lado equivocado y nadie lo nota hasta conciliar.

Se apoya en el `_ar_now()` de LibraCore para que la hora del producto y la que
estampan las tablas del motor sean **la misma**; tener dos definiciones seria
volver a tener el problema, mas dificil de ver.
"""

from __future__ import annotations

from datetime import datetime

from libracore.db.core import _ar_now


def ahora() -> datetime:
    """`datetime` en hora de Argentina, naive (sin tzinfo).

    Naive a proposito: es lo que esperan `occurred_at`/`fecha` de los dos
    motores, que guardan texto. Un aware acá se serializaria con offset y
    dejaria dos formatos distintos en la misma columna.
    """
    return datetime.strptime(_ar_now(), "%Y-%m-%d %H:%M:%S")


def hoy() -> str:
    """La fecha de hoy en Argentina, ISO (`aaaa-mm-dd`).

    ISO y no `dd-mm-aaaa`: el formato `dd-mm-aaaa` es **de presentacion** y va
    en la pantalla. La base y las APIs siguen en ISO 8601, tambien por regla
    del proyecto.
    """
    return _ar_now()[:10]
