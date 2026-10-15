"""Una base NUEVA, armada como la arma el deploy, tiene que quedar como una migrada.

El defecto que fija este archivo (2026-10-15): el reset nocturno de la demo (`DROP
SCHEMA` + las cadenas + el arranque + `seed_demo.py`) moría en `POST /api/ventas` con
`ForeignKeyViolation: ventas_pagos_venta_id_fkey ... not present in table "ventas"`.

La causa es el ORDEN de quién crea `ventas_pagos`:

- **Antes del ADR-012** (2026-10-07) el deploy no corría `libracore-migrar`, y la
  primera en crear `ventas_pagos` era `comercial.ensure_schema()` de este producto,
  con la FK contra `sales` (las ventas de LibraDesk viven en `sales`, de LibraCommerce).
- **Desde el ADR-012** la cadena del motor corre ANTES de que arranque la app, y su
  baseline (`init_core_schema()`) crea `ventas_pagos` con la FK contra `ventas`, la
  tabla legada de LibraCore. El `CREATE TABLE IF NOT EXISTS` de `comercial.py` ya no
  hace nada, y nadie repuntaba la FK. Las bases que existían antes (dev, compulibra,
  lagrace) conservaron la FK buena; una base de cero --la demo cada noche, el alta de
  un cliente, el restore de un backup-- nace con la mala.

**Por qué la suite no lo veía**: la plantilla de `conftest.py` arma la base con el
arranque de la app SOLO (sin `libracore-migrar`), o sea con el orden de antes del
ADR-012. Estos tests usan la secuencia real, la que declara `scripts/panel_admin.py`.
"""
import shutil
from pathlib import Path

import psycopg
import pytest
from test_motor_en_el_arranque import _correr, _declaradas

#: Las FK de `ventas_pagos` hacia la tabla padre, tal como las ve PostgreSQL.
_SQL_FK_DE_PAGOS = (
    "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
    "WHERE conrelid = 'ventas_pagos'::regclass AND contype = 'f' AND conname = 'ventas_pagos_venta_id_fkey'"
)

#: Todas las FK de la base, una línea por restricción.
_SQL_TODAS_LAS_FK = (
    "SELECT conrelid::regclass::text || '.' || conname || ' ' || pg_get_constraintdef(oid) "
    "FROM pg_constraint WHERE contype = 'f' AND connamespace = 'public'::regnamespace"
)

#: Seis FK que una base nueva tiene de más respecto de una migrada, y que NO son este defecto.
#: Las crea la baseline del motor (`init_core_schema()`) antes de que `comercial.py` pueda
#: declarar las tablas sin ellas: es la regla «el DDL crudo no referencia tablas de Alembic»
#: de `app/services/comercial.py` (motivo 2) violada por el orden. Las de `remitos` y
#: `presupuestos` las acepta el ADR-012 (`ON DELETE SET NULL`, inocuas); las otras cuatro
#: quedan pendientes de decisión. Están acá, nombradas, para que la comparación sirva: una
#: diferencia NUEVA entre base nueva y base migrada pone el test en rojo, y si alguna de
#: estas desaparece (alguien las arregló) también, para que se saque de la lista.
_DIFERENCIAS_CONOCIDAS = {
    "cc_debitos.cc_debitos_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES clients(id) ON DELETE CASCADE",
    "cc_pagos.cc_pagos_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES clients(id) ON DELETE CASCADE",
    "egresos.egresos_proveedor_id_fkey FOREIGN KEY (proveedor_id) REFERENCES proveedores(id) ON DELETE SET NULL",
    "presupuestos.presupuestos_client_id_fkey FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL",
    "recibos.recibos_cliente_id_fkey FOREIGN KEY (cliente_id) REFERENCES clients(id) ON DELETE SET NULL",
    "remitos.remitos_client_id_fkey FOREIGN KEY (client_id) REFERENCES clients(id) ON DELETE SET NULL",
}


def _consultar(url: str, sql: str) -> list:
    crudo = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(crudo, autocommit=True) as c:
        return [r[0] for r in c.execute(sql).fetchall()]


@pytest.fixture
def crear_base(tmp_path, monkeypatch):
    """Fábrica de bases PostgreSQL vacías y propias del test, que se borran al terminar."""
    from conftest import _ENV_DE_INSTANCIA, _borrar_base, _sql_admin, _url_de

    creadas: list[str] = []

    def _crear(sufijo: str) -> tuple[str, Path]:
        nombre = f"ld_nueva_{sufijo}_{tmp_path.name[-12:].replace('-', '_').lower()}"
        _sql_admin(f'DROP DATABASE IF EXISTS "{nombre}"', f'CREATE DATABASE "{nombre}"')
        creadas.append(nombre)
        datos = tmp_path / f"datos_{sufijo}"
        datos.mkdir()
        return _url_de(nombre), datos

    # Lo mismo que hace la fixture `data_dir` del conftest con el entorno de la instancia.
    monkeypatch.setenv("ENV", "development")
    for var in _ENV_DE_INSTANCIA:
        monkeypatch.delenv(var, raising=False)

    yield _crear

    from conftest import _soltar_conexiones

    _soltar_conexiones()
    for nombre in creadas:
        _borrar_base(nombre)
    for sufijo in ("nueva", "migrada"):
        shutil.rmtree(tmp_path / f"datos_{sufijo}", ignore_errors=True)


