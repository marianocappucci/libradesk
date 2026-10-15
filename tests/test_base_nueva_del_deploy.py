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

**El mismo orden dejaba otra diferencia (medida el 2026-10-15, ADR-016)**: la baseline
crea también seis tablas que este producto declara SIN FK (`cc_debitos`, `cc_pagos`,
`recibos`, `remitos`, `presupuestos`, `egresos`), con FK hacia `clients` y `proveedores` y
dos de ellas `ON DELETE CASCADE`, y deja `presupuestos.status` en `'pendiente'` en vez de
`'borrador'`. Una base nueva no es igual a una migrada hasta que el arranque las suelta
(`soltar_fk()` del motor, `comercial.ensure_schema()` y `remitos_presupuestos.ensure_schema()`).
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

#: Lo que una base nueva puede tener distinto de una migrada y está aceptado POR ESCRITO, por sección
#: del volcado de `libracore.db.schema_dump` (`tablas`, `claves primarias`, `claves foráneas`, `índices`,
#: `checks`). **Hoy no hay nada**: el ADR-012 había aceptado las FK de `remitos` y `presupuestos` (inocuas,
#: `SET NULL`) y las otras cuatro quedaron pendientes; el ADR-016 las sacó todas. Agregar una línea acá es una
#: decisión que se escribe en `DECISIONS.md`, no un parche para que el test pase. Una diferencia NUEVA entre
#: base nueva y base migrada pone el test en rojo --por ejemplo una FK que el motor agregue a una de estas
#: tablas en una versión futura--, y si algo de esta lista deja de diferir también, para que se saque.
_DIFERENCIAS_ACEPTADAS: dict[str, set[str]] = {}

_SECCIONES = ("tablas", "claves primarias", "claves foráneas", "índices", "checks")


def _consultar(url: str, sql: str) -> list:
    crudo = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(crudo, autocommit=True) as c:
        return [r[0] for r in c.execute(sql).fetchall()]


def _volcar(url: str) -> dict[str, set[str]]:
    """El schema completo de la base, por sección: `libracore.db.schema_dump`, el mismo volcado que congela la baseline."""
    from libracore.db._postgres import ConnectionWrapper
    from libracore.db.schema_dump import volcar_schema

    crudo = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(crudo, autocommit=True) as c:
        texto = volcar_schema(ConnectionWrapper(c))
    secciones: dict[str, set[str]] = {}
    actual = None
    for linea in texto.splitlines():
        if linea.startswith("## "):
            actual = linea[3:].rsplit(" (", 1)[0]
            secciones[actual] = set()
        elif linea and not linea.startswith("#") and actual:
            secciones[actual].add(linea)
    return secciones


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


def _base_migrada(crear_base, monkeypatch):
    """La historia real de dev, compulibra y lagrace: las tres cadenas y la app (el deploy hasta el ADR-012),
    y DESPUÉS `libracore-migrar`."""
    migrada, datos = crear_base("migrada")
    comandos = _declaradas("panel_admin")
    _correr([c for c in comandos if c[0] != "libracore-migrar"], migrada, datos)
    _arrancar_app(migrada, datos, monkeypatch)
    _correr([c for c in comandos if c[0] == "libracore-migrar"], migrada, datos)
    return migrada


def test_una_base_nueva_tiene_el_mismo_schema_que_una_migrada(crear_base, monkeypatch):
    """La instancia de hoy (lagrace, compulibra, dev) contra la que nace de cero.

    La «migrada» sigue la historia real de esas bases (ver `_base_migrada`). La «nueva» es el reset de la
    demo: las cuatro cadenas y después la app. Se compara TODO el volcado del schema --tablas con sus tipos y
    `DEFAULT`, claves primarias y foráneas, índices y checks--, no sólo las FK donde se vio el defecto: el
    `DEFAULT` de `presupuestos.status` también difería. Sólo se admite lo de `_DIFERENCIAS_ACEPTADAS`.
    """
    nueva, _ = _base_nueva(crear_base, monkeypatch)
    migrada = _base_migrada(crear_base, monkeypatch)

    vn, vm = _volcar(nueva), _volcar(migrada)
    assert set(vn) == set(vm) == set(_SECCIONES), (sorted(vn), sorted(vm))
    for seccion in _SECCIONES:
        solo_nueva, solo_migrada = vn[seccion] - vm[seccion], vm[seccion] - vn[seccion]
        aceptadas = _DIFERENCIAS_ACEPTADAS.get(seccion, set())
        assert solo_nueva | solo_migrada == aceptadas, (
            f"[{seccion}] la base nueva y la migrada difieren en algo distinto de lo aceptado.\n"
            f"  sólo en la nueva (no aceptado): {sorted(solo_nueva - aceptadas)}\n"
            f"  sólo en la migrada (no aceptado): {sorted(solo_migrada - aceptadas)}\n"
            f"  aceptadas que ya no difieren (sacarlas de la lista): {sorted(aceptadas - (solo_nueva | solo_migrada))}\n"
            "Ver el docstring de este archivo."
        )


def test_en_una_base_nueva_borrar_un_cliente_no_borra_su_cuenta_corriente(crear_base, monkeypatch):
    """El daño concreto de la diferencia: la baseline crea `cc_pagos` y `cc_debitos` con `ON DELETE CASCADE`.

    Con esa FK, un `DELETE FROM clients` se llevaba los movimientos de cuenta corriente del cliente. En una base
    migrada nunca pasó (la tabla no tiene FK); una base nueva tiene que comportarse igual.
    """
    url, _ = _base_nueva(crear_base, monkeypatch)
    crudo = url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(crudo) as c:
        cid = c.execute(
            "INSERT INTO clients (name, tipo_facturacion) VALUES ('Cliente de prueba', 'por_servicio') RETURNING id"
        ).fetchone()[0]
        c.execute("INSERT INTO cc_pagos (cliente_id, monto, fecha) VALUES (%s, 100, '2026-10-15')", (cid,))
        c.execute("INSERT INTO cc_debitos (cliente_id, monto, fecha) VALUES (%s, 50, '2026-10-15')", (cid,))
        c.commit()
        c.execute("DELETE FROM clients WHERE id = %s", (cid,))
        c.commit()
        pagos = c.execute("SELECT COUNT(*) FROM cc_pagos WHERE cliente_id = %s", (cid,)).fetchone()[0]
        debitos = c.execute("SELECT COUNT(*) FROM cc_debitos WHERE cliente_id = %s", (cid,)).fetchone()[0]
    assert (pagos, debitos) == (1, 1), "borrar el cliente se llevó su cuenta corriente: la base nueva tiene el CASCADE"


def test_reiniciar_la_app_sobre_una_base_ya_alineada_no_cambia_el_schema(crear_base, monkeypatch):
    """El reinicio de un contenedor (`ensure_schema()` otra vez) sobre una base nueva ya alineada es un no-op."""
    url, datos = crear_base("nueva")
    _correr(_declaradas("panel_admin"), url, datos)
    _arrancar_app(url, datos, monkeypatch)
    primero = _volcar(url)
    _arrancar_app(url, datos, monkeypatch)
    assert _volcar(url) == primero
