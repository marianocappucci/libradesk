"""Log de actividad: quien creo, edito o borro que, y que cambio.

**Por que es automatico y no una llamada en cada servicio.** La alternativa era
sembrar `registrar(...)` en los ~40 metodos de escritura de los repositorios.
Eso funciona el primer dia y se degrada solo: el metodo que se agrega el mes
que viene no lo lleva, nadie se entera —un log incompleto se ve igual que uno
completo— y el dia que alguien pregunta "quien borro este equipo" la respuesta
es "no quedo registrado". Aca el registro cuelga del `flush` de SQLAlchemy, asi
que **una escritura que no pase por esto no existe**: no hay forma de olvidarse.

Lo que se audita esta declarado en `AUDITABLES` y es una lista blanca. Las
tablas que YA son historial (`equipos_movimientos`, `incidencias_estados_log`,
`actividades_incidencia`) quedan afuera a proposito: auditarlas duplicaria en
esta pantalla lo que la ficha del equipo y la de la incidencia ya muestran.

**Los dos listeners son uno solo partido en dos, y el orden importa:**

- `before_flush` es el unico momento en que el historial de cada atributo
  todavia esta intacto (`get_history`), asi que ahi se calcula el diff.
- Pero ahi los objetos nuevos **todavia no tienen `id`** (lo asigna el INSERT),
  y un log de auditoria sin el id de la fila que describe no sirve para
  buscar nada. Por eso las filas se completan y se escriben en `after_flush`,
  cuando el id ya existe.

El INSERT final va por Core (`table.insert()`) y no por el ORM: agregar objetos
a la sesion dentro de `after_flush` no los incluiria en el flush en curso, y
ademas dispararia el listener de nuevo.
"""
from __future__ import annotations

import json
from contextvars import ContextVar
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, event, select
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from ..database import Base

CREAR = "crear"
EDITAR = "editar"
BORRAR = "borrar"

# Quien esta haciendo la escritura, resuelto por el middleware de `main.py` a
# partir de la cookie de sesion. Es un ContextVar y no un parametro porque el
# dato tiene que llegar hasta el `flush`, que ocurre dentro del repositorio,
# tres capas mas abajo del router — pasarlo a mano obligaria a agregarle un
# argumento `usuario` a cada metodo de cada repositorio.
#
# El default no es "" sino este texto: una fila escrita fuera de una request
# (un seed, una migracion, un script) es legitima y tiene que poder
# distinguirse de "no se supo quien fue".
SISTEMA = "Sistema"
usuario_actual: ContextVar[str] = ContextVar("usuario_actual", default=SISTEMA)


class ActividadLog(Base):
    """Una fila por cambio. `cambios` es JSON y no columnas fijas porque cada
    entidad tiene los suyos; se lee solo para mostrarlo, nunca se filtra por
    adentro."""

    __tablename__ = "actividad_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Hora local, igual que `auth_log` de libraauth: las dos se muestran en la
    # misma pantalla y una en UTC quedaria tres horas corrida contra la otra.
    ts: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.now, index=True)
    usuario: Mapped[str] = mapped_column(String(100), nullable=False, default=SISTEMA)
    accion: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    entidad: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entidad_id: Mapped[int | None] = mapped_column(Integer)
    descripcion: Mapped[str] = mapped_column(String(500), nullable=False, default="")
    cambios: Mapped[str | None] = mapped_column(Text)


# ── Que se audita ─────────────────────────────────────────────────────────

# {nombre del modelo: (nombre logico, etiqueta legible)}. Se indexa por nombre
# de clase y no por la clase para no importar los 12 modulos de servicio desde
# aca — varios de ellos importan este.
AUDITABLES: dict[str, str] = {
    "Cliente": "cliente",
    "Equipo": "equipo",
    "Incidencia": "incidencia",
    "Contrato": "contrato",
    "Activo": "activo",
    "Deposito": "deposito",
    "Proveedor": "proveedor",
    "Tecnico": "tecnico",
    "Sector": "sector",
    "CategoriaIncidencia": "categoria",
    "Reparacion": "reparacion",
    "EquipoTrabajo": "equipo_trabajo",
    "Vehiculo": "vehiculo",
}

