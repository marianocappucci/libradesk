"""Contratos de equipos — alquiler, comodato, prestamo, leasing y cesion.

**Por que la entidad se llama `contratos` y no `alquileres`** (lineamientos del
usuario, 2026-08-04): si la entidad se llama por la modalidad, sumar comodatos o
prestamos despues obliga a rehacer el modulo. Modelando el **contrato**, la
modalidad es una columna — `tipo_contrato`— y las seis entran sin tocar el
schema. En la UI el menu dice "Equipos en alquiler", que es lo que el usuario
entiende; adentro es un contrato.

Tres tablas, y cada una existe por un motivo puntual:

- `contratos` — la ficha contractual. **Sin columna `importe`**: ver
  `ContratoPrecio`.
- `contratos_precios` — el importe **con vigencia**. Nunca se sobreescribe el
  precio anterior, asi que una liquidacion de agosto rehecha en diciembre sigue
  dando el numero de agosto.
- `contratos_equipos` — que activo esta puesto, desde cuando y hasta cuando. Un
  reemplazo **cierra** la linea vieja y abre una nueva apuntando a ella; el
  equipo anterior no desaparece del contrato.

**Dos estados derivados, ninguno duplicado en una columna**, mismo criterio con
el que `equipos_reparaciones` deriva el suyo de `fecha_retorno`:

- Linea vigente = `fecha_retiro IS NULL`.
- Precio vigente = `vigencia_hasta IS NULL`.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import (
    Boolean, Date, DateTime, ForeignKey, Integer, Numeric, String, Text,
    UniqueConstraint, func, select,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base

TIPOS_CONTRATO = (
    "alquiler",
    "comodato",
    "prestamo",
    "incluido_en_servicio",
    "leasing",
    "venta_financiada",
)

# Los que llevan una cuota periodica. Los otros tres se entregan sin cobrar por
# el equipo —el comodato va atado a otro servicio, el prestamo es temporal—, asi
# que un precio ahi no significa nada y se rechaza.
TIPOS_CON_CUOTA = ("alquiler", "leasing", "venta_financiada")

ESTADOS_CONTRATO = (
    "borrador",
    "activo",
    "suspendido",
    "vencido",
    "rescindido",
    "finalizado",
)

# Con el contrato en uno de estos ya no se colocan equipos: termino.
ESTADOS_CERRADOS = ("rescindido", "finalizado")

PERIODICIDADES = ("mensual", "bimestral", "trimestral", "semestral", "anual")

# `indice` queda declarado pero se comporta como `manual` hasta que se defina de
# donde sale el indice — es una de las decisiones que el diseno dejo abiertas.
# Declararlo ahora evita una migracion despues solo para agregar un valor.
METODOS_ACTUALIZACION = ("fijo", "manual", "porcentaje", "indice", "dolar", "lista")

MONEDAS = ("ARS", "USD")

MOTIVOS_RETIRO = ("reemplazo", "devolucion", "baja")

_PREFIJO_NUMERO = "CTR-"

# El paso entre dos vigencias contiguas: el precio viejo termina el dia antes de
# que arranque el nuevo, para que no se solapen ni dejen un dia sin precio.
_UN_DIA = timedelta(days=1)


class Contrato(Base):
    __tablename__ = "contratos"
    __table_args__ = (UniqueConstraint("numero"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero: Mapped[str] = mapped_column(String(50), nullable=False)
    tipo_contrato: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # El **locatario**: quien usa el equipo y paga por el.
    cliente_id: Mapped[int] = mapped_column(
        ForeignKey("clientes.id"), nullable=False, index=True,
    )
    # El **propietario**, y `NULL` significa "la empresa de esta instancia" —
    # los datos que ya vivien en `config_empresa`. Se modela asi y no con una
    # tabla de propietarios porque el caso normal es que el dueno seamos
    # nosotros; un cliente-propietario es la excepcion, y esta columna la cubre
    # sin inventar una entidad que casi siempre tendria una sola fila.
    propietario_cliente_id: Mapped[int | None] = mapped_column(
        ForeignKey("clientes.id"), index=True,
    )

    # Donde queda instalado. `sector_id` cuando el cliente tiene sus sectores
    # cargados; `domicilio_instalacion` para la sucursal que todavia no es un
    # sector. Una empresa puede tener varios contratos con equipos en sucursales
    # distintas, que es justo lo que esto permite distinguir.
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectores.id"), index=True)
    domicilio_instalacion: Mapped[str | None] = mapped_column(String(500))

    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # NULL = sin fecha de fin pactada (el caso del alquiler indefinido).
    fecha_fin: Mapped[date | None] = mapped_column(Date, index=True)
    renovacion_automatica: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )

    periodicidad: Mapped[str] = mapped_column(String(20), nullable=False, default="mensual")
    dia_vencimiento: Mapped[int | None] = mapped_column(Integer)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="ARS")
    metodo_actualizacion: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual",
    )

    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="borrador", index=True)

    # Texto libre y **no** FK a `tecnicos`: los lineamientos piden un
    # responsable *comercial*, y este producto no tiene ese catalogo. Inventarlo
    # aca seria tomar una decision de producto que nadie tomo.
    responsable: Mapped[str | None] = mapped_column(String(255))
    observaciones: Mapped[str | None] = mapped_column(Text)
    # Ruta del contrato firmado escaneado. Cargarlo es fase 3 (junto con las
    # actas); la columna existe desde ahora para no migrar dos veces.
    archivo_pdf: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContratoPrecio(Base):
    """El importe del contrato, con vigencia. **Nunca se sobreescribe.**

    Es la decision mas importante del modulo y sale textual de los lineamientos:
    *"nunca deberias sobrescribir el precio anterior"*. Una columna `importe` en
    `contratos` seria la segunda fuente de verdad y volveria irreproducible
    cualquier liquidacion vieja — si en noviembre se rehace la factura de
    agosto, el sistema tiene que conocer el valor **de agosto**.
    """

    __tablename__ = "contratos_precios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contratos.id"), nullable=False, index=True,
    )
    vigencia_desde: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    # NULL = es el precio vigente. Ver el docstring del modulo.
    vigencia_hasta: Mapped[date | None] = mapped_column(Date, index=True)
    importe: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    moneda: Mapped[str] = mapped_column(String(3), nullable=False, default="ARS")
    motivo: Mapped[str | None] = mapped_column(String(50))
    usuario: Mapped[str] = mapped_column(String(255), nullable=False, default="Sistema")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContratoEquipo(Base):
    """La linea del contrato: que activo esta puesto y en que ventana.

    **Aca vive el reemplazo.** Cambiar un equipo no edita esta fila: le pone
    `fecha_retiro` y crea una nueva con `reemplaza_a_id` apuntando a ella. Es lo
    que pedian los lineamientos —*"el reemplazo no elimine el equipo anterior
    del contrato"*— y lo que permite que el contrato diga "del 01/08 al 14/09
    serie A123; desde el 14/09 serie B456".
    """

    __tablename__ = "contratos_equipos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contratos.id"), nullable=False, index=True,
    )
    activo_id: Mapped[int] = mapped_column(
        ForeignKey("activos.id"), nullable=False, index=True,
    )
    fecha_instalacion: Mapped[date] = mapped_column(Date, nullable=False)
    # NULL = el activo sigue puesto. Ver el docstring del modulo.
    fecha_retiro: Mapped[date | None] = mapped_column(Date, index=True)
    motivo_retiro: Mapped[str | None] = mapped_column(String(50))
    # La linea a la que esta sustituye. Nullable: la primera instalacion no
    # reemplaza a nada.
    reemplaza_a_id: Mapped[int | None] = mapped_column(
        ForeignKey("contratos_equipos.id"), index=True,
    )
    tecnico_instalador_id: Mapped[int | None] = mapped_column(
        ForeignKey("tecnicos.id"), index=True,
    )
    # El ticket que causo el cambio, cuando lo hubo. Hoy se carga a mano; en la
    # fase 4 lo va a escribir `ReemplazoService`, igual que ya hace con
    # `equipos_movimientos.incidencia_id`.
    incidencia_id: Mapped[int | None] = mapped_column(
        ForeignKey("incidencias.id"), index=True,
    )
    ubicacion: Mapped[str | None] = mapped_column(String(255))
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --- serializacion -----------------------------------------------------------

def _precio_to_dict(p: ContratoPrecio) -> dict:
    return {
        "id": p.id,
        "contrato_id": p.contrato_id,
        "vigencia_desde": p.vigencia_desde.isoformat() if p.vigencia_desde else None,
        "vigencia_hasta": p.vigencia_hasta.isoformat() if p.vigencia_hasta else None,
        "vigente": p.vigencia_hasta is None,
        "importe": float(p.importe) if p.importe is not None else None,
        "moneda": p.moneda,
        "motivo": p.motivo,
        "usuario": p.usuario,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _linea_to_dict(le: ContratoEquipo, *, activo=None) -> dict:
    from .activos import descripcion_activo

    return {
        "id": le.id,
        "contrato_id": le.contrato_id,
        "activo_id": le.activo_id,
        # Resueltos para que la ficha del contrato no pida un endpoint por fila,
        # mismo criterio que `proveedor_nombre` en las reparaciones.
        "activo_descripcion": descripcion_activo(activo) if activo is not None else None,
        "activo_serial": activo.serial if activo is not None else None,
        "activo_codigo_interno": activo.codigo_interno if activo is not None else None,
        "fecha_instalacion": (
            le.fecha_instalacion.isoformat() if le.fecha_instalacion else None
        ),
        "fecha_retiro": le.fecha_retiro.isoformat() if le.fecha_retiro else None,
        # Derivado, nunca almacenado.
        "vigente": le.fecha_retiro is None,
        "motivo_retiro": le.motivo_retiro,
        "reemplaza_a_id": le.reemplaza_a_id,
        "tecnico_instalador_id": le.tecnico_instalador_id,
        "incidencia_id": le.incidencia_id,
        "ubicacion": le.ubicacion,
        "observaciones": le.observaciones,
    }


def _to_dict(
    c: Contrato, *, cliente_nombre: str | None = None,
    propietario_nombre: str | None = None, precio: ContratoPrecio | None = None,
    equipos_vigentes: int = 0, lineas: list[dict] | None = None,
    precios: list[dict] | None = None,
) -> dict:
    d = {
        "id": c.id,
        "numero": c.numero,
        "tipo_contrato": c.tipo_contrato,
        "cliente_id": c.cliente_id,
        "cliente_nombre": cliente_nombre,
        "propietario_cliente_id": c.propietario_cliente_id,
        # `None` en el id significa "la empresa de esta instancia"; el nombre lo
        # pone la UI desde `config_empresa`, no este modulo.
        "propietario_nombre": propietario_nombre,
        "sector_id": c.sector_id,
        "domicilio_instalacion": c.domicilio_instalacion,
        "fecha_inicio": c.fecha_inicio.isoformat() if c.fecha_inicio else None,
        "fecha_fin": c.fecha_fin.isoformat() if c.fecha_fin else None,
        "renovacion_automatica": bool(c.renovacion_automatica),
        "periodicidad": c.periodicidad,
        "dia_vencimiento": c.dia_vencimiento,
        "moneda": c.moneda,
        "metodo_actualizacion": c.metodo_actualizacion,
        "estado": c.estado,
        "responsable": c.responsable,
        "observaciones": c.observaciones,
        "archivo_pdf": c.archivo_pdf,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        # Derivados: el importe vigente NO es una columna del contrato.
        "importe_vigente": float(precio.importe) if precio is not None else None,
        "precio_vigente_desde": (
            precio.vigencia_desde.isoformat()
            if precio is not None and precio.vigencia_desde else None
        ),
        "lleva_cuota": c.tipo_contrato in TIPOS_CON_CUOTA,
        "equipos_vigentes": equipos_vigentes,
    }
    if lineas is not None:
        d["lineas"] = lineas
    if precios is not None:
        d["precios"] = precios
    return d


class ContratoRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    # --- helpers internos ---------------------------------------------------

    def _siguiente_numero(self, session) -> str:
        """`CTR-00000001`, correlativo. Misma forma que `PRES-NNNNNNNN`.

        Se calcula del maximo dentro de la misma transaccion que inserta, que es
        lo que evita el duplicado entre dos altas simultaneas; el
        `UniqueConstraint` esta abajo como red, y a diferencia de las FK **si**
        se ejecuta en SQLite (el pragma apagado es `foreign_keys`, no las
        constraints de unicidad).
        """
        ultimo = session.execute(
            select(func.max(Contrato.numero)).where(
                Contrato.numero.like(f"{_PREFIJO_NUMERO}%")
            )
        ).scalar_one_or_none()
        siguiente = 1 if not ultimo else int(ultimo.removeprefix(_PREFIJO_NUMERO)) + 1
        return f"{_PREFIJO_NUMERO}{siguiente:08d}"

    def _precio_vigente(self, session, contrato_id: int) -> ContratoPrecio | None:
        return session.execute(
            select(ContratoPrecio).where(
                ContratoPrecio.contrato_id == contrato_id,
                ContratoPrecio.vigencia_hasta.is_(None),
            )
        ).scalars().first()

    def _validar_campos(self, data: dict) -> None:
        tipo = data.get("tipo_contrato")
        if tipo is not None and tipo not in TIPOS_CONTRATO:
            raise ValueError(f"Tipo de contrato inválido: {tipo}")
        for campo, validos, etiqueta in (
            ("estado", ESTADOS_CONTRATO, "Estado"),
            ("periodicidad", PERIODICIDADES, "Periodicidad"),
            ("metodo_actualizacion", METODOS_ACTUALIZACION, "Método de actualización"),
            ("moneda", MONEDAS, "Moneda"),
        ):
            valor = data.get(campo)
            if valor is not None and valor not in validos:
                raise ValueError(f"{etiqueta} inválida: {valor}")

        dia = data.get("dia_vencimiento")
        if dia is not None and not 1 <= dia <= 31:
            raise ValueError("El día de vencimiento tiene que estar entre 1 y 31")

        inicio, fin = data.get("fecha_inicio"), data.get("fecha_fin")
        if inicio and fin and fin < inicio:
            raise ValueError("La fecha de fin no puede ser anterior a la de inicio")

    # --- contrato -----------------------------------------------------------

    def create(self, *, importe: Decimal | float | None = None,
               usuario: str = "Sistema", **data) -> dict:
        """Crea el contrato y, si lleva cuota, su **primer precio**.

        El importe viaja en el alta y no en una llamada aparte a proposito:
        separarlos admite un contrato de alquiler activo sin ningun precio, que
        es un estado del que despues no se puede derivar cuanto cobrar. Mismo
        criterio con el que `DatosService` viaja dentro del reemplazo.
        """
        self._validar_campos(data)
        tipo = data["tipo_contrato"]
        if importe is not None and tipo not in TIPOS_CON_CUOTA:
            raise ValueError(
                f"Un contrato de tipo {tipo!r} no lleva cuota, así que no puede "
                "tener importe."
            )

        with self.session_factory() as session:
            data.setdefault("numero", self._siguiente_numero(session))
            c = Contrato(**data)
            session.add(c)
            session.flush()

            if importe is not None:
                session.add(ContratoPrecio(
                    contrato_id=c.id,
                    vigencia_desde=c.fecha_inicio,
                    importe=Decimal(str(importe)),
                    moneda=c.moneda,
                    motivo="alta",
                    usuario=usuario,
                ))
            session.commit()
            session.refresh(c)
            return self._resolver(session, c)

    def _resolver(self, session, c: Contrato, *, detalle: bool = False) -> dict:
        from .activos import Activo
        from .clientes import Cliente

        nombres = dict(
            session.execute(
                select(Cliente.id, Cliente.nombre).where(
                    Cliente.id.in_([
                        i for i in (c.cliente_id, c.propietario_cliente_id)
                        if i is not None
                    ])
                )
            ).all()
        )
        lineas_orm = list(session.execute(
            select(ContratoEquipo)
            .where(ContratoEquipo.contrato_id == c.id)
            .order_by(ContratoEquipo.fecha_instalacion.desc(), ContratoEquipo.id.desc())
        ).scalars())
        vigentes = sum(1 for le in lineas_orm if le.fecha_retiro is None)

        lineas = precios = None
        if detalle:
            activos = {
                a.id: a for a in session.execute(
                    select(Activo).where(
                        Activo.id.in_([le.activo_id for le in lineas_orm] or [0])
                    )
                ).scalars()
            }
            lineas = [
                _linea_to_dict(le, activo=activos.get(le.activo_id))
                for le in lineas_orm
            ]
            precios = [
                _precio_to_dict(p) for p in session.execute(
                    select(ContratoPrecio)
                    .where(ContratoPrecio.contrato_id == c.id)
                    .order_by(ContratoPrecio.vigencia_desde.desc(), ContratoPrecio.id.desc())
                ).scalars()
            ]

        return _to_dict(
            c,
            cliente_nombre=nombres.get(c.cliente_id),
            propietario_nombre=nombres.get(c.propietario_cliente_id),
            precio=self._precio_vigente(session, c.id),
            equipos_vigentes=vigentes,
            lineas=lineas,
            precios=precios,
        )

    def list(self, *, cliente_id: int | None = None, estado: str | None = None,
             tipo_contrato: str | None = None, activo_id: int | None = None) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Contrato).order_by(Contrato.fecha_inicio.desc(), Contrato.id.desc())
            if cliente_id is not None:
                stmt = stmt.where(Contrato.cliente_id == cliente_id)
            if estado is not None:
                stmt = stmt.where(Contrato.estado == estado)
            if tipo_contrato is not None:
                stmt = stmt.where(Contrato.tipo_contrato == tipo_contrato)
            if activo_id is not None:
                stmt = stmt.where(Contrato.id.in_(
                    select(ContratoEquipo.contrato_id)
                    .where(ContratoEquipo.activo_id == activo_id)
                ))
            return [self._resolver(session, c) for c in session.execute(stmt).scalars()]

    def get(self, contrato_id: int) -> dict | None:
        with self.session_factory() as session:
            c = session.get(Contrato, contrato_id)
            if c is None:
                return None
            return self._resolver(session, c, detalle=True)

    def update(self, contrato_id: int, **data) -> dict:
        """Edita la ficha. **El importe no se toca por acá** — para eso está
        `actualizar_precio`, que conserva el histórico."""
        if "importe" in data:
            raise ValueError(
                "El importe no se edita: se actualiza con vigencia "
                "(POST /api/contratos/{id}/precios)."
            )
        with self.session_factory() as session:
            c = session.get(Contrato, contrato_id)
            if c is None:
                raise KeyError(contrato_id)

            fusion = {
                "tipo_contrato": c.tipo_contrato, "estado": c.estado,
                "periodicidad": c.periodicidad, "moneda": c.moneda,
                "metodo_actualizacion": c.metodo_actualizacion,
                "dia_vencimiento": c.dia_vencimiento,
                "fecha_inicio": c.fecha_inicio, "fecha_fin": c.fecha_fin,
                **data,
            }
            self._validar_campos(fusion)

            nuevo_tipo = fusion["tipo_contrato"]
            if (nuevo_tipo not in TIPOS_CON_CUOTA
                    and self._precio_vigente(session, contrato_id) is not None):
                raise ValueError(
                    f"El contrato tiene un precio vigente, así que no puede pasar "
                    f"a tipo {nuevo_tipo!r}, que no lleva cuota."
                )

            for campo, valor in data.items():
                setattr(c, campo, valor)
            session.commit()
            session.refresh(c)
            return self._resolver(session, c, detalle=True)

    def delete(self, contrato_id: int) -> None:
        """Borra solo un contrato en **borrador y sin equipos** — uno cargado por
        error. Un contrato con historia se rescinde o se finaliza; el estado
        conserva lo que paso, borrarlo lo pierde."""
        with self.session_factory() as session:
            c = session.get(Contrato, contrato_id)
            if c is None:
                raise KeyError(contrato_id)
            if c.estado != "borrador":
                raise ValueError(
                    f"Solo se borra un contrato en borrador; éste está {c.estado!r}. "
                    "Usá rescindido o finalizado."
                )
            lineas = session.execute(
                select(func.count()).select_from(ContratoEquipo)
                .where(ContratoEquipo.contrato_id == contrato_id)
            ).scalar_one()
            if lineas:
                raise ValueError(
                    {"equipos": lineas, "detalle": "Retirá los equipos antes de borrar."}
                )
            session.execute(
                ContratoPrecio.__table__.delete().where(
                    ContratoPrecio.contrato_id == contrato_id
                )
            )
            session.delete(c)
            session.commit()

    # --- precios ------------------------------------------------------------

    def actualizar_precio(self, contrato_id: int, *, importe: Decimal | float,
                          vigencia_desde: date, motivo: str | None = None,
                          usuario: str = "Sistema") -> dict:
        """Cierra el precio vigente y abre el nuevo, **en una sola transaccion**.

        Las dos escrituras van juntas porque el estado intermedio —dos precios
        vigentes, o ninguno— es justo el que hace irreproducible una
        liquidacion. El anterior no se modifica en su importe: se le pone
        `vigencia_hasta` el dia antes de que arranque el nuevo.
        """
        with self.session_factory() as session:
            c = session.get(Contrato, contrato_id)
            if c is None:
                raise KeyError(contrato_id)
            if c.tipo_contrato not in TIPOS_CON_CUOTA:
                raise ValueError(
                    f"Un contrato de tipo {c.tipo_contrato!r} no lleva cuota."
                )

            vigente = self._precio_vigente(session, contrato_id)
            if vigente is not None:
                if vigencia_desde <= vigente.vigencia_desde:
                    raise ValueError(
                        f"El precio vigente arranca el "
                        f"{vigente.vigencia_desde.isoformat()}: el nuevo tiene que "
                        "empezar después."
                    )
                # El día anterior, para que las dos vigencias sean contiguas y no
                # se solapen ni dejen un día sin precio.
                vigente.vigencia_hasta = vigencia_desde - _UN_DIA

            nuevo = ContratoPrecio(
                contrato_id=contrato_id, vigencia_desde=vigencia_desde,
                importe=Decimal(str(importe)), moneda=c.moneda,
                motivo=motivo or "actualizacion_manual", usuario=usuario,
            )
            session.add(nuevo)
            session.commit()
            session.refresh(nuevo)
            return _precio_to_dict(nuevo)

    def precio_en(self, contrato_id: int, fecha: date) -> dict | None:
        """El precio que regia en una fecha dada — la consulta que justifica
        toda la tabla. Sin esto, rehacer una liquidacion vieja daria el precio
        de hoy."""
        with self.session_factory() as session:
            p = session.execute(
                select(ContratoPrecio).where(
                    ContratoPrecio.contrato_id == contrato_id,
                    ContratoPrecio.vigencia_desde <= fecha,
                    (ContratoPrecio.vigencia_hasta.is_(None))
                    | (ContratoPrecio.vigencia_hasta >= fecha),
                ).order_by(ContratoPrecio.vigencia_desde.desc())
            ).scalars().first()
            return _precio_to_dict(p) if p is not None else None

    def list_precios(self, contrato_id: int) -> list[dict]:
        with self.session_factory() as session:
            return [
                _precio_to_dict(p) for p in session.execute(
                    select(ContratoPrecio)
                    .where(ContratoPrecio.contrato_id == contrato_id)
                    .order_by(ContratoPrecio.vigencia_desde.desc(), ContratoPrecio.id.desc())
                ).scalars()
            ]

    # --- equipos del contrato -----------------------------------------------

    def colocar(self, contrato_id: int, *, activo_id: int, fecha_instalacion: date,
                tecnico_instalador_id: int | None = None, ubicacion: str | None = None,
                incidencia_id: int | None = None, observaciones: str | None = None,
                reemplaza_a_id: int | None = None) -> dict:
        """Pone un activo en un contrato y lo deja en `colocado`.

        **Es el unico escritor de ese estado**, junto con `retirar()`. Por eso
        `ActivoRepository.update()` rechaza `estado='colocado'`: si el estado se
        pudiera setear por los dos lados, un activo podria decir que esta puesto
        sin ninguna linea que diga donde.
        """
        from .activos import ESTADOS_NO_COLOCABLES, Activo

        with self.session_factory() as session:
            c = session.get(Contrato, contrato_id)
            if c is None:
                raise KeyError(("contrato", contrato_id))
            if c.estado in ESTADOS_CERRADOS:
                raise ValueError(
                    f"El contrato está {c.estado!r}: no se le pueden colocar equipos."
                )

            a = session.get(Activo, activo_id)
            if a is None:
                raise KeyError(("activo", activo_id))
            if a.estado in ESTADOS_NO_COLOCABLES:
                raise ValueError(
                    f"El activo está {a.estado!r} y no se puede colocar."
                )

            # Red aparte del estado: la pregunta que importa es si tiene una
            # linea abierta, y el estado podria haber quedado atras por un
            # arreglo a mano en la base. La verdad esta en las lineas.
            abierta = session.execute(
                select(ContratoEquipo.contrato_id).where(
                    ContratoEquipo.activo_id == activo_id,
                    ContratoEquipo.fecha_retiro.is_(None),
                )
            ).scalars().first()
            if abierta is not None:
                raise ValueError(
                    f"El activo ya está colocado en el contrato {abierta}."
                )

            if fecha_instalacion < c.fecha_inicio:
                raise ValueError(
                    "La instalación no puede ser anterior al inicio del contrato "
                    f"({c.fecha_inicio.isoformat()})."
                )

            linea = ContratoEquipo(
                contrato_id=contrato_id, activo_id=activo_id,
                fecha_instalacion=fecha_instalacion,
                tecnico_instalador_id=tecnico_instalador_id,
                ubicacion=ubicacion, incidencia_id=incidencia_id,
                observaciones=observaciones, reemplaza_a_id=reemplaza_a_id,
            )
            session.add(linea)
            a.estado = "colocado"
            session.commit()
            session.refresh(linea)
            return _linea_to_dict(linea, activo=a)

    def retirar(self, linea_id: int, *, fecha_retiro: date, motivo_retiro: str,
                estado_activo: str,
                observaciones: str | None = None) -> dict:
        """Cierra una linea y devuelve el activo al estado que se le indique.

        `estado_activo` **no tiene default aca** y si lo tiene el modelo del
        router (`retirado_a_revisar`). Es a proposito y costo un hallazgo: con
        el default declarado en los dos lados, el de este metodo no se ejecuta
        nunca —el router siempre manda un valor— y romperlo no ponia ningun
        test en rojo. Un default que no se puede probar es un comentario, no
        codigo.

        Por que `retirado_a_revisar` y no `disponible`: un equipo que vuelve de
        un cliente no esta listo para salir de nuevo hasta que alguien lo mire.
        Ponerlo directo en disponible haria que el selector de "colocar equipo"
        ofrezca equipos que nadie reviso.
        """
        from .activos import _ESTADOS_MANUALES, Activo

        if motivo_retiro not in MOTIVOS_RETIRO:
            raise ValueError(f"Motivo de retiro inválido: {motivo_retiro}")
        if estado_activo not in _ESTADOS_MANUALES:
            raise ValueError(f"Estado inválido para el activo retirado: {estado_activo}")

        with self.session_factory() as session:
            linea = session.get(ContratoEquipo, linea_id)
            if linea is None:
                raise KeyError(linea_id)
            if linea.fecha_retiro is not None:
                raise ValueError(
                    f"La línea ya se cerró el {linea.fecha_retiro.isoformat()}."
                )
            if fecha_retiro < linea.fecha_instalacion:
                raise ValueError(
                    "El retiro no puede ser anterior a la instalación "
                    f"({linea.fecha_instalacion.isoformat()})."
                )

            linea.fecha_retiro = fecha_retiro
            linea.motivo_retiro = motivo_retiro
            if observaciones:
                linea.observaciones = observaciones

            a = session.get(Activo, linea.activo_id)
            if a is not None:
                a.estado = estado_activo
            session.commit()
            session.refresh(linea)
            return _linea_to_dict(linea, activo=a)

    def reemplazar(self, linea_id: int, *, activo_nuevo_id: int, fecha: date,
                   estado_activo_retirado: str,
                   tecnico_instalador_id: int | None = None,
                   incidencia_id: int | None = None,
                   observaciones: str | None = None) -> dict:
        """Sustituye el equipo de una linea **sin borrar la anterior**.

        Cierra la vieja con motivo `reemplazo` y abre una nueva con
        `reemplaza_a_id` apuntando a ella, las dos en la misma fecha. El
        contrato queda contando la historia completa, que es lo que pedian los
        lineamientos.

        Las dos operaciones van en **una transaccion**: partirlas en dos
        requests admite el estado en que el contrato se quedo sin ningun equipo
        puesto, o con dos.
        """
        from .activos import ESTADOS_NO_COLOCABLES, _ESTADOS_MANUALES, Activo

        if estado_activo_retirado not in _ESTADOS_MANUALES:
            raise ValueError(
                f"Estado inválido para el activo retirado: {estado_activo_retirado}"
            )

        with self.session_factory() as session:
            vieja = session.get(ContratoEquipo, linea_id)
            if vieja is None:
                raise KeyError(("linea", linea_id))
            if vieja.fecha_retiro is not None:
                raise ValueError(
                    f"La línea ya se cerró el {vieja.fecha_retiro.isoformat()}."
                )
            if fecha < vieja.fecha_instalacion:
                raise ValueError(
                    "El reemplazo no puede ser anterior a la instalación "
                    f"({vieja.fecha_instalacion.isoformat()})."
                )

            nuevo = session.get(Activo, activo_nuevo_id)
            if nuevo is None:
                raise KeyError(("activo", activo_nuevo_id))
            if nuevo.id == vieja.activo_id:
                raise ValueError("El activo de reemplazo es el mismo que ya está puesto.")
            if nuevo.estado in ESTADOS_NO_COLOCABLES:
                raise ValueError(f"El activo de reemplazo está {nuevo.estado!r}.")

            viejo_activo = session.get(Activo, vieja.activo_id)

            vieja.fecha_retiro = fecha
            vieja.motivo_retiro = "reemplazo"
            if viejo_activo is not None:
                viejo_activo.estado = estado_activo_retirado

            linea = ContratoEquipo(
                contrato_id=vieja.contrato_id, activo_id=activo_nuevo_id,
                fecha_instalacion=fecha, reemplaza_a_id=vieja.id,
                tecnico_instalador_id=tecnico_instalador_id,
                # La ubicacion la hereda: el equipo nuevo va donde estaba el
                # viejo. Mismo criterio que `ReemplazoService`, donde el
                # sustituto toma el lugar del retirado.
                ubicacion=vieja.ubicacion,
                incidencia_id=incidencia_id, observaciones=observaciones,
            )
            session.add(linea)
            nuevo.estado = "colocado"
            session.commit()
            session.refresh(linea)
            session.refresh(vieja)
            return {
                "retirada": _linea_to_dict(vieja, activo=viejo_activo),
                "nueva": _linea_to_dict(linea, activo=nuevo),
            }

    def list_lineas(self, contrato_id: int) -> list[dict]:
        from .activos import Activo

        with self.session_factory() as session:
            lineas = list(session.execute(
                select(ContratoEquipo)
                .where(ContratoEquipo.contrato_id == contrato_id)
                .order_by(ContratoEquipo.fecha_instalacion.desc(), ContratoEquipo.id.desc())
            ).scalars())
            activos = {
                a.id: a for a in session.execute(
                    select(Activo).where(
                        Activo.id.in_([le.activo_id for le in lineas] or [0])
                    )
                ).scalars()
            }
            return [_linea_to_dict(le, activo=activos.get(le.activo_id)) for le in lineas]

    def historial_activo(self, activo_id: int) -> list[dict]:
        """Por donde paso un activo, mas reciente primero — "depósito → cliente
        A → retirado por reparación → cliente B"."""
        with self.session_factory() as session:
            lineas = list(session.execute(
                select(ContratoEquipo)
                .where(ContratoEquipo.activo_id == activo_id)
                .order_by(ContratoEquipo.fecha_instalacion.desc(), ContratoEquipo.id.desc())
            ).scalars())
            contratos = {
                c.id: c for c in session.execute(
                    select(Contrato).where(
                        Contrato.id.in_([le.contrato_id for le in lineas] or [0])
                    )
                ).scalars()
            }
            from .clientes import Cliente
            nombres = dict(session.execute(
                select(Cliente.id, Cliente.nombre).where(
                    Cliente.id.in_([c.cliente_id for c in contratos.values()] or [0])
                )
            ).all())

            salida = []
            for le in lineas:
                c = contratos.get(le.contrato_id)
                fila = _linea_to_dict(le)
                fila["contrato_numero"] = c.numero if c is not None else None
                fila["tipo_contrato"] = c.tipo_contrato if c is not None else None
                fila["cliente_id"] = c.cliente_id if c is not None else None
                fila["cliente_nombre"] = (
                    nombres.get(c.cliente_id) if c is not None else None
                )
                salida.append(fila)
            return salida
