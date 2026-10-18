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

Se apoya en `libracore.fechas` (ADR-070, LibraCore v1.182.0) para que la hora del
producto y la que estampan las tablas del motor sean **la misma**; tener dos
definiciones seria volver a tener el problema, mas dificil de ver.
"""

from __future__ import annotations

from datetime import datetime

from libracore import fechas


def ahora() -> datetime:
    """`datetime` en hora de Argentina, naive (sin tzinfo).

    Naive a proposito: es lo que esperan `occurred_at`/`fecha` de los dos
    motores, que guardan texto. Un aware acá se serializaria con offset y
    dejaria dos formatos distintos en la misma columna.

    Con microsegundos, como el `datetime.now()` al que reemplaza: una antiguedad
    en dias (`ahora - fecha_creacion`) no puede quedar un dia corta por haber
    redondeado el reloj para abajo.
    """
    return fechas.ahora().replace(tzinfo=None)


def hoy() -> str:
    """La fecha de hoy en Argentina, ISO (`aaaa-mm-dd`).

    ISO y no `dd-mm-aaaa`: el formato `dd-mm-aaaa` es **de presentacion** y va
    en la pantalla. La base y las APIs siguen en ISO 8601, tambien por regla
    del proyecto.
    """
    return fechas.hoy().isoformat()
