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

from sqlalchemy import Boolean, DateTime, Numeric, String, func, or_, select, true
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base


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
    # Un servicio que se deja de ofrecer no se borra: dejaria de sugerirse pero
    # los comprobantes viejos que lo usaron ya guardaron su texto y su precio.
    activo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true(), index=True,
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
        "activo": s.activo,
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

    def crear(self, nombre: str, descripcion: str = "", precio: float = 0) -> dict:
        with self.session_factory() as session:
            s = Servicio(
                nombre=nombre.strip(),
                descripcion=(descripcion or "").strip(),
                precio=precio,
            )
            session.add(s)
            session.commit()
            session.refresh(s)
            return _to_dict(s)

    def actualizar(self, servicio_id: int, nombre: str, descripcion: str,
                   precio: float, activo: bool) -> dict | None:
        with self.session_factory() as session:
            s = session.get(Servicio, servicio_id)
            if s is None:
                return None
            s.nombre = nombre.strip()
            s.descripcion = (descripcion or "").strip()
            s.precio = precio
            s.activo = activo
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
