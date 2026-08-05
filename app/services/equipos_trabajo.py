"""Equipos de trabajo y flota de vehiculos (pedido 42, fase A).

**El pedido.** *"Armar equipos de trabajo, donde haya un responsable del equipo
y sus tecnicos que responden a el. Y una flota de vehiculos, y que cuando un
equipo tiene asignado un trabajo ya sabe en que vehiculo sale de acuerdo a la
disponibilidad."*

**Que entra en esta fase y que no.** Entra el equipo con su responsable y sus
integrantes, la flota, y la asignacion **equipo ↔ vehiculo**: el equipo Norte
sale en la Kangoo, y esa Kangoo no puede estar asignada a otro equipo al mismo
tiempo. Eso contesta *"ya sabe en que vehiculo sale"* para el caso normal.

**No** entra la agenda: hoy LibraDesk no sabe *cuando* se va a atender una
incidencia —solo cuando se creo y cuando se cerro—, asi que "disponible el
martes a las 10" no se puede contestar. Esa es la fase B, con
[LibraGenda](https://github.com/marianocappucci/libragenda), que es el motor de
turnos de la familia y cuya propia doc dice que un recurso puede ser "una
maquina o cualquier otra cosa reservable". La deploy key de CI ya quedo puesta.

**El responsable sale del catalogo de personal**, con una bandera mas
(`es_responsable`), y no de una tabla nueva de coordinadores. Es lo mismo que se
decidio en el pedido 41 y por el mismo motivo: en una empresa chica el
responsable de un equipo tambien es tecnico, y con tablas separadas habria que
cargarlo dos veces. El usuario eligio llamarlo **responsable**.

> ⚠️ La palabra ya existe en `contratos.responsable`, que es el responsable
> **comercial** del contrato y es texto libre. Son cosas distintas en tablas
> distintas y con tipos distintos (aca es una FK al personal); se deja anotado
> para que nadie las cruce mas adelante.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint,
    func, select,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class EquipoTrabajo(Base):
    """Un equipo que sale a la calle: un responsable y sus tecnicos."""

    __tablename__ = "equipos_trabajo"
    __table_args__ = (UniqueConstraint("nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    # Quien manda. Nullable porque un equipo puede quedar sin responsable si esa
    # persona se borra, y perder el equipo entero por eso seria peor.
    responsable_id: Mapped[int | None] = mapped_column(
        ForeignKey("tecnicos.id", ondelete="SET NULL"), index=True,
    )
    observaciones: Mapped[str | None] = mapped_column(Text)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class EquipoTrabajoIntegrante(Base):
    """Quien responde a ese responsable.

    Tabla de union y no una columna `equipo_id` en `tecnicos`, aunque hoy una
    persona este en un solo equipo: en una empresa chica el mismo tecnico
    refuerza dos cuadrillas segun el dia, y una columna obligaria a elegir. La
    unicidad se pone sobre el **par**, no sobre la persona.
    """

    __tablename__ = "equipos_trabajo_integrantes"
    __table_args__ = (UniqueConstraint("equipo_id", "tecnico_id"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    equipo_id: Mapped[int] = mapped_column(
        ForeignKey("equipos_trabajo.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    tecnico_id: Mapped[int] = mapped_column(
        ForeignKey("tecnicos.id", ondelete="CASCADE"), nullable=False, index=True,
    )


class Vehiculo(Base):
    """Un vehiculo de la flota.

    **`equipo_id` es la asignacion**, y es lo que contesta "en que vehiculo
    sale el equipo". Nullable: un vehiculo puede estar sin asignar (en el
    playon, o en el taller). Y la disponibilidad de esta fase es exactamente
    esto: **un vehiculo no puede estar asignado a dos equipos**, garantizado
    porque la asignacion vive en una sola columna del vehiculo y no en una
    tabla de asignaciones que admitiria dos filas.
    """

    __tablename__ = "vehiculos"
    __table_args__ = (UniqueConstraint("patente"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # La patente identifica al vehiculo en la calle y en el taller: unica.
    patente: Mapped[str] = mapped_column(String(20), nullable=False)
    marca: Mapped[str | None] = mapped_column(String(100))
    modelo: Mapped[str | None] = mapped_column(String(100))
    anio: Mapped[int | None] = mapped_column(Integer)
    # `disponible` | `asignado` | `en_taller` | `baja`. Ver ESTADOS_VEHICULO:
    # `asignado` NO se setea a mano, se deriva de tener equipo.
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="disponible")
    equipo_id: Mapped[int | None] = mapped_column(
        ForeignKey("equipos_trabajo.id", ondelete="SET NULL"), index=True,
    )
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# `asignado` se guarda pero **no se setea a mano**: lo escribe `asignar()` /
# `desasignar()`, igual que `colocado` en los activos. Mismo criterio y mismo
# motivo: si se pudiera por los dos lados, un vehiculo podria decir que esta
# asignado sin ningun equipo que lo tenga.
ESTADOS_VEHICULO = ("disponible", "asignado", "en_taller", "baja")
_ESTADOS_MANUALES = tuple(e for e in ESTADOS_VEHICULO if e != "asignado")
# Con el vehiculo en uno de estos no se lo puede asignar: no esta en condiciones
# de salir.
ESTADOS_NO_ASIGNABLES = ("asignado", "en_taller", "baja")


def _equipo_to_dict(e: EquipoTrabajo, *, responsable: str | None = None,
                    integrantes: list[dict] | None = None,
                    vehiculos: list[dict] | None = None) -> dict:
    return {
        "id": e.id,
        "nombre": e.nombre,
        "responsable_id": e.responsable_id,
        "responsable_nombre": responsable,
        "observaciones": e.observaciones,
        "activo": bool(e.activo),
        "created_at": e.created_at.isoformat() if e.created_at else None,
        "integrantes": integrantes if integrantes is not None else [],
        # Plural aunque hoy lo normal sea uno: nada impide que una cuadrilla
        # salga con dos vehiculos, y el modelo ya lo admite.
        "vehiculos": vehiculos if vehiculos is not None else [],
    }


def _vehiculo_to_dict(v: Vehiculo, *, equipo_nombre: str | None = None) -> dict:
    return {
        "id": v.id,
        "patente": v.patente,
        "marca": v.marca,
        "modelo": v.modelo,
        "anio": v.anio,
        "estado": v.estado,
        "equipo_id": v.equipo_id,
        "equipo_nombre": equipo_nombre,
        "descripcion": " ".join(x for x in (v.marca, v.modelo) if x) or v.patente,
        "observaciones": v.observaciones,
        "created_at": v.created_at.isoformat() if v.created_at else None,
    }


class EquipoTrabajoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    # ── Equipos ─────────────────────────────────────────────────────────

    def _resolver(self, session, e: EquipoTrabajo) -> dict:
        from .tecnicos import Tecnico

        responsable = session.get(Tecnico, e.responsable_id) if e.responsable_id else None
        filas = session.execute(
            select(Tecnico)
            .join(EquipoTrabajoIntegrante, EquipoTrabajoIntegrante.tecnico_id == Tecnico.id)
            .where(EquipoTrabajoIntegrante.equipo_id == e.id)
            .order_by(Tecnico.nombre)
        ).scalars()
        vehiculos = session.execute(
            select(Vehiculo).where(Vehiculo.equipo_id == e.id).order_by(Vehiculo.patente)
        ).scalars()
        return _equipo_to_dict(
            e,
            responsable=responsable.nombre if responsable is not None else None,
            integrantes=[{"id": t.id, "nombre": t.nombre} for t in filas],
            vehiculos=[_vehiculo_to_dict(v) for v in vehiculos],
        )

    def create(self, nombre: str, *, responsable_id: int | None = None,
               observaciones: str | None = None,
               integrantes: list[int] | None = None) -> dict:
        with self.session_factory() as session:
            self._validar_personas(session, responsable_id, integrantes or [])
            e = EquipoTrabajo(
                nombre=nombre.strip(), responsable_id=responsable_id,
                observaciones=(observaciones or "").strip() or None,
            )
            session.add(e)
            session.flush()
            for tid in integrantes or []:
                session.add(EquipoTrabajoIntegrante(equipo_id=e.id, tecnico_id=tid))
            session.commit()
            session.refresh(e)
            return self._resolver(session, e)

    def _validar_personas(self, session, responsable_id: int | None,
                          integrantes: list[int]) -> None:
        """El responsable tiene que existir y tener el rol; los integrantes,
        existir.

        El rol se exige **al responsable y no a los integrantes**: quien manda
        el equipo es una decision que se marca en el catalogo de personal, y sin
        el chequeo cualquiera aparecería en ese selector. Un integrante, en
        cambio, puede ser cualquiera del personal.
        """
        from .tecnicos import Tecnico

        if responsable_id is not None:
            r = session.get(Tecnico, responsable_id)
            if r is None:
                raise KeyError(("responsable", responsable_id))
            if not r.es_responsable:
                raise ValueError(
                    f"{r.nombre} no tiene el rol de responsable de equipo."
                )
        for tid in integrantes:
            if session.get(Tecnico, tid) is None:
                raise KeyError(("integrante", tid))

    def list(self, *, solo_activos: bool = False) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(EquipoTrabajo).order_by(EquipoTrabajo.nombre)
            if solo_activos:
                stmt = stmt.where(EquipoTrabajo.activo.is_(True))
            return [self._resolver(session, e) for e in session.execute(stmt).scalars()]

    def get(self, equipo_id: int) -> dict | None:
        with self.session_factory() as session:
            e = session.get(EquipoTrabajo, equipo_id)
            return self._resolver(session, e) if e is not None else None

    def update(self, equipo_id: int, **data) -> dict:
        integrantes = data.pop("integrantes", None)
        with self.session_factory() as session:
            e = session.get(EquipoTrabajo, equipo_id)
            if e is None:
                raise KeyError(equipo_id)
            self._validar_personas(
                session,
                data.get("responsable_id", e.responsable_id),
                integrantes if integrantes is not None else [],
            )
            for campo, valor in data.items():
                setattr(e, campo, valor.strip() if campo == "nombre" else valor)

            if integrantes is not None:
                # Se reemplaza el juego entero en vez de diffear: la pantalla
                # manda la lista completa, y un diff parcial deja integrantes
                # fantasma cuando dos personas se sacan a la vez.
                session.execute(
                    EquipoTrabajoIntegrante.__table__.delete()
                    .where(EquipoTrabajoIntegrante.equipo_id == equipo_id)
                )
                for tid in integrantes:
                    session.add(EquipoTrabajoIntegrante(equipo_id=equipo_id, tecnico_id=tid))
            session.commit()
            session.refresh(e)
            return self._resolver(session, e)

    def delete(self, equipo_id: int) -> None:
        """Borra el equipo, sus integrantes y **libera sus vehiculos**.

        Los `ondelete` declarados no corren nunca —el pragma `foreign_keys`
        esta apagado en este producto—, asi que se hace explicito. Sin esto un
        vehiculo quedaria `asignado` a un equipo que ya no existe, que es
        exactamente el estado imposible que `asignar()` viene a evitar.
        """
        with self.session_factory() as session:
            e = session.get(EquipoTrabajo, equipo_id)
            if e is None:
                raise KeyError(equipo_id)
            for v in session.execute(
                select(Vehiculo).where(Vehiculo.equipo_id == equipo_id)
            ).scalars():
                v.equipo_id = None
                v.estado = "disponible"
            session.execute(
                EquipoTrabajoIntegrante.__table__.delete()
                .where(EquipoTrabajoIntegrante.equipo_id == equipo_id)
            )
            session.delete(e)
            session.commit()

    # ── Vehiculos ───────────────────────────────────────────────────────

    def _resolver_vehiculo(self, session, v: Vehiculo) -> dict:
        e = session.get(EquipoTrabajo, v.equipo_id) if v.equipo_id else None
        return _vehiculo_to_dict(v, equipo_nombre=e.nombre if e is not None else None)

    def create_vehiculo(self, patente: str, **data) -> dict:
        estado = data.pop("estado", None) or "disponible"
        if estado not in _ESTADOS_MANUALES:
            raise ValueError(
                f"El estado {estado!r} no se setea a mano: lo escribe la asignación."
            )
        with self.session_factory() as session:
            patente = patente.strip().upper()
            if session.execute(
                select(Vehiculo.id).where(Vehiculo.patente == patente)
            ).first() is not None:
                raise ValueError(f"Ya hay un vehículo con la patente {patente}.")
            v = Vehiculo(patente=patente, estado=estado, **data)
            session.add(v)
            session.commit()
            session.refresh(v)
            return self._resolver_vehiculo(session, v)

    def list_vehiculos(self, *, estado: str | None = None,
                       equipo_id: int | None = None,
                       disponibles: bool | None = None) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Vehiculo).order_by(Vehiculo.patente)
            if estado is not None:
                stmt = stmt.where(Vehiculo.estado == estado)
            if equipo_id is not None:
                stmt = stmt.where(Vehiculo.equipo_id == equipo_id)
            if disponibles is True:
                stmt = stmt.where(Vehiculo.estado == "disponible")
            return [self._resolver_vehiculo(session, v) for v in session.execute(stmt).scalars()]

    def get_vehiculo(self, vehiculo_id: int) -> dict | None:
        with self.session_factory() as session:
            v = session.get(Vehiculo, vehiculo_id)
            return self._resolver_vehiculo(session, v) if v is not None else None

    def update_vehiculo(self, vehiculo_id: int, **data) -> dict:
        if "equipo_id" in data:
            raise ValueError(
                "El equipo no se edita por acá: usá asignar o desasignar."
            )
        if "estado" in data and data["estado"] not in _ESTADOS_MANUALES:
            raise ValueError(
                f"El estado {data['estado']!r} no se setea a mano: lo escribe la asignación."
            )
        with self.session_factory() as session:
            v = session.get(Vehiculo, vehiculo_id)
            if v is None:
                raise KeyError(vehiculo_id)
            if "estado" in data and v.equipo_id is not None:
                e = session.get(EquipoTrabajo, v.equipo_id)
                raise ValueError(
                    f"El vehículo está asignado a {e.nombre if e else v.equipo_id}. "
                    "Desasignalo antes de cambiarle el estado."
                )
            if "patente" in data:
                data["patente"] = data["patente"].strip().upper()
                if session.execute(
                    select(Vehiculo.id).where(
                        Vehiculo.patente == data["patente"], Vehiculo.id != vehiculo_id,
                    )
                ).first() is not None:
                    raise ValueError(f"Ya hay un vehículo con la patente {data['patente']}.")
            for campo, valor in data.items():
                setattr(v, campo, valor)
            session.commit()
            session.refresh(v)
            return self._resolver_vehiculo(session, v)

    def delete_vehiculo(self, vehiculo_id: int) -> None:
        with self.session_factory() as session:
            v = session.get(Vehiculo, vehiculo_id)
            if v is None:
                raise KeyError(vehiculo_id)
            if v.equipo_id is not None:
                e = session.get(EquipoTrabajo, v.equipo_id)
                raise ValueError(
                    f"El vehículo está asignado a {e.nombre if e else v.equipo_id}: "
                    "desasignalo antes de borrarlo."
                )
            session.delete(v)
            session.commit()

    # ── La asignación, que es lo que contesta "en qué vehículo sale" ────

    def asignar(self, vehiculo_id: int, equipo_id: int) -> dict:
        """Le da un vehículo a un equipo.

        **La disponibilidad de esta fase es esto**: un vehículo no puede estar
        en dos equipos porque la asignación vive en una sola columna suya. Una
        tabla de asignaciones admitiría dos filas y habría que validarlo; así,
        el modelo no puede representar el estado malo.
        """
        with self.session_factory() as session:
            v = session.get(Vehiculo, vehiculo_id)
            if v is None:
                raise KeyError(("vehiculo", vehiculo_id))
            e = session.get(EquipoTrabajo, equipo_id)
            if e is None:
                raise KeyError(("equipo", equipo_id))
            if v.estado in ESTADOS_NO_ASIGNABLES:
                if v.estado == "asignado":
                    actual = session.get(EquipoTrabajo, v.equipo_id)
                    raise ValueError(
                        f"El vehículo ya está asignado a "
                        f"{actual.nombre if actual else v.equipo_id}."
                    )
                raise ValueError(f"El vehículo está {v.estado!r} y no puede salir.")
            if not e.activo:
                raise ValueError(f"El equipo {e.nombre} está inactivo.")
            v.equipo_id = equipo_id
            v.estado = "asignado"
            session.commit()
            session.refresh(v)
            return self._resolver_vehiculo(session, v)

    def desasignar(self, vehiculo_id: int, *, estado: str = "disponible") -> dict:
        """Lo saca del equipo. Vuelve a `disponible` salvo que se diga otra
        cosa —un vehículo que sale del equipo porque se rompió va a
        `en_taller`."""
        if estado not in _ESTADOS_MANUALES:
            raise ValueError(f"Estado inválido para el vehículo liberado: {estado}")
        with self.session_factory() as session:
            v = session.get(Vehiculo, vehiculo_id)
            if v is None:
                raise KeyError(("vehiculo", vehiculo_id))
            if v.equipo_id is None:
                raise ValueError("El vehículo no está asignado a ningún equipo.")
            v.equipo_id = None
            v.estado = estado
            session.commit()
            session.refresh(v)
            return self._resolver_vehiculo(session, v)
