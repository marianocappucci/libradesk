"""El ajuste por índice del contrato (revisión `0043`), con los índices que guarda el motor (ADR-085 de libracore).

Lo que se fija acá:
- un contrato por índice tiene que decir cuál y cada cuánto, y el índice tiene que ser del catálogo del motor;
- el ajuste se cuenta desde `fecha_inicio` y su base es el precio vigente;
- proponer no escribe; aplicar cierra el precio vigente y abre el ajustado, y la cuota siguiente sale con ese precio;
- el período ya ajustado no se vuelve a ajustar, y aplicar con otra fecha se rechaza;
- si falta un valor se baja de la fuente en el momento; si la fuente no está, 409 con las fechas que faltan.
"""
import os
from datetime import date
from decimal import Decimal

import pytest
from libracore import indices_descarga
from libracore.db import indices_ajuste as valores


@pytest.fixture
def client(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    _cadena_del_motor()
    return client


def _cadena_del_motor():
    """La tabla `indices_ajuste` la crea la `0030` del motor, que en producción corre antes de la app
    (`libracore-migrar`, ADR-012). La plantilla de la suite no corre esa cadena, así que se corre acá, de verdad,
    sobre la base del test: no una copia del DDL, que es la que se desactualiza."""
    from libracore.db import core
    from libracore.migrar import upgrade

    upgrade(core._database_url)


@pytest.fixture
def sin_red(monkeypatch):
    """Ningún test sale a internet: una fuente que se consulte sin que el test lo prepare está caída."""
    def caida(url, params):
        raise indices_descarga.FuenteNoDisponible("sin red en los tests")
    monkeypatch.setattr(indices_descarga, "_obtener_http", caida)


@pytest.fixture
def cliente(client):
    return client.post("/api/clientes", json={"nombre": "Estudio Sur"}).json()


def _contrato(client, cliente, **extra):
    datos = {
        "tipo_contrato": "alquiler", "cliente_id": cliente["id"], "fecha_inicio": "2026-02-15",
        "estado": "activo", "importe": 100000, "metodo_actualizacion": "indice",
        "indice_ajuste": "icl", "periodicidad_ajuste": "trimestral", **extra,
    }
    r = client.post("/api/contratos", json=datos)
    assert r.status_code in (200, 201), r.text
    return r.json()


def test_el_catalogo_sale_del_motor(client):
    r = client.get("/api/contratos/ajustes/indices")
    assert r.status_code == 200
    claves = {i["clave"]: i for i in r.json()}
    assert {"icl", "ipc", "ipc_variacion", "cer", "uva", "dolar_a3500", "casa_propia"} <= set(claves)
    assert claves["icl"]["se_baja_solo"] is True and claves["casa_propia"]["se_baja_solo"] is False


@pytest.mark.parametrize("extra", [
    {"indice_ajuste": None},
    {"periodicidad_ajuste": None},
    {"indice_ajuste": "ipc_rosario"},
    {"periodicidad_ajuste": "quincenal"},
])
def test_un_contrato_por_indice_dice_cual_y_cada_cuanto(client, cliente, extra):
    datos = {"tipo_contrato": "alquiler", "cliente_id": cliente["id"], "fecha_inicio": "2026-02-15",
             "estado": "activo", "importe": 100000, "metodo_actualizacion": "indice",
             "indice_ajuste": "icl", "periodicidad_ajuste": "trimestral", **extra}
    r = client.post("/api/contratos", json=datos)
    assert r.status_code >= 400, r.text


def test_proponer_aplicar_y_la_cuota_sale_con_el_precio_ajustado(client, cliente, sin_red):
    contrato = _contrato(client, cliente)
    assert contrato["indice_ajuste"] == "icl" and contrato["periodicidad_ajuste"] == "trimestral"
    valores.guardar("icl", "2026-02-15", "30.00", "bcra")
    valores.guardar("icl", "2026-05-15", "31.50", "bcra")

    r = client.get(f"/api/contratos/{contrato['id']}/ajuste", params={"fecha": "2026-05-20"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["corresponde"] is True
    assert (p["fecha_ajuste"], p["proximo_ajuste"]) == ("2026-05-15", "2026-08-15")
    assert p["ajuste"]["importe_nuevo"] == 105000.0
    assert Decimal(p["ajuste"]["coeficiente"]) == Decimal("1.05")
    assert [v["fecha"] for v in p["ajuste"]["valores"]] == ["2026-02-15", "2026-05-15"]
    # Proponer no escribió nada.
    assert client.get(f"/api/contratos/{contrato['id']}").json()["importe_vigente"] == 100000

    r = client.post(f"/api/contratos/{contrato['id']}/ajuste", json={"fecha_ajuste": "2026-05-15"})
    assert r.status_code == 201, r.text
    assert r.json()["precio"]["importe"] == 105000
    assert r.json()["precio"]["motivo"] == "ajuste_indice:icl"
    precios = client.get(f"/api/contratos/{contrato['id']}/precios").json()
    assert [(x["vigencia_desde"], x["vigencia_hasta"]) for x in precios] == [
        ("2026-05-15", None), ("2026-02-15", "2026-05-14")]

    # El período ya tiene su precio: no se vuelve a ajustar.
    otra = client.get(f"/api/contratos/{contrato['id']}/ajuste", params={"fecha": "2026-06-01"}).json()
    assert otra["corresponde"] is False and otra["ajuste"] is None and otra["motivo"] == "ya_ajustado"
    assert client.post(f"/api/contratos/{contrato['id']}/ajuste",
                       json={"fecha_ajuste": "2026-05-15"}).status_code == 409

    # La cuota de junio sale con el precio ajustado.
    r = client.post("/api/cuotas/generar", json={"ancla": "2026-06-10", "contrato_id": contrato["id"]})
    assert r.status_code == 200, r.text
    assert r.json()["generadas"][0]["importe_total"] == 105000


def test_aplicar_con_otra_fecha_se_rechaza(client, cliente, sin_red):
    contrato = _contrato(client, cliente)
    valores.guardar("icl", "2026-02-15", "30.00", "bcra")
    valores.guardar("icl", "2026-05-15", "31.50", "bcra")
    r = client.post(f"/api/contratos/{contrato['id']}/ajuste", json={"fecha_ajuste": "2026-05-20"})
    assert r.status_code == 409
    assert "2026-05-15" in r.text


def test_si_falta_un_valor_se_baja_de_la_fuente(client, cliente, monkeypatch):
    contrato = _contrato(client, cliente)
    pedidos = []

    def bcra(url, params):
        pedidos.append(params)
        return {"metadata": {"resultset": {"count": 2}}, "results": [{"idVariable": 40, "detalle": [
            {"fecha": "2026-05-15", "valor": Decimal("31.50")}, {"fecha": "2026-02-15", "valor": Decimal("30.00")}]}]}

    monkeypatch.setattr(indices_descarga, "_obtener_http", bcra)
    r = client.get(f"/api/contratos/{contrato['id']}/ajuste", params={"fecha": "2026-05-20"})
    assert r.status_code == 200, r.text
    assert r.json()["ajuste"]["importe_nuevo"] == 105000.0
    assert len(pedidos) == 1


def test_sin_el_valor_y_sin_fuente_dice_que_falta(client, cliente, sin_red):
    contrato = _contrato(client, cliente)
    valores.guardar("icl", "2026-02-15", "30.00", "bcra")
    r = client.get(f"/api/contratos/{contrato['id']}/ajuste", params={"fecha": "2026-05-20"})
    assert r.status_code == 409
    assert r.json()["detail"]["fechas_faltantes"] == ["2026-05-15"]
    assert r.json()["detail"]["indice_nombre"].startswith("Índice para Contratos de Locación")


def test_un_contrato_manual_no_tiene_ajuste(client, cliente):
    contrato = _contrato(client, cliente, metodo_actualizacion="manual", indice_ajuste=None,
                         periodicidad_ajuste=None)
    r = client.get(f"/api/contratos/{contrato['id']}/ajuste")
    assert r.status_code == 409


def test_en_el_primer_periodo_no_hay_ajuste_y_lo_dice(client, cliente, sin_red):
    contrato = _contrato(client, cliente)
    assert contrato["indice_ajuste_nombre"].startswith("Índice para Contratos de Locación")
    p = client.get(f"/api/contratos/{contrato['id']}/ajuste", params={"fecha": "2026-03-01"}).json()
    assert (p["corresponde"], p["motivo"], p["proximo_ajuste"]) == (False, "primer_periodo", "2026-05-15")


def test_un_contrato_cerrado_no_se_ajusta(client, cliente, sin_red):
    contrato = _contrato(client, cliente)
    valores.guardar("icl", "2026-02-15", "30.00", "bcra")
    valores.guardar("icl", "2026-05-15", "31.50", "bcra")
    assert client.put(f"/api/contratos/{contrato['id']}", json={"estado": "rescindido"}).status_code == 200
    r = client.post(f"/api/contratos/{contrato['id']}/ajuste", json={"fecha_ajuste": "2026-05-15"})
    assert r.status_code == 409 and "rescindido" in r.text
