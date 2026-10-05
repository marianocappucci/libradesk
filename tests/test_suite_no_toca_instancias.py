"""La suite no corre contra el PostgreSQL de una instancia, ni deja bases en el servidor.

El 2026-08-12 se corrió con `LIBRADESK_SUITE_POSTGRES_URL` apuntando a `libradesk-demo-db` y dejó 18 bases —una con
datos reales de un cliente de La Grace— que se encontraron el 2026-10-05. La guarda vive en el `conftest` (corre al
importarlo, antes de crear nada); acá se fija qué hosts frena y que la URL del CI pasa.
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import _es_postgres_de_instancia

TESTS = Path(__file__).resolve().parent


@pytest.mark.parametrize("host", [
    "libradesk-demo-db", "libradesk-compulibra-db", "libradesk-lagrace-postgres", "libradesk-postgres",
])
def test_frena_el_postgres_de_cada_instancia(host):
    assert _es_postgres_de_instancia(f"postgresql+psycopg://libradesk:x@{host}:5432/postgres")


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "postgres-de-prueba"])
def test_deja_pasar_un_servidor_descartable(host):
    assert not _es_postgres_de_instancia(f"postgresql+psycopg://libradesk:libradesk-ci@{host}:5432/postgres")


def test_el_conftest_no_arranca_contra_la_demo():
    """La guarda corre al importar el conftest: con la URL de la demo, pytest no llega a crear ninguna base."""
    entorno = dict(os.environ, LIBRADESK_SUITE_POSTGRES_URL="postgresql+psycopg://libradesk:x@libradesk-demo-db:5432/postgres")
    r = subprocess.run([sys.executable, "-c", "import conftest"], cwd=TESTS, env=entorno,
                       capture_output=True, text=True, timeout=120)
    assert r.returncode != 0
    assert "apunta al PostgreSQL de una instancia (libradesk-demo-db:5432/postgres)" in r.stderr
    assert ":x@" not in r.stderr, "el mensaje no muestra la contraseña"
