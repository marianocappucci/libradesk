"""Mandar un comprobante a facturar carga la deuda en la cuenta corriente.

Hasta ahora el saldo de un cliente reflejaba **lo que LibraDesk cobra**, no lo
que el cliente debe: la pata de facturas de `get_cc_saldo()` sale de `facturas`
y `caja_movimientos`, dos tablas que este producto crea vacías porque no
factura. Un remito mandado a facturar no aparecía por ningún lado.

🔴 **Por qué el disparador es «enviado» y no «facturado»** (decidido con el
humano el 2026-08-13): *no existe* un estado facturado. `resuelto_remoto` se
produce sólo al REINTENTAR —es el 409 de Contalibra o el "uniqueid ya usado" de
SOS— y significa "del otro lado ya lo tienen", sin distinguir una factura
emitida de un comprobante descartado. Nadie le avisa a LibraDesk cuando se emite
el CAE. Así que se debita con lo único que se sabe con certeza.

Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que un envío fallido NO debite.** Es la mitad cara del cambio: fiar por
   un comprobante que nunca llegó es plata que el cliente no debe.
2. 🔴 **Que reintentar no fíe dos veces.** El modo de falla normal del puente es
   el corte de red y la reacción normal es reintentar.
3. 🔴 **Que un débito que falla no tumbe el envío.** El comprobante ya está del
   otro lado cuando el débito corre.
4. Que el débito aparezca en el saldo y en los movimientos, que es donde se mira.
"""
import httpx
import pytest

from app.services import cuenta_corriente as cc
from app.services import facturacion_externa as fe

# `tests/` no es un paquete, así que las piezas de `test_facturacion_externa`
# no se pueden importar de ahí. Se redefinen acá —son cuatro líneas— en vez de
# acoplar dos archivos de test por un helper.

URL = "https://contalibra.test"
TOKEN = "token-de-servicio-de-prueba"

_ITEMS = [{"description": "Mano de obra", "qty": 2, "unit_price": 5000, "tax_rate": 0.21}]

# 2 × 5000 + 21% = 12100
TOTAL_DEL_REMITO = 12100.0


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin."""
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def configurado(monkeypatch):
    monkeypatch.setenv(fe.URL_ENV, URL)
    monkeypatch.setenv(fe.TOKEN_ENV, TOKEN)
    monkeypatch.setenv(fe.INSTANCIA_ENV, "compulibra")


class ClienteFalso:
    """Un `httpx.Client` de mentira. Igual que el de `test_facturacion_externa`."""

    def __init__(self, status=201, cuerpo=None, excepcion=None):
        self.status = status
        self.cuerpo = cuerpo if cuerpo is not None else {"id": 7, "creado": True}
        self.excepcion = excepcion
        self.llamadas = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.llamadas.append({"url": url, "json": json})
        if self.excepcion is not None:
            raise self.excepcion
        return httpx.Response(self.status, json=self.cuerpo,
                              request=httpx.Request("POST", url))


def _cliente_final(client, nombre="Ferretería San Martín"):
    r = client.post("/api/clientes", json={"nombre": nombre})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _remito(client, cliente_id):
    r = client.post("/api/remitos", json={"client_id": cliente_id, "items": _ITEMS})
    assert r.status_code == 201, r.text
    return r.json()


def _presupuesto(client, cliente_id, status="aceptado"):
    r = client.post("/api/presupuestos", json={
        "client_id": cliente_id, "items": _ITEMS, "status": status,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _con_puente_falso(client, falso):
    client.app.state.puente_facturacion._cliente_http = falso
    return falso


def _saldo(cliente_id: int) -> float:
    return cc.saldo(cliente_id)


def _debitos_del_puente(cliente_id: int) -> list[dict]:
    return [m for m in cc.movimientos(cliente_id)
            if str(m.get("referencia", "")).startswith(fe.REFERENCIA_DEBITO)]


# ── El camino feliz ──────────────────────────────────────────────────────────

def test_mandar_un_remito_a_facturar_lo_carga_en_la_cuenta_corriente(
        client, configurado):
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    assert _saldo(cliente_id) == 0, "arranca sin deuda"

    _con_puente_falso(client, ClienteFalso())
    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})
    assert r.status_code == 200, r.text

    assert _saldo(cliente_id) == TOTAL_DEL_REMITO


def test_el_movimiento_dice_de_que_comprobante_salio(client, configurado):
    """El saldo sin el porqué no sirve: quien lo mira tiene que poder rastrear
    cada peso hasta su comprobante."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)

    _con_puente_falso(client, ClienteFalso())
    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [remito["id"]]})

    movs = _debitos_del_puente(cliente_id)
    assert len(movs) == 1
    assert remito["number"] in movs[0]["concepto"]
    assert movs[0]["referencia"].endswith(f"remito-{remito['id']}")


