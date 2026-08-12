"""La agenda de los equipos de trabajo (pedido 42, fase B).

Cierra lo que la fase A dejo explicitamente afuera: *"cuando un equipo tiene
asignado un trabajo ya sabe en que vehiculo sale **de acuerdo a la
disponibilidad**"*. Con la fase A la disponibilidad solo podia ser "esta o no
esta en otro equipo", porque la incidencia no sabia **cuando** se iba a
atender. Ahora si: se le agenda fecha, hora y duracion.

**LibraGenda se usa como libreria de REGLAS, no de persistencia**, y esa es la
decision que define el modulo.

El motor de turnos de la familia ([[libragenda]], que ya consumen Gestiolibra y
MedLibra) trae 11 tablas —`resources`, `services`, `clients`, `branches`,
`appointments`, `availability`, `holidays`…— y un juego completo de
repositorios. Instalar todo eso aca habria significado:

- **Espejar cada vehiculo y cada equipo como un `resource`**, o sea dos filas
  para la misma cosa y dos fuentes de verdad sobre su nombre y su estado. Es
  exactamente el defecto que este producto viene evitando en el modulo de
  alquileres (el precio vive en un solo lado) y en los depositos.
- Una tabla `clients` al lado de la `clientes` que ya existe.
- Cinco tablas mas que nadie usaria.

Pero **lo que hacia falta del motor no es su persistencia: son sus reglas**.
`find_conflicts()` es una funcion **pura** —recibe un turno y una lista de
turnos existentes, devuelve los que se pisan— y `Appointment` es un dataclass.
Asi que LibraDesk sigue siendo dueno de sus datos (la incidencia con su fecha y
su equipo) y le pregunta al motor si hay superposicion.

> Que se pierde: `is_appointment_available()`, que valida ventanas horarias
> semanales, feriados y bloqueos. Eso **si** necesita las tablas del motor.
> Nadie lo pidio —el pedido era no pisar dos trabajos— y el dia que haga falta
> ("no agendar sabados") se suman esas tablas sin tirar nada de esto: el
> `Appointment` que se arma aca es el mismo que come esa funcion.

**El recurso es el EQUIPO, no el vehiculo.** Un vehiculo pertenece a un solo
equipo (fase A), asi que si el equipo no esta duplicado el vehiculo tampoco
puede estarlo. Chequear los dos seria chequear lo mismo dos veces y, peor,
admitiria que dieran respuestas distintas.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from libragenda.domain import Appointment, AppointmentStatus
from libragenda.scheduling import find_conflicts
from sqlalchemy import select

# Los tres campos que `Appointment` exige y que a este vertical no le dicen
# nada: un trabajo de soporte no tiene "servicio" ni "cliente" en el sentido de
# una agenda de turnos. Se ponen constantes en vez de inventar entidades — el
# motor solo los usa para su propia validacion de no-vacio.
_SERVICIO = "visita"
_CLIENTE = "libradesk"

# Cuanto dura un trabajo si nadie lo dice. Una hora es lo que dura una visita
# tipica; el usuario puede cambiarlo por ticket.
DURACION_POR_DEFECTO = 60


class Superpuesto(ValueError):
    """El equipo ya tiene otro trabajo en ese horario."""


def _turno(incidencia) -> Appointment:
    """Un `Appointment` del motor armado desde una incidencia de LibraDesk.

    El `resource_id` lleva prefijo (`equipo:12`) y no el id pelado: si algun
    dia se agenda otra clase de recurso —una sala, un instrumento—, dos ids
    numericos iguales de tablas distintas se confundirian entre si y el motor
    reportaria un choque que no existe.
    """
    return Appointment(
        id=str(incidencia.id),
        resource_id=f"equipo:{incidencia.equipo_trabajo_id}",
        service_id=_SERVICIO,
        client_id=_CLIENTE,
        starts_at=incidencia.fecha_programada,
        duration=timedelta(minutes=incidencia.duracion_minutos or DURACION_POR_DEFECTO),
        # Siempre CONFIRMED, sin mirar el estado del ticket. `find_conflicts()`
        # solo perdona `cancelled` y `no_show`: un turno `completed` **sigue
        # ocupando** su horario. Es correcto —el equipo estuvo ahi, cerrar el
        # ticket no lo devuelve al pasado— pero conviene decirlo, porque el
        # mapeo cerrado→COMPLETED que estaba escrito aca antes daba a entender
        # que liberaba el horario y no lo hacia (lo agarro
        # `test_un_trabajo_cerrado_sigue_ocupando_su_horario`).
        #
        # Para liberar un horario se **desagenda** el ticket (fecha_programada a
        # NULL) o se le corrige la duracion. No se toca el estado.
        status=AppointmentStatus.CONFIRMED,
    )


def _agendadas_del_equipo(session, equipo_id: int):
    """Los tickets ya agendados de ese equipo, para preguntarle al motor.

    Esto es un **prefiltro, no la regla**. `find_conflicts()` ya descarta lo que
    sea de otro recurso y el turno consigo mismo; el `where` de aca solo existe
    para no traer a memoria toda la agenda de la empresa en cada alta. La
    consecuencia practica: tiene que ser **igual o mas ancho** que la regla del
    motor. Si un dia se lo achica de mas, se dejan de ver choques reales — que
    es la unica direccion en la que este filtro puede romper algo, y es la que
    verifica la rotura "prefiltro mas angosto que la regla".

    (Aca hubo tambien un `excluyendo=<id propio>`, borrado: era una segunda
    copia del `other.id != appointment.id` del motor. Romperlo no ponia rojo
    ningun test justamente porque el motor lo tapaba — dos escrituras de la
    misma regla que podian, en el futuro, dejar de coincidir.)
    """
    from .incidencias import Incidencia

    return list(session.execute(
        select(Incidencia).where(
            Incidencia.equipo_trabajo_id == equipo_id,
            Incidencia.fecha_programada.is_not(None),
        )
    ).scalars())


def validar_agenda(session, incidencia) -> None:
    """Se planta si el equipo ya tiene otro trabajo pisado en ese horario.

    No hace nada si la incidencia no esta agendada o no tiene equipo: agendar
    es opcional, y un ticket sin fecha no ocupa a nadie.
    """
    if incidencia.fecha_programada is None or incidencia.equipo_trabajo_id is None:
        return

    nuevo = _turno(incidencia)
    existentes = [
        _turno(i)
        for i in _agendadas_del_equipo(session, incidencia.equipo_trabajo_id)
    ]
    # La regla la aplica el motor, no este archivo. Lo unico que hay aca es la
    # traduccion de un modelo al otro. Incluido el "no chocar consigo mismo":
    # `find_conflicts()` compara ids, asi que el ticket que se esta editando
    # viene en `existentes` y el motor lo descarta solo.
    choques = find_conflicts(nuevo, existentes)
    if choques:
        otro = choques[0]
        raise Superpuesto(
            f"El equipo ya tiene el trabajo #{otro.id} entre "
            f"{otro.starts_at.strftime('%d-%m %H:%M')} y "
            f"{otro.ends_at.strftime('%H:%M')}."
        )


def agenda_del_equipo(session, equipo_id: int, desde: datetime,
                      hasta: datetime) -> list[dict]:
    """Lo que tiene el equipo entre dos fechas, mas temprano primero.

    Es la vista que contesta "que hace el equipo el martes" — y, de paso, en que
    vehiculo, que sale de la asignacion de la fase A.
    """
    from .clientes import Cliente
    from .equipos_trabajo import Vehiculo
    from .incidencias import Incidencia

    vehiculos = [
        v.patente for v in session.execute(
            select(Vehiculo).where(Vehiculo.equipo_id == equipo_id)
        ).scalars()
    ]
    filas = session.execute(
        select(Incidencia, Cliente.nombre)
        .join(Cliente, Cliente.id == Incidencia.cliente_id, isouter=True)
        .where(
            Incidencia.equipo_trabajo_id == equipo_id,
            Incidencia.fecha_programada.is_not(None),
            Incidencia.fecha_programada >= desde,
            Incidencia.fecha_programada < hasta,
        )
        .order_by(Incidencia.fecha_programada)
    ).all()
    return [
        {
            "incidencia_id": i.id,
            "titulo": i.titulo,
            "cliente_id": i.cliente_id,
            "cliente_nombre": cliente,
            "estado": i.estado,
            "modalidad": i.modalidad,
            "desde": i.fecha_programada.isoformat(),
            "hasta": (
                i.fecha_programada
                + timedelta(minutes=i.duracion_minutos or DURACION_POR_DEFECTO)
            ).isoformat(),
            "duracion_minutos": i.duracion_minutos or DURACION_POR_DEFECTO,
            # Derivado de la asignación de la fase A: el equipo sale en lo que
            # tenga asignado. Plural porque nada impide dos.
            "vehiculos": vehiculos,
        }
        for i, cliente in filas
    ]