# Columnas que nunca entran al diff. `password_hash` no vive en ninguna tabla
# de este producto (los usuarios son de libraauth), pero esta igual: si algun
# dia un modelo de aca guarda un secreto, el log de auditoria no puede ser el
# lugar donde termina en claro.
COLUMNAS_OCULTAS = frozenset({"password_hash", "password", "token", "token_hash", "secret"})

# En orden: el primero que exista y tenga valor es la etiqueta.
_ATRIBUTOS_ETIQUETA = ("titulo", "numero", "nombre", "patente", "codigo_interno", "serial")


def _etiqueta(obj) -> str:
    for attr in _ATRIBUTOS_ETIQUETA:
        valor = getattr(obj, attr, None)
        if valor:
            return str(valor)[:200]
    # Un equipo puede no tener ninguno de los de arriba: se arma con lo que hay.
    partes = [str(getattr(obj, a, "") or "") for a in ("tipo", "marca", "modelo")]
    armado = " ".join(p for p in partes if p).strip()
    return armado[:200] if armado else ""


def _valor_legible(valor):
    if isinstance(valor, datetime):
        return valor.strftime("%Y-%m-%d %H:%M:%S")
    if valor is None or isinstance(valor, (str, int, float, bool)):
        return valor
    return str(valor)


def _diff(obj) -> dict:
    """`{columna: [antes, despues]}` de lo que realmente cambio.

    Solo columnas: las relaciones quedan afuera porque cargarlas aca dispararia
    un SELECT por atributo en medio del flush.
    """
    from sqlalchemy import inspect as sa_inspect

    estado = sa_inspect(obj)
    cambios = {}
    for columna in obj.__table__.columns.keys():
        if columna in COLUMNAS_OCULTAS:
            continue
        historial = estado.attrs[columna].history
        if not historial.has_changes():
            continue
        antes = historial.deleted[0] if historial.deleted else None
        despues = historial.added[0] if historial.added else None
        if antes == despues:
            continue
        cambios[columna] = [_valor_legible(antes), _valor_legible(despues)]
    return cambios


def _fila(obj, accion: str, cambios: dict | None) -> dict:
    entidad = AUDITABLES[type(obj).__name__]
    etiqueta = _etiqueta(obj)
    return {
        "ts": datetime.now(),
        "usuario": usuario_actual.get()[:100],
        "accion": accion,
        "entidad": entidad,
        # Se completa en after_flush para las creaciones: en before_flush el
        # INSERT todavia no corrio y el id no existe.
        "_obj": obj,
        "descripcion": f"{entidad.replace('_', ' ').capitalize()}{f' — {etiqueta}' if etiqueta else ''}"[:500],
        "cambios": json.dumps(cambios, ensure_ascii=False) if cambios else None,
    }


def _auditable(obj) -> bool:
    return type(obj).__name__ in AUDITABLES


def _antes_del_flush(session: Session, flush_context, instances):  # noqa: ARG001
    if session.info.get("auditoria") is False:
        return
    pendientes = []
    for obj in session.new:
        if _auditable(obj):
            pendientes.append(_fila(obj, CREAR, None))
    for obj in session.dirty:
        if _auditable(obj) and session.is_modified(obj, include_collections=False):
            cambios = _diff(obj)
            # Un `dirty` sin columnas cambiadas es un objeto que alguien toco y
            # dejo igual. Registrarlo llenaria el log de "editar" vacios.
            if cambios:
                pendientes.append(_fila(obj, EDITAR, cambios))
    for obj in session.deleted:
        if _auditable(obj):
            fila = _fila(obj, BORRAR, None)
            # El id se lee ACA y no despues: tras el flush el objeto queda
            # desatachado y `obj.id` puede venir vacio.
            fila["entidad_id"] = obj.id
            fila["_obj"] = None
            pendientes.append(fila)
    if pendientes:
        session.info.setdefault("_auditoria", []).extend(pendientes)


