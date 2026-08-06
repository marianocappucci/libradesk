"""Resumen agregado para el Dashboard — lectura pura sobre las tablas
existentes, sin tabla propia. Mismo criterio que
`gestiolibra/app/services/dashboard.py`.

Tres vistas: `summary()` (global, la del Dashboard), `cliente()` (la ficha
de un cliente, `/clientes/:id`) y `equipo()` (la ficha de un equipo,
`/equipos/:id`)."""
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import aliased, sessionmaker

from .categorias import CategoriaIncidencia
from .clientes import Cliente
from .depositos import Deposito, lugar_de
from .equipos import Equipo, EquipoMovimiento, _mov_to_dict, descripcion_equipo
from .incidencias import Incidencia
from .reparaciones import Reparacion, resolver as resolver_reparacion
from .reportes import _ruta_categoria
from .sectores import Sector
from .tecnicos import Tecnico

# Lo que cuenta como "abierta" en todo el dashboard. Estaba inline en
# `summary()`; la ficha del cliente tiene que usar exactamente el mismo par,
# porque si no el total global y el del cliente no cierran entre si.
ESTADOS_ABIERTOS = ("abierto", "en_progreso")

#: Contratos que todavia pueden vencer. Los cerrados no interesan: ya
#: terminaron, y listarlos como "por vencer" seria ruido permanente.
_CONTRATOS_VIGENTES = ("activo", "suspendido")

#: Los tramos del backlog abierto, en dias desde que entro el ticket. El
#: primero es "hasta 7 dias" y no "hoy": un ticket de esta semana es lo normal,
#: y darle un tramo propio haria parecer urgente al trabajo del dia.
_TRAMOS_BACKLOG = (
    ("hasta_7_dias", 0, 7),
    ("de_8_a_30_dias", 8, 30),
    ("mas_de_30_dias", 31, None),
)

#: Cuantos items se listan por bloque. El dashboard no es un listado: si hay
#: 40 contratos por vencer, lo que importa es que son 40 y cuales son los 5 mas
#: proximos. Para el resto estan las pantallas de cada modulo.
_TOPE_LISTA = 5


