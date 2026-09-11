"""Fase E del puente: lo que SOS ya facturó queda marcado en el reclamo.

Hasta el 2026-09-11 `estado_facturacion` era una marca **manual** que sólo leen
los reportes: un reclamo facturado del otro lado seguía figurando "sin
facturar" hasta que alguien lo tildara. La consulta de estados
(`POST /api/facturacion/estados-sos`) ya sabía si el comprobante tenía CAE; lo
que faltaba era escribirlo en la fuente.

Lo que fijan estos tests:

1. 🔴 Que con CAE los reclamos del remito queden `facturada`.
2. 🔴 Que **sin** CAE no se marque nada: cargado en SOS no es facturado, y el
   contador puede descartarlo.
3. Que consultar de nuevo no vuelva a escribir: la ruta corre en cada click.
"""
import os

import pytest

from app.services import facturacion_externa as fe
from app.services import facturacion_sos as sos


@pytest.fixture
def client(client):
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def sos_configurado(monkeypatch):
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    monkeypatch.setenv(sos.USUARIO_ENV, "api@test")
    monkeypatch.setenv(sos.PASSWORD_ENV, "clave")
    monkeypatch.setenv(sos.IDCUIT_ENV, "30953")
    monkeypatch.setenv(sos.PUNTOVENTA_ENV, "15")
    monkeypatch.setenv(sos.LETRA_ENV, "A")


class PuenteFalso:
    """Un envío ya mandado a SOS por el remito que se le indique."""

    def __init__(self, remito_id):
        self.envios = [{"origen_tipo": fe.ORIGEN_REMITO, "origen_id": remito_id,
                        "comprobante_remoto_id": 906483888,
                        "estado": fe.ESTADO_ENVIADO}]

    def listar(self):
        return self.envios

    def marcar_ausente_remoto(self, *a, **k):
        return {}

    def anular_deuda(self, *a, **k):
        return None


class AdaptadorFalso:
    def __init__(self, emitido):
        self.emitido = emitido

    def estado_venta(self, idventa):
        return {"emitido": self.emitido,
                "cae": "71234567890123" if self.emitido else "",
                "cae_vencimiento": "", "comprobante": "FA 0015-00000001",
                "total": 1210.0}


def _reclamo_remitado(client):
    cliente = client.post("/api/clientes", json={"nombre": "Municipio de Navarro"}).json()
    incidencia = client.post("/api/incidencias", json={
        "cliente_id": cliente["id"], "titulo": "Central sin tono",
        "descripcion": "No hay tono en los internos", "horas_invertidas": 1,
    }).json()
    r = client.put(f"/api/incidencias/{incidencia['id']}",
                   json={**incidencia, "estado": "cerrado"})
    assert r.status_code == 200, r.text
    remito = client.post(f"/api/incidencias/{incidencia['id']}/convertir-en-remito")
    assert remito.status_code in (200, 201), remito.text
    return incidencia["id"], remito.json()["id"]


def _consultar(client, monkeypatch, remito_id, *, emitido):
    client.app.state.puente_facturacion = PuenteFalso(remito_id)
    monkeypatch.setattr(sos, "AdaptadorSOS", lambda *a, **k: AdaptadorFalso(emitido))
    r = client.post("/api/facturacion/estados-sos")
    assert r.status_code == 200, r.text
    return r.json()["items"][0]


def _estado_facturacion(client, incidencia_id):
    return client.get(f"/api/incidencias/{incidencia_id}").json()["estado_facturacion"]


def test_con_cae_los_reclamos_del_remito_quedan_facturados(client, monkeypatch,
                                                          sos_configurado):
    incidencia_id, remito_id = _reclamo_remitado(client)
    assert _estado_facturacion(client, incidencia_id) is None, "arranca sin marca"

    fila = _consultar(client, monkeypatch, remito_id, emitido=True)

    assert fila["emitido"] is True
    assert fila["reclamos_facturados"] == 1
    assert _estado_facturacion(client, incidencia_id) == "facturada"


def test_sin_cae_no_se_marca_nada(client, monkeypatch, sos_configurado):
    """🔴 Cargado en SOS no es facturado: el contador puede descartarlo. Es el
    control del de arriba — sin él, un marcado incondicional pasaría los dos."""
    incidencia_id, remito_id = _reclamo_remitado(client)

    fila = _consultar(client, monkeypatch, remito_id, emitido=False)

    assert "reclamos_facturados" not in fila
    assert _estado_facturacion(client, incidencia_id) is None


def test_consultar_de_nuevo_no_vuelve_a_marcar(client, monkeypatch, sos_configurado):
    """La ruta corre en cada click del botón: la segunda vez no hay nada nuevo."""
    incidencia_id, remito_id = _reclamo_remitado(client)
    _consultar(client, monkeypatch, remito_id, emitido=True)

    fila = _consultar(client, monkeypatch, remito_id, emitido=True)

    assert fila["reclamos_facturados"] == 0
    assert _estado_facturacion(client, incidencia_id) == "facturada"
