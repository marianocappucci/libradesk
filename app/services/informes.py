"""Informe de servicio del periodo — el unico entregable de LibraDesk que ve
**el cliente**, no el equipo de soporte.

Deliberadamente separado de `reportes.py`, aunque consulte las mismas tablas.
Los seis reportes analiticos son internos: traen tecnico, estado de cobro y
costo de las reparaciones. Nada de eso entra aca. Compartir el modulo habria
hecho que cada campo nuevo de un reporte interno tuviera que acordarse de no
filtrarse al informe del cliente; separarlos hace que el default sea el
correcto.

**Todo esta anclado a `hasta`, no a hoy.** Un informe de julio emitido en
agosto tiene que dar lo mismo si se lo vuelve a generar en octubre: las
garantias por vencer se cuentan desde el fin del periodo, y "sigue en service"
significa "seguia en service al cierre del periodo". Anclar a `date.today()`
—que es lo que hace la ficha en pantalla, y esta bien ahi porque muestra el
presente— daria un documento que cambia cada vez que se lo pide.

**El estado que se informa es derivado de las fechas, no de la columna
`estado`.** La columna dice como esta el ticket *hoy*; el informe tiene que
decir como estaba **al cierre del periodo**. Si no, un informe de julio
regenerado en septiembre contaria como resuelto un ticket que en julio seguia
abierto, y el detalle contradiria al resumen de su propia primera pagina.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import aliased, sessionmaker

from .categorias import CategoriaIncidencia
from .clientes import Cliente
from .equipos import Equipo, descripcion_equipo
from .incidencias import ActividadIncidencia, Incidencia
from .proveedores import Proveedor
from .reparaciones import Reparacion
from .reportes import _fin_del_dia, _inicio_del_dia, _nombre_cliente, _ruta_categoria

# Los estados que cuentan como cerrada. `IncidenciaRepository.update()` setea
# `fecha_cierre` al entrar a cualquiera de los dos y la limpia al reabrir, asi
# que normalmente basta con la fecha. Se conserva la lista para el caso de
# datos migrados, abajo.
ESTADOS_CERRADOS = ("resuelta", "cerrado")

# Ventana de garantias por vencer, contada desde el fin del periodo. Mismo
# default que la ficha del cliente y que el reporte de Garantias.
DIAS_GARANTIA = 60


def _cerrada_al(i: Incidencia, hasta: datetime) -> bool:
    """Si el ticket ya estaba cerrado al final del periodo.

    El caso raro que justifica la segunda mitad: las 23 incidencias migradas
    del Node.js viejo pueden tener `estado` cerrado **sin** `fecha_cierre`, que
    esa base no guardaba. Sin este desempate un ticket cerrado hace un anio
    saldria como "Pendiente" en todos los informes, para siempre. Se lo cuenta
    como cerrado pero **fuera** de las resueltas del periodo: sin fecha no hay
    periodo al que atribuirlo, y adjudicarselo al que se esta emitiendo seria
    inventar el dato.
    """
    if i.fecha_cierre is not None:
        return i.fecha_cierre <= hasta
    return i.estado in ESTADOS_CERRADOS


def _horas(valor: Decimal | None) -> float:
    return float(valor) if valor is not None else 0.0


class InformeService:
    """Lectura pura, sin tablas propias — mismo criterio que `ReportesService`
    y `DashboardService`.

    Devuelve el informe entero como dict y **no arma el PDF**: eso lo hace
    `informe_pdf.py`. La separacion es la que permite testear los numeros sin
    abrir un archivo binario, y deja el mismo contenido disponible si algun dia
    se lo quiere en otro formato.
    """

    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def cliente(self, cliente_id: int, desde: str, hasta: str,
                dias_garantia: int = DIAS_GARANTIA) -> dict | None:
        """El informe completo de un cliente para un periodo.

        `None` si el cliente no existe — el router lo traduce a 404.
        """
        desde_dt = _inicio_del_dia(desde)
        hasta_dt = _fin_del_dia(hasta)
        hasta_date = hasta_dt.date()

        with self.session_factory() as session:
            cliente = session.get(Cliente, cliente_id)
            if cliente is None:
                return None

            incidencias = self._incidencias(session, cliente_id, desde_dt, hasta_dt)
            return {
                "cliente": {
                    "id": cliente.id,
                    "nombre": _nombre_cliente(cliente),
                    "contacto": cliente.nombre if cliente.empresa else None,
                    "cuit": cliente.cuit,
                    "domicilio": cliente.domicilio,
                    "ciudad": cliente.ciudad,
                    "email": cliente.email,
                    "telefono": cliente.telefono,
                },
                "periodo": {
                    "desde": desde,
                    "hasta": hasta,
                    "emitido": date.today().isoformat(),
                },
                "resumen": self._resumen(session, cliente_id, incidencias, desde_dt, hasta_dt),
                "incidencias": incidencias,
                "parque": self._parque(session, cliente_id),
                "garantias": self._garantias(session, cliente_id, hasta_date, dias_garantia),
                "service": self._service(session, cliente_id, desde_dt.date(), hasta_date),
                "dias_garantia": dias_garantia,
            }

    # ── Incidencias del periodo ─────────────────────────────────────

    def _incidencias(self, session, cliente_id: int,
                     desde: datetime, hasta: datetime) -> list[dict]:
        """Las creadas en el periodo **o** cerradas en el periodo.

        La union no es un capricho: el ticket que se abrio en junio y se
        resolvio en julio es, para el cliente, trabajo de julio — y si solo se
        filtrara por fecha de creacion no aparecerian en ningun informe los
        cierres de tickets viejos, que es justamente lo que el cliente cuenta
        como resuelto.
        """
        Padre = aliased(CategoriaIncidencia)

        stmt = (
            select(Incidencia, Equipo, CategoriaIncidencia, Padre)
            .outerjoin(Equipo, Incidencia.equipo_id == Equipo.id)
            .outerjoin(CategoriaIncidencia, Incidencia.categoria_id == CategoriaIncidencia.id)
            .outerjoin(Padre, CategoriaIncidencia.parent_id == Padre.id)
            .where(Incidencia.cliente_id == cliente_id)
            .where(
                Incidencia.fecha_creacion.between(desde, hasta)
                | Incidencia.fecha_cierre.between(desde, hasta)
            )
            .order_by(Incidencia.fecha_creacion.asc(), Incidencia.id.asc())
        )
        filas = session.execute(stmt).all()

        actividades = dict(
            session.execute(
                select(ActividadIncidencia.incidencia_id, func.count())
                .where(ActividadIncidencia.incidencia_id.in_([i.id for i, *_ in filas] or [0]))
                .group_by(ActividadIncidencia.incidencia_id)
            ).all()
        )

        return [
            {
                "id": i.id,
                "titulo": i.titulo,
                "categoria": _ruta_categoria(cat, padre),
                "equipo": descripcion_equipo(e) if e else None,
                "sector": e.sector if e else None,
                "fecha_creacion": i.fecha_creacion,
                # La fecha de cierre **solo si cae dentro del periodo**. Un
                # ticket cerrado despues de `hasta` estaba pendiente al cierre,
                # y devolver su fecha real invitaba a que la presentacion la
                # imprimiera como "Resuelta el 02/02" en un informe de enero
                # que en su propio resumen lo cuenta como pendiente. No es
                # hipotetico: la primera version hacia exactamente eso.
                "fecha_cierre": (
                    i.fecha_cierre if i.fecha_cierre is not None
                    and i.fecha_cierre <= hasta else None
                ),
                "cerrada": _cerrada_al(i, hasta),
                # Solo cuenta como resuelta del periodo si la fecha lo dice.
                # Ver `_cerrada_al`: un cierre sin fecha no tiene periodo.
                "resuelta_en_periodo": (
                    i.fecha_cierre is not None and desde <= i.fecha_cierre <= hasta
                ),
                "creada_en_periodo": desde <= i.fecha_creacion <= hasta,
                "horas": _horas(i.horas_invertidas),
                "actividades": actividades.get(i.id, 0),
                "resolucion": i.resolucion,
            }
            for i, e, cat, padre in filas
        ]

    # ── Resumen ejecutivo ───────────────────────────────────────────

    def _resumen(self, session, cliente_id: int, incidencias: list[dict],
                 desde: datetime, hasta: datetime) -> dict:
        recibidas = sum(1 for i in incidencias if i["creada_en_periodo"])
        resueltas = sum(1 for i in incidencias if i["resuelta_en_periodo"])

        # Pendientes al cierre del periodo: se cuentan contra la base entera,
        # no contra `incidencias`, porque un ticket abierto en mayo y todavia
        # sin resolver no entra en el detalle de julio pero **si** es algo que
        # el cliente tiene abierto. Ocultarlo daria un informe que dice "0
        # pendientes" con trabajo sin terminar.
        pendientes = 0
        for i in session.execute(
            select(Incidencia)
            .where(Incidencia.cliente_id == cliente_id)
            .where(Incidencia.fecha_creacion <= hasta)
        ).scalars():
            if not _cerrada_al(i, hasta):
                pendientes += 1

        cerradas = [i for i in incidencias if i["resuelta_en_periodo"]]
        horas_resolucion = [
            (i["fecha_cierre"] - i["fecha_creacion"]).total_seconds() / 3600
            for i in cerradas
        ]

        # De que se trataron los tickets del periodo. Va como desglose y no
        # como columna del detalle: en la columna se comia el ancho del asunto
        # —que es lo que el cliente lee— para repetir "Hardware · Impresoras"
        # en cada fila, y agrupado contesta algo que fila por fila no se ve.
        por_categoria: dict[str, int] = {}
        for i in incidencias:
            por_categoria[i["categoria"] or "Sin clasificar"] = (
                por_categoria.get(i["categoria"] or "Sin clasificar", 0) + 1
            )

        return {
            "recibidas": recibidas,
            "resueltas": resueltas,
            "pendientes": pendientes,
            "horas": round(sum(i["horas"] for i in incidencias), 2),
            "actividades": sum(i["actividades"] for i in incidencias),
            "promedio_resolucion_horas": (
                round(sum(horas_resolucion) / len(horas_resolucion))
                if horas_resolucion else None
            ),
            "por_categoria": sorted(
                por_categoria.items(), key=lambda kv: (-kv[1], kv[0])
            ),
        }

    # ── Parque de equipos ───────────────────────────────────────────

    def _parque(self, session, cliente_id: int) -> dict:
        """Foto del inventario. Los dados de baja no forman parte del parque,
        pero se los cuenta aparte en vez de esconderlos: si el cliente tenia 40
        equipos y ahora ve 38, la linea explica los 2 que faltan."""
        por_estado = dict(
            session.execute(
                select(Equipo.estado, func.count())
                .where(Equipo.cliente_id == cliente_id)
                .group_by(Equipo.estado)
            ).all()
        )
        bajas = por_estado.pop("baja", 0)

        por_sector = session.execute(
            select(Equipo.sector, func.count())
            .where(Equipo.cliente_id == cliente_id)
            .where(Equipo.estado != "baja")
            .group_by(Equipo.sector)
            .order_by(func.count().desc(), Equipo.sector)
        ).all()

        por_tipo = session.execute(
            select(Equipo.tipo, func.count())
            .where(Equipo.cliente_id == cliente_id)
            .where(Equipo.estado != "baja")
            .group_by(Equipo.tipo)
            .order_by(func.count().desc(), Equipo.tipo)
        ).all()

        return {
            "por_estado": por_estado,
            "total": sum(por_estado.values()),
            "bajas": bajas,
            "por_sector": [(s or "Sin sector", n) for s, n in por_sector],
            "por_tipo": [(t, n) for t, n in por_tipo],
        }

    # ── Garantias ───────────────────────────────────────────────────

    def _garantias(self, session, cliente_id: int, hasta: date, dias: int) -> list[dict]:
        """Las que vencen dentro de `dias` contados **desde el fin del
        periodo**, incluidas las ya vencidas — que son las que hay que ver
        primero. Mismo criterio que la ficha del cliente y el reporte de
        Garantias, con la unica diferencia del ancla temporal (ver el docstring
        del modulo)."""
        limite = hasta + timedelta(days=dias)
        equipos = session.execute(
            select(Equipo)
            .where(Equipo.cliente_id == cliente_id)
            .where(Equipo.garantia_vence.is_not(None))
            .where(Equipo.estado != "baja")
            .where(Equipo.garantia_vence <= limite)
            .order_by(Equipo.garantia_vence.asc())
        ).scalars()

        return [
            {
                "equipo": descripcion_equipo(e),
                "serial": e.serial,
                "sector": e.sector,
                "garantia_vence": e.garantia_vence,
                "dias_restantes": (e.garantia_vence - hasta).days,
            }
            for e in equipos
        ]

    # ── Equipos en service ──────────────────────────────────────────

    def _service(self, session, cliente_id: int, desde: date, hasta: date) -> list[dict]:
        """Reparaciones con actividad en el periodo (salio o volvio) mas las
        que seguian abiertas al cierre.

        **Sin costo ni flag de garantia**: son datos de la relacion con el
        proveedor, no del servicio que se le presta al cliente. Van en el
        reporte interno.
        """
        filas = session.execute(
            select(Reparacion, Equipo, Proveedor)
            .join(Equipo, Equipo.id == Reparacion.equipo_id)
            .join(Proveedor, Proveedor.id == Reparacion.proveedor_id)
            .where(Equipo.cliente_id == cliente_id)
            .where(Reparacion.fecha_envio <= hasta)
            .where(
                Reparacion.fecha_retorno.is_(None)
                | (Reparacion.fecha_retorno >= desde)
            )
            .order_by(Reparacion.fecha_envio.asc(), Reparacion.id.asc())
        ).all()

        informe = []
        for r, e, p in filas:
            # `fecha_retorno` posterior al periodo = al cierre seguia afuera.
            # Se informa lo que era cierto entonces, no lo que pasó despues.
            volvio = r.fecha_retorno is not None and r.fecha_retorno <= hasta
            informe.append({
                "equipo": descripcion_equipo(e),
                "serial": e.serial,
                "proveedor": p.nombre,
                "fecha_envio": r.fecha_envio,
                "fecha_retorno": r.fecha_retorno if volvio else None,
                "abierta": not volvio,
                "dias_afuera": ((r.fecha_retorno if volvio else hasta) - r.fecha_envio).days,
                "rma": r.rma,
                "diagnostico": r.diagnostico if volvio else None,
            })
        return informe
