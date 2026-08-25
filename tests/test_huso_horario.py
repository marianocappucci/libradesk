"""El huso horario del ecosistema: Argentina, UTC-3 fijo, sin horario de verano.

Regla del proyecto (`wiki/concepts/estandares-desarrollo.md`, sección "Fecha y
hora"). Esta guarda existe porque el defecto **no da error**: hasta el
2026-08-23 los contenedores de este producto corrían en UTC y la suite estaba
entera en verde. Lo único que se veía era el reloj 3 h adelantado, y una vez por
día — entre las 21:00 y la medianoche — `date.today()` devolviendo mañana: una
factura fechada el día siguiente, un cierre de caja del lado equivocado.

Se chequean cuatro cosas por separado, porque fallan por separado:

  1. el proceso que corre la suite;
  2. lo que declara el Dockerfile, que hace la imagen correcta por sí sola;
  3. lo que declara el compose para la app **y para el servidor PostgreSQL**;
  4. la zona en la que está corriendo la base contra la que corre la suite,
     preguntada a la base y no leída de un archivo del repo.

🔴 **Lo tercero tiene dos mitades, y una es fácil de dar por hecha.** Al sidecar
no le alcanza con `TZ`: la imagen de PostgreSQL escribe `timezone` en
`postgresql.conf` UNA vez, en el `initdb`, y ese archivo vive en el volumen de
datos. Sobre un volumen que ya existe, `TZ` cambia el `date` del contenedor y no
cambia nada de lo que hace el servidor — `now()` sigue devolviendo UTC. Y `now()`
es el reloj que estampa los `server_default=func.now()`, así que quedaba
desfasado del reloj del proceso justo después de "arreglarlo".

Se midió: con `TZ` puesta y sin `command:`, `date` adentro del contenedor decía
`-03` y `select now()` seguía dando la hora de Londres. Por eso el chequeo
pregunta por `-c timezone=`, que es lo que sí lo fija.
"""
from datetime import datetime, timedelta
from pathlib import Path

import pytest

TZ = "America/Argentina/Buenos_Aires"
OFFSET = timedelta(hours=-3)
RAIZ = Path(__file__).resolve().parents[1]


def test_el_proceso_de_la_suite_corre_en_hora_de_argentina():
    """No se compara la FECHA a propósito.

    `datetime.now().date() == fecha_en_argentina()` da verdadero 21 de las 24
    horas del día aunque el proceso esté en UTC: se cumpliría por la razón
    equivocada y no serviría de guarda. El offset, en cambio, está mal siempre
    que la zona esté mal.
    """
    assert datetime.now().astimezone().utcoffset() == OFFSET


def test_el_dockerfile_le_fija_la_zona_a_la_imagen():
    assert "ENV TZ=" + TZ in (RAIZ / "Dockerfile").read_text(encoding="utf-8")


@pytest.mark.parametrize("declaracion", [
    pytest.param("- TZ=" + TZ, id="la app, por variable de entorno"),
    pytest.param("TZ: " + TZ, id="el sidecar, por variable de entorno"),
    pytest.param("command: postgres -c timezone=" + TZ,
                 id="el SERVIDOR PostgreSQL, que es lo que TZ no alcanza a mover"),
])
def test_el_compose_fija_la_zona_donde_hace_falta(declaracion):
    assert declaracion in (RAIZ / "docker-compose.yml").read_text(encoding="utf-8")


# ── Lo cuarto: la zona de la BASE, PREGUNTADA y no leída de un archivo ─────
#
# 🔴 Los tres chequeos de arriba miran el proceso y el TEXTO de dos archivos
# del repo. Ninguno pregunta en qué hora está la base contra la que la suite
# realmente corre — y ése es justamente el reloj que estampa `fecha_creacion`
# y los ~30 `created_at` del producto: los declara `server_default=func.now()`,
# así que el valor lo escribe el SERVIDOR PostgreSQL, no la app.
#
# Con el proceso en Argentina y la base en UTC, una incidencia recién creada
# nace tres horas en el futuro. Su antigüedad da −1 día, no cae en ningún
# tramo de `_TRAMOS_BACKLOG` de `app/services/dashboard.py` —todos piden
# `d >= desde` con `desde >= 0`— y el ticket desaparece del backlog del
# dashboard en vez de contarse en «hasta 7 días».
#
# Es exactamente el defecto del 2026-08-23, y así se manifestaba: como un
# `{'hasta_7_dias': 0} != {'hasta_7_dias': 1}` en `test_dashboard_operativo.py`,
# a cuatrocientas líneas de su causa y sin nombrarla.
#
# El compose de este repo ya fija la zona del sidecar, y el chequeo de arriba
# verifica que la línea siga estando. Pero el compose no es la base contra la
# que uno corre la suite en su máquina: un `docker run postgres:16-alpine`
# suelto —sin `TZ` ni `-c timezone=`— levanta un servidor en UTC, y sin este
# chequeo el rojo aparece lejos y no dice esto.
#
# Del lado del proceso no hace falta un chequeo gemelo: `conftest.py` le fija
# la zona al importar, y el primer test de este archivo lo verifica.


def test_el_servidor_de_la_base_corre_en_hora_de_argentina(client):
    """El `TimeZone` de la sesión, preguntado a la base.

    Mismo criterio que el chequeo del proceso: se compara el OFFSET y no la
    fecha, porque el offset está mal siempre que la zona esté mal.

    `select now()` y no `select current_setting('TimeZone')`: lo que importa no
    es cómo se llama la zona sino cuánto se corre el valor, que es lo que
    después queda guardado en las columnas `DateTime` sin zona del producto.
    """
    from sqlalchemy import text

    from app import database

    with database.get_engine().connect() as conn:
        ahora_en_la_base = conn.execute(text("select now()")).scalar_one()

    assert ahora_en_la_base.utcoffset() == OFFSET
