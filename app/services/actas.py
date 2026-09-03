"""Actas de entrega y devolución — **fase 3** del módulo de alquiler.

El hueco que cierra, en una línea: hasta hoy se entregaba un equipo y no
quedaba papel que lo probara. El contrato decía qué se pactó y
`contratos_equipos` desde cuándo está puesto, pero el momento físico —quién lo
llevó, quién lo recibió, con qué accesorios, en qué estado— no se registraba en
ningún lado. Cuando el equipo vuelve sin el cargador, no hay nada firmado que
diga que salió con cargador.

Dos tablas, encabezado y líneas:

- `contratos_actas` — el **documento**: tipo, fecha, quién entrega, quién
  recibe, observaciones. Nada del equipo.
- `contratos_actas_lineas` — **una fila por activo**: cómo está, con qué
  accesorios, qué falta, qué daños tiene y cuánto se le cobra por eso.

## Las tres correcciones al diseño del 2026-08-04

El diseño original está en el wiki (`libradesk-alquiler-de-equipos-diseno`) y
se escribió antes de que existiera nada de esto. Lo que cambió, y por qué:

1. **Los campos por equipo van en la línea, no en el encabezado.** El diseño
   listaba `estado_fisico`, `accesorios`, `faltantes`, `danios` y
   `cargo_reposicion` arriba *y* declaraba líneas por activo. Un acta cubre
   varios equipos —se entregan tres el mismo día en un solo papel—, así que un
   `estado_fisico` de encabezado no puede contestar por los tres.

2. **Las firmas son de papel, y hay precedente explícito.** El PR #121
   (revisión `0020`) agregó un pad de firma en pantalla y la revisión `0023` lo
   **retiró**, dropeando `incidencias_firmas`: *"la conformidad del cliente
   vuelve al papel"*. Acá se respeta: `entrega_nombre` y `recibe_nombre` son
   **aclaraciones tipeadas**, el acta se imprime y se firma a mano, y el vínculo
   entre el papel firmado y el registro es el número del comprobante. Una
   casilla "aceptado" que marca el operador no prueba nada.

3. **La maqueta y la leyenda salen de `ingreso_pdf.py`**, que es el generador
   hermano y ya existía cuando se escribió el diseño. Ver `acta_pdf.py`.

## Lo que NO tiene, a propósito

**No hay `pdf_path`.** El diseño lo listaba, pero el PDF es una función de los
datos —igual que el de los ingresos, los remitos y los presupuestos— y se
genera al pedirlo. Una columna con la ruta de un archivo que nadie escribe es
una promesa que la primera lectura desmiente. Lo que sí es un archivo de
verdad es `contratos.archivo_pdf`: el contrato firmado **escaneado**, que entra
cuando el producto tenga dónde guardar archivos subidos.

## Los cargos no se quedan en el acta

Una devolución con faltantes cobra: la suma de los `cargo_reposicion` de las
líneas emite **una** cuota `reposicion` en la misma transacción, y el acta
guarda su `cuota_id`. Sin eso, `cargo_reposicion` sería un número que el
sistema conoce y nunca cobra — exactamente el defecto que la fase 2 vino a
arreglar con el devengado.
"""
from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    select,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base
from .contratos import Contrato, ContratoEquipo

TIPOS_ACTA = ("entrega", "devolucion")

ESTADOS_ACTA = ("emitida", "anulada")

_PREFIJO_NUMERO = "ACT-"

# Los campos que **sólo** tienen sentido devolviendo. En una entrega el equipo
# sale de casa: no hay nada que falte ni que cobrarle a nadie, y aceptarlos
# dejaría actas que describen algo que no pasó.
_CAMPOS_DE_DEVOLUCION = ("faltantes", "danios", "cargo_reposicion")

_CENTAVO = Decimal("0.01")


