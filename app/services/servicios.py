"""Catalogo de servicios reutilizables en remitos y presupuestos.

> *"Lista de servicios para poder reutilizar en los presupuestos (que se pueda
> usar campo libre o items que ya esten preformateados)."*

## El hibrido: el campo libre NO se pierde

Un item de comprobante sigue siendo `{description, qty, unit_price}` de texto
libre, exactamente como antes. Este catalogo **sugiere** mientras se tipea: si
el usuario elige una sugerencia se completan descripcion y precio, y si no,
queda lo que escribio.

Es el patron que [[contalibra]] ya usa contra su catalogo de productos
(`PresupuestoForm.tsx` → `/productos/buscar`), probado y sin fricción. Lo que a
este producto le faltaba no era el patron: era el catalogo contra el cual
buscar.

**Por eso el item NO guarda un `servicio_id`.** Si lo guardara, cambiar el
precio del servicio cambiaria retroactivamente presupuestos ya enviados —
mismo criterio que `description_snapshot` en LibraCommerce. El catalogo acelera
la carga; el comprobante conserva lo que se acordó.

## Por que aca y no en un motor

Se evaluaron las dos alternativas que la pagina de pendientes dejaba abiertas:

- **LibraCommerce** SI admite un item sin stock (`CatalogItemType.SERVICE`, y
  `usecases/sales.py` saltea el movimiento de stock para lo que no sea
  PRODUCT). Pero traerlo a LibraDesk seria importar catalogo, inventario,
  compras, ventas y POS —19 tablas— para un producto que no vende productos.
- **LibraCore**, donde vive el dominio de presupuestos que comparten los tres:
  ahi le daria a [[contalibra]] y [[restolibra]] un SEGUNDO catalogo, al lado
  del de productos que ya buscan desde su propio formulario.

Los otros dos ya tienen su catalogo. El unico sin uno es este.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean, DateTime, Numeric, String, false, func, or_, select, true, update,
)
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base
from . import iva


class Servicio(Base):
    __tablename__ = "servicios"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # `index=True` en el MODELO y no solo en la migracion: si estuviera solo
    # alla, una base creada por `create_all()` —que es como arranca una
    # instancia nueva antes de la primera migracion— quedaria sin los indices,
    # y `test_alembic_construye_lo_mismo_que_create_all` lo caza. El nombre que
    # genera SQLAlchemy (`ix_servicios_nombre`) es el mismo que declara la
    # migracion, asi que los dos caminos convergen.
    nombre: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    # Lo que termina en la descripcion del item si el usuario lo elige. Vacio
    # = se usa el nombre. Existe para el caso real de un servicio cuyo nombre
    # corto sirve para buscarlo ("Mantenimiento") y cuyo texto en el
    # comprobante es mas largo ("Mantenimiento preventivo, incluye limpieza
    # interna y cambio de pasta termica").
    # `server_default` ademas de `default`: el primero es la DDL que ve la base
    # y el segundo lo que pone Python. Declarar solo uno hace que una base
    # creada por `create_all()` no coincida con una creada por la migracion.
    descripcion: Mapped[str] = mapped_column(
        String(500), nullable=False, default="", server_default="",
    )
    # Numeric y no Float: es plata. Un `float` acumula error al multiplicar por
    # cantidad y sumar, y el total del presupuesto termina a centavos del que
    # se muestra fila por fila.
    precio: Mapped[float] = mapped_column(
        Numeric(12, 2), nullable=False, default=0, server_default="0",
    )
    # La alicuota con la que se cotiza este servicio. Es propiedad del
    # servicio y no del cliente: en Argentina el 21 / 10,5 / 27 / exento sale
    # de QUE se vende. Ver `app/services/iva.py`.
    iva_rate: Mapped[float] = mapped_column(
        Numeric(5, 4), nullable=False, default=0.21, server_default="0.21",
    )
    # Un servicio que se deja de ofrecer no se borra: dejaria de sugerirse pero
    # los comprobantes viejos que lo usaron ya guardaron su texto y su precio.
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true(), index=True,
    )
    # Cual de estos servicios es **la hora de trabajo**: el precio con el que se
    # cotiza el trabajo de un reclamo al generarle el remito
    # (`IncidenciaRepository.convertir_a_remito`).
    #
    # Vive aca y no en una tabla de configuracion propia porque este catalogo ya
    # es exactamente eso: un nombre, un precio y una alicuota, editables desde
    # una pantalla que existe (Configuracion -> Servicios). Una tabla de un solo
    # numero habria necesitado migracion, endpoint y pestania nuevas para
    # guardar menos de lo que esta fila ya guarda.
    #
    # 🔴 **Uno solo puede estar marcado**, y lo garantiza el repositorio
    # desmarcando al resto en la misma transaccion --no un indice unico parcial,
    # que SQLite y PostgreSQL declaran distinto--. Con dos marcados, `valor_hora()`
    # devolveria "el primero por nombre" y el precio del trabajo pasaria a
    # depender de como se llamen los servicios: la clase de dato que alguien
    # cambia sin sospechar que le esta moviendo el importe a un remito.
    es_valor_hora: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=false(), index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


def _to_dict(s: Servicio) -> dict:
    return {
        "id": s.id,
        "nombre": s.nombre,
        "descripcion": s.descripcion or "",
        # El texto que va al comprobante, ya resuelto: la pantalla no tiene que
        # repetir la regla de "descripcion o, si esta vacia, el nombre".
        "texto": s.descripcion or s.nombre,
        "precio": float(s.precio or 0),
        "iva_rate": float(s.iva_rate if s.iva_rate is not None else iva.DEFECTO),
        "activo": s.activo,
        "es_valor_hora": s.es_valor_hora,
    }


class ServicioEnUso(Exception):
    """Se intento borrar algo que conviene desactivar."""


class ServicioRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def listar(self, *, incluir_inactivos: bool = False) -> list[dict]:
        with self.session_factory() as session:
            stmt = select(Servicio)
            if not incluir_inactivos:
                stmt = stmt.where(Servicio.activo.is_(True))
            filas = session.execute(stmt.order_by(Servicio.nombre)).scalars().all()
            return [_to_dict(s) for s in filas]

    def buscar(self, q: str, *, limite: int = 8) -> list[dict]:
        """Las sugerencias que se muestran mientras se tipea.

        Busca en nombre Y en descripcion: el nombre es como lo llama quien
        carga el catalogo, y la descripcion lo que lee el cliente. Quien arma
        el presupuesto puede acordarse de cualquiera de los dos.

        Con `q` vacio devuelve lista vacia, no el catalogo entero: el
        desplegable aparece al escribir, no al enfocar el campo.
        """
        q = (q or "").strip()
        if not q:
            return []
        patron = f"%{q}%"
        with self.session_factory() as session:
            filas = session.execute(
                select(Servicio)
                .where(Servicio.activo.is_(True))
                .where(or_(Servicio.nombre.ilike(patron), Servicio.descripcion.ilike(patron)))
                .order_by(Servicio.nombre)
                .limit(limite)
            ).scalars().all()
            return [_to_dict(s) for s in filas]

    def get(self, servicio_id: int) -> dict | None:
        with self.session_factory() as session:
            s = session.get(Servicio, servicio_id)
            return _to_dict(s) if s else None

    def valor_hora(self) -> dict | None:
        """El servicio marcado como hora de trabajo, o `None` si no hay ninguno.

        `None` **no es un error**: es una instancia que todavía no cargó su
        valor hora, y el remito de un reclamo nace igual con la mano de obra en
        cero para que el operador le ponga el precio. Devolver 0 en vez de
        `None` borraría la diferencia entre "no está configurado" y "vale cero",
        que son la misma pantalla pero no el mismo problema.

        Sólo cuenta si está **activo**: dar de baja el servicio es la forma de
        decir que se dejó de usar, y seguir cotizando con él sería usar un
        precio que la pantalla ya no muestra.
        """
        with self.session_factory() as session:
            s = session.execute(
                select(Servicio)
                .where(Servicio.es_valor_hora.is_(True))
                .where(Servicio.activo.is_(True))
            ).scalars().first()
            return _to_dict(s) if s else None

    def _marcar_unico_valor_hora(self, session, servicio_id: int) -> None:
        """Deja a `servicio_id` como el único con el flag puesto.

        En la misma sesión que la escritura que la llama, así que no hay una
        ventana con dos marcados ni con ninguno.
        """
        session.execute(
            update(Servicio)
            .where(Servicio.id != servicio_id)
            .where(Servicio.es_valor_hora.is_(True))
            .values(es_valor_hora=False)
        )

    def crear(self, nombre: str, descripcion: str = "", precio: float = 0,
              iva_rate=None, es_valor_hora: bool = False) -> dict:
        # `iva.validar` explota con `AlicuotaInvalida` ante una alicuota que
        # ARCA no sabe mapear. Se valida al GUARDAR y no al mostrar: una fila
        # ya guardada se muestra como este, aunque la lista cambie.
        alicuota = iva.validar(iva.DEFECTO if iva_rate is None else iva_rate)
        with self.session_factory() as session:
            s = Servicio(
                nombre=nombre.strip(),
                descripcion=(descripcion or "").strip(),
                precio=precio,
                iva_rate=alicuota,
                es_valor_hora=es_valor_hora,
            )
            session.add(s)
            # Antes del commit hace falta el id, y el id lo da el flush.
            session.flush()
            if es_valor_hora:
                self._marcar_unico_valor_hora(session, s.id)
            session.commit()
            session.refresh(s)
            return _to_dict(s)

    def actualizar(self, servicio_id: int, nombre: str, descripcion: str,
                   precio: float, activo: bool, iva_rate=None,
                   es_valor_hora: bool = False) -> dict | None:
        alicuota = iva.validar(iva.DEFECTO if iva_rate is None else iva_rate)
        with self.session_factory() as session:
            s = session.get(Servicio, servicio_id)
            if s is None:
                return None
            s.nombre = nombre.strip()
            s.descripcion = (descripcion or "").strip()
            s.precio = precio
            s.iva_rate = alicuota
            s.activo = activo
            s.es_valor_hora = es_valor_hora
            if es_valor_hora:
                self._marcar_unico_valor_hora(session, servicio_id)
            session.commit()
            session.refresh(s)
            return _to_dict(s)

    def borrar(self, servicio_id: int) -> bool:
        """Borra de verdad.

        Se puede porque **el comprobante no referencia al servicio**: guarda su
        propio texto y su propio precio. Borrar uno no deja ningun presupuesto
        colgado ni le cambia el total a nadie.

        Aun asi la pantalla ofrece desactivar antes que borrar: lo normal es
        dejar de ofrecer un servicio, no olvidarse de que existio.
        """
        with self.session_factory() as session:
            s = session.get(Servicio, servicio_id)
            if s is None:
                return False
            session.delete(s)
            session.commit()
            return True