class DashboardService:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def summary(self, date_from: str | None = None, date_to: str | None = None) -> dict:
        with self.session_factory() as session:
            incidencias_por_estado = dict(
                session.execute(
                    select(Incidencia.estado, func.count()).group_by(Incidencia.estado)
                ).all()
            )
            incidencias_por_prioridad_abiertas = dict(
                session.execute(
                    select(Incidencia.prioridad, func.count())
                    .where(Incidencia.estado.in_(ESTADOS_ABIERTOS))
                    .group_by(Incidencia.prioridad)
                ).all()
            )
            total_clientes_activos = session.execute(
                select(func.count()).select_from(Cliente).where(Cliente.activo.is_(True))
            ).scalar_one()
            total_equipos = session.execute(
                select(func.count()).select_from(Equipo)
            ).scalar_one()
            horas_totales = session.execute(
                select(func.coalesce(func.sum(Incidencia.horas_invertidas), 0))
            ).scalar_one()

            # `COUNT` en la base, no `len(...all())`: traer todas las filas
            # para contarlas funciona con 29 incidencias y no con 29.000.
            stmt = select(func.count()).select_from(Incidencia)
            if date_from:
                stmt = stmt.where(Incidencia.fecha_creacion >= datetime.fromisoformat(date_from))
            if date_to:
                stmt = stmt.where(Incidencia.fecha_creacion <= datetime.fromisoformat(date_to))
            incidencias_en_rango = session.execute(stmt).scalar_one()

            # Las horas del RANGO, no de todos los tiempos. Antes eran el total
            # historico y colgaban del subtitulo de "Equipos", que no tiene
            # nada que ver: el usuario movia las fechas y el numero no se
            # movia, sin ninguna forma de saber por que.
            stmt_horas = select(func.coalesce(func.sum(Incidencia.horas_invertidas), 0))
            if date_from:
                stmt_horas = stmt_horas.where(
                    Incidencia.fecha_creacion >= datetime.fromisoformat(date_from))
            if date_to:
                stmt_horas = stmt_horas.where(
                    Incidencia.fecha_creacion <= datetime.fromisoformat(date_to))
            horas_en_rango = session.execute(stmt_horas).scalar_one()

            return {
                "incidencias_por_estado": incidencias_por_estado,
                "incidencias_por_prioridad_abiertas": incidencias_por_prioridad_abiertas,
                "incidencias_en_rango": incidencias_en_rango,
                "horas_en_rango": float(horas_en_rango),
                "total_clientes_activos": total_clientes_activos,
                "total_equipos": total_equipos,
                "horas_totales_invertidas": float(horas_totales),
                # Cuales de los numeros de arriba responden al filtro de
                # fechas. La pantalla lo usa para rotularlos: sin esto el
                # usuario mueve el rango, ve que casi nada cambia y no tiene
                # como saber cuales miran el rango y cuales son totales.
                # Se lee peor que no tener filtro.
                "responden_al_rango": ["incidencias_en_rango", "horas_en_rango"],
            }

    def operativo(self, dias: int = 30) -> dict:
        """Qué hay que hacer hoy.

        Decidido con el humano el 2026-08-05: el dashboard de LibraDesk es
        **operativo**, no de gestión. Contesta "qué se vence, qué está
        esperando hace mucho, qué hay en el taller y qué no tiene a nadie", no
        "cómo viene el mes". La pantalla que había no era ninguna de las dos:
        cuatro tarjetas con seis totales absolutos que no cambian de un día
        para el otro.

        `dias` es el horizonte de los vencimientos y **se aplica a los tres**
        —contratos, garantías y turnos—, a diferencia del filtro de fechas de
        `summary()`, que tocaba un solo número de seis.

        Todo sale de columnas que ya existen. No hay tabla nueva.
        """
        from .contratos import Contrato
        from .ingresos import IngresoReparacion

        hoy = date.today()
        limite = hoy + timedelta(days=dias)
        ahora = datetime.now()

        with self.session_factory() as session:
            nombre_cliente = dict(session.execute(select(Cliente.id, Cliente.nombre)).all())

            # --- 1. Lo que se vence ------------------------------------------
            contratos = [
                {
                    "id": c.id,
                    "numero": c.numero,
                    "cliente": nombre_cliente.get(c.cliente_id, "—"),
                    "vence": c.fecha_fin.isoformat(),
                    "dias_restantes": (c.fecha_fin - hoy).days,
                    "estado": c.estado,
                }
                for c in session.execute(
                    select(Contrato)
                    .where(Contrato.estado.in_(_CONTRATOS_VIGENTES))
                    .where(Contrato.fecha_fin.is_not(None))
                    .where(Contrato.fecha_fin <= limite)
                    .order_by(Contrato.fecha_fin.asc())
                ).scalars()
            ]

            # Mismo criterio **exacto** que `cliente()`: `estado != "baja"`. El
            # equipo no tiene columna `activo` —el estado es un string— y usar
            # otro filtro acá haría que el total global y el de la ficha del
            # cliente no cerraran entre sí.
            garantias = []
            for e in session.execute(
                select(Equipo)
                .where(Equipo.estado != "baja")
                .where(Equipo.garantia_vence.is_not(None))
                .where(Equipo.garantia_vence <= limite)
                .order_by(Equipo.garantia_vence.asc())
            ).scalars():
                vence = e.garantia_vence
                vence = vence.date() if isinstance(vence, datetime) else vence
                garantias.append({
                    "id": e.id,
                    "equipo": descripcion_equipo(e),
                    "cliente": nombre_cliente.get(e.cliente_id, "—"),
                    "vence": vence.isoformat(),
                    "dias_restantes": (vence - hoy).days,
                })

            # Los turnos ya agendados. `fecha_programada` es cuándo se va a
            # atender — no tiene nada que ver con cuándo entró el ticket.
            agenda = [
                {
                    "id": i.id,
                    "titulo": i.titulo,
                    "cliente": nombre_cliente.get(i.cliente_id, "—"),
                    "cuando": i.fecha_programada.isoformat(),
                    "dias_restantes": (i.fecha_programada.date() - hoy).days,
                    "prioridad": i.prioridad,
                }
                for i in session.execute(
                    select(Incidencia)
                    .where(Incidencia.estado.in_(ESTADOS_ABIERTOS))
                    .where(Incidencia.fecha_programada.is_not(None))
                    .where(Incidencia.fecha_programada <= datetime.combine(limite, datetime.max.time()))
                    .order_by(Incidencia.fecha_programada.asc())
                ).scalars()
            ]

            # --- 2. El backlog, por antigüedad -------------------------------
            #
            # 🔴 Es la pregunta que un sistema de tickets tiene que contestar y
            # la que la pantalla vieja no contestaba: el desglose por estado
            # dice cuántas hay abiertas, no cuántas están esperando hace un mes.
            abiertas = session.execute(
                select(Incidencia)
                .where(Incidencia.estado.in_(ESTADOS_ABIERTOS))
                .order_by(Incidencia.fecha_creacion.asc())
            ).scalars().all()

            def antiguedad(i) -> int:
                return (ahora - i.fecha_creacion).days if i.fecha_creacion else 0

            backlog = {clave: 0 for clave, _, _ in _TRAMOS_BACKLOG}
            for i in abiertas:
                d = antiguedad(i)
                for clave, desde, hasta in _TRAMOS_BACKLOG:
                    if d >= desde and (hasta is None or d <= hasta):
                        backlog[clave] += 1
                        break

            # Ya vienen de la más vieja a la más nueva.
            mas_viejas = [
                {
                    "id": i.id,
                    "titulo": i.titulo,
                    "cliente": nombre_cliente.get(i.cliente_id, "—"),
                    "dias": antiguedad(i),
                    "prioridad": i.prioridad,
                    "estado": i.estado,
                }
                for i in abiertas[:_TOPE_LISTA]
            ]

            # --- 3. Lo que está físicamente en el taller ---------------------
            en_taller = [
                {
                    "id": g.id,
                    "numero": g.numero,
                    "equipo": " ".join(
                        p for p in (g.equipo_tipo, g.equipo_marca, g.equipo_modelo) if p),
                    "cliente": nombre_cliente.get(g.cliente_id, "—"),
                    "dias": (ahora - g.fecha_recepcion).days,
                }
                for g in session.execute(
                    select(IngresoReparacion)
                    .where(IngresoReparacion.fecha_entrega.is_(None))
                    .order_by(IngresoReparacion.fecha_recepcion.asc())
                ).scalars()
            ]

            # --- 4. Lo que no tiene a nadie ----------------------------------
            sin_asignar = session.execute(
                select(func.count()).select_from(Incidencia)
                .where(Incidencia.estado.in_(ESTADOS_ABIERTOS))
                .where(Incidencia.tecnico_id.is_(None))
            ).scalar_one()

            return {
                "dias": dias,
                "hoy": hoy.isoformat(),
                "vencimientos": {
                    "contratos": {"total": len(contratos), "items": contratos[:_TOPE_LISTA]},
                    "garantias": {"total": len(garantias), "items": garantias[:_TOPE_LISTA]},
                    "agenda": {"total": len(agenda), "items": agenda[:_TOPE_LISTA]},
                },
                "backlog": {
                    "total_abiertas": len(abiertas),
                    "por_antiguedad": backlog,
                    "mas_viejas": mas_viejas,
                },
                "taller": {"total": len(en_taller), "items": en_taller[:_TOPE_LISTA]},
                "sin_asignar": sin_asignar,
            }

    def cliente(self, cliente_id: int, dias_garantia: int = 60) -> dict:
        """Lo mismo que `summary()` pero de un solo cliente, mas las dos
        listas que su ficha muestra en pantalla.

        Las tres cosas que pedia el pendiente 24 —parque, incidencias
        abiertas y garantias por vencer— ya las calculaba `ReportesService`
        (reportes de Equipamiento y Garantias), pero solo para volcarlas a un
        xlsx. Aca se responden en una llamada, en vez de que la ficha se baje
        las tres tablas enteras y las filtre en el browser.

        **No valida que el cliente exista**: eso lo hace el router contra
        `ClienteRepository`, que es el que sabe devolver el 404 y la ficha.
        """
        with self.session_factory() as session:
            equipos_por_estado = dict(
                session.execute(
                    select(Equipo.estado, func.count())
                    .where(Equipo.cliente_id == cliente_id)
                    .group_by(Equipo.estado)
                ).all()
            )
            incidencias_por_estado = dict(
                session.execute(
                    select(Incidencia.estado, func.count())
                    .where(Incidencia.cliente_id == cliente_id)
                    .group_by(Incidencia.estado)
                ).all()
            )
            horas = session.execute(
                select(func.coalesce(func.sum(Incidencia.horas_invertidas), 0))
                .where(Incidencia.cliente_id == cliente_id)
            ).scalar_one()
            total_sectores = session.execute(
                select(func.count()).select_from(Sector).where(Sector.cliente_id == cliente_id)
            ).scalar_one()

            # Equipo y tecnico por outerjoin: los dos son opcionales en una
            # incidencia, y en `compulibra` la mayoria de las migradas no
            # tienen ninguno de los dos (ver la nota del pendiente 21).
            abiertas = [
                {
                    "id": i.id,
                    "titulo": i.titulo,
                    "estado": i.estado,
                    "prioridad": i.prioridad,
                    "fecha_creacion": i.fecha_creacion.isoformat() if i.fecha_creacion else None,
                    "equipo_id": i.equipo_id,
                    "equipo": descripcion_equipo(e) if e else None,
                    "tecnico": t.nombre if t else None,
                }
                for i, e, t in session.execute(
                    select(Incidencia, Equipo, Tecnico)
                    .outerjoin(Equipo, Incidencia.equipo_id == Equipo.id)
                    .outerjoin(Tecnico, Incidencia.tecnico_id == Tecnico.id)
                    .where(Incidencia.cliente_id == cliente_id)
                    .where(Incidencia.estado.in_(ESTADOS_ABIERTOS))
                    .order_by(Incidencia.fecha_creacion.desc(), Incidencia.id.desc())
                ).all()
            ]

            # Mismo criterio que el reporte de Garantias: se excluyen las
            # bajas (la garantia de un equipo dado de baja no le importa a
            # nadie) y entran tambien las YA vencidas, que son justamente las
            # que hay que ver primero.
            hoy = date.today()
            limite = hoy + timedelta(days=dias_garantia)
            garantias = []
            for e in session.execute(
                select(Equipo)
                .where(Equipo.cliente_id == cliente_id)
                .where(Equipo.garantia_vence.is_not(None))
                .where(Equipo.estado != "baja")
                .where(Equipo.garantia_vence <= limite)
                .order_by(Equipo.garantia_vence.asc())
            ).scalars():
                vence = e.garantia_vence
                vence_date = vence.date() if isinstance(vence, datetime) else vence
                garantias.append({
                    "id": e.id,
                    "descripcion": descripcion_equipo(e),
                    "serial": e.serial,
                    "sector": e.sector,
                    "ubicacion_oficina": e.ubicacion_oficina,
                    "estado": e.estado,
                    "garantia_vence": vence_date.isoformat(),
                    "dias_restantes": (vence_date - hoy).days,
                })

            return {
                "equipos_por_estado": equipos_por_estado,
                "total_equipos": sum(equipos_por_estado.values()),
                "incidencias_por_estado": incidencias_por_estado,
                "total_incidencias": sum(incidencias_por_estado.values()),
                "incidencias_abiertas": abiertas,
                "garantias": garantias,
                "dias_garantia": dias_garantia,
                "total_sectores": total_sectores,
                "horas_invertidas": float(horas),
            }

    def equipo(self, equipo_id: int) -> dict | None:
        """La ficha de un equipo: que es, **de quien es**, donde esta, y todo
        lo que le paso.

        `None` si el equipo no existe — el router lo traduce a 404, igual que
        la ficha del cliente.

        **Una llamada y no tres.** La pantalla anterior (el diálogo "ver
        historial") pedia incidencias, reparaciones y movimientos por separado
        y no traia el cliente, que era justamente lo que faltaba: la ficha
        decia que el equipo se movio de Admision a Deposito sin decir de que
        cliente era Admision. Aca los cuatro datos salen juntos y el cliente
        viene resuelto.

        Los totales se calculan aca y no en el browser porque son la respuesta
        a "¿lo reemplazo o lo sigo arreglando?": cuanto se lleva gastado en
        reparaciones y cuantas veces fallo.
        """
        with self.session_factory() as session:
            e = session.get(Equipo, equipo_id)
            if e is None:
                return None

            cliente = session.get(Cliente, e.cliente_id)
            deposito = (
                session.get(Deposito, e.deposito_id) if e.deposito_id is not None else None
            )

            Padre = aliased(CategoriaIncidencia)
            incidencias = [
                {
                    "id": i.id,
                    "titulo": i.titulo,
                    "estado": i.estado,
                    "prioridad": i.prioridad,
                    "categoria": _ruta_categoria(cat, padre),
                    "tecnico": t.nombre if t else None,
                    "horas_invertidas": float(i.horas_invertidas) if i.horas_invertidas else 0.0,
                    "fecha_creacion": i.fecha_creacion.isoformat() if i.fecha_creacion else None,
                    "fecha_cierre": i.fecha_cierre.isoformat() if i.fecha_cierre else None,
                    "resolucion": i.resolucion,
                }
                for i, t, cat, padre in session.execute(
                    select(Incidencia, Tecnico, CategoriaIncidencia, Padre)
                    .outerjoin(Tecnico, Incidencia.tecnico_id == Tecnico.id)
                    .outerjoin(CategoriaIncidencia, Incidencia.categoria_id == CategoriaIncidencia.id)
                    .outerjoin(Padre, CategoriaIncidencia.parent_id == Padre.id)
                    .where(Incidencia.equipo_id == equipo_id)
                    .order_by(Incidencia.fecha_creacion.desc(), Incidencia.id.desc())
                ).all()
            ]

            reparaciones = [
                resolver_reparacion(session, r)
                for r in session.execute(
                    select(Reparacion)
                    .where(Reparacion.equipo_id == equipo_id)
                    .order_by(Reparacion.fecha_envio.desc(), Reparacion.id.desc())
                ).scalars()
            ]

            movimientos = [
                _mov_to_dict(m)
                for m in session.execute(
                    select(EquipoMovimiento)
                    .where(EquipoMovimiento.equipo_id == equipo_id)
                    .order_by(EquipoMovimiento.fecha.desc(), EquipoMovimiento.id.desc())
                ).scalars()
            ]

            vence = e.garantia_vence
            vence_date = vence.date() if isinstance(vence, datetime) else vence

            return {
                "equipo": {
                    "id": e.id,
                    "cliente_id": e.cliente_id,
                    "descripcion": descripcion_equipo(e),
                    "tipo": e.tipo,
                    "marca": e.marca,
                    "modelo": e.modelo,
                    "serial": e.serial,
                    "estado": e.estado,
                    "sector": e.sector,
                    "ubicacion_oficina": e.ubicacion_oficina,
                    "deposito_id": e.deposito_id,
                    "deposito_nombre": deposito.nombre if deposito else None,
                    # Donde esta de verdad, ya resuelto: la pantalla no tiene
                    # que elegir entre `sector` y el deposito. Ver `lugar_de`.
                    "lugar": lugar_de(deposito.nombre if deposito else None, e.sector),
                    "garantia_vence": vence_date.isoformat() if vence_date else None,
                    "dias_garantia_restantes": (
                        (vence_date - date.today()).days if vence_date else None
                    ),
                    "fecha_adicion": e.fecha_adicion.isoformat() if e.fecha_adicion else None,
                    "observaciones": e.observaciones,
                },
                "cliente": {
                    "id": cliente.id,
                    "nombre": cliente.nombre,
                    "empresa": cliente.empresa,
                    "telefono": cliente.telefono,
                    "email": cliente.email,
                    "ciudad": cliente.ciudad,
                    "activo": cliente.activo,
                } if cliente is not None else None,
                "resumen": {
                    "total_incidencias": len(incidencias),
                    "incidencias_abiertas": sum(
                        1 for i in incidencias if i["estado"] in ESTADOS_ABIERTOS
                    ),
                    "horas_invertidas": round(
                        sum(i["horas_invertidas"] for i in incidencias), 2
                    ),
                    "total_reparaciones": len(reparaciones),
                    "reparaciones_abiertas": sum(1 for r in reparaciones if r["abierta"]),
                    # Lo que ninguna fila suelta contesta: cuanto lleva gastado
                    # este aparato. Con eso al lado del precio de uno nuevo, la
                    # decision de reemplazarlo deja de ser una corazonada.
                    "gastado_reparaciones": round(
                        sum(r["costo"] or 0 for r in reparaciones), 2
                    ),
                    "dias_en_service": sum(r["dias_afuera"] or 0 for r in reparaciones),
                    "total_movimientos": len(movimientos),
                },
                "incidencias": incidencias,
                "reparaciones": reparaciones,
                "movimientos": movimientos,
            }
