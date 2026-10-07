"""La cadena de migraciones de LibraCore (`libracore-migrar`) en el arranque de LibraDesk.

Hasta el 2026-10-07 este producto declaraba `alembic`, `libracommerce-migrar` y
`libraauth-migrar`, pero no la cadena del motor. Sus bases (dev, demo, compulibra,
lagrace) no tenían la tabla de versión del motor ni tablas como
`arca_credenciales_servicio` (0022), y quedaron fuera de la pre factura (0021).

Dos grupos de pruebas:

1. **La declaración** (sin base): `libracore-migrar` está en los dos scripts, con el
   prefijo del producto, y en el orden que no rompe nada. Que el compose de `dev`
   diga lo mismo ya lo cubre `test_provisioning.py`.
2. **La cadena corrida de verdad** contra una PostgreSQL descartable, con los
   comandos que declara el deploy y no con una copia escrita acá.
"""
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

RAIZ = Path(__file__).resolve().parent.parent

#: Tablas que el motor SIEMBRA cuando no las encuentra con filas. Son las únicas
#: cuyo conteo puede cambiar al aplicar la cadena sobre una base viva.
SEMBRADAS_POR_EL_MOTOR = {"cajas", "categorias_egreso"}


def _declaradas(script: str) -> list[list[str]]:
    from libracore.provisioning import get_config

    importlib.reload(importlib.import_module(f"scripts.{script}"))
    return [list(c) for c in get_config().migraciones]


@pytest.mark.parametrize("script", ["nuevo_cliente", "panel_admin"])
def test_el_deploy_declara_la_cadena_del_motor_con_el_prefijo_del_producto(script):
    comandos = _declaradas(script)
    del_motor = [c for c in comandos if c[0] == "libracore-migrar"]
    assert del_motor == [["libracore-migrar", "upgrade", "--prefijo", "libradesk"]], (
        f"scripts/{script}.py declara {comandos!r}: falta `libracore-migrar upgrade "
        "--prefijo libradesk` (o está repetido / sin prefijo). Sin el prefijo el comando "
        "cae a DATABASE_URL a secas, que es la base del dominio sólo por casualidad."
    )


@pytest.mark.parametrize("script", ["nuevo_cliente", "panel_admin"])
def test_el_motor_corre_despues_de_alembic_y_de_libraauth(script):
    """El orden, con el motivo medido de cada restricción.

    - Antes de `alembic`: el motor crea `modulos`, `clients`, `depositos`... y la `0001`
      de este repo muere con `DuplicateTable`. Esas tablas tienen dueño propio acá.
    - Antes de `libraauth-migrar`: el motor declara `usuarios` y FK hacia ella; es de
      libraauth.
    """
    nombres = [c[0] for c in _declaradas(script)]
    motor = nombres.index("libracore-migrar")
    assert nombres.index("alembic") < motor, "el motor tiene que ir DESPUÉS de alembic"
    assert nombres.index("libraauth-migrar") < motor, "el motor tiene que ir DESPUÉS de libraauth-migrar"


def test_el_prefijo_del_producto_resuelve_a_la_base_del_dominio():
    """`libracore-migrar --prefijo libradesk` migra la base de DATABASE_URL.

    Es la guarda de la que depende todo lo demás: LibraDesk lleva el schema del motor en
    la MISMA base que el dominio. Si el motor sacara a `libradesk` de `_UNA_SOLA_BASE`,
    el comando fallaría (SinURL) en el deploy en vez de migrar la base equivocada, y
    este test lo dice antes.
    """
    from libracore.migrar import url_de_core

    url = "postgresql+psycopg://u:p@h:5432/libradesk"
    assert url_de_core("libradesk", entorno={"DATABASE_URL": url}) == url


# --- La cadena corrida de verdad ---------------------------------------------


def _entorno(url: str, data_dir: Path) -> dict:
    """El entorno de un contenedor de la instancia: sólo `DATABASE_URL`, como el real."""
    env = {k: v for k, v in os.environ.items() if not k.startswith(("LIBRADESK_", "LIBRACORE_"))}
    env.update(DATABASE_URL=url, ENV="development", DATA_DIR=str(data_dir))
    # Los comandos son console scripts del mismo venv que corre pytest.
    env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
    return env


def _correr(comandos, url: str, data_dir: Path) -> None:
    for comando in comandos:
        r = subprocess.run(comando, cwd=RAIZ, env=_entorno(url, data_dir), capture_output=True,
                           text=True, timeout=300)
        assert r.returncode == 0, f"`{' '.join(comando)}` salió con {r.returncode}:\n{r.stderr[-1500:]}"


