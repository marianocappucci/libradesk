"""
Módulos habilitados por plan comercial (ver `plans.py` en la raíz del repo —
fuente de verdad del mapeo plan→módulos, compartida con
`libracore.provisioning`).

El core de tickets (clientes, equipos, incidencias, técnicos, sectores) no es
gateable; lo que se vende por nivel es dashboard/reportes y
remitos/presupuestos.

Por defecto —instancia recién actualizada, sin plan asignado todavía— **todo
queda habilitado**. Mismo criterio que el resto de la familia: el seed inicial
no bloquea nada, y recién `aplicar_plan_en_db()` (que llama el provisioning al
dar de alta un cliente con un plan elegido) achica el acceso. Eso es lo que
hace que agregar módulos a LibraDesk no le cambie nada a las dos instancias
que ya existen.
"""
from sqlalchemy import select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from plans import TODOS_LOS_MODULOS

from ..database import Base


class ModuleRow(Base):
    __tablename__ = "modulos"

    modulo: Mapped[str] = mapped_column(primary_key=True)
    habilitado: Mapped[bool] = mapped_column(default=True)
    plan: Mapped[str] = mapped_column(default="premium")


class ModuleRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self.session_factory = session_factory

    def ensure_seeded(self) -> None:
        """Inserta los módulos que falten con `habilitado=True`, sin pisar el
        estado de los que ya existen. Idempotente ante reinicios."""
        with self.session_factory.begin() as session:
            existentes = {row.modulo for row in session.scalars(select(ModuleRow)).all()}
            for modulo in sorted(TODOS_LOS_MODULOS - existentes):
                session.add(ModuleRow(modulo=modulo, habilitado=True, plan="premium"))

    def is_enabled(self, modulo: str) -> bool:
        """Los módulos que no son gateables (no están en `TODOS_LOS_MODULOS`,
        ej. incidencias) están siempre habilitados, aunque nunca se haya
        sembrado una fila — no tiene sentido gatear el core."""
        if modulo not in TODOS_LOS_MODULOS:
            return True
        with self.session_factory() as session:
            row = session.get(ModuleRow, modulo)
            return bool(row.habilitado) if row is not None else True

    def get_all(self) -> dict[str, bool]:
        with self.session_factory() as session:
            rows = session.scalars(select(ModuleRow)).all()
            return {row.modulo: bool(row.habilitado) for row in rows}

    def set_enabled(self, modulo: str, habilitado: bool) -> None:
        """Prende o apaga un módulo puntual, sin pasar por un plan completo.
        La vía real para asignar un plan es `aplicar_plan_en_db()`."""
        with self.session_factory.begin() as session:
            row = session.get(ModuleRow, modulo)
            if row is None:
                session.add(ModuleRow(modulo=modulo, habilitado=habilitado, plan="premium"))
            else:
                row.habilitado = habilitado