class ContratoActa(Base):
    """El documento. **Todo lo que dice es del acta, no de los equipos.**"""

    __tablename__ = "contratos_actas"
    __table_args__ = (UniqueConstraint("numero"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    numero: Mapped[str] = mapped_column(String(50), nullable=False)
    contrato_id: Mapped[int] = mapped_column(
        ForeignKey("contratos.id"), nullable=False, index=True,
    )
    #: `entrega` | `devolucion`. Una serie de numeración para los dos, y el tipo
    #: como columna — mismo criterio que `contratos.tipo_contrato`: la modalidad
    #: es un dato del documento, no una entidad aparte.
    tipo: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)

    # Las dos partes, **tipeadas**. No son firmas: ver el docstring del módulo.
    entrega_nombre: Mapped[str | None] = mapped_column(String(255))
    recibe_nombre: Mapped[str | None] = mapped_column(String(255))

    observaciones: Mapped[str | None] = mapped_column(Text)
    estado: Mapped[str] = mapped_column(
        String(20), nullable=False, default="emitida", index=True,
    )
    #: La cuota de reposición que emitió esta acta, cuando cobró algo. Sin FK a
    #: nada de afuera: `contratos_cuotas` es de este mismo producto.
    cuota_id: Mapped[int | None] = mapped_column(
        ForeignKey("contratos_cuotas.id"), index=True,
    )
    usuario: Mapped[str] = mapped_column(String(255), nullable=False, default="Sistema")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ContratoActaLinea(Base):
    """Un equipo dentro del acta, con su estado. Ver la corrección 1 del módulo.

    Cuelga de `contratos_equipos` y no de `activos` directo, y la diferencia
    importa: un mismo activo puede haber estado puesto, retirado y vuelto a
    poner en el mismo contrato, o sea dos líneas distintas. Apuntando a la
    **colocación** el acta dice de cuál de las dos habla; apuntando al activo
    sería ambiguo justo en el caso en que alguien va a discutir.
    """

    __tablename__ = "contratos_actas_lineas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    acta_id: Mapped[int] = mapped_column(
        ForeignKey("contratos_actas.id"), nullable=False, index=True,
    )
    contrato_equipo_id: Mapped[int] = mapped_column(
        ForeignKey("contratos_equipos.id"), nullable=False, index=True,
    )

    estado_fisico: Mapped[str | None] = mapped_column(Text)
    accesorios: Mapped[str | None] = mapped_column(Text)
    # Los tres de devolución. Ver `_CAMPOS_DE_DEVOLUCION`.
    faltantes: Mapped[str | None] = mapped_column(Text)
    danios: Mapped[str | None] = mapped_column(Text)
    cargo_reposicion: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    observaciones: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


# --- serialización -----------------------------------------------------------

def _importe(valor) -> float | None:
    return float(valor) if valor is not None else None


def _linea_to_dict(le: ContratoActaLinea, *, equipo=None, activo=None) -> dict:
    from .activos import descripcion_activo

    return {
        "id": le.id,
        "acta_id": le.acta_id,
        "contrato_equipo_id": le.contrato_equipo_id,
        # Resueltos acá para que la ficha no pida un endpoint por fila, mismo
        # criterio que `activo_descripcion` en las líneas del contrato.
        "activo_id": equipo.activo_id if equipo is not None else None,
        "activo_descripcion": descripcion_activo(activo) if activo is not None else None,
        "activo_serial": activo.serial if activo is not None else None,
        "activo_codigo_interno": activo.codigo_interno if activo is not None else None,
        "estado_fisico": le.estado_fisico,
        "accesorios": le.accesorios,
        "faltantes": le.faltantes,
        "danios": le.danios,
        "cargo_reposicion": _importe(le.cargo_reposicion),
        "observaciones": le.observaciones,
    }


