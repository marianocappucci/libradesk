"""La conformidad del cliente sobre un trabajo terminado.

Cierra la brecha 7 del backlog de [[lagrace-comunicaciones]]: el pie de su
comprobante en papel dice que **la firma certifica la conformidad** y que el
pago va a 15 dias de la factura. Hoy ese respaldo vive solo en el talonario
archivado; esto lo pone adentro del ticket y lo imprime.

## Que valida, y por que cada cosa

La imagen entra como data URL desde un canvas del navegador. Tres guardas, y
ninguna es defensiva porque si:

1. **Prefijo `data:image/png;base64,`**. Sin esto la columna acepta cualquier
   texto --un `data:text/html` que despues alguien renderice, o simplemente
   basura que rompe el PDF al imprimir--. Se acepta **solo PNG**: es lo que
   produce `canvas.toDataURL()` sin argumentos y lo unico que hace falta
   soportar.
2. **Tamano maximo**. Una columna `Text` acepta 10 MB sin quejarse. Una firma
   de un canvas de 600x200 pesa entre 5 y 40 KB; el tope esta puesto un orden
   de magnitud arriba para no rechazar una pantalla grande, y dos ordenes
   abajo de lo que arruinaria el backup.
3. **Que el base64 decodifique y empiece con la firma PNG**. El prefijo lo
   escribe el cliente: es una promesa, no una verificacion. Sin decodificar,
   `data:image/png;base64,cualquiercosa` pasa el chequeo 1 y el PDF explota al
   imprimir, que es el peor momento para enterarse.

## Lo que NO hace

No es una firma digital ni tiene valor probatorio criptografico: es la imagen
de una firma manuscrita, exactamente el mismo valor que la del papel --que es
lo que se esta reemplazando--. Si alguna vez hace falta valor legal, eso es
firma electronica avanzada y es otro proyecto.
"""

from __future__ import annotations

import base64
import binascii
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from ..database import Base
from .fecha import ahora as _ahora

_PREFIJO = "data:image/png;base64,"
#: 1 MB de data URL. Una firma real pesa entre 5 y 40 KB.
_MAXIMO_BYTES = 1_000_000
#: Los 8 bytes con los que empieza todo PNG.
_MAGIC_PNG = b"\x89PNG\r\n\x1a\n"


class FirmaIncidencia(Base):
    __tablename__ = "incidencias_firmas"

    incidencia_id: Mapped[int] = mapped_column(
        ForeignKey("incidencias.id", ondelete="CASCADE"), primary_key=True,
    )
    firmante: Mapped[str | None] = mapped_column(String(160))
    observaciones: Mapped[str | None] = mapped_column(Text)
    imagen: Mapped[str] = mapped_column(Text, nullable=False)
    firmado_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    usuario_id: Mapped[int | None] = mapped_column(Integer)


def _validar(imagen: str) -> None:
    if not imagen.startswith(_PREFIJO):
        raise ValueError("La firma tiene que ser un PNG en base64 (data URL).")
    if len(imagen) > _MAXIMO_BYTES:
        raise ValueError("La firma es demasiado grande.")
    crudo = imagen[len(_PREFIJO):]
    try:
        binario = base64.b64decode(crudo, validate=True)
    except (binascii.Error, ValueError) as e:
        raise ValueError("La firma no es base64 valido.") from e
    if not binario.startswith(_MAGIC_PNG):
        # El prefijo lo escribe el cliente; esto lo comprueba.
        raise ValueError("La firma no es un PNG.")


def _a_dict(f: FirmaIncidencia) -> dict:
    return {
        "incidencia_id": f.incidencia_id,
        "firmante": f.firmante,
        "observaciones": f.observaciones,
        "imagen": f.imagen,
        "firmado_at": f.firmado_at.isoformat() if f.firmado_at else None,
    }


class FirmaRepository:
    def __init__(self, session_factory: sessionmaker):
        self.session_factory = session_factory

    def obtener(self, incidencia_id: int) -> dict | None:
        with self.session_factory() as session:
            f = session.get(FirmaIncidencia, incidencia_id)
            return _a_dict(f) if f else None

    def guardar(self, incidencia_id: int, imagen: str, *, firmante: str = "",
                observaciones: str = "", usuario_id: int | None = None) -> dict:
        """Alta o reemplazo de la conformidad.

        **Reemplaza en vez de acumular**, y es una decision: una firma mal
        tomada --el dedo resbalo, firmo la persona equivocada-- se corrige
        volviendo a firmar delante del cliente. Guardar las dos obligaria a
        elegir cual es la buena, y la respuesta siempre seria "la ultima".
        """
        _validar(imagen)
        with self.session_factory() as session:
            f = session.get(FirmaIncidencia, incidencia_id)
            if f is None:
                f = FirmaIncidencia(incidencia_id=incidencia_id)
                session.add(f)
            f.imagen = imagen
            f.firmante = (firmante or "").strip() or None
            f.observaciones = (observaciones or "").strip() or None
            # Hora de Argentina, no del contenedor: una conformidad firmada a
            # las 21:00 no puede quedar fechada al dia siguiente. Ver
            # `app/services/fecha.py`.
            f.firmado_at = _ahora()
            f.usuario_id = usuario_id
            session.commit()
            session.refresh(f)
            return _a_dict(f)

    def borrar(self, incidencia_id: int) -> bool:
        with self.session_factory() as session:
            f = session.get(FirmaIncidencia, incidencia_id)
            if f is None:
                return False
            session.delete(f)
            session.commit()
            return True
