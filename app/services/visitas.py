"""Las visitas de mantenimiento: el abono deja de cobrar sin operar.

## Qué problema resuelve

La revisión del circuito del 2026-08-16 encontró que **el abono cobra la cuota y
no programa la visita**, y era el hueco más grande de los cuatro circuitos:
verificado dos veces, no había **nada** de preventivo en todo `app/`. El sistema
le cobraba el mantenimiento al cliente todos los meses y no sabía que había que
ir.

Es el espejo exacto de lo que le faltaba al alquiler en agosto: allá el sistema
sabía cuánto valía el mes y nunca decía que el mes se devengó; acá sabe que hay
un abono y nunca dice que toca visitar.

## Por qué este módulo es tan corto

Porque casi todo ya existía. Una visita **es una incidencia** —decisión del
humano— así que la agenda, la detección de choques, la hoja de ruta, la
cuadrilla, las horas, los materiales, el cierre con control y el camino a
facturación vienen de arriba sin escribir una línea. Lo único propio de acá es
*qué contratos toca visitar en este período y cuáles ya se generaron*.

La aritmética de períodos tampoco es propia: es `cuotas.periodo_por_cadencia()`,
la misma que usa el devengado. Se separó de `periodo_de()` el 2026-08-16 justo
para esto — dos copias del recorte de día y de la alineación al año iban a
divergir.

## Las cuatro decisiones del humano (2026-08-16)

1. **Se visita al CLIENTE, una vez por período.** No una visita por equipo: hoy
   nada dice qué equipos del cliente cubre el abono, y modelarlo era un trabajo
   aparte. El técnico ve lo que hay cuando llega.
2. **La frecuencia es un campo propio** (`contratos.frecuencia_visita`) y no la
   `periodicidad` de facturación. Cobrar y visitar no son lo mismo.
3. **La visita es una incidencia**, no una entidad nueva.
4. **Con confirmación humana**, no por cron. `previsualizar()` muestra sin
   escribir; `generar()` escribe.

## La visita nace cubierta por el abono

`cobertura_abono='total'`, y no es un detalle: **es lo que el abono es**. El
cliente ya paga esa visita en la cuota, así que `convertir_a_remito()` se va a
negar a facturarla —dice "el abono cubre por completo estos reclamos"— que es
exactamente lo correcto.

Si en la visita se usan materiales o horas que el abono no cubre, alguien la pasa
a `parcial` y declara qué queda afuera. Ese es el camino que ya existe desde la
revisión `0024`.

> 🔑 Esto además **achica a mano** el hueco estructural nº 2 de la revisión del
> circuito ("la cobertura del abono se declara ticket por ticket"): para las
> visitas generadas, el contrato ya la contesta. Para los reclamos correctivos de
> un cliente con abono sigue siendo manual.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .contratos import FRECUENCIAS_VISITA, Contrato  # noqa: F401  (se reexporta)
from .cuotas import Periodo, periodo_por_cadencia
from .incidencias import Incidencia

# `FRECUENCIAS_VISITA` vive en `contratos.py` y se importa: es donde se valida al
# guardar, y una segunda tupla acá sería la que se olvidara de un valor nuevo.
# Se reexporta para que quien lea este módulo la encuentre donde la busca.

#: Cuánto dura una visita si el contrato no lo dice. Dos horas es lo que dura
#: una visita de mantenimiento típica; se edita en el ticket como cualquier otro.
DURACION_DEFECTO_MINUTOS = 120

_MESES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def titulo_de(periodo: Periodo) -> str:
    """«Mantenimiento preventivo — septiembre 2026».

    Para un período multi-mes nombra las dos puntas: «septiembre a noviembre
    2026». Un trimestral titulado sólo por su primer mes se lee como si fuera
    mensual, y el técnico que abre la agenda no tiene de dónde sacar la
    diferencia.
    """
    desde, hasta = periodo.desde, periodo.hasta
    if (desde.year, desde.month) == (hasta.year, hasta.month):
        return f"Mantenimiento preventivo — {_MESES[desde.month - 1]} {desde.year}"
    if desde.year == hasta.year:
        return (f"Mantenimiento preventivo — {_MESES[desde.month - 1]} a "
                f"{_MESES[hasta.month - 1]} {desde.year}")
    return (f"Mantenimiento preventivo — {_MESES[desde.month - 1]} {desde.year} a "
            f"{_MESES[hasta.month - 1]} {hasta.year}")


@dataclass(frozen=True)
class VisitaPropuesta:
    """Una visita que correspondería generar. No toca la base."""

    contrato_id: int
    contrato_numero: str
    cliente_id: int
    periodo: Periodo
    fecha_programada: date
    duracion_minutos: int
    ya_generada: bool

    def to_dict(self) -> dict:
        return {
            "contrato_id": self.contrato_id,
            "contrato_numero": self.contrato_numero,
            "cliente_id": self.cliente_id,
            "periodo_desde": self.periodo.desde.isoformat(),
            "periodo_hasta": self.periodo.hasta.isoformat(),
            "titulo": titulo_de(self.periodo),
            "fecha_programada": self.fecha_programada.isoformat(),
            "duracion_minutos": self.duracion_minutos,
            "ya_generada": self.ya_generada,
        }


class VisitaService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def _fecha_de_la_visita(self, contrato: Contrato, periodo: Periodo) -> date:
        """Qué día se agenda. El `dia_vencimiento` del contrato, o el día 1.

        Se reusa `dia_vencimiento` en vez de agregar otra columna: es el día del
        mes que el contrato ya tiene declarado, y en la práctica el abono se
        visita cerca de cuando se cobra. Si el día no existe en ese mes —el 31 en
        febrero— cae al último, misma regla que la aritmética de períodos.

        **Nunca cae fuera del período**: un `dia_vencimiento` de 31 sobre un
        trimestral daría el 31 del primer mes, que sí está adentro.
        """
        dia = contrato.dia_vencimiento or 1
        ultimo = calendar.monthrange(periodo.desde.year, periodo.desde.month)[1]
        return periodo.desde.replace(day=min(dia, ultimo))

    def _proponer(self, session, contrato: Contrato, ancla: date) -> VisitaPropuesta | None:
        """La visita que le toca a este contrato en el período de `ancla`.

        `None` cuando el contrato no visita: sin frecuencia declarada, o con el
        período entero fuera de la vigencia del contrato.
        """
        # Cubre los dos casos de una: `None` —el contrato no visita, que es el
        # default— y un valor que la aritmética de períodos no entiende.
        #
        # 🔑 **Había un `if not contrato.frecuencia_visita` arriba y se sacó**:
        # `None` tampoco está en `FRECUENCIAS_VISITA`, así que esta línea ya lo
        # atrapaba y aquélla no podía fallar nunca. Lo destapó la mutación —
        # sacarla no mataba ningún test, y sacarla junto con el filtro de la
        # consulta tampoco—. Un guard que no puede fallar no protege: engorda.
        #
        # Se saltea en vez de explotar porque una pantalla de previsualización no
        # puede caerse entera por un contrato mal cargado; que el valor inválido
        # no entre es responsabilidad de la validación de `contratos.py`.
        if contrato.frecuencia_visita not in FRECUENCIAS_VISITA:
            return None

        periodo = periodo_por_cadencia(contrato.frecuencia_visita, ancla)

        # Fuera de vigencia no se visita. Se compara contra el período completo
        # y no contra el ancla: un contrato que terminó el 5 de septiembre no
        # tiene que generar la visita de septiembre.
        if contrato.fecha_inicio > periodo.hasta:
            return None
        if contrato.fecha_fin and contrato.fecha_fin < periodo.desde:
            return None

        return VisitaPropuesta(
            contrato_id=contrato.id,
            contrato_numero=contrato.numero,
            cliente_id=contrato.cliente_id,
            periodo=periodo,
            fecha_programada=self._fecha_de_la_visita(contrato, periodo),
            duracion_minutos=(
                contrato.duracion_visita_minutos or DURACION_DEFECTO_MINUTOS
            ),
            ya_generada=self._ya_generada(session, contrato.id, periodo.desde),
        )

    def _ya_generada(self, session, contrato_id: int, periodo_desde: date) -> bool:
        return session.execute(
            select(Incidencia.id).where(
                Incidencia.contrato_id == contrato_id,
                Incidencia.periodo_visita == periodo_desde,
            )
        ).first() is not None

    def _armar(self, session, ancla: date, *,
               contrato_id: int | None = None) -> list[VisitaPropuesta]:
        """Las visitas del período, las que faltan y las que ya están.

        **Las ya generadas se devuelven, no se esconden.** Que un mes ya esté
        agendado es información; una pantalla que simplemente no lo lista se lee
        como "este contrato no visita" — mismo criterio que la previsualización
        de cuotas.

        🔴 **El período se resuelve por contrato, no una vez para todos.** Dos
        contratos con la misma frecuencia pueden caer en bloques distintos, y una
        sola consulta con un `periodo_desde` común daría por generado lo que no
        lo está.
        """
        stmt = select(Contrato).where(
            Contrato.estado == "activo",
            Contrato.frecuencia_visita.is_not(None),
        )
        if contrato_id is not None:
            stmt = stmt.where(Contrato.id == contrato_id)
        contratos = list(session.execute(stmt.order_by(Contrato.numero)).scalars())

        propuestas = []
        for c in contratos:
            p = self._proponer(session, c, ancla)
            if p is not None:
                propuestas.append(p)
        return propuestas

    def previsualizar(self, ancla: date, *, contrato_id: int | None = None) -> dict:
        """Lo que se generaría, **sin escribir nada**."""
        with self.session_factory() as session:
            propuestas = self._armar(session, ancla, contrato_id=contrato_id)
        pendientes = [p for p in propuestas if not p.ya_generada]
        return {
            "ancla": ancla.isoformat(),
            "visitas": [p.to_dict() for p in propuestas],
            "a_generar": len(pendientes),
            "ya_generadas": len(propuestas) - len(pendientes),
        }

    def generar(self, ancla: date, *, contrato_id: int | None = None,
                usuario_id: int | None = None) -> dict:
        """Escribe las visitas que faltan del período.

        **Idempotente**: las que ya existen se saltean, y el único parcial de la
        revisión `0027` lo sostiene además en la base. Correr esto dos veces el
        mismo mes no duplica nada.

        La incidencia nace `abierto` y **agendada**, que es la diferencia con un
        reclamo: una visita de mantenimiento se sabe cuándo es desde que se
        genera. Se le pone `cobertura_abono='total'` porque el abono la cubre —
        ver el docstring del módulo.

        > ⚠️ **No valida choques de agenda.** `fecha_programada` se pone pero
        > `equipo_trabajo_id` queda en NULL: todavía no se sabe qué cuadrilla va,
        > y `agenda.validar_agenda()` chequea contra el equipo asignado. La
        > validación ocurre cuando alguien le asigna la cuadrilla, que es el
        > momento en que el choque es real.
        """
        creadas = []
        with self.session_factory() as session:
            for p in self._armar(session, ancla, contrato_id=contrato_id):
                if p.ya_generada:
                    continue
                visita = Incidencia(
                    cliente_id=p.cliente_id,
                    contrato_id=p.contrato_id,
                    periodo_visita=p.periodo.desde,
                    titulo=titulo_de(p.periodo),
                    descripcion=(
                        f"Visita de mantenimiento del contrato {p.contrato_numero}, "
                        f"período {p.periodo.desde.isoformat()} a "
                        f"{p.periodo.hasta.isoformat()}."
                    ),
                    estado="abierto",
                    prioridad="media",
                    modalidad="on_site",
                    fecha_programada=datetime.combine(
                        p.fecha_programada, datetime.min.time()
                    ),
                    duracion_minutos=p.duracion_minutos,
                    # El abono la cubre: es lo que el abono es. Ver el módulo.
                    cobertura_abono="total",
                )
                session.add(visita)
                session.flush()
                creadas.append({
                    "incidencia_id": visita.id,
                    "contrato_id": p.contrato_id,
                    "contrato_numero": p.contrato_numero,
                    "titulo": visita.titulo,
                    "fecha_programada": p.fecha_programada.isoformat(),
                })
            session.commit()
        return {"generadas": len(creadas), "visitas": creadas}
