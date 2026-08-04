"""El **personal** de la empresa: quien recepciona, quien ejecuta y quien vende.

Historicamente esta tabla era solo "tecnicos" — el staff asignable a una
incidencia. Desde el 2026-08-04 (pedido 41 del usuario) el mismo registro sirve
para los tres papeles que aparecen alrededor de un ticket: el **recepcionista**
que lo toma, el **tecnico** que lo ejecuta y el **vendedor** que habla con el
cliente.

**Un solo catalogo y no tres tablas.** Recepcionista, tecnico y vendedor son la
misma clase de cosa —una persona que trabaja acá—, y en una empresa chica la
misma persona hace dos de las tres. Con tablas separadas, cargarla dos veces
seria obligatorio y ninguna consulta podria decir "todo lo que hizo Fulano".
Es el mismo criterio con el que el modulo de alquileres se llamo `contratos` y
no `alquileres`.

**Los roles son banderas, no un campo `rol`.** Una persona puede ser tecnico
**y** vendedor a la vez, que es el caso normal en una empresa de pocas personas;
un unico `rol` obligaria a duplicar la fila y a partir su historial en dos. Con
tres booleanos la combinacion es directa y las consultas ("quienes pueden
ejecutar") son un `WHERE es_tecnico`.

> ⚠️ **La tabla sigue llamandose `tecnicos`.** Se evaluo renombrarla a
> `personal` y se descarto **por ahora**, medido: el nombre aparece en 28
> archivos —incluidos los 6 reportes XLSX y el informe que ve el cliente— y la
> ruta `/api/tecnicos` es contrato publico que consume tambien el backoffice de
> la suite. Renombrar es mecanico pero ancho, y no era lo que el pedido pedia.
> En la UI el modulo se llama **Personal**; acá el nombre es historico. Si el
> pedido 42 (equipos de trabajo y coordinadores) obliga a tocar esto de nuevo,
> ahi conviene hacer el rename completo de una vez.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, func, select, text, update
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


# Los papeles que una persona puede cumplir. Se guardan como banderas
# independientes: la misma persona puede tener varias.
# `responsable` se sumo el 2026-08-04 con el pedido 42: es quien manda un equipo
# de trabajo. Entra como una bandera mas y no como una tabla de coordinadores —
# que es exactamente lo que el pedido 41 dejo anticipado, porque en una empresa
# chica el responsable de la cuadrilla tambien es tecnico.
ROLES = ("tecnico", "recepcionista", "vendedor", "responsable")


class Tecnico(Base):
    __tablename__ = "tecnicos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # `es_tecnico` arranca en True para que las filas que ya existen —que eran
    # tecnicos por definicion, porque la tabla no servia para otra cosa— queden
    # descritas igual que antes sin backfill.
    #
    # **Llevan `server_default` y no solo `default`**, a diferencia de `activo`,
    # que es de antes: la revision 0007 los necesita para poder agregarlos
    # `NOT NULL` sobre una tabla con filas, y sin declararlos tambien acá el
    # schema que construye Alembic difiere del que construye `create_all()`.
    # Lo agarro `test_alembic_construye_lo_mismo_que_create_all`.
    es_tecnico: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("1"),
    )
    es_recepcionista: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"),
    )
    es_vendedor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"),
    )
    # Quien manda un equipo de trabajo (pedido 42). Mismo patron que los otros
    # tres, incluido el `server_default` que necesita la migracion para poder
    # agregar la columna `NOT NULL` sobre una tabla con filas.
    es_responsable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"),
    )

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(t: Tecnico) -> dict:
    return {
        "id": t.id,
        "nombre": t.nombre,
        "activo": t.activo,
        # Las banderas salen de `ROLES` y no escritas a mano: sumar un rol —
        # `responsable` fue el cuarto— tocaba ocho lugares distintos y era
        # cuestión de tiempo que uno quedara sin actualizar.
        **{f"es_{r}": bool(getattr(t, f"es_{r}")) for r in ROLES},
        # Derivado, para que la lista no tenga que armar el texto en cada fila.
        "roles": [r for r in ROLES if getattr(t, f"es_{r}")],
    }


def _exigir_un_rol(**banderas: bool) -> None:
    """Una persona sin ningún rol no aparecería en ningún selector: estaría
    cargada y sería invisible, que se lee como un bug del sistema y no como un
    dato mal puesto."""
    if not any(banderas.values()):
        raise ValueError("La persona tiene que tener al menos un rol")


def _banderas(datos: dict, actual: Tecnico | None = None) -> dict[str, bool]:
    """Las banderas de rol resueltas: lo que vino, o lo que ya tenía.

    `actual=None` es un alta, y ahí el default es `es_tecnico` — que es como se
    comportaba la tabla antes de que existieran los roles.
    """
    salida = {}
    for r in ROLES:
        campo = f"es_{r}"
        valor = datos.get(campo)
        if valor is None:
            valor = getattr(actual, campo) if actual is not None else (r == "tecnico")
        salida[campo] = bool(valor)
    return salida


class TecnicoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def create(self, nombre: str, activo: bool = True, **roles) -> dict:
        banderas = _banderas(roles)
        _exigir_un_rol(**banderas)
        with self.session_factory() as session:
            t = Tecnico(nombre=nombre.strip(), activo=activo, **banderas)
            session.add(t)
            session.commit()
            session.refresh(t)
            return _to_dict(t)

    def list(self, solo_activos: bool = False, *, rol: str | None = None) -> list[dict]:
        """`rol` filtra por papel — es lo que alimenta cada selector del ticket:
        el de recepcionista sólo ofrece recepcionistas, y así."""
        if rol is not None and rol not in ROLES:
            raise ValueError(f"Rol inválido: {rol}")
        with self.session_factory() as session:
            stmt = select(Tecnico).order_by(Tecnico.nombre)
            if solo_activos:
                stmt = stmt.where(Tecnico.activo.is_(True))
            if rol is not None:
                stmt = stmt.where(getattr(Tecnico, f"es_{rol}").is_(True))
            return [_to_dict(t) for t in session.execute(stmt).scalars()]

    def get(self, tecnico_id: int) -> dict | None:
        with self.session_factory() as session:
            t = session.get(Tecnico, tecnico_id)
            return _to_dict(t) if t else None

    def update(self, tecnico_id: int, nombre: str, activo: bool, **roles) -> dict:
        with self.session_factory() as session:
            t = session.get(Tecnico, tecnico_id)
            if t is None:
                raise KeyError(tecnico_id)
            nuevos = _banderas(roles, actual=t)
            _exigir_un_rol(**nuevos)
            t.nombre = nombre.strip()
            t.activo = activo
            for campo, valor in nuevos.items():
                setattr(t, campo, valor)
            session.commit()
            session.refresh(t)
            return _to_dict(t)

    def delete(self, tecnico_id: int) -> None:
        """Borra el tecnico y **desasigna** las incidencias que tenia.

        Mismo caso que `SectorRepository.delete`: `incidencias.tecnico_id`
        declara `ondelete="SET NULL"` y ese ondelete no corre nunca, porque
        el engine no activa `PRAGMA foreign_keys`. Sin esto, borrar un
        tecnico dejaba tickets apuntando a un id inexistente y el reporte
        "Por tecnico" —que agrupa por esa FK— los perdia de vista sin decir
        por que.
        """
        with self.session_factory() as session:
            t = session.get(Tecnico, tecnico_id)
            if t is None:
                raise KeyError(tecnico_id)

            from .incidencias import Incidencia

            # Los TRES papeles, no sólo el de técnico: desde el pedido 41 la
            # misma persona puede estar apuntada como recepcionista o vendedor
            # en otros tickets, y dejar esas dos columnas colgando reproduce
            # exactamente el defecto que este método vino a arreglar.
            for columna in ("tecnico_id", "recepcionista_id", "vendedor_id"):
                session.execute(
                    update(Incidencia)
                    .where(getattr(Incidencia, columna) == tecnico_id)
                    .values(**{columna: None})
                )
            session.delete(t)
            session.commit()
