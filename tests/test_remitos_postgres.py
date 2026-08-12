"""El camino de remitos y presupuestos, EJECUTADO contra PostgreSQL.

Por qué existe, que es lo que menos se ve:

`tests/test_database_backend.py::test_application_starts_against_postgres` es el
gate que cerró la F1 del piloto — y lo único que asierta es que `/api/health`
responde 200. Eso prueba que las 31 tablas **nacen** en PostgreSQL, no que se
puedan leer. El 2026-08-09, con ese gate en verde y 483 tests sin salteos, **5
de las 7 lecturas de `libracore.db.remitos_presupuestos` fallaban** contra
PostgreSQL real: `dict(fila)` moría porque el `Row` del adaptador no tenía
`keys()`, y `valid_until < date('now')` se traducía a `text < date`.

O sea: la primera pantalla de remitos de una instancia migrada habría dado 500.

Este archivo cubre el hueco desde el lado del producto — el `_DDL` propio de
LibraDesk (sin la FK a `clients`, con `usuario_id`), el `configure()` que
distingue URL de ruta, y el alta y lectura de verdad. Y siembra filas siempre:
con las tablas vacías estas mismas lecturas devuelven `[]` y pasan aunque el
adaptador esté roto.
"""


import pytest

# La forma que espera `_normalizar_items` (la misma del PDF de LibraCore).
ITEMS = [{"description": "Servicio tecnico", "qty": 2, "unit_price": 500.0}]


def _preparar(url_o_ruta, data_dir, monkeypatch):
    """Monta la app entera y devuelve el módulo de servicios ya configurado.

    Se construye con `create_app()` y no llamando a `configure()` a secas, por
    una razón que ya costó una corrida: el `_DDL` de estas dos tablas declara
    `usuario_id REFERENCES usuarios(id)`, y `usuarios` la crea `libraauth` en
    el `create_all()`. En PostgreSQL la FK se exige al crear la tabla, así que
    fuera de ese orden el `ensure_schema()` muere con *"relation usuarios does
    not exist"*. Es además el orden real del arranque.

    `ENV=development` es lo mismo que hace la fixture `data_dir` del conftest:
    sin eso `libraauth.bootstrap` exige `LIBRADESK_ADMIN_PASSWORD` y aborta.
    """
    from app.services import remitos_presupuestos as rp_service

    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(data_dir))

    # Ya no hace falta limpiar el schema a mano: la fixture `url_de_base` del
    # conftest le da a cada test su propia base, copiada de la plantilla. Antes
    # este archivo hacia `DROP SCHEMA public CASCADE` porque el PostgreSQL del
    # CI era uno solo para toda la suite.
    from app.main import create_app

    create_app(url_o_ruta, str(data_dir))
    return rp_service


def _alta_y_lectura(rp_service):
    """Alta de un remito y un presupuesto, y todas las lecturas que usan los
    routers. Devuelve algo comparable entre motores."""
    remitos = rp_service.RemitoService()
    presupuestos = rp_service.PresupuestoService()

    remito = remitos.create(
        date="2026-08-01", client_id=None, client_name="Cliente Uno",
        items=ITEMS, tax_rate=0.21, observations="alta de prueba",
    )
    # Los dos pasan por `set_status("enviado")` a propósito: el vencimiento
    # automático de LibraCore sólo toca los `enviado`/`pendiente`, y LibraDesk
    # crea en `borrador`. Sin este paso el presupuesto vencido se quedaría en
    # borrador y la consulta que interesa —`valid_until < date('now')`, la que
    # fallaba con "operator does not exist: text < date"— igual se ejecutaría,
    # pero el test no podría distinguir que hizo algo.
    vencido = presupuestos.create(
        date="2026-08-01", valid_until="2026-01-15", client_id=None,
        client_name="Cliente Uno", items=ITEMS, tax_rate=0.21,
    )
    vigente = presupuestos.create(
        date="2026-08-01", valid_until="2099-12-31", client_id=None,
        client_name="Cliente Uno", items=ITEMS, tax_rate=0.21,
    )
    presupuestos.set_status(vencido["id"], "enviado")
    presupuestos.set_status(vigente["id"], "enviado")

    return {
        "remito_creado": _comparable(remito),
        "remitos_list": _comparable(remitos.list()),
        "remito_get": _comparable(remitos.get(remito["id"])),
        "presupuestos_list": _comparable(presupuestos.list()),
        "presupuestos_vencidos": _comparable(presupuestos.list(estado="vencido")),
        "counts_by_estado": dict(presupuestos.counts_by_estado()),
    }