def _conteos(url: str) -> dict:
    crudo = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(crudo, autocommit=True) as c:
        tablas = [r[0] for r in c.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='public' AND table_type='BASE TABLE'")]
        return {t: c.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tablas}


def _ejecutar(url: str, sql: str) -> None:
    crudo = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(crudo, autocommit=True) as c:
        c.execute(sql)


@pytest.fixture
def base_vacia(tmp_path):
    """Una base PostgreSQL vacía y propia del test, que se borra al terminar."""
    from conftest import _borrar_base, _sql_admin, _url_de

    nombre = "ld_motor_arranque_" + tmp_path.name[-12:].replace("-", "_").lower()
    _sql_admin(f'DROP DATABASE IF EXISTS "{nombre}"', f'CREATE DATABASE "{nombre}"')
    yield _url_de(nombre)
    _borrar_base(nombre)
    shutil.rmtree(tmp_path / "datos", ignore_errors=True)


def test_sobre_una_instancia_viva_agrega_las_tablas_del_motor_y_no_toca_ninguna_fila(base_vacia, tmp_path):
    """El caso de dev, la demo, compulibra y lagrace: la base ya existe y tiene datos.

    Medido el 2026-10-07 sobre la copia del respaldo de la demo (82 tablas, 372 filas): la
    cadena termina sin error, agrega 19 tablas, 25 columnas a cuatro tablas existentes,
    convierte 21 columnas de dinero de `double precision` a `numeric` y deja **las 368 filas
    comparadas con los mismos valores**. Lo único que cambia de conteo son las dos tablas que
    el motor siembra.
    """
    todas = _declaradas("panel_admin")
    sin_motor = [c for c in todas if c[0] != "libracore-migrar"]
    motor = [c for c in todas if c[0] == "libracore-migrar"]
    datos = tmp_path / "datos"
    datos.mkdir()

    # La instancia como está hoy: las tres cadenas que ya corría, y datos de verdad. El
    # depósito importa: todas las instancias reales tienen al menos uno (ver el test de
    # la base vacía, más abajo).
    _correr(sin_motor, base_vacia, datos)
    _ejecutar(base_vacia, "INSERT INTO depositos (nombre, activo, es_default) VALUES ('Taller', true, true)")
    _ejecutar(base_vacia, "INSERT INTO clients (name, email, tipo_facturacion) "
                          "VALUES ('Cliente de prueba', 'prueba@example.test', 'por_servicio')")
    antes = _conteos(base_vacia)
    assert "alembic_version" not in antes, "la base de partida tiene que ser la de hoy, sin la cadena del motor"
    assert "arca_credenciales_servicio" not in antes

    _correr(motor, base_vacia, datos)
    despues = _conteos(base_vacia)

    assert "arca_credenciales_servicio" in despues, "la 0022 del motor no se aplicó"
    assert despues["alembic_version"] == 1
    cambiaron = {t: (antes[t], despues[t]) for t in antes if antes[t] != despues[t]}
    assert set(cambiaron) <= SEMBRADAS_POR_EL_MOTOR, (
        f"el motor cambió filas de tablas que no siembra: {cambiaron}")
    assert despues["clients"] == antes["clients"] == 1 and despues["depositos"] == antes["depositos"] == 1

    # Idempotente: el deploy lo corre en cada actualización.
    _correr(motor, base_vacia, datos)
    assert _conteos(base_vacia) == despues


def test_sobre_una_base_vacia_la_cadena_entera_termina_sin_error(base_vacia, tmp_path):
    """El alta de un cliente nuevo y el reset de la demo (`DROP SCHEMA` + las cadenas declaradas).

    Exige `libracore >= v1.142.1`: hasta v1.142.0 la baseline del motor sembraba `Depósito
    Principal` con `es_default=1` en la `depositos` de este producto, que la tiene BOOLEAN, y
    la cadena moría con `DatatypeMismatch` (ADR-012; en el motor, ADR-033). Desde v1.142.1 el
    motor no siembra en una `depositos` que no es la suya, así que la base nace sin depósitos.
    """
    datos = tmp_path / "datos"
    datos.mkdir()
    _correr(_declaradas("panel_admin"), base_vacia, datos)
    conteos = _conteos(base_vacia)
    assert conteos["alembic_version"] == 1
    assert conteos["depositos"] == 0, "una base nueva de LibraDesk nace sin depósitos; los crea su pantalla"
