"""La elección de destino del puente: Contalibra o SOS Contador.

Lo que fijan estos tests:

1. 🔴 **Que el default no cambie.** Una instancia que actualiza y no toca su
   compose sigue mandando a Contalibra, con el mismo cuerpo de antes.
2. 🔴 **Que un rechazo de SOS no quede registrado como enviado.** Es el mismo
   falso verde que cubre `test_facturacion_sos.py`, pero acá importa el efecto
   visible: qué estado queda en la tabla que mira el operador.
3. Que "el comprobante ya está del otro lado" se distinga de "falló".
"""
import httpx
import pytest

from app.services import facturacion_externa as fe
from app.services import facturacion_sos as sos

COMPROBANTE = {
    "id": 12,
    "number": "REM-00000012",
    "client_name": "Cliente de Prueba",
    "client_cuit": "20111111112",
    "client_address": "Belgrano 448",
    "date": "2026-08-11",
    "observations": "Service de agosto",
    "items": [{"description": "Mano de obra", "qty": 2, "unit_price": 5000,
               "tax_rate": 0.21}],
}


@pytest.fixture
def puente(tmp_path):
    """Un puente sobre una base propia.

    No usa el `client` de conftest a propósito: ese fixture levanta las
    migraciones, que hoy fallan por un `libracore` viejo en el venv
    (`No module named 'libracore.db.url_de_instancia'`, ya presente en
    `develop`). Lo que se prueba acá es el servicio, no el router, así que no
    hace falta la app entera — y así estos tests no quedan rehenes de eso.
    """
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from app.database import Base

    engine = create_engine(f"sqlite:///{tmp_path}/puente.db")
    Base.metadata.create_all(engine)
    return fe.PuenteFacturacion(sessionmaker(engine))


class AdaptadorFalso:
    """Un `AdaptadorSOS` de mentira. Guarda el payload que le llegó."""

    def __init__(self, resultado=900492665, excepcion=None):
        self.resultado = resultado
        self.excepcion = excepcion
        self.payloads = []

    def enviar_venta(self, payload):
        self.payloads.append(payload)
        if self.excepcion:
            raise self.excepcion
        return self.resultado


# ── 1. El default ───────────────────────────────────────────────────────────

def test_sin_variable_el_destino_es_contalibra(monkeypatch):
    """🔴 La garantía de adopción: nadie cambia de destino por actualizar."""
    monkeypatch.delenv(fe.DESTINO_ENV, raising=False)
    assert fe.destino() == fe.DESTINO_CONTALIBRA


def test_un_valor_desconocido_cae_en_contalibra(monkeypatch):
    """Un typo en el compose no puede dejar a una instancia sin puente."""
    monkeypatch.setenv(fe.DESTINO_ENV, "sos-contador")   # no es "sos"
    assert fe.destino() == fe.DESTINO_CONTALIBRA


def test_con_destino_sos_no_se_contacta_a_contalibra(monkeypatch, puente):
    """Elegir SOS tiene que sacar a Contalibra del camino por completo."""
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    monkeypatch.setenv(fe.URL_ENV, "https://contalibra.test")
    monkeypatch.setenv(fe.TOKEN_ENV, "token")

    adaptador = AdaptadorFalso()
    puente._adaptador_sos = adaptador
    llamadas_http = []
    puente._cliente_http = type("X", (), {
        "post": lambda self, *a, **k: llamadas_http.append(a) or None
    })()

    puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)

    assert llamadas_http == [], "no se debe postear a la bandeja de Contalibra"
    assert len(adaptador.payloads) == 1


# ── 2. El rechazo no es un envío ────────────────────────────────────────────

def test_un_rechazo_de_sos_queda_como_error_no_como_enviado(monkeypatch, puente):
    """🔴 Lo que ve el operador en la tabla.

    Si esto se rompe, la pantalla dice "enviado" sobre un comprobante que en
    SOS no existe, y nadie se entera hasta que el contador no lo encuentra.
    """
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    puente._adaptador_sos = AdaptadorFalso(
        excepcion=sos.ErrorSOS("SOS rechazó el alta por validación")
    )

    envio = puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)

    assert envio["estado"] == fe.ESTADO_ERROR
    assert envio["comprobante_remoto_id"] is None
    assert "validación" in envio["detalle"]


def test_un_alta_exitosa_guarda_el_id_de_sos(monkeypatch, puente):
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    puente._adaptador_sos = AdaptadorFalso(resultado=900492665)

    envio = puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)

    assert envio["estado"] == fe.ESTADO_ENVIADO
    assert envio["comprobante_remoto_id"] == 900492665


def test_uniqueid_ya_usado_es_resuelto_remoto_y_no_error(monkeypatch, puente):
    """SOS diciendo "ya lo tenés mandado" no es una falla: es la señal para
    dejar de reintentar. Mismo significado que el 409 de Contalibra."""
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    puente._adaptador_sos = AdaptadorFalso(
        excepcion=sos.ErrorSOS("SOS rechazó el alta: el `uniqueid` ya fue usado")
    )

    envio = puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)

    assert envio["estado"] == fe.ESTADO_RESUELTO_REMOTO


def test_sos_caido_se_registra_y_no_rompe(monkeypatch, puente):
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    puente._adaptador_sos = AdaptadorFalso(excepcion=httpx.ConnectError("caido"))

    envio = puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)

    assert envio["estado"] == fe.ESTADO_ERROR
    assert "SOS Contador" in envio["detalle"]


def test_sin_configurar_sos_no_manda(monkeypatch, puente):
    """Falla cerrado, igual que el camino a Contalibra."""
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    for var in (sos.USUARIO_ENV, sos.PASSWORD_ENV, sos.IDCUIT_ENV, sos.PUNTOVENTA_ENV):
        monkeypatch.delenv(var, raising=False)
    puente._adaptador_sos = None

    assert fe.esta_configurado() is False
    with pytest.raises(fe.EnvioNoConfigurado):
        puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)


# ── 3. El payload que sale ──────────────────────────────────────────────────

def test_el_uniqueid_viaja_y_es_estable(monkeypatch, puente):
    """Reintentar el mismo remito manda el mismo `uniqueid`: es lo que hace
    que un reenvío no duplique la venta del otro lado."""
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    adaptador = AdaptadorFalso()
    puente._adaptador_sos = adaptador

    puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)
    puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)

    uniqueids = [p["uniqueid"] for p in adaptador.payloads]
    assert uniqueids[0] == uniqueids[1]
    assert uniqueids[0]  # no vacío


def test_el_payload_a_contalibra_no_lleva_uniqueid(monkeypatch, puente):
    """El campo es de SOS. Agregarlo al cuerpo que recibe la bandeja de
    Contalibra le cambiaría el contrato a un destino que hoy funciona."""
    monkeypatch.delenv(fe.DESTINO_ENV, raising=False)
    payload = fe.armar_payload(fe.ORIGEN_REMITO, COMPROBANTE, "compulibra")
    assert "uniqueid" not in payload