def test_un_presupuesto_convertido_debita_UNA_vez(client, configurado):
    """🔴 El test de la plata: un trabajo, un débito.

    Hasta el 2026-08-13 la bandeja ofrecía el presupuesto `aceptado` **y** el
    remito que salía de convertirlo, porque `convertir_a_remito()` deja el
    presupuesto en `aceptado`. Mandar los dos —que es lo que hacía cualquiera
    que tildara todo— generaba dos débitos con referencias distintas
    (`…presupuesto-1` y `…remito-1`), y el cliente quedaba debiendo el doble del
    trabajo. La desduplicación del otro lado tampoco los unía: su UNIQUE incluye
    `origen_tipo`.

    Ahora el presupuesto no es mandable, así que el circuito completo deja un
    solo débito por definición.
    """
    cliente_id = _cliente_final(client)
    presupuesto = _presupuesto(client, cliente_id)

    remito = client.post(
        f"/api/presupuestos/{presupuesto['id']}/convertir-en-remito"
    ).json()
    # El presupuesto sigue en `aceptado` después de convertirse: es la condición
    # que hacía posible el doble cobro, y no cambió.
    estado = client.get(f"/api/presupuestos/{presupuesto['id']}").json()["status"]
    assert estado == "aceptado"

    _con_puente_falso(client, ClienteFalso())
    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [remito["id"]]})

    assert len(_debitos_del_puente(cliente_id)) == 1
    assert _saldo(cliente_id) == TOTAL_DEL_REMITO


def test_un_presupuesto_no_puede_debitar_por_su_cuenta(client, configurado):
    """La otra mitad: aunque alguien llame a la API a mano con el tipo viejo."""
    cliente_id = _cliente_final(client)
    presupuesto = _presupuesto(client, cliente_id)

    _con_puente_falso(client, ClienteFalso())
    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "presupuesto", "ids": [presupuesto["id"]]})

    assert r.status_code == 422, r.text
    assert _debitos_del_puente(cliente_id) == []
    assert _saldo(cliente_id) == 0


# ── Lo que NO tiene que debitar ──────────────────────────────────────────────

def test_un_envio_que_falla_no_debita_nada(client, configurado):
    """🔴 La mitad cara. Contalibra caído deja el envío en `error` y el
    comprobante se va a reintentar: fiar acá sería deuda por algo que no llegó.
    """
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)

    _con_puente_falso(client, ClienteFalso(
        excepcion=httpx.ConnectError("sin ruta al host")))
    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["resultados"][0]["estado"] == fe.ESTADO_ERROR

    assert _saldo(cliente_id) == 0
    assert _debitos_del_puente(cliente_id) == []


