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
from app.services import facturacion_sos as sos

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


# ── Lo que ya no está del otro lado ──────────────────────────────────────────
#
# Decidido con el humano el 2026-09-10, después de revertir a mano la deuda de
# tres remitos de prueba de `lagrace` cuyas ventas se habían borrado en SOS:
# cuando el destino CONFIRMA que el comprobante no está, la deuda se anula; y
# si se vuelve a mandar, se carga de nuevo. Nada se borra: el libro del
# comprobante muestra cargo, anulación y cargo nuevo.

def _enviar(client, remito):
    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})
    assert r.status_code == 200, r.text
    return r.json()["resultados"][0]


def _montos(cliente_id):
    return [float(m["monto"]) for m in _debitos_del_puente(cliente_id)]


def test_si_el_comprobante_ya_no_esta_la_deuda_se_anula(client, configurado):
    """🔴 El caso pedido."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso())
    _enviar(client, remito)
    assert _saldo(cliente_id) == TOTAL_DEL_REMITO

    client.app.state.puente_facturacion.marcar_ausente_remoto(
        "remito", remito["id"], detalle="SOS ya no tiene la venta")

    assert _saldo(cliente_id) == 0
    assert _montos(cliente_id) == [TOTAL_DEL_REMITO, -TOTAL_DEL_REMITO]
    anulacion = _debitos_del_puente(cliente_id)[1]
    assert "Anulado" in anulacion["concepto"]
    assert remito["number"] in anulacion["concepto"], "tiene que decir de qué"


def test_la_anulacion_no_es_un_pago(client, configurado):
    """Un `cc_pago` es plata que entró, y de él se emite un recibo. Anular con
    un pago dejaría emitir un recibo por algo que nadie cobró."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso())
    _enviar(client, remito)

    client.app.state.puente_facturacion.marcar_ausente_remoto("remito", remito["id"])

    assert all(m["tipo"] == "debito" for m in cc.movimientos(cliente_id))


def test_anular_dos_veces_no_deja_saldo_a_favor(client, configurado):
    """🔴 La consulta de estado anula en cada vuelta lo que ya está marcado
    ausente. Sin idempotencia, cada click le dejaría al cliente saldo a favor."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso())
    _enviar(client, remito)
    puente = client.app.state.puente_facturacion

    puente.marcar_ausente_remoto("remito", remito["id"])
    puente.marcar_ausente_remoto("remito", remito["id"])
    puente.anular_deuda("remito", remito["id"])

    assert _saldo(cliente_id) == 0
    assert len(_debitos_del_puente(cliente_id)) == 2


def test_reenviar_despues_de_anular_vuelve_a_cargar(client, configurado):
    """🔴 La otra mitad. Con la idempotencia por fila de antes esto fallaba en
    silencio: el cargo original seguía existiendo, así que el reenvío no cargaba
    nada y el remito quedaba mandado y sin deuda."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso())
    _enviar(client, remito)
    client.app.state.puente_facturacion.marcar_ausente_remoto("remito", remito["id"])

    _enviar(client, remito)

    assert _saldo(cliente_id) == TOTAL_DEL_REMITO
    assert _montos(cliente_id) == [TOTAL_DEL_REMITO, -TOTAL_DEL_REMITO,
                                   TOTAL_DEL_REMITO]
    assert "reenvío" in _debitos_del_puente(cliente_id)[2]["concepto"]

    # Y reintentar el reenvío no fía dos veces.
    _enviar(client, remito)
    assert _saldo(cliente_id) == TOTAL_DEL_REMITO
    assert len(_debitos_del_puente(cliente_id)) == 3