def _to_dict(a: ContratoActa, *, lineas: list[dict] | None = None,
             contrato_numero: str | None = None,
             cliente_nombre: str | None = None) -> dict:
    d = {
        "id": a.id,
        "numero": a.numero,
        "contrato_id": a.contrato_id,
        "contrato_numero": contrato_numero,
        "cliente_nombre": cliente_nombre,
        "tipo": a.tipo,
        "fecha": a.fecha.isoformat() if a.fecha else None,
        "entrega_nombre": a.entrega_nombre,
        "recibe_nombre": a.recibe_nombre,
        "observaciones": a.observaciones,
        "estado": a.estado,
        "anulada": a.estado == "anulada",
        "cuota_id": a.cuota_id,
        "usuario": a.usuario,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
    if lineas is not None:
        d["lineas"] = lineas
        d["equipos"] = len(lineas)
        # Derivado, nunca almacenado: es la suma de las líneas y guardarlo
        # aparte sería la segunda fuente de verdad del mismo número.
        total = sum(
            Decimal(str(le["cargo_reposicion"]))
            for le in lineas if le["cargo_reposicion"]
        )
        d["cargo_total"] = float(total) if total else 0.0
    return d


class ActaRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    # --- helpers internos ---------------------------------------------------

    def _siguiente_numero(self, session) -> str:
        """`ACT-00000001`, correlativo y **compartido entre los dos tipos**.

        Se calcula del máximo dentro de la misma transacción que inserta, igual
        que `CTR-`: es lo que evita el duplicado entre dos altas simultáneas, y
        el `UniqueConstraint` queda abajo como red.
        """
        ultimo = session.execute(
            select(func.max(ContratoActa.numero)).where(
                ContratoActa.numero.like(f"{_PREFIJO_NUMERO}%")
            )
        ).scalar_one_or_none()
        siguiente = 1 if not ultimo else int(ultimo.removeprefix(_PREFIJO_NUMERO)) + 1
        return f"{_PREFIJO_NUMERO}{siguiente:08d}"

    def _equipos_del_contrato(self, session, contrato_id: int) -> dict[int, ContratoEquipo]:
        return {
            le.id: le for le in session.execute(
                select(ContratoEquipo).where(ContratoEquipo.contrato_id == contrato_id)
            ).scalars()
        }

    def _ya_documentada(self, session, contrato_equipo_id: int, tipo: str) -> str | None:
        """El número del acta **no anulada** que ya documentó esa colocación.

        Es la idempotencia del módulo, y vive en Python y no en un índice único
        parcial por un motivo concreto: el estado que hay que mirar
        —`anulada`— está en el encabezado y la unicidad sería sobre la línea, y
        un índice parcial no puede leer la otra tabla. Anular el acta libera la
        colocación, que es lo que permite rehacer una que salió mal.
        """
        return session.execute(
            select(ContratoActa.numero)
            .join(ContratoActaLinea, ContratoActaLinea.acta_id == ContratoActa.id)
            .where(
                ContratoActaLinea.contrato_equipo_id == contrato_equipo_id,
                ContratoActa.tipo == tipo,
                ContratoActa.estado != "anulada",
            ).limit(1)
        ).scalar_one_or_none()

    def _validar_linea(self, datos: dict, *, tipo: str, equipo: ContratoEquipo) -> None:
        if tipo == "entrega":
            sobran = [c for c in _CAMPOS_DE_DEVOLUCION if datos.get(c) not in (None, "")]
            if sobran:
                raise ValueError(
                    f"Un acta de entrega no lleva {', '.join(sobran)}: el equipo "
                    "sale de acá, así que no hay nada que falte ni que cobrar. "
                    "Esos campos son de la devolución."
                )
        elif equipo.fecha_retiro is None:
            raise ValueError(
                "El equipo figura instalado: no se puede documentar su "
                "devolución mientras el contrato lo tenga puesto. Primero "
                "«Retirar equipo», que es lo que registra que volvió."
            )

        cargo = datos.get("cargo_reposicion")
        if cargo is not None and Decimal(str(cargo)) < 0:
            raise ValueError("El cargo de reposición no puede ser negativo")

    def _cuota_de_reposicion(self, session, contrato: Contrato, acta: ContratoActa,
                             total: Decimal):
        """La cuota que cobra los faltantes, **en la misma transacción**.

        Se construye la fila acá en vez de llamar a `CuotaRepository`, y no es
        por evitar la dependencia: ese repositorio abre su propia sesión, así
        que el acta commitearía primero y un fallo del cargo dejaría el papel
        emitido sin nada que cobrar. La aritmética no se duplica —`periodo_de`
        y `vencimiento_de` son las de `cuotas.py`—, sólo el `INSERT`.
        """
        from .cuotas import ContratoCuota, periodo_de, vencimiento_de

        periodo = periodo_de(contrato, acta.fecha)
        cuota = ContratoCuota(
            contrato_id=contrato.id,
            periodo_desde=periodo.desde, periodo_hasta=periodo.hasta,
            concepto=f"Reposición s/acta {acta.numero}",
            tipo_cargo="reposicion",
            fecha_emision=acta.fecha,
            fecha_vencimiento=vencimiento_de(contrato, periodo),
            importe_base=total, importe_total=total,
            moneda=contrato.moneda,
            observaciones=f"Faltantes y daños del acta {acta.numero}.",
        )
        session.add(cuota)
        session.flush()
        return cuota

    def _resolver(self, session, a: ContratoActa, *, detalle: bool = True) -> dict:
        from .activos import Activo
        from .clientes import Cliente

        contrato = session.get(Contrato, a.contrato_id)
        cliente = (
            session.get(Cliente, contrato.cliente_id) if contrato is not None else None
        )

        lineas = None
        if detalle:
            filas = list(session.execute(
                select(ContratoActaLinea)
                .where(ContratoActaLinea.acta_id == a.id)
                .order_by(ContratoActaLinea.id)
            ).scalars())
            equipos = {
                le.id: le for le in session.execute(
                    select(ContratoEquipo).where(
                        ContratoEquipo.id.in_([f.contrato_equipo_id for f in filas] or [0])
                    )
                ).scalars()
            }
            activos = {
                act.id: act for act in session.execute(
                    select(Activo).where(
                        Activo.id.in_([e.activo_id for e in equipos.values()] or [0])
                    )
                ).scalars()
            }
            lineas = []
            for f in filas:
                equipo = equipos.get(f.contrato_equipo_id)
                lineas.append(_linea_to_dict(
                    f, equipo=equipo,
                    activo=activos.get(equipo.activo_id) if equipo is not None else None,
                ))

        return _to_dict(
            a, lineas=lineas,
            contrato_numero=contrato.numero if contrato is not None else None,
            cliente_nombre=cliente.nombre if cliente is not None else None,
        )

    # --- API ----------------------------------------------------------------

    def list(self, contrato_id: int) -> list[dict]:
        """Las actas del contrato, la más nueva primero. Con sus líneas: son
        pocas por contrato y la ficha las muestra todas."""
        with self.session_factory() as session:
            actas = session.execute(
                select(ContratoActa)
                .where(ContratoActa.contrato_id == contrato_id)
                .order_by(ContratoActa.fecha.desc(), ContratoActa.id.desc())
            ).scalars()
            return [self._resolver(session, a) for a in actas]

    def get(self, acta_id: int) -> dict | None:
        with self.session_factory() as session:
            a = session.get(ContratoActa, acta_id)
            return None if a is None else self._resolver(session, a)

    def create(self, contrato_id: int, *, tipo: str, fecha: date,
               lineas: list[dict], entrega_nombre: str | None = None,
               recibe_nombre: str | None = None, observaciones: str | None = None,
               usuario: str = "Sistema") -> dict:
        """Emite el acta con sus líneas y, si cobra, su cuota de reposición.

        Todo en una transacción: el papel, sus equipos y el cargo son el mismo
        hecho.
        """
        if tipo not in TIPOS_ACTA:
            raise ValueError(f"Tipo de acta inválido: {tipo}")
        if not lineas:
            raise ValueError(
                "Un acta sin equipos no documenta nada: hay que elegir al menos "
                "uno."
            )

        ids = [le.get("contrato_equipo_id") for le in lineas]
        if len(set(ids)) != len(ids):
            raise ValueError("Hay un equipo repetido en el acta")

        with self.session_factory() as session:
            contrato = session.get(Contrato, contrato_id)
            if contrato is None:
                raise KeyError(("contrato", contrato_id))

            del_contrato = self._equipos_del_contrato(session, contrato_id)
            for datos in lineas:
                equipo = del_contrato.get(datos["contrato_equipo_id"])
                if equipo is None:
                    raise ValueError(
                        f"El equipo {datos['contrato_equipo_id']} no es de este "
                        "contrato"
                    )
                self._validar_linea(datos, tipo=tipo, equipo=equipo)
                previa = self._ya_documentada(session, equipo.id, tipo)
                if previa is not None:
                    raise ValueError(
                        f"Ese equipo ya tiene un acta de {tipo} ({previa}). Si "
                        "está mal, se anula esa y se emite una nueva."
                    )

            acta = ContratoActa(
                numero=self._siguiente_numero(session),
                contrato_id=contrato_id, tipo=tipo, fecha=fecha,
                entrega_nombre=entrega_nombre, recibe_nombre=recibe_nombre,
                observaciones=observaciones, estado="emitida", usuario=usuario,
            )
            session.add(acta)
            session.flush()

            total = Decimal("0")
            for datos in lineas:
                cargo = datos.get("cargo_reposicion")
                cargo = None if cargo in (None, "") else Decimal(str(cargo)).quantize(_CENTAVO)
                if cargo:
                    total += cargo
                session.add(ContratoActaLinea(
                    acta_id=acta.id,
                    contrato_equipo_id=datos["contrato_equipo_id"],
                    estado_fisico=datos.get("estado_fisico"),
                    accesorios=datos.get("accesorios"),
                    faltantes=datos.get("faltantes"),
                    danios=datos.get("danios"),
                    cargo_reposicion=cargo,
                    observaciones=datos.get("observaciones"),
                ))

            if total > 0:
                acta.cuota_id = self._cuota_de_reposicion(
                    session, contrato, acta, total,
                ).id

            session.commit()
            session.refresh(acta)
            return self._resolver(session, acta)

    def anular(self, acta_id: int, *, motivo: str | None = None) -> dict:
        """Anula en vez de borrar, mismo criterio que las cuotas.

        Un acta borrada deja el equipo sin papel y sin rastro de que alguna vez
        lo tuvo. Anulada queda a la vista, y **libera la colocación** para que
        se pueda emitir la correcta.

        Si cobró, se anula también su cuota — y si esa cuota ya salió en un
        remito o está cobrada, no se anula ninguna de las dos: el comprobante
        que ya vio el cliente quedaría sin respaldo.
        """
        from .cuotas import ContratoCuota

        with self.session_factory() as session:
            a = session.get(ContratoActa, acta_id)
            if a is None:
                raise KeyError(acta_id)
            if a.estado == "anulada":
                raise ValueError("El acta ya está anulada")

            if a.cuota_id is not None:
                cuota = session.get(ContratoCuota, a.cuota_id)
                if cuota is not None and cuota.estado != "anulada":
                    if cuota.estado == "cobrada" or cuota.remito_id is not None:
                        raise ValueError(
                            f"El cargo de reposición de esta acta ({cuota.concepto}) "
                            "ya está cobrado o salió en un remito: anular el acta "
                            "dejaría ese cobro sin respaldo. Primero hay que "
                            "revertirlo."
                        )
                    cuota.estado = "anulada"
                    cuota.observaciones = (
                        f"{cuota.observaciones or ''}\nAnulada junto con el acta "
                        f"{a.numero}."
                    ).strip()

            a.estado = "anulada"
            if motivo:
                a.observaciones = f"{a.observaciones or ''}\nAnulada: {motivo}".strip()
            session.commit()
            session.refresh(a)
            return self._resolver(session, a)

    def datos_para_pdf(self, acta_id: int) -> dict | None:
        """Lo que imprime `acta_pdf`, ya resuelto a texto.

        Las etiquetas y los nombres se resuelven acá y no en el generador, por
        el mismo motivo que en `ingreso_pdf`: el generador dibuja, no decide.
        """
        from .clientes import Cliente
        from .contratos import TIPO_CONTRATO_ETIQUETAS

        with self.session_factory() as session:
            a = session.get(ContratoActa, acta_id)
            if a is None:
                return None
            contrato = session.get(Contrato, a.contrato_id)
            cliente = (
                session.get(Cliente, contrato.cliente_id)
                if contrato is not None else None
            )

            datos = self._resolver(session, a)
            datos["contrato"] = {
                "numero": contrato.numero if contrato is not None else "—",
                "tipo": TIPO_CONTRATO_ETIQUETAS.get(
                    contrato.tipo_contrato, contrato.tipo_contrato,
                ) if contrato is not None else "—",
                "domicilio_instalacion": (
                    contrato.domicilio_instalacion if contrato is not None else None
                ),
                "fecha_inicio": (
                    contrato.fecha_inicio.isoformat()
                    if contrato is not None and contrato.fecha_inicio else None
                ),
                "moneda": contrato.moneda if contrato is not None else "ARS",
            }
            datos["cliente"] = {
                "nombre": cliente.nombre if cliente else "—",
                "cuit": (cliente.cuit if cliente else None) or "",
                "domicilio": (cliente.domicilio if cliente else None) or "",
                "telefono": (cliente.telefono if cliente else None) or "",
                "email": (cliente.email if cliente else None) or "",
            }
            return datos
