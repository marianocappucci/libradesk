"""Accion compuesta "Reemplazar equipo": una operacion, dos activos y un
ticket, todo en una transaccion.

**Por que no alcanzaba con lo que ya habia.** Registrar un reemplazo
requeria tres pasos manuales y desconectados entre si: editar el equipo
retirado (estado + ubicacion), editar el sustituto, y escribir a mano dos
notas en la incidencia contando lo que uno acababa de hacer. Nada ataba
las tres cosas: el historial del equipo decia *que* se movio pero no *por
que*, y la incidencia decia *que* se reemplazo solo si el tecnico se
acordo de escribirlo. Con tres pasos manuales, ademas, se puede hacer uno
y olvidar los otros dos — el inventario y la mesa de ayuda quedan
contando historias distintas.

Aca es una sola llamada que:

1. Mueve el **retirado** a su destino (service / deposito / baja),
   cambiando estado y ubicacion.
2. Pone al **sustituto** en el lugar que dejo el retirado, en `activo`.
3. Genera los movimientos de ambos **con `incidencia_id`**, o sea que la
   ficha del equipo dice de que ticket vino cada movimiento.
4. Deja las dos intervenciones narradas en la actividad del ticket.

**El caso de la vuelta del service es esta misma operacion al reves**, no
una funcion aparte: `retirado=<el sustituto temporal>`,
`sustituto=<el equipo que volvio>`, `destino=deposito`. El sustituto toma
la ubicacion que tenia el retirado, que es exactamente lo que se quiere
al reinstalar el equipo original y mandar el prestado de vuelta al
deposito.

Los movimientos los deriva `equipos.movimientos_por_cambio()`, el mismo
codigo que usa la edicion manual: un reemplazo y una edicion a mano
producen historial identico, no dos dialectos.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from .equipos import (
    Equipo, _mov_to_dict, _to_dict as _equipo_to_dict, descripcion_equipo,
    movimientos_por_cambio, ubicacion_texto,
)
from .incidencias import ActividadIncidencia, Incidencia, _actividad_to_dict
from .proveedores import Proveedor
from .reparaciones import Reparacion, resolver as resolver_reparacion

# destino -> (estado del equipo retirado, sector por defecto, frase para la nota)
DESTINOS: dict[str, tuple[str, str, str]] = {
    "service": ("en_reparacion", "Service", "se envía a service"),
    "deposito": ("almacenado", "Depósito", "vuelve a depósito"),
    "baja": ("baja", "Baja", "se da de baja"),
}


@dataclass
class DatosService:
    """Lo que hay que saber de un equipo que sale a reparar.

    Viaja junto al reemplazo y no en una llamada aparte **a proposito**: mandar
    el equipo y registrar a donde se lo mando son el mismo hecho, y separarlos
    en dos requests admite el estado que este pendiente venia a eliminar — un
    equipo `en_reparacion` sin ninguna reparacion que diga donde esta.
    """
    proveedor_id: int
    fecha_envio: date
    remito_salida: str | None = None
    rma: str | None = None
    en_garantia: bool = False
    observaciones: str | None = None


@dataclass
class CierreService:
    """La vuelta: se cierra la reparacion abierta del equipo que **entra**.

    Es el sustituto y no el retirado porque la vuelta del service es esta misma
    operacion al reves (ver el docstring del modulo): el equipo que estaba
    afuera vuelve a su lugar entrando como sustituto, y el prestado sale a
    deposito.
    """
    fecha_retorno: date
    diagnostico: str | None = None
    costo: Decimal | float | None = None


def _sellar_cronologia(filas: list) -> None:
    """Fecha explicita y creciente, en el orden en que pasaron los hechos.

    **Encontrado probando la UI, no por los tests**: un reemplazo genera
    hasta 6 filas y el default de las tres tablas es `CURRENT_TIMESTAMP`,
    que en SQLite tiene resolucion de **un segundo** — o sea que las 6
    quedan con la misma hora y el timeline las ordena como quiera. En la
    primera prueba en el navegador la instalacion del sustituto aparecio
    *antes* del retiro del equipo que venia a reemplazar, que es la
    historia al reves.

    **Milisegundos y no microsegundos**, aunque la columna DATETIME de
    SQLite conserve los seis digitos: el `Date` de JavaScript trunca a
    milisegundos, asi que un sellado por microsegundos vuelve a empatar
    del lado del navegador y no arregla nada. Se probo primero con
    microsegundos y el timeline seguia desordenado — el defecto solo se
    ve en la UI, no en la API.

    Naive-UTC a proposito: es lo que guarda `CURRENT_TIMESTAMP` en el
    resto de las filas, y mezclar husos ordenaria mal contra las que ya
    existen.

    **La columna no se llama igual en todas las tablas**: los movimientos y la
    actividad la tienen como `fecha`, y `equipos_reparaciones` como
    `created_at`. Se sella la que exista en vez de asumir un nombre — asumirlo
    dejaria a la reparacion con el `CURRENT_TIMESTAMP` por default, o sea
    empatada con el resto, que es exactamente el defecto que esta funcion
    existe para evitar.
    """
    base = datetime.now(timezone.utc).replace(tzinfo=None)
    for i, fila in enumerate(filas):
        campo = "fecha" if hasattr(fila, "fecha") else "created_at"
        setattr(fila, campo, base + timedelta(milliseconds=i))


class ReemplazoService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def reemplazar(
        self,
        incidencia_id: int,
        *,
        equipo_retirado_id: int,
        equipo_sustituto_id: int | None = None,
        destino: str = "service",
        motivo: str | None = None,
        sector_destino: str | None = None,
        ubicacion_destino: str | None = None,
        usuario_actor: str | None = None,
        service: DatosService | None = None,
        cierre_service: CierreService | None = None,
    ) -> dict:
        """Devuelve `{retirado, sustituto, movimientos, actividades, reparacion,
        reparacion_cerrada}`.

        `equipo_sustituto_id` es opcional: retirar un equipo sin reponer
        nada es un caso real (no siempre hay repuesto a mano), y es
        preferible a obligar a inventar un sustituto.

        Valida que el **retirado** sea del cliente de la incidencia — un
        ticket de un cliente no puede retirar el equipo de otro. El
        **sustituto** no se restringe a proposito: puede venir del stock
        propio, que en este modelo tambien es un `equipo` con su cliente.

        `service` abre la reparacion del equipo que sale (solo con
        `destino="service"`); `cierre_service` cierra la que tuviera abierta el
        que entra. Las dos cosas ocurren **en la misma transaccion** que el
        movimiento de inventario: si el reemplazo se revierte, la reparacion no
        queda colgada, y viceversa.
        """
        if destino not in DESTINOS:
            raise ValueError(f"destino invalido: {destino!r}")
        if equipo_sustituto_id is not None and equipo_sustituto_id == equipo_retirado_id:
            raise ValueError("el equipo sustituto no puede ser el mismo que el retirado")
        # Una reparacion sobre un equipo que va a deposito o de baja describiria
        # algo que no paso. Se rechaza en vez de ignorarse en silencio: el
        # llamador cargo esos datos creyendo que iban a alguna parte.
        if service is not None and destino != "service":
            raise ValueError(
                f"los datos de service solo aplican con destino='service', no {destino!r}"
            )
        if cierre_service is not None and equipo_sustituto_id is None:
            raise ValueError(
                "no hay equipo que vuelva del service: el cierre necesita un sustituto"
            )

        estado_destino, sector_por_defecto, frase_destino = DESTINOS[destino]

        with self.session_factory() as session:
            incidencia = session.get(Incidencia, incidencia_id)
            if incidencia is None:
                raise KeyError(("incidencia", incidencia_id))

            retirado = session.get(Equipo, equipo_retirado_id)
            if retirado is None:
                raise KeyError(("equipo_retirado", equipo_retirado_id))
            if retirado.cliente_id != incidencia.cliente_id:
                raise ValueError("el equipo retirado no pertenece al cliente de la incidencia")

            sustituto = None
            if equipo_sustituto_id is not None:
                sustituto = session.get(Equipo, equipo_sustituto_id)
                if sustituto is None:
                    raise KeyError(("equipo_sustituto", equipo_sustituto_id))

            # Todo lo del bloque de service se valida ACA, antes de la primera
            # escritura, igual que el resto de las validaciones de este metodo.
            # La transaccion cubre el caso de todos modos, pero un rollback es
            # el plan B: lo barato es no empezar.
            if service is not None:
                if session.get(Proveedor, service.proveedor_id) is None:
                    raise KeyError(("proveedor", service.proveedor_id))
                ya_abierta = session.execute(
                    select(func.count()).select_from(Reparacion)
                    .where(Reparacion.equipo_id == equipo_retirado_id)
                    .where(Reparacion.fecha_retorno.is_(None))
                ).scalar_one()
                if ya_abierta:
                    raise ValueError("el equipo ya tiene una reparacion abierta")

            reparacion_a_cerrar = None
            if cierre_service is not None:
                reparacion_a_cerrar = session.execute(
                    select(Reparacion)
                    .where(Reparacion.equipo_id == equipo_sustituto_id)
                    .where(Reparacion.fecha_retorno.is_(None))
                    .order_by(Reparacion.fecha_envio.desc())
                ).scalars().first()
                if reparacion_a_cerrar is None:
                    raise ValueError(
                        "el equipo que entra no tiene ninguna reparacion abierta que cerrar"
                    )
                if cierre_service.fecha_retorno < reparacion_a_cerrar.fecha_envio:
                    raise ValueError("la fecha de retorno es anterior a la de envio")

            actor = usuario_actor or "Sistema"
            motivo_final = motivo or f"Incidencia #{incidencia_id}"

            # El hueco que deja el retirado: es donde entra el sustituto.
            hueco_sector = retirado.sector
            hueco_ubicacion = retirado.ubicacion_oficina
            hueco_texto = ubicacion_texto(hueco_sector, hueco_ubicacion)

            movimientos = []
            actividades = []
            # Las filas en el orden en que pasaron los hechos. Ver
            # `_sellar_cronologia()`: sin esto las 6 caen en el mismo
            # segundo y el timeline las muestra en cualquier orden.
            cronologia = []

            # ── 1. El equipo que sale ───────────────────────────────────
            previo = (retirado.sector, retirado.ubicacion_oficina, retirado.estado)
            retirado.sector = sector_destino if sector_destino is not None else sector_por_defecto
            retirado.ubicacion_oficina = ubicacion_destino
            retirado.estado = estado_destino
            movs_retirado = movimientos_por_cambio(
                retirado,
                sector_previo=previo[0], ubicacion_previa=previo[1], estado_previo=previo[2],
                usuario=actor, motivo=motivo_final, incidencia_id=incidencia_id,
            )
            movimientos += movs_retirado
            texto_retiro = (
                f"Se retira {descripcion_equipo(retirado)} de {hueco_texto} y "
                f"{frase_destino} ({ubicacion_texto(retirado.sector, retirado.ubicacion_oficina)})."
            )
            if motivo:
                texto_retiro += f" Motivo: {motivo}."
            acta_retiro = ActividadIncidencia(
                incidencia_id=incidencia_id, descripcion=texto_retiro, usuario=actor,
            )
            actividades.append(acta_retiro)
            cronologia += [acta_retiro, *movs_retirado]

            # ── 1b. La reparacion, si el equipo sale a service ──────────
            # Cierra el pendiente 19: hasta aca, "a quien se lo mandamos" y
            # "con que RMA" solo podian vivir dentro del texto del motivo.
            reparacion = None
            if service is not None:
                reparacion = Reparacion(
                    equipo_id=retirado.id,
                    incidencia_id=incidencia_id,
                    proveedor_id=service.proveedor_id,
                    fecha_envio=service.fecha_envio,
                    remito_salida=service.remito_salida,
                    rma=service.rma,
                    en_garantia=service.en_garantia,
                    observaciones=service.observaciones,
                    usuario=actor,
                )
                proveedor = session.get(Proveedor, service.proveedor_id)
                detalle = [f"proveedor: {proveedor.nombre}"]
                if service.remito_salida:
                    detalle.append(f"remito {service.remito_salida}")
                if service.rma:
                    detalle.append(f"RMA {service.rma}")
                detalle.append("en garantía" if service.en_garantia else "sin garantía")
                acta_service = ActividadIncidencia(
                    incidencia_id=incidencia_id,
                    descripcion=f"Enviado a service — {', '.join(detalle)}.",
                    usuario=actor,
                )
                actividades.append(acta_service)
                cronologia += [reparacion, acta_service]

            # ── 2. El equipo que entra en su lugar ──────────────────────
            if sustituto is not None:
                previo_s = (sustituto.sector, sustituto.ubicacion_oficina, sustituto.estado)
                sustituto.sector = hueco_sector
                sustituto.ubicacion_oficina = hueco_ubicacion
                sustituto.estado = "activo"
                movs_sustituto = movimientos_por_cambio(
                    sustituto,
                    sector_previo=previo_s[0], ubicacion_previa=previo_s[1],
                    estado_previo=previo_s[2],
                    usuario=actor, motivo=motivo_final, incidencia_id=incidencia_id,
                )
                movimientos += movs_sustituto
                acta_instalacion = ActividadIncidencia(
                    incidencia_id=incidencia_id,
                    descripcion=(
                        f"Se instala {descripcion_equipo(sustituto)} en {hueco_texto} "
                        f"en reemplazo de {descripcion_equipo(retirado)}."
                    ),
                    usuario=actor,
                )
                actividades.append(acta_instalacion)
                cronologia += [acta_instalacion, *movs_sustituto]

            # ── 2b. La vuelta: se cierra la reparacion del que entro ────
            if reparacion_a_cerrar is not None:
                reparacion_a_cerrar.fecha_retorno = cierre_service.fecha_retorno
                if cierre_service.diagnostico is not None:
                    reparacion_a_cerrar.diagnostico = cierre_service.diagnostico
                if cierre_service.costo is not None:
                    reparacion_a_cerrar.costo = Decimal(str(cierre_service.costo))
                dias = (cierre_service.fecha_retorno - reparacion_a_cerrar.fecha_envio).days
                proveedor_cierre = session.get(Proveedor, reparacion_a_cerrar.proveedor_id)
                texto_vuelta = (
                    f"Vuelve de service {descripcion_equipo(sustituto)} "
                    f"({proveedor_cierre.nombre}, {dias} días)."
                )
                if cierre_service.diagnostico:
                    texto_vuelta += f" Diagnóstico: {cierre_service.diagnostico}."
                acta_vuelta = ActividadIncidencia(
                    incidencia_id=incidencia_id, descripcion=texto_vuelta, usuario=actor,
                )
                actividades.append(acta_vuelta)
                cronologia.append(acta_vuelta)

            _sellar_cronologia(cronologia)

            for fila in cronologia:
                session.add(fila)
            session.commit()

            for fila in (*movimientos, *actividades):
                session.refresh(fila)
            session.refresh(retirado)
            if sustituto is not None:
                session.refresh(sustituto)
            for r in (reparacion, reparacion_a_cerrar):
                if r is not None:
                    session.refresh(r)

            return {
                "retirado": _equipo_to_dict(retirado),
                "sustituto": _equipo_to_dict(sustituto) if sustituto is not None else None,
                "movimientos": [_mov_to_dict(m) for m in movimientos],
                "actividades": [_actividad_to_dict(a) for a in actividades],
                # Mismo `resolver` que usa el repositorio, no una copia: dos
                # armados del mismo dict dejan que un test cubra uno y el otro
                # quede suelto (lo agarro `forzar_fallos.py`).
                "reparacion": resolver_reparacion(session, reparacion),
                "reparacion_cerrada": resolver_reparacion(session, reparacion_a_cerrar),
            }