def test_anular_lo_que_nunca_se_cargo_no_hace_nada(client, configurado):
    """Un envío que falló no debitó: no hay nada que compensar, y compensar
    igual dejaría saldo a favor."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso(excepcion=httpx.ConnectError("caído")))
    _enviar(client, remito)

    client.app.state.puente_facturacion.anular_deuda("remito", remito["id"])

    assert _saldo(cliente_id) == 0
    assert _debitos_del_puente(cliente_id) == []


# ── La pregunta previa al reenvío también anula ────────────────────────────
#
# Es el tercero de los tres lugares donde se anula (`anular_deuda`), y el único
# que no tenía test propio hasta el 2026-09-11. Cubre las marcas de "ya no
# está" hechas **antes** de que existiera la anulación: el envío dice ausente
# pero su deuda sigue cargada.

class _SOSQueDice:
    """Contesta `estado_venta`, que es lo único que usa la pregunta previa."""

    def __init__(self, excepcion=None):
        self.excepcion = excepcion

    def estado_venta(self, idventa):
        if self.excepcion:
            raise self.excepcion
        return {"emitido": False, "cae": "", "comprobante": "FA 0015-00000001"}


def _marca_vieja_de_ausente(client, cliente_id, remito):
    """El estado de una marca anterior al 2026-09-10: ausente y con la deuda."""
    puente = client.app.state.puente_facturacion
    puente._registrar("remito", remito["id"], fe.ESTADO_ENVIADO,
                      comprobante_remoto_id=906683730)
    puente._ajustar_deuda("remito", remito["id"], debe=True, cliente_id=cliente_id,
                          total=TOTAL_DEL_REMITO, concepto=f"Remito {remito['number']}")
    puente._registrar("remito", remito["id"], fe.ESTADO_AUSENTE_REMOTO,
                      detalle="marca vieja, sin anulación")
    # Control del escenario: si esto diera 0, los tests de abajo pasarían sin
    # que la pregunta previa hubiera anulado nada.
    assert _saldo(cliente_id) == TOTAL_DEL_REMITO
    return puente, puente.get_envio("remito", remito["id"])


def test_la_pregunta_previa_al_reenvio_anula_la_deuda_de_una_marca_vieja(
        client, configurado):
    """🔴 Con la idempotencia por **neto**, un reenvío sobre una deuda vieja
    todavía cargada no carga nada y el saldo da bien igual. Por eso se mira el
    libro y no el saldo: tiene que decir cargo y anulación, en ese orden, antes
    de que el reenvío cargue el suyo."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    puente, previo = _marca_vieja_de_ausente(client, cliente_id, remito)

    freno = puente._confirmar_que_ya_no_esta(
        _SOSQueDice(sos.VentaInexistente("no está")), previo)

    assert freno is None, "confirmado que no está: se puede reenviar"
    assert _saldo(cliente_id) == 0
    assert _montos(cliente_id) == [TOTAL_DEL_REMITO, -TOTAL_DEL_REMITO]


def test_si_la_venta_sigue_alla_la_pregunta_previa_no_anula(client, configurado):
    """Control: la venta está —la marca de ausente era un fallo de SOS—, así que
    la deuda es real y no se toca."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    puente, previo = _marca_vieja_de_ausente(client, cliente_id, remito)

    freno = puente._confirmar_que_ya_no_esta(_SOSQueDice(), previo)

    assert freno is not None, "no se reenvía lo que sigue allá"
    assert _montos(cliente_id) == [TOTAL_DEL_REMITO]


def test_si_no_se_puede_preguntar_la_pregunta_previa_no_anula(client, configurado):
    """🔴 No saber no es saber que no está: anular sobre un SOS caído le borraría
    la deuda a un cliente que la tiene."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    puente, previo = _marca_vieja_de_ausente(client, cliente_id, remito)

    freno = puente._confirmar_que_ya_no_esta(
        _SOSQueDice(sos.ErrorSOS("detalle de la venta: Token expirado")), previo)

    assert freno["estado"] == fe.ESTADO_ERROR
    assert _montos(cliente_id) == [TOTAL_DEL_REMITO]


def test_el_libro_del_remito_9_no_se_lleva_el_del_90(client):
    """El `LIKE` es `base-%`, con guión: sin él, anular el remito 9 sumaría
    también la deuda del 90 y la del 91."""
    cliente_id = _cliente_final(client)
    base = f"{fe.REFERENCIA_DEBITO}remito-9"
    cc.create_cc_debito(cliente_id, 100, "2026-09-10", referencia=base)
    cc.create_cc_debito(cliente_id, 900, "2026-09-10",
                        referencia=f"{fe.REFERENCIA_DEBITO}remito-90")
    cc.create_cc_debito(cliente_id, -100, "2026-09-10", referencia=f"{base}-1")

    referencias = [f["referencia"] for f in cc.debitos_de_referencia(base)]

    assert referencias == [base, f"{base}-1"]


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
