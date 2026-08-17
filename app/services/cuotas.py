"""El devengado de un contrato: `contratos_cuotas` — fase 2 del modulo.

## Que problema resuelve

Hasta hoy el sistema sabia **cuanto** vale el alquiler de agosto —lo resuelve
`contratos_precios`— pero **nunca decia que agosto se devengo**. El precio de un
contrato se sabia y no se cobraba nunca: no habia ninguna fila que dijera "este
contrato, este mes, este importe".

Eso lo convierte en el insumo de todo lo demas. El remito automatico que pidio
el humano el 2026-08-14 —*"son remitos que se deberian generar automaticamente
en el sistema"*— necesita de donde sacar el periodo que cobra, la idempotencia
de no emitir agosto dos veces, el prorrateo del primer mes y la mora. Todo eso
es la cuota; el remito es el ultimo paso, no el primero.

## Por que un modulo aparte de `contratos.py`

Las otras tres tablas del contrato viven juntas ahi, y esta es la cuarta del
mismo agregado. Se separa por tamanio y no por diseno: `contratos.py` ya son
1.179 lineas, y la aritmetica de periodos —limites del mes, prorrateo por dias,
idempotencia, previsualizacion— es lo bastante grande como para que meterla ahi
tape a lo que ya vive en ese archivo. El modelo va con su logica.

## Las cuatro decisiones del humano (2026-08-15)

1. **Hay abonos de puro servicio.** `abono` entra como un `tipo_contrato` mas,
   con equipos **opcionales**. Es la brecha 11 de las de Lagrace: un abono de
   mantenimiento sin equipo entregado no tenia donde vivir. No hizo falta tocar
   `contratos_equipos`: un contrato sin lineas ya era representable, lo que
   faltaba era el tipo.
2. **El mes se cobra ADELANTADO.** La cuota de agosto se emite el 1 de agosto y
   cubre del 01-08 al 31-08.
3. **Prorrateo proporcional por dias, en las DOS puntas.** Un alquiler que
   arranca el 20 cobra 12/31; uno que termina el 10 cobra 10/31. Sale con
   `tipo_cargo='proporcional'`, que la tabla ya tenia previsto.
4. **La emision es con confirmacion humana**, no un cron. `previsualizar()`
   devuelve lo que se generaria sin escribir nada, y `generar()` lo escribe.

La 4 no se eligio por gusto: la regla del producto es que **nada se factura sin
confirmacion humana** (decision del 2026-08-07), y un remito emitido de mas
obliga a dar de baja a mano la fila de `envios_facturacion` porque el `uniqueid`
de SOS queda quemado. El job automatico se suma despues, sobre este mismo
camino.

## Lo que NO se recalcula

🔴 **El importe se congela al generar.** Si mañana el precio se actualiza con
retroactivo, la cuota ya emitida no se mueve; `precio_id` deja la trazabilidad
de con que precio salio. Recalcular al vuelo haria que reimprimir una
liquidacion vieja diera otro numero, que es exactamente lo que
`contratos_precios` existe para evitar.
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import (
    Date, DateTime, ForeignKey, Index, Numeric, String, Text, func, select, text,
    update,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base
from .contratos import Contrato, ContratoPrecio, TIPOS_CON_CUOTA

# Los cargos que puede llevar una cuota. Cubre los extras de los lineamientos
# sin una tabla por cada uno.
TIPOS_CARGO = (
    "alquiler",
    "proporcional",
    "mantenimiento",
    "instalacion",
    "configuracion",
    "deposito_garantia",
    "reparacion",
    "reposicion",
)

# 🔑 Los que representan **el periodo en si**, contra los que son cargos sueltos.
#
# La diferencia no es cosmetica: es lo que hace idempotente a `generar()`. Un
# periodo tiene UNO de estos —completo o prorrateado, nunca los dos— y puede
# tener ademas cuantos cargos sueltos haga falta. Por eso el unico de abajo se
# arma sobre `(contrato_id, periodo_desde)` filtrando por estos tres, y no sobre
# `(contrato_id, tipo_cargo, periodo_desde)` como decia el diseno del
# 2026-08-04: aquella forma dejaba convivir un `alquiler` y un `proporcional`
# del mismo mes —o sea, cobrar el mes dos veces, una entera y otra a medias— y
# de paso prohibia dos reparaciones en el mismo periodo, que es legitimo.
CARGOS_RECURRENTES = ("alquiler", "proporcional", "mantenimiento")

ESTADOS_CUOTA = ("pendiente", "facturada", "cobrada", "vencida", "anulada")

# Con la cuota en uno de estos ya no se toca: o se cobro o se dio de baja.
ESTADOS_CERRADOS_CUOTA = ("cobrada", "anulada")

# Cuantos meses cubre un periodo, por periodicidad del contrato.
_MESES_POR_PERIODICIDAD = {
    "mensual": 1, "bimestral": 2, "trimestral": 3, "semestral": 6, "anual": 12,
}

_CENTAVO = Decimal("0.01")

# El paso entre dos periodos contiguos: uno termina el dia antes de que arranque
# el siguiente, mismo criterio que las vigencias de `contratos_precios`.
_UN_DIA = timedelta(days=1)


def _redondear(valor: Decimal) -> Decimal:
    """Dos decimales, medio hacia arriba.

    `ROUND_HALF_UP` y no el `ROUND_HALF_EVEN` que trae Python por defecto: el
    banquero redondea 0.125 a 0.12 y una factura argentina lo redondea a 0.13.
    Sobre un prorrateo, que es una division, esto aparece seguido.
    """
    return valor.quantize(_CENTAVO, rounding=ROUND_HALF_UP)


def _ultimo_dia(anio: int, mes: int) -> int:
    return calendar.monthrange(anio, mes)[1]


def _sumar_meses(d: date, meses: int) -> date:
    """`d` mas N meses, recortando el dia al ultimo del mes destino.

    El 31 de enero mas un mes es el 28 (o 29) de febrero. Sin este recorte la
    aritmetica de periodos revienta con `ValueError: day is out of range` en los
    meses cortos, que es un defecto que sale una vez al anio y en produccion.
    """
    total = d.month - 1 + meses
    anio = d.year + total // 12
    mes = total % 12 + 1
    return date(anio, mes, min(d.day, _ultimo_dia(anio, mes)))


@dataclass(frozen=True)
class Periodo:
    """La ventana que cubre una cuota, con sus dos puntas inclusive."""

    desde: date
    hasta: date

    @property
    def dias(self) -> int:
        return (self.hasta - self.desde).days + 1


def periodo_de(contrato: Contrato, ancla: date) -> Periodo:
    """El periodo de FACTURACION de calendario que contiene a `ancla`.

    Envoltorio de `periodo_por_cadencia()` sobre la periodicidad de **cobro**.
    Se separaron el 2026-08-16, cuando aparecio el segundo consumidor de la
    misma aritmetica: las visitas de mantenimiento, que tienen su propia
    cadencia (`contratos.frecuencia_visita`) porque cobrar y visitar no son lo
    mismo — se puede cobrar mensual y visitar trimestral.

    Una sola aritmetica con dos llamadores, y no dos copias que puedan
    divergir: el recorte de dia de `_sumar_meses()` y la alineacion al anio de
    los multi-mes son sutiles, y la segunda copia iba a ser la que se olvidara
    de alguno.
    """
    return periodo_por_cadencia(contrato.periodicidad, ancla)


def vencimiento_de(contrato: Contrato, periodo: Periodo) -> date | None:
    """El `dia_vencimiento` del contrato, dentro del mes en que se emite.

    Se recorta al ultimo dia del mes: un contrato con vencimiento el 31 no
    puede vencer el 31 de febrero. Sin `dia_vencimiento` no se inventa
    ninguno — queda `NULL`, que significa "no pactado".

    Es una funcion del modulo y no un metodo del repositorio por el mismo
    motivo por el que `periodo_de` lo es desde el 2026-08-16: aparecio un
    segundo consumidor —las actas de devolucion, que emiten su cargo de
    reposicion dentro de SU transaccion— y una segunda copia de este recorte
    seria la que se olvidara de febrero.
    """
    if contrato.dia_vencimiento is None:
        return None
    base = periodo.desde
    return date(
        base.year, base.month,
        min(contrato.dia_vencimiento, _ultimo_dia(base.year, base.month)),
    )


def periodo_por_cadencia(cadencia: str, ancla: date) -> Periodo:
    """El periodo de CALENDARIO que **contiene** a `ancla`.

    🔴 **Los periodos son de calendario, no se cuentan desde `fecha_inicio`.**
    El primer intento los anclaba al arranque del contrato —un mensual que
    empieza el 20 devengaba del 20 al 19— y eso **hace imposible el prorrateo**:
    el primer periodo arranca justo el dia que arranca el contrato, asi que
    siempre esta completo y no hay nada que prorratear. Contradecia de plano la
    decision del humano del 2026-08-15 ("proporcional por dias, primer y ultimo
    mes"), y el test que lo cubria compartia la premisa, asi que pasaba en verde.

    Con periodos de calendario, un mensual que arranca el 20 de agosto tiene el
    periodo 01-08 al 31-08 y **cubre 12 de esos 31 dias**, que es de donde sale
    la cuota proporcional.

    Para los multi-mes el bloque se alinea al anio: un trimestral devenga
    ene-mar, abr-jun, jul-sep, oct-dic sin importar cuando arranco el contrato,
    y el primero le sale prorrateado igual que al mensual.
    """
    paso = _MESES_POR_PERIODICIDAD[cadencia]
    # En que bloque del anio cae el ancla. Para el mensual (paso 1) esto es
    # simplemente su mes.
    bloque = (ancla.month - 1) // paso
    desde = date(ancla.year, bloque * paso + 1, 1)
    hasta = _sumar_meses(desde, paso) - _UN_DIA
    return Periodo(desde=desde, hasta=hasta)


class ContratoCuota(Base):
    """El devengado: este contrato, este periodo, este importe.

    **No es un comprobante.** Una cuota dice que el periodo se devengo; el
    comprobante que sale hacia el cliente es el remito, que se genera a partir de
    ella (pieza B) y queda enlazado en `remito_id`.
    """

    __tablename__ = "contratos_cuotas"
    __table_args__ = (
        # El unico que hace idempotente a `generar()`. Es **parcial**: sobre los
        # tres cargos que representan el periodo, no sobre todas las filas. Ver
        # el comentario de `CARGOS_RECURRENTES`.
        #
        # PostgreSQL es el unico motor de este producto (guarda en
        # `app/database.py`), asi que el indice parcial esta disponible sin
        # condiciones.
        Index(
            "ix_cuota_periodo_recurrente",
            "contrato_id", "periodo_desde",
            unique=True,
            # Se escribe con `text()` y no con una expresion sobre las columnas
            # porque todavia no existen como atributos en este punto de la
            # definicion de la clase. Tiene que ser **igual, caracter por
            # caracter**, a la de la migracion: si difieren, `alembic check`
            # reporta el indice como cambio pendiente en cada corrida.
            postgresql_where=text(
                "tipo_cargo IN ('alquiler', 'proporcional', 'mantenimiento') "
                "AND estado <> 'anulada'"
            ),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contratos.id"), nullable=False, index=True,
    )

    periodo_desde: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    periodo_hasta: Mapped[date] = mapped_column(Date, nullable=False)
    concepto: Mapped[str] = mapped_column(String(255), nullable=False)
    tipo_cargo: Mapped[str] = mapped_column(String(30), nullable=False, index=True)

    fecha_emision: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fecha_vencimiento: Mapped[date | None] = mapped_column(Date, index=True)

    importe_base: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    bonificacion: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"),
    )
    impuestos: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"),
    )
    interes_mora: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0"),
    )
    # Congelado al generar, nunca recalculado al leer. Ver el docstring del
    # modulo.
    importe_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="ARS")

    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pendiente", index=True,
    )

    # Con que precio salio. Es la trazabilidad que permite explicar un importe
    # viejo sin tener que reconstruirlo.
    precio_id: Mapped[int | None] = mapped_column(
        ForeignKey("contratos_precios.id"), index=True,
    )
    # El remito que la cobra. Lo escribe la pieza B; la columna existe desde
    # ahora para no migrar dos veces, mismo criterio que `contratos.archivo_pdf`.
    remito_id: Mapped[int | None] = mapped_column(index=True)

    factura_numero: Mapped[str | None] = mapped_column(String(50))
    comprobante_pago: Mapped[str | None] = mapped_column(String(255))
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(c: ContratoCuota, *, contrato_numero: str | None = None,
             cliente_nombre: str | None = None) -> dict:
    return {
        "id": c.id,
        "contrato_id": c.contrato_id,
        "contrato_numero": contrato_numero,
        "cliente_nombre": cliente_nombre,
        "periodo_desde": c.periodo_desde.isoformat(),
        "periodo_hasta": c.periodo_hasta.isoformat(),
        "concepto": c.concepto,
        "tipo_cargo": c.tipo_cargo,
        "fecha_emision": c.fecha_emision.isoformat(),
        "fecha_vencimiento": (
            c.fecha_vencimiento.isoformat() if c.fecha_vencimiento else None
        ),
        "importe_base": float(c.importe_base),
        "bonificacion": float(c.bonificacion),
        "impuestos": float(c.impuestos),
        "interes_mora": float(c.interes_mora),
        "importe_total": float(c.importe_total),
        "moneda": c.moneda,
        "estado": c.estado,
        "precio_id": c.precio_id,
        "remito_id": c.remito_id,
        "factura_numero": c.factura_numero,
        "comprobante_pago": c.comprobante_pago,
        "observaciones": c.observaciones,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


# --- el calculo de una cuota, sin tocar la base ------------------------------

@dataclass
class CuotaPropuesta:
    """Lo que se generaria para un contrato en un periodo. **No se persiste.**

    Existe para que `previsualizar()` y `generar()` compartan el calculo entero
    en vez de tener cada uno el suyo. Si fueran dos caminos, la pantalla podria
    mostrar un numero y la base guardar otro — y nadie se enteraria hasta que un
    cliente reclamara la diferencia.
    """

    contrato_id: int
    contrato_numero: str
    cliente_id: int
    tipo_cargo: str
    periodo: Periodo
    concepto: str
    fecha_emision: date
    fecha_vencimiento: date | None
    importe_total: Decimal
    moneda: str
    precio_id: int | None
    # Los dias efectivamente cubiertos y los del periodo entero. Iguales salvo
    # en el prorrateo, y es lo que la previsualizacion muestra para explicar por
    # que un mes sale menos que el anterior.
    dias_cubiertos: int
    dias_del_periodo: int

    @property
    def prorrateada(self) -> bool:
        return self.tipo_cargo == "proporcional"

    def to_dict(self) -> dict:
        return {
            "contrato_id": self.contrato_id,
            "contrato_numero": self.contrato_numero,
            "cliente_id": self.cliente_id,
            "tipo_cargo": self.tipo_cargo,
            "periodo_desde": self.periodo.desde.isoformat(),
            "periodo_hasta": self.periodo.hasta.isoformat(),
            "concepto": self.concepto,
            "fecha_emision": self.fecha_emision.isoformat(),
            "fecha_vencimiento": (
                self.fecha_vencimiento.isoformat() if self.fecha_vencimiento else None
            ),
            "importe_total": float(self.importe_total),
            "moneda": self.moneda,
            "precio_id": self.precio_id,
            "prorrateada": self.prorrateada,
            "dias_cubiertos": self.dias_cubiertos,
            "dias_del_periodo": self.dias_del_periodo,
        }


_NOMBRE_MES = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)


def _concepto(contrato: Contrato, periodo: Periodo, *, parcial: bool) -> str:
    """El texto que ve el cliente, y que **viaja en la descripcion del remito**.

    No es cosmetico: `armar_payload` del puente manda `periodo_desde` y
    `periodo_hasta` vacios, y el PDF de un remito solo imprime descripcion y
    cantidad. Si el periodo no esta escrito aca, no llega a ninguna parte —
    mismo motivo por el que el `N° CDS` va en la descripcion y no en un campo
    propio.
    """
    etiqueta = "Abono" if contrato.tipo_contrato == "abono" else "Alquiler"
    if periodo.desde.month == periodo.hasta.month and periodo.desde.year == periodo.hasta.year:
        cuando = f"{_NOMBRE_MES[periodo.desde.month - 1]} {periodo.desde.year}"
    else:
        cuando = (
            f"{_NOMBRE_MES[periodo.desde.month - 1]} a "
            f"{_NOMBRE_MES[periodo.hasta.month - 1]} {periodo.hasta.year}"
        )
    texto = f"{etiqueta} {cuando} — {contrato.numero}"
    if parcial:
        # Las fechas van en dd-mm-aaaa, que es el formato de presentacion del
        # ecosistema (decision del 2026-08-12). La base sigue en ISO.
        texto += (
            f" (proporcional {periodo.desde.strftime('%d-%m-%Y')} al "
            f"{periodo.hasta.strftime('%d-%m-%Y')})"
        )
    return texto


class CuotaRepository:
    """Genera y consulta el devengado.

    Dos caminos y un solo calculo: `previsualizar()` arma las propuestas y no
    escribe; `generar()` arma las mismas y las persiste. La confirmacion humana
    vive entre las dos.
    """

    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    # --- calculo ------------------------------------------------------------

    def _proponer(self, session, contrato: Contrato, ancla: date) -> CuotaPropuesta | None:
        """Que cuota corresponde a este contrato en el periodo que contiene a
        `ancla`, o `None` si no corresponde ninguna.

        Devuelve `None` —y no una cuota en cero— cuando el contrato no llega a
        tocar el periodo. Una cuota en cero seria una fila que dice "este mes se
        devengo nada", y eso no es lo mismo que "este mes no se devengo".
        """
        periodo = periodo_de(contrato, ancla)

        # La ventana efectiva: la interseccion entre el periodo y la vida del
        # contrato. Es lo que produce el prorrateo de las dos puntas.
        desde = max(periodo.desde, contrato.fecha_inicio)
        hasta = periodo.hasta if contrato.fecha_fin is None else min(
            periodo.hasta, contrato.fecha_fin,
        )
        if desde > hasta:
            return None  # el contrato no toca este periodo

        cubierto = Periodo(desde=desde, hasta=hasta)
        parcial = cubierto.dias < periodo.dias

        precio = session.execute(
            select(ContratoPrecio).where(
                ContratoPrecio.contrato_id == contrato.id,
                ContratoPrecio.vigencia_desde <= cubierto.desde,
                (ContratoPrecio.vigencia_hasta.is_(None))
                | (ContratoPrecio.vigencia_hasta >= cubierto.desde),
            ).order_by(ContratoPrecio.vigencia_desde.desc())
        ).scalars().first()
        if precio is None:
            return None  # sin precio no hay nada que devengar

        # Prorrateo por dias sobre el periodo COMPLETO, no sobre 30 fijos: un
        # febrero de 28 y un marzo de 31 valen lo mismo por mes, asi que el dia
        # de febrero vale mas. Dividir siempre por 30 le cobraria de menos a
        # febrero y de mas a los meses de 31.
        if parcial:
            importe = _redondear(
                precio.importe * Decimal(cubierto.dias) / Decimal(periodo.dias)
            )
            tipo_cargo = "proporcional"
        else:
            importe = _redondear(precio.importe)
            tipo_cargo = (
                "mantenimiento" if contrato.tipo_contrato == "abono" else "alquiler"
            )

        return CuotaPropuesta(
            contrato_id=contrato.id,
            contrato_numero=contrato.numero,
            cliente_id=contrato.cliente_id,
            tipo_cargo=tipo_cargo,
            periodo=cubierto,
            concepto=_concepto(contrato, cubierto, parcial=parcial),
            # ADELANTADO (decision del humano, 2026-08-15): se emite el primer
            # dia que el contrato cubre del periodo, no al terminarlo.
            fecha_emision=cubierto.desde,
            fecha_vencimiento=self._vencimiento(contrato, cubierto),
            importe_total=importe,
            moneda=precio.moneda or contrato.moneda,
            precio_id=precio.id,
            dias_cubiertos=cubierto.dias,
            dias_del_periodo=periodo.dias,
        )

    def _vencimiento(self, contrato: Contrato, periodo: Periodo) -> date | None:
        return vencimiento_de(contrato, periodo)

    def _ya_tiene_recurrente(self, session, contrato_id: int, periodo_desde: date) -> bool:
        """La otra mitad de la idempotencia: el indice unico impide el
        duplicado, esto impide el error.

        Las anuladas no cuentan, igual que en el indice — anular una cuota tiene
        que permitir volver a generar el periodo.
        """
        return session.execute(
            select(ContratoCuota.id).where(
                ContratoCuota.contrato_id == contrato_id,
                ContratoCuota.periodo_desde == periodo_desde,
                ContratoCuota.tipo_cargo.in_(CARGOS_RECURRENTES),
                ContratoCuota.estado != "anulada",
            ).limit(1)
        ).first() is not None

    # --- previsualizar y generar --------------------------------------------

    def _armar(self, session, ancla: date, *, contrato_id: int | None = None):
        """El calculo compartido por los dos caminos.

        Devuelve `(propuestas, ya_generadas)`: lo que corresponde emitir y lo que
        ya estaba. Lo segundo se muestra en vez de esconderse — que un mes ya
        este emitido es informacion, y una pantalla que simplemente no lo lista
        se lee como "este contrato no devenga".

        🔴 **El periodo se pregunta por contrato, no una vez para todos.** Dos
        contratos con la misma periodicidad pero distinto `fecha_inicio` tienen
        periodos corridos entre si (ver `periodo_de`), asi que una sola consulta
        con un `periodo_desde` comun daria por generado lo que no lo esta.
        """
        stmt = select(Contrato).where(
            Contrato.tipo_contrato.in_(TIPOS_CON_CUOTA),
            Contrato.estado == "activo",
        )
        if contrato_id is not None:
            stmt = stmt.where(Contrato.id == contrato_id)
        contratos = list(session.execute(stmt.order_by(Contrato.numero)).scalars())

        propuestas, ya = [], set()
        for c in contratos:
            p = self._proponer(session, c, ancla)
            if p is None:
                continue
            propuestas.append(p)
            if self._ya_tiene_recurrente(session, c.id, p.periodo.desde):
                ya.add(c.id)
        return propuestas, ya

    def previsualizar(self, ancla: date, *, contrato_id: int | None = None) -> dict:
        """Lo que se generaria, **sin escribir nada**.

        Es la mitad "confirmacion humana" de la decision del 2026-08-15: la
        pantalla muestra esto, alguien lo mira, y recien despues se llama a
        `generar()`.
        """
        with self.session_factory() as session:
            propuestas, ya = self._armar(session, ancla, contrato_id=contrato_id)
            a_generar = [p for p in propuestas if p.contrato_id not in ya]
            return {
                "ancla": ancla.isoformat(),
                "a_generar": [p.to_dict() for p in a_generar],
                "ya_generadas": [
                    p.to_dict() for p in propuestas if p.contrato_id in ya
                ],
                "total": float(
                    sum((p.importe_total for p in a_generar), Decimal("0"))
                ),
            }

    def generar(self, ancla: date, *, contrato_id: int | None = None,
                usuario: str = "Sistema") -> dict:
        """Persiste las cuotas del periodo que contiene a `ancla`.

        Idempotente: correrla dos veces sobre el mismo periodo no duplica nada.
        La segunda vuelta devuelve `generadas: []` y las mismas en
        `ya_generadas`, que es informacion util y no un error — es lo que
        contesta "¿esto ya se emitio?".
        """
        with self.session_factory() as session:
            propuestas, ya = self._armar(session, ancla, contrato_id=contrato_id)
            nuevas = []
            for p in propuestas:
                if p.contrato_id in ya:
                    continue
                cuota = ContratoCuota(
                    contrato_id=p.contrato_id,
                    periodo_desde=p.periodo.desde,
                    periodo_hasta=p.periodo.hasta,
                    concepto=p.concepto,
                    tipo_cargo=p.tipo_cargo,
                    fecha_emision=p.fecha_emision,
                    fecha_vencimiento=p.fecha_vencimiento,
                    importe_base=p.importe_total,
                    importe_total=p.importe_total,
                    moneda=p.moneda,
                    precio_id=p.precio_id,
                    observaciones=f"Generada por {usuario}",
                )
                session.add(cuota)
                nuevas.append(cuota)
            session.commit()
            for c in nuevas:
                session.refresh(c)
            return {
                "generadas": [_to_dict(c) for c in nuevas],
                "ya_generadas": [
                    p.to_dict() for p in propuestas if p.contrato_id in ya
                ],
            }

    # --- consulta y cargos sueltos ------------------------------------------

    def list(self, *, contrato_id: int | None = None, estado: str | None = None,
             desde: date | None = None, hasta: date | None = None) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(ContratoCuota, Contrato.numero).join(
                Contrato, Contrato.id == ContratoCuota.contrato_id,
            )
            if contrato_id is not None:
                stmt = stmt.where(ContratoCuota.contrato_id == contrato_id)
            if estado is not None:
                stmt = stmt.where(ContratoCuota.estado == estado)
            # Se solapa con la ventana pedida, no "empieza adentro": una cuota
            # trimestral que arranca antes del filtro igual toca el periodo.
            if desde is not None:
                stmt = stmt.where(ContratoCuota.periodo_hasta >= desde)
            if hasta is not None:
                stmt = stmt.where(ContratoCuota.periodo_desde <= hasta)
            stmt = stmt.order_by(
                ContratoCuota.periodo_desde.desc(), ContratoCuota.id.desc(),
            )
            return [
                _to_dict(c, contrato_numero=numero)
                for c, numero in session.execute(stmt).all()
            ]

    def get(self, cuota_id: int) -> dict | None:
        with self.session_factory() as session:
            fila = session.execute(
                select(ContratoCuota, Contrato.numero)
                .join(Contrato, Contrato.id == ContratoCuota.contrato_id)
                .where(ContratoCuota.id == cuota_id)
            ).first()
            if fila is None:
                return None
            c, numero = fila
            return _to_dict(c, contrato_numero=numero)

    def agregar_cargo(self, contrato_id: int, *, tipo_cargo: str, concepto: str,
                      importe: Decimal | float, fecha: date,
                      observaciones: str | None = None) -> dict:
        """Un cargo suelto: instalacion, reparacion, reposicion, garantia.

        Va a la misma tabla y no a una propia, que es lo que el diseno eligio
        para no tener una tabla por cada tipo de cargo. No entra al unico
        parcial —no es recurrente—, asi que se pueden cargar dos reparaciones en
        el mismo mes, que es lo que pasa en la calle.
        """
        if tipo_cargo not in TIPOS_CARGO:
            raise ValueError(f"Tipo de cargo inválido: {tipo_cargo}")
        if tipo_cargo in CARGOS_RECURRENTES:
            raise ValueError(
                f"{tipo_cargo!r} es el cargo del período y lo emite «Generar "
                "cuotas», no la carga manual: cargarlo a mano dejaría dos cobros "
                "del mismo mes."
            )
        importe = _redondear(Decimal(str(importe)))
        with self.session_factory() as session:
            c = session.get(Contrato, contrato_id)
            if c is None:
                raise KeyError(contrato_id)
            periodo = periodo_de(c, fecha)
            cuota = ContratoCuota(
                contrato_id=contrato_id,
                periodo_desde=periodo.desde, periodo_hasta=periodo.hasta,
                concepto=concepto, tipo_cargo=tipo_cargo,
                fecha_emision=fecha,
                fecha_vencimiento=self._vencimiento(c, periodo),
                importe_base=importe, importe_total=importe,
                moneda=c.moneda, observaciones=observaciones,
            )
            session.add(cuota)
            session.commit()
            session.refresh(cuota)
            return _to_dict(cuota)

    def convertir_a_remito(self, cuota_ids: list[int], remitos, clientes,
                           usuario_id: int | None = None) -> dict:
        """El remito de las cuotas elegidas — **pieza B de la fase 2**.

        Cierra el pedido del humano del 2026-08-14: *"son remitos que se
        deberian generar automaticamente en el sistema"*. La cuota dice que el
        periodo se devengo; esto emite el comprobante que sale hacia el cliente.

        ## Por que no toca el puente de facturacion

        `ORIGENES_ENVIABLES` de la bandeja es `(ORIGEN_REMITO,)`. Una cuota
        convertida en remito llega a [[sos-contador]] **sin una linea nueva del
        lado del adaptador**: es un remito como cualquier otro. Sumar `cuota`
        como tercer origen habria sido mas fiel y bastante mas caro.

        ## El periodo viaja en la DESCRIPCION

        `armar_payload` del puente manda `periodo_desde` y `periodo_hasta` en
        vacio, y el PDF de un remito **solo imprime descripcion y cantidad**
        (`_draw_items_table` con `show_prices=False`). Asi que el periodo tiene
        que estar escrito en el concepto o no llega a ninguna parte — mismo
        motivo por el que el `N° CDS` va ahi y no en un campo propio. El
        concepto ya lo trae: *"Alquiler agosto 2026 — CTR-00000012"*.

        ## Recibe una LISTA, igual que el de los reclamos

        Un cliente con tres contratos recibe **un** remito por los tres, porque
        es una factura la que va a salir de ahi. Y con un solo camino no hay dos
        formas de armar el remito de una cuota que puedan divergir: el de a una
        es este con la lista de largo 1.

        **Todas del mismo cliente** —un remito se emite a nombre de uno solo— y
        el cliente sale del contrato, no de la cuota.

        **Idempotente por lote**, mismo criterio que `convertir_a_remito()` de
        incidencias: si TODAS apuntan al MISMO remito se devuelve ese (el doble
        click); una mezcla de convertidas y no convertidas es un error, porque
        devolver el remito viejo dejaria a las nuevas sin facturar y en silencio.

        ## Lo que NO se toca: el `estado` de la cuota

        Emitir el remito **no** la pasa a `facturada`. La factura la produce SOS
        Contador desde la bandeja, y hasta que eso ocurra decir "facturada"
        seria afirmar algo que no paso. El hecho de que la cuota ya salio lo
        dice `remito_id`, que es tambien lo que mira la guarda de `anular()`.

        ## Lo que NO es atomico

        Igual que en incidencias: el remito lo escribe la conexion de LibraCore
        y el vinculo lo escribe SQLAlchemy, asi que no hay una transaccion que
        cubra las dos. Se emite primero el remito y despues se ata, porque el
        error al reves es peor — una cuota que dice "ya se remitio" apuntando a
        un remito que no existe no se podria facturar nunca.
        """
        from . import fecha
        from .remitos_presupuestos import datos_cliente_para_comprobante

        # Sin repetidas y en el orden elegido, igual que el de los reclamos: el
        # remito se lee en el mismo orden en que la pantalla las mostraba.
        ids = list(dict.fromkeys(cuota_ids))
        if not ids:
            raise ValueError("No se eligió ninguna cuota.")

        with self.session_factory() as session:
            filas = {
                c.id: c for c in session.execute(
                    select(ContratoCuota).where(ContratoCuota.id.in_(ids))
                ).scalars()
            }
            faltantes = [x for x in ids if x not in filas]
            if faltantes:
                raise KeyError(
                    faltantes[0] if len(faltantes) == 1 else tuple(faltantes)
                )

            # ── Idempotencia del LOTE ────────────────────────────────────
            convertidas = {x: filas[x].remito_id for x in ids if filas[x].remito_id}
            if convertidas:
                unicos = set(convertidas.values())
                if len(convertidas) == len(ids) and len(unicos) == 1:
                    existente = remitos.get(next(iter(unicos)))
                    if existente is not None:
                        return existente
                    # El remito que se referenciaba no está: se borró por fuera.
                    # Se sigue de largo, para no dejar la cuota sin camino.
                else:
                    cuales = ", ".join(f"#{x}" for x in sorted(convertidas))
                    raise ValueError(
                        f"Ya salieron en un remito: {cuales}. Sacalas de la "
                        "selección o emití el remito de las que faltan."
                    )

            anuladas = [x for x in ids if filas[x].estado == "anulada"]
            if anuladas:
                detalle = ", ".join(f"#{x}" for x in sorted(anuladas))
                raise ValueError(
                    f"Están anuladas y no se cobran: {detalle}."
                )

            # El cliente sale del CONTRATO: la cuota no lo guarda, y duplicarlo
            # ahí sería una segunda fuente de verdad sobre a quién se le cobra.
            contratos = {
                c.id: c for c in session.execute(
                    select(Contrato).where(
                        Contrato.id.in_({filas[x].contrato_id for x in ids})
                    )
                ).scalars()
            }
            clientes_del_lote = {
                contratos[filas[x].contrato_id].cliente_id for x in ids
            }
            if len(clientes_del_lote) > 1:
                raise ValueError(
                    "Las cuotas elegidas son de contratos de más de un cliente, "
                    "y un remito se emite a nombre de uno solo."
                )
            cliente_id = clientes_del_lote.pop()

            items = [
                {
                    # El concepto ya trae el período adentro. Ver el docstring:
                    # es lo único que llega al PDF y al puente.
                    "description": filas[x].concepto,
                    # Una cuota es una línea, no N horas: el importe ya está
                    # calculado y congelado.
                    "qty": 1,
                    "unit_price": float(filas[x].importe_total),
                }
                for x in ids
            ]

        cliente = clientes.get(cliente_id)
        if cliente is None:
            raise KeyError(cliente_id)

        remito = remitos.create(
            # El día en que se emite, en hora de Argentina — no la fecha de
            # emisión de la cuota, que puede ser de hace meses si se está
            # poniendo al día un devengado viejo.
            date=fecha.hoy(),
            client_id=cliente["id"],
            client_cuit=cliente["cuit"] or "",
            items=items,
            observations="",
            usuario_id=usuario_id,
            **datos_cliente_para_comprobante(cliente, cliente["domicilio"] or None),
        )

        with self.session_factory() as session:
            # Una sola sentencia, así que no hay un estado intermedio donde la
            # mitad del lote quedó atada al remito y la otra mitad no.
            session.execute(
                update(ContratoCuota)
                .where(ContratoCuota.id.in_(ids))
                .values(remito_id=remito["id"])
            )
            session.commit()
        return remito

    def anular(self, cuota_id: int, *, motivo: str | None = None) -> dict:
        """Anula en vez de borrar, mismo criterio que la baja logica de clientes.

        Una cuota borrada deja un agujero en el devengado que nadie puede
        explicar despues. Anulada, sale del indice parcial —asi el periodo se
        puede volver a generar— y queda a la vista.
        """
        with self.session_factory() as session:
            c = session.get(ContratoCuota, cuota_id)
            if c is None:
                raise KeyError(cuota_id)
            if c.estado == "cobrada":
                raise ValueError(
                    "La cuota está cobrada: anularla dejaría un cobro sin "
                    "devengado. Primero hay que revertir el cobro."
                )
            if c.remito_id is not None:
                raise ValueError(
                    f"La cuota ya salió en un remito (id {c.remito_id}): anularla "
                    "acá dejaría el comprobante sin respaldo."
                )
            c.estado = "anulada"
            if motivo:
                c.observaciones = f"{c.observaciones or ''}\nAnulada: {motivo}".strip()
            session.commit()
            session.refresh(c)
            return _to_dict(c)
