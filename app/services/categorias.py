"""Categorias de incidencia — catalogo de dos niveles y **global**, no por
cliente (decidido con el usuario el 2026-08-02).

El pedido original era literal: *"Tipo: Hardware -> Impresoras"*. Hasta ahora
esa informacion viajaba dentro del titulo del ticket, asi que "cuantas fallas
de impresoras hubo este mes" no se podia contestar sin leer los 22 titulos.

**Dos niveles con auto-referencia** (`parent_id`) en vez de dos tablas: una
sola tabla, un solo repositorio, y el reporte agrupa por el padre haciendo un
join contra si misma. La incidencia apunta **a la hoja**; el padre se deriva.

**Global y no por cliente**, a diferencia de `sectores`: "Impresoras" es
"Impresoras" sea el cliente que sea, y asi los reportes por categoria comparan
entre clientes en vez de contra un catalogo distinto cada uno.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
    select,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


class CategoriaIncidencia(Base):
    __tablename__ = "categorias_incidencia"
    # Unico dentro del mismo padre: puede haber "Otros" bajo Hardware y "Otros"
    # bajo Software, que es lo natural, pero no dos "Impresoras" hermanas.
    __table_args__ = (UniqueConstraint("parent_id", "nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # NULL = es una categoria raiz. No lleva `ondelete`: el pragma
    # `foreign_keys` esta apagado en las conexiones de SQLAlchemy (medido),
    # asi que seria decorativo — el borrado lo controla el repositorio, que
    # directamente se niega si algo cuelga.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("categorias_incidencia.id"), index=True,
    )
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(c: CategoriaIncidencia, padre: CategoriaIncidencia | None = None) -> dict:
    return {
        "id": c.id,
        "parent_id": c.parent_id,
        "nombre": c.nombre,
        # El nombre del padre viaja resuelto para que la UI no tenga que
        # rearmar el arbol solo para escribir "Hardware · Impresoras".
        "parent_nombre": padre.nombre if padre else None,
        "ruta": f"{padre.nombre} · {c.nombre}" if padre else c.nombre,
    }


class CategoriaRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def _padres(self, session) -> dict[int, CategoriaIncidencia]:
        return {c.id: c for c in session.execute(
            select(CategoriaIncidencia).where(CategoriaIncidencia.parent_id.is_(None))
        ).scalars()}

    def create(self, nombre: str, parent_id: int | None = None) -> dict:
        with self.session_factory() as session:
            if parent_id is not None:
                padre = session.get(CategoriaIncidencia, parent_id)
                if padre is None:
                    raise KeyError(parent_id)
                # Dos niveles y punto: sin esto, colgar una hija de una hija
                # arma un arbol arbitrario que ni la UI ni los reportes saben
                # recorrer.
                if padre.parent_id is not None:
                    raise ValueError("nivel")
            c = CategoriaIncidencia(nombre=nombre.strip(), parent_id=parent_id)
            session.add(c)
            session.commit()
            session.refresh(c)
            return _to_dict(c, session.get(CategoriaIncidencia, parent_id) if parent_id else None)

    def list(self) -> list[dict]:
        """Plano pero **ordenado como arbol**: cada raiz seguida de sus hijas,
        que es como lo quiere tanto el `<select>` como la pantalla del ABM."""
        with self.session_factory() as session:
            todas = list(session.execute(
                select(CategoriaIncidencia).order_by(CategoriaIncidencia.nombre)
            ).scalars())
            por_padre: dict[int | None, list[CategoriaIncidencia]] = {}
            for c in todas:
                por_padre.setdefault(c.parent_id, []).append(c)

            salida: list[dict] = []
            for raiz in por_padre.get(None, []):
                salida.append(_to_dict(raiz))
                for hija in por_padre.get(raiz.id, []):
                    salida.append(_to_dict(hija, raiz))
            return salida

    def get(self, categoria_id: int) -> dict | None:
        with self.session_factory() as session:
            c = session.get(CategoriaIncidencia, categoria_id)
            if c is None:
                return None
            padre = session.get(CategoriaIncidencia, c.parent_id) if c.parent_id else None
            return _to_dict(c, padre)

    def update(self, categoria_id: int, nombre: str) -> dict:
        """Solo el nombre. Mover una categoria de padre cambiaria de golpe la
        clasificacion de todos sus tickets historicos, asi que no se ofrece."""
        with self.session_factory() as session:
            c = session.get(CategoriaIncidencia, categoria_id)
            if c is None:
                raise KeyError(categoria_id)
            c.nombre = nombre.strip()
            session.commit()
            session.refresh(c)
            padre = session.get(CategoriaIncidencia, c.parent_id) if c.parent_id else None
            return _to_dict(c, padre)

    def dependencias(self, categoria_id: int) -> dict[str, int]:
        from .incidencias import Incidencia

        with self.session_factory() as session:
            return {
                "subcategorías": session.execute(
                    select(func.count()).select_from(CategoriaIncidencia)
                    .where(CategoriaIncidencia.parent_id == categoria_id)
                ).scalar_one(),
                "incidencias": session.execute(
                    select(func.count()).select_from(Incidencia)
                    .where(Incidencia.categoria_id == categoria_id)
                ).scalar_one(),
            }

    def delete(self, categoria_id: int, *, forzar: bool = False) -> None:
        """Se niega si tiene subcategorias. Con incidencias asignadas, `forzar`
        las **desclasifica** (`categoria_id` a NULL) en vez de borrarlas.

        El `ondelete` del modelo no corre —el pragma esta apagado—, asi que sin
        este `UPDATE` explicito las incidencias quedarian apuntando a un id
        inexistente. Es el mismo hallazgo que ya pago este producto con
        `equipos_movimientos` y con `sectores`.
        """
        from .incidencias import Incidencia

        colgando = self.dependencias(categoria_id)
        if colgando["subcategorías"]:
            raise ValueError(colgando)
        if colgando["incidencias"] and not forzar:
            raise ValueError(colgando)

        with self.session_factory() as session:
            c = session.get(CategoriaIncidencia, categoria_id)
            if c is None:
                raise KeyError(categoria_id)
            session.execute(
                update(Incidencia)
                .where(Incidencia.categoria_id == categoria_id)
                .values(categoria_id=None)
            )
            session.delete(c)
            session.commit()