def test_un_409_del_otro_lado_tampoco_debita(client, configurado):
    """`resuelto_remoto` es "allá ya lo tienen", y no dice si lo facturaron o lo
    descartaron. Debitar sobre esa ambigüedad es justo lo que no se quiere; y si
    lo facturaron, el débito ya se cargó en el envío que salió bien."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)

    _con_puente_falso(client, ClienteFalso(status=409, cuerpo={"detail": "ya existe"}))
    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})
    assert r.json()["resultados"][0]["estado"] == fe.ESTADO_RESUELTO_REMOTO

    assert _saldo(cliente_id) == 0


def test_sin_configurar_no_manda_y_no_debita(client):
    """La garantía de adopción también vale para la cuenta corriente: una
    instancia que actualiza y no toca su compose no ve cambiar ningún saldo."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)

    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})
    assert r.status_code == 409

    assert _saldo(cliente_id) == 0


# ── Reintentos ───────────────────────────────────────────────────────────────

def test_reintentar_el_mismo_envio_no_fia_dos_veces(client, configurado):
    """🔴 El modo de falla normal entre dos contenedores es el corte de red, y la
    reacción normal es reintentar. Sin idempotencia, cada reintento duplicaría la
    deuda — y el destino ya es idempotente, así que el usuario reintenta sin
    miedo."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso())

    for _ in range(3):
        client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})

    assert _saldo(cliente_id) == TOTAL_DEL_REMITO
    assert len(_debitos_del_puente(cliente_id)) == 1


def test_dos_comprobantes_distintos_si_suman(client, configurado):
    """La contracara del test anterior: la idempotencia es por comprobante, no
    un "debitá una sola vez por cliente"."""
    cliente_id = _cliente_final(client)
    uno = _remito(client, cliente_id)
    otro = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso())

    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [uno["id"], otro["id"]]})

    assert _saldo(cliente_id) == TOTAL_DEL_REMITO * 2
    assert len(_debitos_del_puente(cliente_id)) == 2


# ── Cuando el débito falla ───────────────────────────────────────────────────

def test_si_el_debito_falla_el_envio_igual_queda_registrado(
        client, configurado, monkeypatch):
    """🔴 El comprobante YA está del otro lado cuando el débito corre. Si esto
    propagara, se perdería la fila del envío y el próximo intento lo mandaría de
    nuevo: un duplicado allá para no perder un débito acá."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso())

    def explota(*a, **kw):
        raise RuntimeError("la base de cuenta corriente no responde")

    monkeypatch.setattr(fe.cuenta_corriente, "create_cc_debito", explota)

    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})
    assert r.status_code == 200, r.text
    assert r.json()["resultados"][0]["estado"] == fe.ESTADO_ENVIADO

    # Y el envío quedó guardado, que es lo que permite no remandarlo.
    envios = client.get("/api/facturacion/estado").json()["envios"]
    assert [e["estado"] for e in envios] == [fe.ESTADO_ENVIADO]


# ── Comprobante sin cliente de la base ───────────────────────────────────────

@pytest.mark.parametrize("comprobante, por_que", [
    ({"id": 1, "number": "R-1", "client_id": None, "total": 12100},
     "sin cliente de la base no hay cuenta a la que cargarlo"),
    ({"id": 2, "number": "R-2", "total": 12100},
     "la clave puede no venir"),
    ({"id": 3, "number": "R-3", "client_id": 5, "total": 0},
     "un comprobante en cero no es deuda"),
])
def test_lo_que_no_se_puede_debitar_se_saltea_sin_romper(
        client, comprobante, por_que):
    """Se prueba contra el método y no por HTTP **a propósito**: `RemitoIn`
    declara `client_id: int` obligatorio, así que por la API estos casos dan 422
    y el test se saltearía siempre — un verde que no ejercita nada. La columna
    de la base **sí** es nullable y el servicio recibe dicts de varias fuentes,
    así que la guarda es real aunque hoy el router no la alcance.
    """
    puente = client.app.state.puente_facturacion
    # No levanta, y no deja nada cargado: lo que se afirma es que no explota.
    puente._debitar_en_cuenta_corriente("remito", comprobante), por_que
