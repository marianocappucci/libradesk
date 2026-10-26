"""El ajuste por índice de un contrato: qué precio le toca y aplicarlo (revisión `0043`).

## Qué problema resuelve

`metodo_actualizacion='indice'` existía desde la fase 1 y se comportaba como `manual` «hasta que se defina de dónde sale
el índice». Desde libracore v1.196.0 el motor guarda los índices oficiales y hace la cuenta (`libracore.indices_ajuste`,
ADR-085 del motor), así que acá queda lo propio del contrato: **cuándo** le toca y **sobre qué precio**. Pedido del
humano del 2026-10-26, junto con el producto nuevo LibraInmo, que usa el mismo motor.

## Las decisiones

1. **El ajuste se cuenta desde `fecha_inicio`**, cada `periodicidad_ajuste` (`libracore.periodos.periodo_anclado`): un
   contrato trimestral que arrancó el 15-02 se ajusta el 15-05, el 15-08 y así. No se alinea al calendario: un ajuste
   no se prorratea.
2. **La base es el precio vigente**: de su `vigencia_desde` a la fecha del ajuste. Así un ajuste a mano en el medio no
   se pisa ni se cuenta dos veces: el próximo arranca desde ahí.
3. **Con confirmación humana**, como todo lo que mueve plata en este producto (decisión del 2026-08-07): `proponer`
   muestra la cuenta con los valores que tomó, y `aplicar` la escribe con `actualizar_precio`, que cierra el vigente y
   abre el nuevo en una transacción. El importe queda congelado en `contratos_precios`.
4. **Si falta un valor del índice, se baja en el momento** (`libracore.indices_descarga.sincronizar`) y se vuelve a
   probar una vez. Si igual falta (la fuente no publicó todavía, o es Casa Propia, que se carga a mano), no hay ajuste:
   `IndiceFaltante` dice qué fechas faltan.

Lo que **no** hace: no ajusta solo (no hay cron), no prorratea, y el dólar A 3500, que no se publica los fines de
semana, no encuentra valor si la fecha del ajuste cae sábado o domingo (el motor no toma el anterior: ADR-085).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from libracore import indices_ajuste as ia
from libracore import indices_descarga
from libracore.fechas import hoy
from libracore.periodos import periodo_anclado
from sqlalchemy import select

from .contratos import Contrato, ContratoPrecio, ContratoRepository

#: Cuántos días antes de la primera fecha que falta se pide a la fuente: un IPC mensual se fecha el primero del mes y
#: la fuente lo devuelve igual, pero así una semana de ICL sin bajar entra en el mismo pedido.
_MARGEN_DE_DESCARGA = timedelta(days=40)


class SinAjuste(ValueError):
    """El contrato no se ajusta por índice, o no tiene precio vigente. El mensaje dice por qué."""


def _decimal_a_json(valor: Decimal) -> str:
    return format(valor, "f")


def _serializar(ajuste: dict) -> dict:
    return {
        "indice": ajuste["indice"],
        "indice_nombre": ajuste["indice_nombre"],
        "fecha_base": ajuste["fecha_base"],
        "fecha_ajuste": ajuste["fecha_ajuste"],
        "importe_anterior": float(ajuste["importe_anterior"]),
        "importe_nuevo": float(ajuste["importe_nuevo"]),
        "coeficiente": _decimal_a_json(ajuste["coeficiente"]),
        "variacion_pct": float(ajuste["variacion_pct"]),
        "valores": [{"fecha": v["fecha"], "valor": _decimal_a_json(v["valor"]), "fuente": v["fuente"]}
                    for v in ajuste["valores"]],
    }


def _ajustar_bajando_si_falta(indice: str, importe, base: date, fecha: date) -> dict:
    try:
        return ia.ajustar(indice, importe, base, fecha)
    except ia.IndiceFaltante as faltan:
        if indice not in indices_descarga.DESCARGABLES:
            raise
        desde = date.fromisoformat(min(faltan.fechas)) - _MARGEN_DE_DESCARGA
        try:
            indices_descarga.sincronizar(indice, desde=desde, hasta=max(fecha, hoy()))
        except indices_descarga.FuenteNoDisponible:
            raise faltan from None
    return ia.ajustar(indice, importe, base, fecha)


class AjusteRepository:
    def __init__(self, contratos: ContratoRepository):
        self.contratos = contratos

    def _contrato_y_precio(self, contrato_id: int) -> tuple[Contrato, ContratoPrecio]:
        with self.contratos.session_factory() as session:
            c = session.get(Contrato, contrato_id)
            if c is None:
                raise KeyError(contrato_id)
            if c.metodo_actualizacion != "indice" or not c.indice_ajuste or not c.periodicidad_ajuste:
                raise SinAjuste("Este contrato no se actualiza por índice.")
            precio = session.execute(
                select(ContratoPrecio).where(
                    ContratoPrecio.contrato_id == contrato_id, ContratoPrecio.vigencia_hasta.is_(None),
                )
            ).scalars().first()
            if precio is None:
                raise SinAjuste("El contrato no tiene un precio vigente sobre el que ajustar.")
            session.expunge_all()
            return c, precio

    def proponer(self, contrato_id: int, *, fecha: date | None = None) -> dict:
        """Qué ajuste le toca al contrato en `fecha` (hoy, si no se dice). **No escribe nada** en el contrato.

        `{corresponde, fecha_ajuste, proximo_ajuste, precio_vigente, precio_vigente_desde, ajuste}`. Con
        `corresponde=False` el período de ajuste en curso ya tiene su precio y `ajuste` es `None`."""
        c, precio = self._contrato_y_precio(contrato_id)
        periodo = periodo_anclado(c.periodicidad_ajuste, ancla=fecha or hoy(), arranque=c.fecha_inicio)
        respuesta = {
            "indice": c.indice_ajuste,
            "periodicidad_ajuste": c.periodicidad_ajuste,
            "fecha_ajuste": periodo.desde.isoformat(),
            "proximo_ajuste": (periodo.hasta + timedelta(days=1)).isoformat(),
            "precio_vigente": float(precio.importe),
            "precio_vigente_desde": precio.vigencia_desde.isoformat(),
        }
        if periodo.desde <= precio.vigencia_desde:
            return {**respuesta, "corresponde": False, "ajuste": None}
        ajuste = _ajustar_bajando_si_falta(c.indice_ajuste, precio.importe, precio.vigencia_desde, periodo.desde)
        return {**respuesta, "corresponde": True, "ajuste": _serializar(ajuste)}

    def aplicar(self, contrato_id: int, *, fecha_ajuste: date, usuario: str = "Sistema") -> dict:
        """Aplica el ajuste que `proponer` muestra para `fecha_ajuste`: cierra el precio vigente y abre el nuevo.

        Se vuelve a calcular acá, no se confía en el importe de la pantalla: entre que se mostró y se confirmó pudo
        haber cambiado el precio vigente o el índice. Si `fecha_ajuste` no es la del período en curso, no se aplica."""
        propuesta = self.proponer(contrato_id, fecha=fecha_ajuste)
        if not propuesta["corresponde"]:
            raise SinAjuste("El período de ajuste en curso ya tiene su precio.")
        if propuesta["fecha_ajuste"] != fecha_ajuste.isoformat():
            raise SinAjuste(f"El ajuste de este período es el del {propuesta['fecha_ajuste']}, no el del "
                            f"{fecha_ajuste.isoformat()}.")
        nuevo = self.contratos.actualizar_precio(
            contrato_id, importe=Decimal(str(propuesta["ajuste"]["importe_nuevo"])),
            vigencia_desde=fecha_ajuste, motivo=f"ajuste_indice:{propuesta['indice']}", usuario=usuario,
        )
        return {"precio": nuevo, "ajuste": propuesta["ajuste"]}


def catalogo() -> list[dict]:
    """Los índices que ofrece el motor, para el selector del contrato."""
    return [{"clave": i.clave, "nombre": i.nombre, "periodicidad": i.periodicidad,
             "se_baja_solo": i.clave in indices_descarga.DESCARGABLES}
            for i in ia.INDICES.values()]
