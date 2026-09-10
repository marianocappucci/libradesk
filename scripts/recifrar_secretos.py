#!/usr/bin/env python3
"""Cierra una rotación de `SECRET_KEY`: deja los secretos bajo la clave viva.

    docker exec <contenedor> python scripts/recifrar_secretos.py --ver
    docker exec <contenedor> python scripts/recifrar_secretos.py

**Cuándo se usa.** Después de rotar el `SECRET_KEY` de la instancia, con el
valor anterior declarado en `LIBRAAUTH_CLAVES_ANTERIORES`. Mientras haya
secretos cifrados con la clave vieja, sacar esa variable dejaría la integración
de facturación sin credencial — o sea que la rotación **todavía no terminó**.

El ciclo completo es: rotar, declarar el valor viejo, correr esto, y **sacar la
variable**. Este paso es el único que no se puede saltear sin perder algo.

🔴 **Por qué existe.** El 2026-09-07 se rotó la `SECRET_KEY` de `lagrace` como
respuesta a un incidente y la credencial de SOS Contador quedó ilegible. Se
detectó **20 días después**, de casualidad, mirando la pantalla de
configuración: `config_facturacion.habilitado` seguía en `true` y no se había
intentado emitir nada desde la rotación, así que ni siquiera había un error que
mirar.

**Un secreto que no se puede leer con ninguna clave conocida no se toca** y se
reporta aparte: ése hay que volver a cargarlo por pantalla. Son dos situaciones
distintas y este comando las distingue.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.database import configure, get_session_factory  # noqa: E402
from app.services.facturacion_config import (  # noqa: E402
    ConfiguracionFacturacion,
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Recifra los secretos de facturación.")
    p.add_argument(
        "--ver",
        action="store_true",
        help="solo informa qué secretos dependen de una clave anterior; no escribe",
    )
    args = p.parse_args(argv)

    if not os.environ.get("SECRET_KEY"):
        print("falta SECRET_KEY en el entorno", file=sys.stderr)
        return 2
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        print("falta DATABASE_URL en el entorno", file=sys.stderr)
        return 2
    configure(url)
    config = ConfiguracionFacturacion(get_session_factory())

    pendientes = config.pendientes_de_recifrado()
    if args.ver:
        if pendientes:
            print(f"dependen de una clave anterior ({len(pendientes)}): "
                  f"{', '.join(pendientes)}")
            print("la rotación no terminó: recifrar antes de sacar "
                  "LIBRAAUTH_CLAVES_ANTERIORES")
            return 1
        print("ningún secreto depende de una clave anterior")
        return 0

    cambiados = config.recifrar_secretos()
    if not cambiados:
        print("no había nada que recifrar")
        return 0
    print(f"recifrados ({len(cambiados)}): {', '.join(cambiados)}")

    # Se vuelve a preguntar en vez de confiar en lo que se acaba de hacer: si
    # quedó alguno pendiente, este comando NO puede decir que la rotación cerró.
    quedan = config.pendientes_de_recifrado()
    if quedan:
        print(f"AVISO: siguen dependiendo de una clave anterior: {', '.join(quedan)}",
              file=sys.stderr)
        return 1
    print("ya se puede sacar LIBRAAUTH_CLAVES_ANTERIORES del entorno")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
