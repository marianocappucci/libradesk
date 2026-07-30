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

from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import sessionmaker

from .equipos import (
    Equipo, _mov_to_dict, _to_dict as _equipo_to_dict, descripcion_equipo,
    movimientos_por_cambio, ubicacion_texto,
)
from .incidencias import ActividadIncidencia, Incidencia, _actividad_to_dict

# destino -> (estado del equipo retirado, sector por defecto, frase para la nota)
DESTINOS: dict[str, tuple[str, str, str]] = {
    "service": ("en_reparacion", "Service", "se envía a service"),
    "deposito": ("almacenado", "Depósito", "vuelve a depósito"),
    "baja": ("baja", "Baja", "se da de baja"),
}


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
    """
    base = datetime.now(timezone.utc).replace(tzinfo=None)
    for i, fila in enumerate(filas):
        fila.fecha = base + timedelta(milliseconds=i)


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
    ) -> dict:
        """Devuelve `{retirado, sustituto, movimientos, actividades}`.

        `equipo_sustituto_id` es opcional: retirar un equipo sin reponer
        nada es un caso real (no siempre hay repuesto a mano), y es
        preferible a obligar a inventar un sustituto.

        Valida que el **retirado** sea del cliente de la incidencia — un
        ticket de un cliente no puede retirar el equipo de otro. El
        **sustituto** no se restringe a proposito: puede venir del stock
        propio, que en este modelo tambien es un `equipo` con su cliente.
        """
        if destino not in DESTINOS:
            raise ValueError(f"destino invalido: {destino!r}")
        if equipo_sustituto_id is not None and equipo_sustituto_id == equipo_retirado_id:
            raise ValueError("el equipo sustituto no puede ser el mismo que el retirado")

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

            _sellar_cronologia(cronologia)

            for fila in cronologia:
                session.add(fila)
            session.commit()

            for fila in (*movimientos, *actividades):
                session.refresh(fila)
            session.refresh(retirado)
            if sustituto is not None:
                session.refresh(sustituto)

            return {
                "retirado": _equipo_to_dict(retirado),
                "sustituto": _equipo_to_dict(sustituto) if sustituto is not None else None,
                "movimientos": [_mov_to_dict(m) for m in movimientos],
                "actividades": [_actividad_to_dict(a) for a in actividades],
            }