def _arrancar_app(url: str, datos: Path, monkeypatch):
    """El contenedor sano: `uvicorn app.asgi:app` con la cadena ya corrida."""
    from conftest import construir_app

    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("DATA_DIR", str(datos))
    return construir_app(datos, url)


def _base_nueva(crear_base, monkeypatch):
    """Lo que hace el reset de la demo: base vacía, las cadenas que declara el deploy, la app."""
    url, datos = crear_base("nueva")
    _correr(_declaradas("panel_admin"), url, datos)
    app = _arrancar_app(url, datos, monkeypatch)
    return url, app


def test_en_una_base_nueva_los_pagos_cuelgan_de_sales(crear_base, monkeypatch):
    """`ventas_pagos.venta_id` apunta a `sales`, no a la `ventas` legada de LibraCore.

    LibraDesk vende por `sales` (LibraCommerce): con la FK contra `ventas`, que está vacía y
    nadie escribe, no entra ni un pago.
    """
    url, _ = _base_nueva(crear_base, monkeypatch)
    definiciones = _consultar(url, _SQL_FK_DE_PAGOS)
    assert definiciones == ["FOREIGN KEY (venta_id) REFERENCES sales(id) ON DELETE CASCADE"], (
        f"la FK de ventas_pagos quedó {definiciones!r}: una base nueva (las cadenas del deploy y "
        "después el arranque) tiene que repuntarla a sales, como las bases migradas. Ver el docstring "
        "de este archivo."
    )


def test_en_una_base_nueva_se_puede_vender_con_un_pago(crear_base, monkeypatch):
    """Lo que hace `seed_demo.py` y moría con 500: `POST /api/ventas` con un pago, en una base nueva."""
    from fastapi.testclient import TestClient
    from test_comercial_api import _crear_base, _login

    _, app = _base_nueva(crear_base, monkeypatch)
    with TestClient(app, base_url="https://testserver") as c:
        _login(c)
        ids = _crear_base(c)
        r = c.post("/api/recepciones-compra", json={
            "proveedor_id": ids["proveedor"], "deposito_id": ids["deposito"],
            "documento": "FC A 0001-00000001",
            "items": [{"item_id": ids["producto"], "cantidad": 20, "costo": 95}],
        })
        assert r.status_code == 201, r.text

        v = c.post("/api/ventas", json={
            "cliente_id": ids["cliente"], "deposito_id": ids["deposito"],
            "sucursal_id": ids["sucursal"],
            "items": [{"item_id": ids["producto"], "descripcion": "PLUG RJ 45 CAT 6",
                       "cantidad": 2, "precio": 160}],
            "pagos": [{"medio": "efectivo", "monto": 320}],
        })
        assert v.status_code == 201, v.text
        assert c.get(f"/api/ventas/{v.json()['id']}").json()["pagos"], "la venta quedó sin su pago"


def test_una_base_nueva_tiene_las_mismas_fk_que_una_migrada(crear_base, monkeypatch):
    """La instancia de hoy (lagrace, compulibra, dev) contra la que nace de cero.

    La «migrada» sigue la historia real de esas bases: las tres cadenas y la app (como era el
    deploy hasta el ADR-012), y DESPUÉS `libracore-migrar`. La «nueva» es el reset de la demo:
    las cuatro cadenas y después la app. Se comparan las FK de las dos --que es donde se vio
    el defecto-- salvo `_DIFERENCIAS_CONOCIDAS`.
    """
    nueva, _ = _base_nueva(crear_base, monkeypatch)

    migrada, datos = crear_base("migrada")
    comandos = _declaradas("panel_admin")
    _correr([c for c in comandos if c[0] != "libracore-migrar"], migrada, datos)
    _arrancar_app(migrada, datos, monkeypatch)
    _correr([c for c in comandos if c[0] == "libracore-migrar"], migrada, datos)

    fk_nueva, fk_migrada = set(_consultar(nueva, _SQL_TODAS_LAS_FK)), set(_consultar(migrada, _SQL_TODAS_LAS_FK))
    assert fk_migrada - fk_nueva == set(), f"a la base nueva le faltan FK que tiene la migrada: {fk_migrada - fk_nueva}"
    assert fk_nueva - fk_migrada == _DIFERENCIAS_CONOCIDAS, (
        "la base nueva y la migrada difieren en FK distintas de las conocidas.\n"
        f"  de más (no listadas): {sorted((fk_nueva - fk_migrada) - _DIFERENCIAS_CONOCIDAS)}\n"
        f"  listadas que ya no difieren (sacarlas de la lista): "
        f"{sorted(_DIFERENCIAS_CONOCIDAS - (fk_nueva - fk_migrada))}"
    )