# La hora de escritura no se compara entre motores: las dos corridas ocurren en
# momentos distintos y un cruce de segundo las haría fallar sin que hubiera
# nada roto. Lo que importa de esas columnas es el formato, y de eso se ocupa
# el test equivalente en LibraCore.
VOLATILES = {"created_at", "updated_at"}


def _comparable(valor):
    if isinstance(valor, dict):
        return {k: _comparable(v) for k, v in valor.items() if k not in VOLATILES}
    if isinstance(valor, list):
        return [_comparable(v) for v in valor]
    try:
        return round(float(valor), 6)
    except (TypeError, ValueError):
        return valor


@pytest.fixture
def resultados(tmp_path, monkeypatch, url_de_base):
    """El camino entero ejecutado contra la PostgreSQL propia del test.

    Antes había dos fixtures —una SQLite y una PostgreSQL— y el test comparaba
    los resultados entre motores. Con SQLite retirado (2026-08-12) esa
    comparación se quedó sin premisa, así que lo que se asierta pasa a ser el
    **valor esperado** contra el motor real, que es más fuerte: una comparación
    entre dos motores pasa igual si los dos se equivocan del mismo modo.
    """
    destino = tmp_path / "datos"
    destino.mkdir()
    rp_service = _preparar(url_de_base, destino, monkeypatch)
    try:
        return _alta_y_lectura(rp_service)
    finally:
        from libracore.db import core as libracore_core
        libracore_core._db_path = None
        libracore_core._database_url = None


def test_el_camino_se_ejecuta_entero_contra_postgres(resultados):
    """El gate que faltaba: ejecutar el camino, no sólo arrancar la app.

    Los dos defectos que motivaron este archivo eran **de lectura y de
    PostgreSQL**: `dict(fila)` moría porque el `Row` del adaptador no tenía
    `keys()`, y `valid_until < date('now')` se traducía a `text < date`. Con
    las tablas creadas y la app arrancando, los dos pasaban desapercibidos.
    """
    remito = resultados["remito_creado"]
    assert remito["client_name"] == "Cliente Uno"
    # 2 x 500 + 21% = 1210. El total se calcula en el servidor, así que si la
    # lectura devolviera basura esto no da.
    assert remito["total"] == 1210.0

    assert resultados["remito_get"] == remito

    # El vencimiento automático corrió: el presupuesto con `valid_until` en el
    # pasado quedó `vencido`, que es la consulta que fallaba con
    # "operator does not exist: text < date".
    vencidos = resultados["presupuestos_vencidos"]
    assert len(vencidos) == 1
    assert vencidos[0]["valid_until"] == "2026-01-15"
    assert resultados["counts_by_estado"].get("vencido") == 1


def test_las_lecturas_traen_filas_de_verdad(resultados):
    """Contraprueba: sin filas, las lecturas devuelven `[]` y el test de arriba
    pasaría con el adaptador roto — que es exactamente cómo estas fallas se
    escondieron durante el gate del piloto.

    🔴 Hasta el 2026-08-12 esta contraprueba pedía la fixture **SQLite**, así
    que nunca probó que las lecturas de PostgreSQL trajeran nada — y PostgreSQL
    era el único motor donde el defecto existía.
    """
    assert len(resultados["remitos_list"]) == 1
    assert len(resultados["presupuestos_list"]) == 2
    assert resultados["remito_get"] is not None
    assert resultados["remito_creado"]["total"] == pytest.approx(1210.0)


def test_el_presupuesto_vencido_se_marca_solo(resultados):
    """`valid_until < date('now')` es la consulta que fallaba con
    *"operator does not exist: text < date"*.

    Se asierta sobre los DOS presupuestos: que el de fecha pasada quede
    `vencido` y que el de 2099 siga `enviado`. Con uno solo, un `status` que se
    quedara clavado en cualquiera de los dos valores pasaría igual — que es la
    diferencia entre probar que la consulta corrió y probar que hizo lo que
    tenía que hacer.
    """
    estados = {p["number"]: p["status"] for p in resultados["presupuestos_list"]}
    assert len(estados) == 2, f"se esperaban dos presupuestos, hay {estados}"
    assert sorted(estados.values()) == ["enviado", "vencido"], (
        f"el vencimiento automatico no discrimino por fecha: {estados}"
    )