def _despues_del_flush(session: Session, flush_context):  # noqa: ARG001
    pendientes = session.info.pop("_auditoria", None)
    if not pendientes:
        return
    filas = []
    for fila in pendientes:
        obj = fila.pop("_obj", None)
        if obj is not None:
            fila["entidad_id"] = getattr(obj, "id", None)
        filas.append(fila)
    # Core y no ORM: `session.add()` aca no entraria en este flush, y volveria
    # a disparar estos mismos listeners.
    session.execute(ActividadLog.__table__.insert(), filas)


def configurar_auditoria(session_factory: sessionmaker) -> None:
    """Engancha los listeners. Idempotente: llamarla dos veces (los tests
    arman varias apps en el mismo proceso) no duplica las filas."""
    if not event.contains(session_factory, "before_flush", _antes_del_flush):
        event.listen(session_factory, "before_flush", _antes_del_flush)
    if not event.contains(session_factory, "after_flush", _despues_del_flush):
        event.listen(session_factory, "after_flush", _despues_del_flush)


class AuditoriaRepository:
    """Lectura del log. No expone ningun metodo de escritura a proposito: lo
    que se escribe lo decide el flush, no un llamador."""

    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def listar(self, *, entidad: str = "", accion: str = "", usuario: str = "",
               desde: str = "", hasta: str = "", limit: int = 100, offset: int = 0) -> list[dict]:
        with self.session_factory() as session:
            filas = session.execute(
                self._filtrada(entidad, accion, usuario, desde, hasta)
                .order_by(ActividadLog.id.desc()).limit(limit).offset(offset)
            ).scalars()
            return [{
                "id": f.id,
                "ts": f.ts.strftime("%Y-%m-%d %H:%M:%S") if f.ts else "",
                "usuario": f.usuario,
                "accion": f.accion,
                "entidad": f.entidad,
                "entidad_id": f.entidad_id,
                "descripcion": f.descripcion,
                "cambios": json.loads(f.cambios) if f.cambios else None,
            } for f in filas]

    def contar(self, *, entidad: str = "", accion: str = "", usuario: str = "",
               desde: str = "", hasta: str = "") -> int:
        from sqlalchemy import func

        with self.session_factory() as session:
            sub = self._filtrada(entidad, accion, usuario, desde, hasta).subquery()
            return int(session.execute(select(func.count()).select_from(sub)).scalar_one())

    def usuarios(self) -> list[str]:
        """Los usuarios que aparecen en el log — para poblar el filtro sin
        mostrar a los que nunca escribieron nada."""
        with self.session_factory() as session:
            return [u for (u,) in session.execute(
                select(ActividadLog.usuario).distinct().order_by(ActividadLog.usuario)
            )]

    def _filtrada(self, entidad: str, accion: str, usuario: str, desde: str, hasta: str):
        consulta = select(ActividadLog)
        if entidad:
            consulta = consulta.where(ActividadLog.entidad.in_(entidad.split(",")))
        if accion:
            consulta = consulta.where(ActividadLog.accion == accion)
        if usuario:
            consulta = consulta.where(ActividadLog.usuario == usuario)
        if desde:
            consulta = consulta.where(ActividadLog.ts >= datetime.fromisoformat(desde))
        if hasta:
            # `hasta` es un dia, no un instante: sin esto, filtrar "hasta hoy"
            # dejaria afuera todo lo de hoy salvo lo de las 00:00:00.
            consulta = consulta.where(ActividadLog.ts < datetime.fromisoformat(hasta).replace(
                hour=23, minute=59, second=59))
        return consulta
