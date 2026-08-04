"""Consultas de los 6 reportes analiticos, reconstruidas desde el backend
Node.js viejo (`reportesXlsxController.ts`) sobre el esquema actual.

Dos diferencias de esquema respecto del original, ninguna opcional:

- `incidencias.tecnico_asignado` y `.sector` eran texto libre; ahora son
  FK (`tecnico_id`/`sector_id`), asi que se resuelven por join. El
  reporte "Por tecnico" agrupa por la FK, no por un string.
- La columna "Tar." del reporte de Incidencias contaba filas de
  `incidencia_tareas`, tabla que **ya no existe** (Tareas se elimino en la
  reescritura). Se cae esa columna; no hay dato equivalente.

Lectura pura, sin tablas propias — mismo criterio que `DashboardService`.
"""
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import aliased, sessionmaker

from .categorias import CategoriaIncidencia
from .clientes import Cliente
from .depositos import Deposito, lugar_de
from .equipos import Equipo, EquipoMovimiento
from .incidencias import ActividadIncidencia, Incidencia
from .sectores import Sector
from .tecnicos import Tecnico


def _fin_del_dia(fecha: str) -> datetime:
    """`hasta` llega como fecha sin hora; sin esto, todo lo del ultimo dia
    queda afuera del rango."""
    return datetime.fromisoformat(fecha).replace(hour=23, minute=59, second=59, microsecond=999999)


def _inicio_del_dia(fecha: str) -> datetime:
    return datetime.fromisoformat(fecha).replace(hour=0, minute=0, second=0, microsecond=0)


def _nombre_cliente(c: Cliente) -> str:
    return c.empresa or c.nombre


def _ruta_categoria(cat: CategoriaIncidencia | None, padre: CategoriaIncidencia | None) -> str | None:
    """"Hardware · Impresoras", o solo el nombre si el ticket quedo clasificado
    en una categoria raiz. `None` si no tiene ninguna — que es el caso de las
    23 incidencias reales, previas al catalogo."""
    if cat is None:
        return None
    return f"{padre.nombre} · {cat.nombre}" if padre else cat.nombre


def _horas_resolucion(i: Incidencia) -> int | None:
    if not i.fecha_cierre or not i.fecha_creacion:
        return None
    return round((i.fecha_cierre - i.fecha_creacion).total_seconds() / 3600)


