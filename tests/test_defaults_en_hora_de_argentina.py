"""Ningun DEFAULT del DDL de Libradesk estampa una hora que no sea la de Argentina.

🔴 **El defecto que cubre no daba error y estuvo desde siempre.** El DEFAULT de
las columnas `created_at`/`updated_at` era `datetime('now')`, que en
SQLite es UTC y que el adaptador de PostgreSQL traduce a UTC **a proposito**,
para que las dos bases guarden el mismo texto. O sea que las dos guardaban la
hora equivocada, y de la misma manera. Lo creado entre las 21:00 y la medianoche
quedaba fechado el dia siguiente.

Se midio en la instancia `compulibra` de Contalibra el 2026-08-29 y se barrieron
las 19 bases del VPS con schema de LibraCore: las 19 en UTC. Ver la revision
`0003` de [[libracore]] para el diagnostico completo.

🔑 **El barrido vive en el motor, no aca.** `defaults_fuera_de_hora_ar()` es la
misma funcion que corren LibraCore y los otros tres productos con DDL propio.
Copiar la regex en cada repo es la forma conocida de que empiecen a decir cosas
distintas: paso con las cinco definiciones de "hoy" del frontend, y solo tres
fijaban la zona.

🔑 **Y mira la PROPIEDAD final**, no el patron viejo: "ninguna columna con reloj
queda fuera de la hora de Argentina". Buscar `datetime('now')` dejaria pasar una
columna nueva escrita como `DEFAULT CURRENT_TIMESTAMP`, que tiene el mismo
problema con otra cara.
"""
from pathlib import Path

import pytest
from libracore.db.schema import defaults_con_reloj, defaults_fuera_de_hora_ar

RAIZ = Path(__file__).resolve().parents[1]

#: Se barren los directorios, no una lista de archivos escrita a mano: un DDL
#: nuevo en un modulo nuevo tiene que entrar solo. Las revisiones ya aplicadas
#: quedan afuera porque son historia y no se tocan.
_DIRECTORIOS = ('app',)
_EXCLUIR = ("__pycache__", "/migrations/versions/", "/tests/")


def _fuentes():
    for sub in _DIRECTORIOS:
        for archivo in sorted((RAIZ / sub).rglob("*.py")):
            if any(x in str(archivo) for x in _EXCLUIR):
                continue
            yield archivo


def test_el_barrido_encuentra_el_ddl():
    """Control: sin esto, una lista vacia pasaria por verde para siempre.

    Es el mismo control que lleva la guarda del motor. Un barrido que dejo de
    encontrar archivos —porque el DDL se movio de carpeta, por ejemplo— informa
    "limpio" sobre un repo que no miro.
    """
    encontradas = sum(
        len(defaults_con_reloj(f.read_text(encoding="utf-8"))) for f in _fuentes()
    )
    assert encontradas >= 13, f"el barrido encontro solo {encontradas} columnas con reloj"


@pytest.mark.parametrize("archivo", sorted(_fuentes()), ids=lambda f: f.name)
def test_ninguna_columna_estampa_una_hora_que_no_sea_la_de_argentina(archivo):
    fuera = defaults_fuera_de_hora_ar(archivo.read_text(encoding="utf-8"))
    assert fuera == [], (
        f"{archivo.relative_to(RAIZ)} declara columnas con una hora que no es la "
        "de Argentina:\n" + "\n".join(fuera)
    )


# ── La base que deja la cadena, mirada de verdad ────────────────────────────

_COLUMNAS_CON_RELOJ = """
    SELECT table_name, column_name, column_default
    FROM information_schema.columns
    WHERE table_schema = current_schema() AND data_type = 'text'
      AND (column_default LIKE '%interval%'
           OR column_default LIKE '%AT TIME ZONE ''UTC''%')
"""


def test_la_cadena_no_deja_ninguna_columna_de_texto_en_utc(url_de_base):
    """🔴 La guarda que atrapo el hueco real, y que mira LA BASE y no la lista.

    Cada revision lleva su lista de columnas escrita a mano, y una lista a mano
    no es un barrido. El ensayo del 2026-08-29 sobre una copia de la forma de
    `libradesk-compulibra` mostro que despues de migrar quedaban columnas de
    texto en UTC, entre ellas `clients.created_at` — que este producto adopto
    del motor en la revision `0017` y que ninguna lista contemplaba, porque el
    relevamiento se habia hecho barriendo el DDL de `app/services/`.

    Lo otro que hace falta saber: **las revisiones de LibraCore no corren sobre
    estas bases**. Las seis instancias del VPS tienen `alembic_version_libradesk`
    y ninguna tiene `alembic_version`, asi que lo que no arregle esta cadena no
    lo arregla nadie.

    Este test no mira la lista: mira la base que deja la cadena. Una columna
    nueva que nadie agrego a ninguna revision aparece aca, con su nombre.
    """
    import sqlalchemy as sa

    motor = sa.create_engine(url_de_base)
    try:
        with motor.connect() as conn:
            filas = list(conn.execute(sa.text(_COLUMNAS_CON_RELOJ)))
    finally:
        motor.dispose()

    # Control: sin columnas que mirar, la lista vacia de abajo pasaria por verde
    # para siempre.
    assert len(filas) >= 10, f"el barrido encontro solo {len(filas)} columnas con reloj"

    en_utc = sorted(
        (fila[0], fila[1]) for fila in filas if "interval" not in (fila[2] or "")
    )
    assert en_utc == [], (
        "estas columnas de texto siguen estampando UTC; hay que agregarlas a la "
        f"revision correspondiente:\n{en_utc}"
    )
