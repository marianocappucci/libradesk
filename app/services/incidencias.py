"""Incidencias (tickets de soporte) + `ActividadIncidencia` (log de
actividad por ticket) + `IncidenciaEstadoLog` (auditoria de cambios de
estado — 31 filas reales migradas desde Postgres). `tecnico_id`/
`sector_id` reemplazan a las columnas de texto libre `tecnico_asignado`/
`sector` que tenia la version anterior (Node.js) — la migracion de datos
(Fase 4) resuelve el texto libre contra las tablas `tecnicos`/`sectores`
donde haya coincidencia."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, delete, func,
    select, update,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base

ESTADOS_VALIDOS = ("abierto", "en_progreso", "resuelta", "cerrado")
PRIORIDADES_VALIDAS = ("alta", "media", "baja")
# Cómo se atendió el ticket (pedido 37). `None` es un valor legítimo: los
# tickets viejos no lo saben.
MODALIDADES_VALIDAS = ("on_site", "remoto")

# Etiquetas legibles. Viven acá —en el dominio— y no en el generador de PDF,
# porque son cómo se llama un estado, no cómo se lo dibuja: el día que haya un
# segundo consumidor (un mail, un export) no tiene que copiarlas.
ESTADO_LABELS = {
    "abierto": "Abierta", "en_progreso": "En progreso",
    "resuelta": "Resuelta", "cerrado": "Cerrada",
}
PRIORIDAD_LABELS = {"alta": "Alta", "media": "Media", "baja": "Baja"}
MODALIDAD_LABELS = {"on_site": "On-site", "remoto": "Remoto"}


class Incidencia(Base):
    __tablename__ = "incidencias"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id", ondelete="CASCADE"), nullable=False, index=True)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("equipos.id", ondelete="SET NULL"), index=True)
    # El activo alquilado sobre el que se abre el ticket, cuando el problema es
    # de un equipo NUESTRO puesto en el cliente y no del parque de el.
    #
    # Columna aparte y **sin** CHECK de exclusion mutua con `equipo_id`, a
    # diferencia de `equipos_movimientos` y `equipos_reparaciones`: alla el XOR
    # dice de quien es el historial y ninguna fila puede ser de los dos. Aca un
    # ticket puede tocar legitimamente las dos cosas —"el telefono alquilado no
    # registra en la PC del cliente"— y forzar uno solo obligaria a elegir cual
    # de los dos se pierde.
    activo_id: Mapped[int | None] = mapped_column(
        ForeignKey("activos.id", ondelete="SET NULL"), index=True,
    )
    # Los tres papeles alrededor del ticket (pedido 41, 2026-08-04). Apuntan al
    # MISMO catalogo (`tecnicos`, que es el personal de la empresa): en una
    # empresa chica la misma persona recepciona y ejecuta, y con tablas
    # separadas habria que cargarla dos veces. Ver services/tecnicos.py.
    #
    # `tecnico_id` es quien **ejecuta**, y conserva su nombre porque es la
    # columna que usan los 6 reportes, el informe al cliente y el dashboard
    # desde siempre; renombrarla ahora seria un cambio ancho sin pedido detras.
    tecnico_id: Mapped[int | None] = mapped_column(ForeignKey("tecnicos.id", ondelete="SET NULL"))
    # Quien **toma** el ticket, que puede no ser tecnico.
    recepcionista_id: Mapped[int | None] = mapped_column(
        ForeignKey("tecnicos.id", ondelete="SET NULL"), index=True,
    )
    # Quien habla con el cliente por este trabajo.
    vendedor_id: Mapped[int | None] = mapped_column(
        ForeignKey("tecnicos.id", ondelete="SET NULL"), index=True,
    )
    # `on_site` o `remoto` (pedido 37). Nullable y **sin default**: los 23
    # tickets que ya existen no saben como se atendieron, y ponerles `on_site`
    # seria inventar el dato. En pantalla salen con "—".
    modalidad: Mapped[str | None] = mapped_column(String(20), index=True)
    # La agenda (pedido 42, fase B). Nullable: agendar es opcional — un ticket
    # que entra por telefono y se resuelve en el momento nunca se agenda.
    #
    # `fecha_programada` es CUANDO se va a atender, y no tiene nada que ver con
    # `fecha_creacion` (cuando entro el ticket) ni con `fecha_cierre` (cuando se
    # termino). Sin esta columna la disponibilidad de un equipo solo podia ser
    # "esta o no esta en otro equipo"; con ella, el motor de turnos puede decir
    # si dos trabajos se pisan. Ver services/agenda.py.
    fecha_programada: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    duracion_minutos: Mapped[int | None] = mapped_column(Integer)
    # Que equipo lo hace. El vehiculo NO se guarda aca: sale de lo que ese
    # equipo tenga asignado (fase A), y duplicarlo admitiria que el ticket diga
    # una patente y el equipo otra.
    equipo_trabajo_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipos_trabajo.id", ondelete="SET NULL"), index=True,
    )
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectores.id", ondelete="SET NULL"))
    # Que clase de problema es ("Hardware -> Impresoras"). Apunta siempre a la
    # HOJA del catalogo; el padre se deriva. Nullable y sin `ondelete`: las 23
    # incidencias reales de `compulibra` son previas al catalogo, y el pragma
    # de FKs esta apagado, asi que el desenlace lo hace explicitamente
    # `CategoriaRepository.delete()`. Ver services/categorias.py y migrations.py.
    categoria_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias_incidencia.id"), index=True,
    )
    titulo: Mapped[str] = mapped_column(String(255), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(String(50), nullable=False, default="abierto", index=True)
    prioridad: Mapped[str] = mapped_column(String(20), nullable=False, default="media")
    horas_invertidas: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    notas: Mapped[str | None] = mapped_column(Text)
    resolucion: Mapped[str | None] = mapped_column(Text)
    estado_facturacion: Mapped[str | None] = mapped_column(String(20))
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime)


class ActividadIncidencia(Base):
    __tablename__ = "actividades_incidencia"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incidencia_id: Mapped[int] = mapped_column(ForeignKey("incidencias.id", ondelete="CASCADE"), nullable=False, index=True)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    descripcion: Mapped[str | None] = mapped_column(Text)
    usuario: Mapped[str | None] = mapped_column(String(100))


class IncidenciaEstadoLog(Base):
    __tablename__ = "incidencias_estados_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    incidencia_id: Mapped[int] = mapped_column(ForeignKey("incidencias.id", ondelete="CASCADE"), nullable=False, index=True)
    estado_anterior: Mapped[str | None] = mapped_column(String(50))
    estado_nuevo: Mapped[str] = mapped_column(String(50), nullable=False)
    fecha: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    tecnico: Mapped[str | None] = mapped_column(String(100))


def _to_dict(i: Incidencia) -> dict:
    return {
        "id": i.id,
        "cliente_id": i.cliente_id,
        "equipo_id": i.equipo_id,
        "activo_id": i.activo_id,
        "tecnico_id": i.tecnico_id,
        "recepcionista_id": i.recepcionista_id,
        "vendedor_id": i.vendedor_id,
        "modalidad": i.modalidad,
        "fecha_programada": (
            i.fecha_programada.isoformat() if i.fecha_programada else None
        ),
        "duracion_minutos": i.duracion_minutos,
        "equipo_trabajo_id": i.equipo_trabajo_id,
        "sector_id": i.sector_id,
        "categoria_id": i.categoria_id,
        "titulo": i.titulo,
        "descripcion": i.descripcion,
        "estado": i.estado,
        "prioridad": i.prioridad,
        "horas_invertidas": float(i.horas_invertidas) if i.horas_invertidas is not None else None,
        "notas": i.notas,
        "resolucion": i.resolucion,
        "estado_facturacion": i.estado_facturacion,
        "activo": i.activo,
        "fecha_creacion": i.fecha_creacion.isoformat() if i.fecha_creacion else None,
        "fecha_cierre": i.fecha_cierre.isoformat() if i.fecha_cierre else None,
    }


def _actividad_to_dict(a: ActividadIncidencia) -> dict:
    return {
        "id": a.id,
        "incidencia_id": a.incidencia_id,
        "fecha": a.fecha.isoformat() if a.fecha else None,
        "descripcion": a.descripcion,
        "usuario": a.usuario,
    }


def _estado_log_to_dict(e: IncidenciaEstadoLog) -> dict:
    return {
        "id": e.id,
        "incidencia_id": e.incidencia_id,
        "estado_anterior": e.estado_anterior,
        "estado_nuevo": e.estado_nuevo,
        "fecha": e.fecha.isoformat() if e.fecha else None,
        "tecnico": e.tecnico,
    }


def _validar_agenda(session, incidencia) -> None:
    """Delega en el motor de turnos. Import local por el ciclo: `agenda` importa
    `Incidencia` de acá para armar los turnos existentes."""
    from .agenda import validar_agenda

    validar_agenda(session, incidencia)


def _validar_modalidad(data: dict) -> None:
    """`modalidad` sí se valida, a diferencia de `estado` y `prioridad`.

    Esas dos tienen sus tuplas declaradas arriba y **nadie las usa** — vienen
    así de antes. No se retrofitean acá porque cambiar qué acepta el endpoint de
    incidencias no es lo que pedía el 37 y podría rechazar datos que hoy entran;
    queda anotado como algo a decidir aparte.
    """
    modalidad = data.get("modalidad")
    if modalidad is not None and modalidad not in MODALIDADES_VALIDAS:
        raise ValueError(f"Modalidad inválida: {modalidad}")


class IncidenciaRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, usuario_actor: str | None = None, **data) -> dict:
        _validar_modalidad(data)
        with self.session_factory() as session:
            i = Incidencia(**data)
            # Antes de la primera escritura: si el horario se pisa, el ticket no
            # se crea. Mismo criterio que el service de los activos — lo barato
            # es no empezar.
            _validar_agenda(session, i)
            session.add(i)
            session.flush()
            session.add(IncidenciaEstadoLog(
                incidencia_id=i.id, estado_anterior=None, estado_nuevo=i.estado,
                tecnico=usuario_actor,
            ))
            session.commit()
            session.refresh(i)
            return _to_dict(i)

    def list(self, cliente_id: int | None = None, estado: str | None = None,
             equipo_id: int | None = None, categoria_id: int | None = None,
             activo_id: int | None = None) -> list[dict]:
        """`equipo_id` es lo que hace contestable "¿cuántas veces falló
        este equipo?": el dato estaba desde la migracion, pero no habia
        forma de pedirlo — el listado solo filtraba por cliente y estado,
        asi que la unica manera era abrir incidencia por incidencia.

        `activo_id` contesta lo mismo para un equipo **nuestro** alquilado, que
        es la pregunta que decide si conviene seguir alquilandolo o darlo de
        baja."""
        with self.session_factory() as session:
            stmt = select(Incidencia).order_by(Incidencia.fecha_creacion.desc())
            if cliente_id is not None:
                stmt = stmt.where(Incidencia.cliente_id == cliente_id)
            if estado is not None:
                stmt = stmt.where(Incidencia.estado == estado)
            if equipo_id is not None:
                stmt = stmt.where(Incidencia.equipo_id == equipo_id)
            if activo_id is not None:
                stmt = stmt.where(Incidencia.activo_id == activo_id)
            if categoria_id is not None:
                stmt = stmt.where(Incidencia.categoria_id == categoria_id)
            return [_to_dict(i) for i in session.execute(stmt).scalars()]

    def get(self, incidencia_id: int) -> dict | None:
        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            return _to_dict(i) if i else None

    def datos_para_pdf(self, incidencia_id: int) -> dict | None:
        """El ticket con todo lo suyo ya resuelto a texto, para imprimirlo.

        Devuelve **datos, no PDF**: mismo corte que `informes.py` contra
        `informe_pdf.py`, que es lo que permite testear el contenido sin abrir
        un binario. Las etiquetas se resuelven acá y no en el generador porque
        son del dominio (`on_site` → "On-site"), no de la maqueta.
        """
        from .categorias import CategoriaIncidencia
        from .clientes import Cliente
        from .equipos import Equipo
        from .sectores import Sector
        from .tecnicos import Tecnico

        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            if i is None:
                return None

            cliente = session.get(Cliente, i.cliente_id)
            equipo = session.get(Equipo, i.equipo_id) if i.equipo_id else None
            sector = session.get(Sector, i.sector_id) if i.sector_id else None
            categoria = (
                session.get(CategoriaIncidencia, i.categoria_id) if i.categoria_id else None
            )

            def persona(pid: int | None) -> str | None:
                p = session.get(Tecnico, pid) if pid else None
                return p.nombre if p is not None else None

            actividad = [
                {
                    "fecha": a.fecha.strftime("%d/%m/%Y %H:%M") if a.fecha else "—",
                    "descripcion": a.descripcion,
                }
                for a in session.execute(
                    select(ActividadIncidencia)
                    .where(ActividadIncidencia.incidencia_id == incidencia_id)
                    .order_by(ActividadIncidencia.fecha, ActividadIncidencia.id)
                ).scalars()
            ]

            return {
                "id": i.id,
                "cliente": {
                    "nombre": cliente.nombre if cliente else "—",
                    "cuit": getattr(cliente, "cuit", None),
                    "domicilio": getattr(cliente, "domicilio", None),
                    "email": getattr(cliente, "email", None),
                },
                "estado_label": ESTADO_LABELS.get(i.estado, i.estado),
                "prioridad_label": PRIORIDAD_LABELS.get(i.prioridad, i.prioridad),
                "modalidad_label": MODALIDAD_LABELS.get(i.modalidad or "", "—"),
                "fecha_creacion": (
                    i.fecha_creacion.strftime("%d/%m/%Y %H:%M") if i.fecha_creacion else "—"
                ),
                "fecha_cierre": (
                    i.fecha_cierre.strftime("%d/%m/%Y %H:%M") if i.fecha_cierre else "—"
                ),
                "categoria": categoria.nombre if categoria is not None else None,
                "horas": str(i.horas_invertidas) if i.horas_invertidas is not None else None,
                "equipo": (
                    " ".join(x for x in (equipo.tipo, equipo.marca, equipo.modelo) if x)
                    if equipo is not None else None
                ),
                "sector": sector.nombre if sector is not None else None,
                "recepcionista": persona(i.recepcionista_id),
                "tecnico": persona(i.tecnico_id),
                "vendedor": persona(i.vendedor_id),
                "titulo": i.titulo,
                "descripcion": i.descripcion,
                "resolucion": i.resolucion,
                "notas": i.notas,
                "actividad": actividad,
            }

    def update(self, incidencia_id: int, usuario_actor: str | None = None, **data) -> dict:
        """Si `data` incluye un `estado` distinto al actual, registra el
        cambio en `IncidenciaEstadoLog` y setea `fecha_cierre` al pasar a
        `cerrado`/`resuelta` (limpia `fecha_cierre` si vuelve a abrirse)."""
        _validar_modalidad(data)
        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            if i is None:
                raise KeyError(incidencia_id)
            estado_anterior = i.estado
            for key, value in data.items():
                setattr(i, key, value)
            # Después de aplicar los cambios y **antes** del commit: se valida
            # el horario que va a quedar, no el que había. La sesión no se
            # commiteó todavía, así que si esto se planta no queda nada escrito.
            _validar_agenda(session, i)
            if "estado" in data and data["estado"] != estado_anterior:
                session.add(IncidenciaEstadoLog(
                    incidencia_id=i.id, estado_anterior=estado_anterior,
                    estado_nuevo=i.estado, tecnico=usuario_actor,
                ))
                if i.estado in ("resuelta", "cerrado"):
                    i.fecha_cierre = datetime.now(timezone.utc)
                else:
                    i.fecha_cierre = None
            session.commit()
            session.refresh(i)
            return _to_dict(i)

    def delete(self, incidencia_id: int) -> None:
        """Borra el ticket con su actividad y su auditoria de estado, y
        **desvincula** los movimientos de equipo que causo.

        Los `ondelete=CASCADE` declarados en los modelos **no alcanzan**:
        el engine de SQLAlchemy de LibraDesk no activa
        `PRAGMA foreign_keys` (verificado con `PRAGMA foreign_keys` sobre
        una conexion real, da 0), asi que hasta ahora un DELETE dejaba
        `actividades_incidencia` e `incidencias_estados_log` huerfanas —
        justo lo contrario de lo que dice el dialogo de confirmacion de la
        UI. Se hace explicito aca en vez de prender el pragma, que es un
        cambio de comportamiento global sobre una base de produccion y
        merece decidirse aparte.

        Los movimientos NO se borran: el equipo salio de Admision de
        verdad, y ese hecho fisico sobrevive al ticket. Solo pierden el
        link. **Lo mismo vale para las reparaciones**: el equipo estuvo en
        service, con su remito y su RMA, aunque el ticket que lo origino ya
        no exista."""
        with self.session_factory() as session:
            i = session.get(Incidencia, incidencia_id)
            if i is None:
                raise KeyError(incidencia_id)

            # Import local: `equipos` no importa a `incidencias`, y de este
            # modo se mantiene asi (sin ciclo) aunque la dependencia exista
            # en esta direccion.
            from .contratos import ContratoEquipo
            from .equipos import EquipoMovimiento
            from .ingresos import IngresoReparacion
            from .reparaciones import Reparacion

            session.execute(
                update(EquipoMovimiento)
                .where(EquipoMovimiento.incidencia_id == incidencia_id)
                .values(incidencia_id=None)
            )
            # Mismo criterio para las lineas de contrato: el equipo se
            # reemplazo de verdad ese dia, y esa historia le sobrevive al
            # ticket. Sin esto la linea quedaria apuntando a un ticket que ya
            # no existe, que es peor que no apuntar a nada.
            session.execute(
                update(ContratoEquipo)
                .where(ContratoEquipo.incidencia_id == incidencia_id)
                .values(incidencia_id=None)
            )
            session.execute(
                update(Reparacion)
                .where(Reparacion.incidencia_id == incidencia_id)
                .values(incidencia_id=None)
            )
            # Y los ingresos a reparación (pedido 43). Acá pesa más que en el
            # resto: el comprobante que quedó en manos del cliente nombra ese
            # número, así que la fila **no se puede borrar** con el ticket. Sólo
            # pierde el link.
            session.execute(
                update(IngresoReparacion)
                .where(IngresoReparacion.incidencia_id == incidencia_id)
                .values(incidencia_id=None)
            )
            session.execute(
                delete(ActividadIncidencia)
                .where(ActividadIncidencia.incidencia_id == incidencia_id)
            )
            session.execute(
                delete(IncidenciaEstadoLog)
                .where(IncidenciaEstadoLog.incidencia_id == incidencia_id)
            )
            session.delete(i)
            session.commit()

    def list_actividades(self, incidencia_id: int) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(ActividadIncidencia)
                .where(ActividadIncidencia.incidencia_id == incidencia_id)
                .order_by(ActividadIncidencia.fecha.desc(), ActividadIncidencia.id.desc())
            )
            return [_actividad_to_dict(a) for a in session.execute(stmt).scalars()]

    def add_actividad(self, incidencia_id: int, descripcion: str, usuario: str | None) -> dict:
        with self.session_factory() as session:
            a = ActividadIncidencia(incidencia_id=incidencia_id, descripcion=descripcion, usuario=usuario)
            session.add(a)
            session.commit()
            session.refresh(a)
            return _actividad_to_dict(a)

    def list_estado_log(self, incidencia_id: int) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(IncidenciaEstadoLog)
                .where(IncidenciaEstadoLog.incidencia_id == incidencia_id)
                .order_by(IncidenciaEstadoLog.fecha.desc(), IncidenciaEstadoLog.id.desc())
            )
            return [_estado_log_to_dict(e) for e in session.execute(stmt).scalars()]