class ReportesService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    # ── Equipamiento ────────────────────────────────────────────────
    def equipamiento(self, cliente_id: int | None = None, estado: str | None = None,
                     tipo: str | None = None) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(Equipo, Cliente, Deposito.nombre)
                .join(Cliente, Equipo.cliente_id == Cliente.id)
                .outerjoin(Deposito, Equipo.deposito_id == Deposito.id)
                .where(Cliente.activo.is_(True))
            )
            if cliente_id:
                stmt = stmt.where(Equipo.cliente_id == cliente_id)
            if estado:
                stmt = stmt.where(Equipo.estado == estado)
            if tipo:
                stmt = stmt.where(Equipo.tipo.ilike(f"%{tipo}%"))
            stmt = stmt.order_by(Cliente.nombre, Equipo.tipo, Equipo.marca)

            # Conteo de incidencias por equipo en una sola consulta, en vez
            # de una subconsulta por fila.
            conteos = dict(
                session.execute(
                    select(Incidencia.equipo_id, func.count())
                    .where(Incidencia.equipo_id.is_not(None))
                    .group_by(Incidencia.equipo_id)
                ).all()
            )

            return [
                {
                    "cliente": _nombre_cliente(c),
                    "tipo": e.tipo,
                    "marca": e.marca,
                    "modelo": e.modelo,
                    "serial": e.serial,
                    "sector": e.sector,
                    "deposito": deposito,
                    # Donde esta de verdad: el deposito si esta guardado, si no
                    # el sector del cliente. Es lo que se muestra; `sector` se
                    # conserva aparte porque es de donde salio.
                    "lugar": lugar_de(deposito, e.sector),
                    "ubicacion_oficina": e.ubicacion_oficina,
                    "estado": e.estado,
                    "garantia_vence": e.garantia_vence,
                    "incidencias_count": conteos.get(e.id, 0),
                    "fecha_adicion": e.fecha_adicion,
                }
                for e, c, deposito in session.execute(stmt).all()
            ]

    # ── Incidencias por periodo ─────────────────────────────────────
    def incidencias(self, desde: str, hasta: str, cliente_id: int | None = None,
                    estado: str | None = None, prioridad: str | None = None,
                    sector_id: int | None = None, keyword: str | None = None,
                    categoria_id: int | None = None) -> list[dict]:
        with self.session_factory() as session:
            # Alias sobre la MISMA tabla para traer el padre de la categoria:
            # el catalogo es de dos niveles con auto-referencia, asi que
            # "Hardware · Impresoras" sale de un solo join contra si misma.
            Padre = aliased(CategoriaIncidencia)
            stmt = (
                select(Incidencia, Cliente, Tecnico, Sector, CategoriaIncidencia, Padre)
                .join(Cliente, Incidencia.cliente_id == Cliente.id)
                .outerjoin(Tecnico, Incidencia.tecnico_id == Tecnico.id)
                .outerjoin(Sector, Incidencia.sector_id == Sector.id)
                .outerjoin(CategoriaIncidencia, Incidencia.categoria_id == CategoriaIncidencia.id)
                .outerjoin(Padre, CategoriaIncidencia.parent_id == Padre.id)
                .where(Incidencia.fecha_creacion >= _inicio_del_dia(desde))
                .where(Incidencia.fecha_creacion <= _fin_del_dia(hasta))
            )
            if cliente_id:
                stmt = stmt.where(Incidencia.cliente_id == cliente_id)
            if estado:
                stmt = stmt.where(Incidencia.estado == estado)
            if prioridad:
                stmt = stmt.where(Incidencia.prioridad == prioridad)
            if sector_id:
                stmt = stmt.where(Incidencia.sector_id == sector_id)
            if categoria_id:
                # Elegir una categoria RAIZ trae todo lo que cuelga de ella:
                # "Hardware" contesta por impresoras, notebooks y red juntas,
                # que es la pregunta que se hace de verdad.
                stmt = stmt.where(
                    (Incidencia.categoria_id == categoria_id)
                    | (CategoriaIncidencia.parent_id == categoria_id)
                )
            if keyword:
                like = f"%{keyword}%"
                stmt = stmt.where(
                    Incidencia.titulo.ilike(like) | Incidencia.descripcion.ilike(like)
                )
            stmt = stmt.order_by(Incidencia.fecha_creacion.desc(), Incidencia.id.desc())

            actividades = dict(
                session.execute(
                    select(ActividadIncidencia.incidencia_id, func.count())
                    .group_by(ActividadIncidencia.incidencia_id)
                ).all()
            )

            return [
                {
                    "id": i.id,
                    "cliente": _nombre_cliente(c),
                    "tipo_facturacion": c.tipo_facturacion,
                    "sector": s.nombre if s else None,
                    "categoria": _ruta_categoria(cat, padre),
                    "titulo": i.titulo,
                    "descripcion": i.descripcion,
                    "estado": i.estado,
                    "prioridad": i.prioridad,
                    "tecnico": t.nombre if t else None,
                    "fecha_creacion": i.fecha_creacion,
                    "fecha_cierre": i.fecha_cierre,
                    "estado_facturacion": i.estado_facturacion,
                    "actividades_count": actividades.get(i.id, 0),
                    "horas_resolucion": _horas_resolucion(i),
                }
                for i, c, t, s, cat, padre in session.execute(stmt).all()
            ]

    # ── Facturacion ─────────────────────────────────────────────────
    def facturacion(self, desde: str, hasta: str, cliente_id: int | None = None,
                    estado_facturacion: str | None = None) -> list[dict]:
        """Solo incidencias cerradas de clientes `por_servicio`: a los
        `mensual` se les factura el abono, no la incidencia."""
        with self.session_factory() as session:
            stmt = (
                select(Incidencia, Cliente, Tecnico)
                .join(Cliente, Incidencia.cliente_id == Cliente.id)
                .outerjoin(Tecnico, Incidencia.tecnico_id == Tecnico.id)
                .where(Incidencia.estado == "cerrado")
                .where(Cliente.tipo_facturacion == "por_servicio")
                .where(Incidencia.fecha_cierre >= _inicio_del_dia(desde))
                .where(Incidencia.fecha_cierre <= _fin_del_dia(hasta))
            )
            if cliente_id:
                stmt = stmt.where(Incidencia.cliente_id == cliente_id)
            if estado_facturacion == "sin_facturar":
                stmt = stmt.where(Incidencia.estado_facturacion.is_(None))
            elif estado_facturacion:
                stmt = stmt.where(Incidencia.estado_facturacion == estado_facturacion)
            stmt = stmt.order_by(Cliente.nombre, Incidencia.fecha_cierre.desc())

            return [
                {
                    "id": i.id,
                    "cliente_id": c.id,
                    "cliente": _nombre_cliente(c),
                    "titulo": i.titulo,
                    "tecnico": t.nombre if t else None,
                    "fecha_cierre": i.fecha_cierre,
                    "estado_facturacion": i.estado_facturacion,
                }
                for i, c, t in session.execute(stmt).all()
            ]

    # ── Garantias ───────────────────────────────────────────────────
    def garantias(self, dias: int = 60, cliente_id: int | None = None) -> list[dict]:
        with self.session_factory() as session:
            hoy = datetime.now()
            limite = hoy + timedelta(days=dias)
            stmt = (
                select(Equipo, Cliente, Deposito.nombre)
                .join(Cliente, Equipo.cliente_id == Cliente.id)
                .outerjoin(Deposito, Equipo.deposito_id == Deposito.id)
                .where(Equipo.garantia_vence.is_not(None))
                .where(Equipo.estado != "baja")
                .where(Equipo.garantia_vence <= limite)
            )
            if cliente_id:
                stmt = stmt.where(Equipo.cliente_id == cliente_id)
            stmt = stmt.order_by(Equipo.garantia_vence.asc())

            filas = []
            for e, c, deposito in session.execute(stmt).all():
                vence = e.garantia_vence
                if isinstance(vence, datetime):
                    restantes = (vence.date() - hoy.date()).days
                else:
                    restantes = (vence - hoy.date()).days
                filas.append({
                    "cliente": _nombre_cliente(c),
                    "tipo": e.tipo,
                    "marca": e.marca,
                    "modelo": e.modelo,
                    "serial": e.serial,
                    "sector": e.sector,
                    "deposito": deposito,
                    "lugar": lugar_de(deposito, e.sector),
                    "estado": e.estado,
                    "garantia_vence": vence,
                    "dias_restantes": restantes,
                })
            return filas

    # ── Por tecnico ─────────────────────────────────────────────────
    def por_tecnico(self, desde: str, hasta: str) -> list[dict]:
        """Agrupa por la FK `tecnico_id` (el original agrupaba por el texto
        libre `tecnico_asignado`, que ya no existe). Las incidencias sin
        tecnico caen en 'Sin asignar'."""
        with self.session_factory() as session:
            stmt = (
                select(Incidencia, Tecnico)
                .outerjoin(Tecnico, Incidencia.tecnico_id == Tecnico.id)
                .where(Incidencia.fecha_creacion >= _inicio_del_dia(desde))
                .where(Incidencia.fecha_creacion <= _fin_del_dia(hasta))
            )
            actividades = dict(
                session.execute(
                    select(ActividadIncidencia.incidencia_id, func.count())
                    .group_by(ActividadIncidencia.incidencia_id)
                ).all()
            )

            acc: dict[str, dict] = {}
            for i, t in session.execute(stmt).all():
                nombre = t.nombre if t else "Sin asignar"
                g = acc.setdefault(nombre, {
                    "tecnico": nombre, "total": 0, "abiertas": 0, "en_progreso": 0,
                    "cerradas": 0, "total_actividades": 0, "_horas": [],
                })
                g["total"] += 1
                if i.estado == "abierto":
                    g["abiertas"] += 1
                elif i.estado == "en_progreso":
                    g["en_progreso"] += 1
                elif i.estado in ("cerrado", "resuelta"):
                    g["cerradas"] += 1
                    horas = _horas_resolucion(i)
                    if horas is not None:
                        g["_horas"].append(horas)
                g["total_actividades"] += actividades.get(i.id, 0)

            filas = []
            for g in acc.values():
                horas = g.pop("_horas")
                g["promedio_horas_resolucion"] = round(sum(horas) / len(horas)) if horas else None
                filas.append(g)
            return sorted(filas, key=lambda g: g["total"], reverse=True)

    # ── Movimientos ─────────────────────────────────────────────────
    def movimientos(self, desde: str, hasta: str, cliente_id: int | None = None) -> list[dict]:
        with self.session_factory() as session:
            stmt = (
                select(EquipoMovimiento, Equipo, Cliente)
                .join(Equipo, EquipoMovimiento.equipo_id == Equipo.id)
                .join(Cliente, Equipo.cliente_id == Cliente.id)
                .where(EquipoMovimiento.fecha >= _inicio_del_dia(desde))
                .where(EquipoMovimiento.fecha <= _fin_del_dia(hasta))
            )
            if cliente_id:
                stmt = stmt.where(Equipo.cliente_id == cliente_id)
            stmt = stmt.order_by(EquipoMovimiento.fecha.desc(), EquipoMovimiento.id.desc())

            return [
                {
                    "fecha": m.fecha,
                    "cliente": _nombre_cliente(c),
                    "equipo": " ".join(x for x in (e.tipo, e.marca, e.modelo) if x),
                    "tipo": m.tipo,
                    "sector_origen": m.sector_origen,
                    "ubicacion_origen": m.ubicacion_origen,
                    "sector_destino": m.sector_destino,
                    "ubicacion_destino": m.ubicacion_destino,
                    "motivo": m.motivo,
                }
                for m, e, c in session.execute(stmt).all()
            ]
