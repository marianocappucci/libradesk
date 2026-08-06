"""Las reglas de IVA de LibraDesk: que alicuotas valen y quien discrimina.

> *"El iva se tiene que calcular segun el tipo de condicion de iva que tenga el
> cliente."*

## Lo que el pedido queria decir, y lo que no

La formulacion original decia "como en contalibra", y eso resulto no describir
lo que Contalibra hace. Se resolvio con el humano el 2026-08-05: **la alicuota
es una propiedad del servicio, no del cliente**. En Argentina el 21 / 10,5 / 27
/ exento sale de QUE se vende; lo que depende de la condicion del receptor es
el tipo de comprobante y si el IVA va discriminado o incluido en el precio.

## Lo que aplica a ESTE producto

LibraDesk **no factura**: no tiene ARCA, ni WSFE, ni tipos de comprobante A/B/C.
Emite remitos y presupuestos. Asi que de las dos consecuencias de la condicion
del receptor, sobre este producto aplica **una sola**:

| Consecuencia | Aplica aca |
|---|---|
| Tipo de comprobante (A/B/C) | No — no emite comprobantes fiscales |
| Discriminar el IVA o incluirlo en el precio | **Si** |

Un Responsable Inscripto espera ver el neto y el IVA por separado, porque lo
computa como credito fiscal. Un Consumidor Final espera **un precio final**: el
desglose no le sirve para nada y le hace parecer mas caro lo mismo.

## Por que la lista de alicuotas es cerrada

Aunque este producto no facture, un presupuesto aceptado termina en una factura
—hoy a mano, manana quizas no— y ahi ARCA espera un `Id` de `AlicIva`. Como
`libracore.arca_wsfe._iva_id()` **cae al 21% ante un porcentaje que no conoce**,
un 13% cargado a mano no fallaria: se declararia como 21% sin ningun aviso.
Mismo criterio y misma lista que `medlibra/app/services/iva_rates.py`.
"""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

EXENTO = Decimal("0")

#: Las cuatro que `libracore.arca_wsfe._IVA_ID` sabe mapear a un Id de ARCA
#: (3=0%, 4=10,5%, 5=21%, 6=27%).
ALICUOTAS = (EXENTO, Decimal("0.105"), Decimal("0.21"), Decimal("0.27"))

DEFECTO = Decimal("0.21")

#: Las condiciones que el sistema conoce. Es la misma lista que ofrece la
#: pantalla de Configuracion para el EMISOR, para que no haya dos vocabularios.
CONDICIONES = (
    "Responsable Inscripto",
    "Monotributista",
    "IVA Exento",
    "Consumidor Final",
    "No Alcanzado",
)

#: Quienes esperan ver el IVA por separado. Los demas, un precio final.
#:
#: Sale de quien computa credito fiscal: un Responsable Inscripto lo hace y
#: necesita el neto; el resto no. Un Monotributista **no** discrimina — es el
#: error mas comun de este tema, porque "tiene CUIT" se confunde con "computa
#: IVA".
_DISCRIMINAN = frozenset({"Responsable Inscripto"})


class AlicuotaInvalida(ValueError):
    """La alicuota pedida no es una de las que ARCA sabe mapear."""


def validar(rate) -> Decimal:
    """Devuelve la alicuota como `Decimal`, o explota si no es una de las
    cuatro. Se llama al guardar, no al mostrar."""
    valor = Decimal(str(rate))
    if valor not in ALICUOTAS:
        validas = ", ".join(_pct(a) for a in ALICUOTAS)
        raise AlicuotaInvalida(f"alícuota {_pct(valor)} inválida; las válidas son {validas}")
    return valor


def _pct(rate: Decimal) -> str:
    """`Decimal("0.105")` → `"10.5%"`.

    El `:g` se aplica sobre un `float` a proposito: sobre un `Decimal` respeta
    los ceros significativos del literal y escribe `10.500%` y `21.00%`, que en
    un mensaje de error dirigido a una persona se leen como otra cosa.
    """
    return f"{float(rate) * 100:g}%"


def discrimina(condicion_iva: str | None) -> bool:
    """Si el comprobante para este cliente muestra el IVA por separado.

    Ante una condicion desconocida o vacia devuelve **False**, o sea precio
    final. Es el default seguro: mostrarle un desglose a quien no lo espera
    confunde, pero no rompe nada; al reves tampoco, y entre los dos el precio
    final es lo que espera la mayoria de los clientes de una mesa de ayuda.
    """
    return (condicion_iva or "") in _DISCRIMINAN


def totales(items: list[dict]) -> tuple[float, float, float]:
    """Subtotal, IVA y total de una lista de items, **cada uno con su
    alicuota**.

    Reemplaza al calculo viejo (`subtotal * tax_rate` con una sola alicuota
    para todo el comprobante), que daba mal apenas una linea era exenta.

    Se redondea **por linea** antes de sumar, no al final: es como se lee el
    comprobante —cada fila muestra su importe— y sumar los redondeados es lo
    que hace que el total coincida con la suma de lo que el cliente ve. Al
    reves, la caja de totales y la columna de importes difieren en centavos y
    parece un error de cuentas.
    """
    subtotal = Decimal("0")
    iva = Decimal("0")
    for i in items:
        linea = (Decimal(str(i["qty"])) * Decimal(str(i["unit_price"]))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP,
        )
        alicuota = Decimal(str(i.get("tax_rate", DEFECTO)))
        subtotal += linea
        iva += (linea * alicuota).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return float(subtotal), float(iva), float(subtotal + iva)


def alicuota_del_documento(items: list[dict]) -> float:
    """La que se guarda en la columna `tax_rate` del comprobante.

    La columna es del schema de LibraCore y no se puede sacar. Cuando todas las
    lineas coinciden guarda esa; cuando mezclan guarda `0`, que es lo unico
    honesto: cualquier otra seria falsa para parte del comprobante.

    **El PDF no la usa para decidir el rotulo** — mira las alicuotas de las
    lineas (LibraCore v1.12.0). Esta columna queda para los listados y para no
    romper lo que ya la leia.
    """
    alicuotas = {round(float(i.get("tax_rate", DEFECTO)), 4) for i in items}
    return alicuotas.pop() if len(alicuotas) == 1 else 0.0
