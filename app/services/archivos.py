"""El primer camino de subida de archivos del producto.

Hasta hoy LibraDesk no tenía ninguno: `git grep UploadFile` sobre `app/` daba
**cero**. Los tres routers que sí reciben archivos —datos de empresa, logo y
restore del backup— salen de LibraCore, así que el producto sabía recibir un
logo y un ZIP, y nada más. Por eso `contratos.archivo_pdf` existe desde la fase
1 del módulo de alquiler y seguía sin usarse: la columna estaba, el camino no.

Vive en un módulo propio y no adentro del router de contratos porque **el
contrato firmado no va a ser el único**: el acta conformada y el remito firmado
son el mismo problema. Lo que NO se hace acá es inventar un modelo de adjuntos
con tabla propia — hay un solo consumidor, y una tabla para un caso es diseñar
sobre una suposición.

**Las tres defensas, y por qué cada una.**

1. **El tope se controla mientras se lee, no después.** `await archivo.read()`
   —que es lo que hace el router de logo de LibraCore, donde el archivo pesa
   kilobytes— trae el cuerpo entero a memoria antes de que nadie pueda medirlo.
   Un contrato escaneado no tiene ese techo natural, así que acá se lee de a
   `_CHUNK` y se corta apenas pasa.
2. **El tipo se mira por dentro, no por la extensión.** Un `.pdf` que no
   empieza con `%PDF-` es un archivo que el visor del navegador abre en blanco,
   y el que lo subió se entera el día que lo necesita — que es el día que hay
   una discusión con el cliente sobre lo que firmó.
3. **Se escribe a un temporal y se renombra.** Si el tope salta a mitad de
   camino, el destino no queda con medio archivo encima del anterior. En este
   caso "el anterior" es el contrato firmado que ya estaba bien.
"""
from __future__ import annotations

import os

from fastapi import HTTPException, UploadFile

#: 20 MB. Un contrato de 10 páginas escaneado a 300 dpi en escala de grises
#: pesa 3-4 MB; 20 deja margen para uno en color sin dejar la puerta abierta.
MAX_BYTES = 20 * 1024 * 1024

#: De a 1 MB: chico para que el tope salte temprano, grande para que un archivo
#: legítimo no cueste mil vueltas de loop.
_CHUNK = 1024 * 1024

#: Los cinco bytes con los que la especificación obliga a que arranque un PDF.
_FIRMA_PDF = b"%PDF-"


async def guardar_pdf(archivo: UploadFile, destino: str) -> int:
    """Guarda `archivo` en `destino` si es un PDF y entra en el tope.

    Devuelve el tamaño en bytes. Los errores salen como `HTTPException` con el
    texto que la pantalla muestra tal cual: quien sube un archivo equivocado
    tiene que leer qué pasó, no un código.
    """
    nombre = archivo.filename or ""
    if not nombre.lower().endswith(".pdf"):
        raise HTTPException(422, "El archivo tiene que ser un PDF.")

    os.makedirs(os.path.dirname(destino), exist_ok=True)
    # `.parcial` y no `tempfile`: al lado del destino, así el `os.replace` de
    # abajo es un rename dentro del mismo sistema de archivos y no una copia.
    temporal = f"{destino}.parcial"
    total = 0
    try:
        with open(temporal, "wb") as f:
            primero = True
            while True:
                bloque = await archivo.read(_CHUNK)
                if not bloque:
                    break
                if primero:
                    if not bloque.startswith(_FIRMA_PDF):
                        raise HTTPException(
                            422,
                            "El archivo no es un PDF: no arranca con la firma "
                            "`%PDF-`. Si lo escaneaste como imagen, convertilo "
                            "a PDF antes de subirlo.",
                        )
                    primero = False
                total += len(bloque)
                if total > MAX_BYTES:
                    raise HTTPException(
                        413,
                        f"El archivo supera el máximo de "
                        f"{MAX_BYTES // (1024 * 1024)} MB.",
                    )
                f.write(bloque)
        if total == 0:
            raise HTTPException(422, "El archivo está vacío.")
        os.replace(temporal, destino)
    finally:
        # Corre también en el camino feliz, donde `os.replace` ya se lo llevó.
        if os.path.exists(temporal):
            os.remove(temporal)
    return total
