"""El arranque exige la cadena de LibraAuth en vez de crear las tablas.

Desde libraauth v0.45 (2026-09-17) `create_app()` ya no corre
`AuthBase.metadata.create_all()`: llama a `exigir_schema_al_dia`, después del
Alembic del dominio y antes de las tablas de LibraCore que tienen FK a
`usuarios`. Se fija que sin la cadena la app no arranca y el error nombra el
comando que declara `scripts/panel_admin.py`, con su control.
"""
import re
from pathlib import Path

import psycopg
import pytest
from libraauth.migrar import TABLA_DE_VERSION, SchemaDesactualizado

RAIZ = Path(__file__).resolve().parent.parent
COMANDO = "libraauth-migrar upgrade --prefijo libradesk --base dominio"


def _cruda(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def test_sin_la_cadena_la_app_no_arranca_y_dice_el_comando(url_de_base, tmp_path, monkeypatch):
    from app.main import create_app

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    with psycopg.connect(_cruda(url_de_base), autocommit=True) as c:
        c.execute(f"DROP TABLE {TABLA_DE_VERSION}")
    with pytest.raises(SchemaDesactualizado) as e:
        create_app(url_de_base, str(tmp_path))
    assert COMANDO in str(e.value)


def test_la_guarda_usa_el_comando_que_declara_el_deploy():
    fuente = (RAIZ / "scripts" / "panel_admin.py").read_text(encoding="utf-8")
    declarado = re.search(r'\("libraauth-migrar",([^)]*)\)', fuente)
    assert declarado, "scripts/panel_admin.py no declara libraauth-migrar"
    partes = ["libraauth-migrar"] + re.findall(r'"([^"]+)"', declarado.group(1))
    assert " ".join(partes) == COMANDO


def test_control_con_la_cadena_arranca(url_de_base, tmp_path, monkeypatch):
    from app.main import create_app

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    assert create_app(url_de_base, str(tmp_path)) is not None
