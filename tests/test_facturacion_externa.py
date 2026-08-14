"""El puente que manda lo facturable a Contalibra — fase B.

LibraDesk no factura: deja el comprobante en la bandeja del otro lado. Lo que
fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que sin configurar no mande nada.** Es la garantía de adopción: una
   instancia que actualiza y no toca su compose se comporta igual que antes.
2. 🔴 **Que el token no salga nunca por la API**, ni siquiera enmascarado.
3. 🔴 **Que lo único que se mande sea un remito.** Ni un presupuesto aceptado,
   ni un remito con total 0. Del otro lado el paso siguiente es emitir con CAE,
   y desde que el envío además debita en cuenta corriente, mandar de más le
   carga deuda de más a un cliente real.
4. Que un Contalibra caído no rompa la operación: se registra el error y se
   puede reintentar, porque el destino es idempotente.
5. Que el estado de cada envío quede guardado y visible.
"""
import httpx
import pytest

from app.services import facturacion_externa as fe

URL = "https://contalibra.test"
TOKEN = "token-de-servicio-de-prueba"

_ITEMS = [{"description": "Mano de obra", "qty": 2, "unit_price": 5000, "tax_rate": 0.21}]


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin."""
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def client_sin_login(armar_cliente):
    """Una instancia aparte, sin sesión. Hace falta porque el `client` de este
    archivo está logueado."""
    _, c = armar_cliente()
    return c


@pytest.fixture
def configurado(monkeypatch):
    monkeypatch.setenv(fe.URL_ENV, URL)
    monkeypatch.setenv(fe.TOKEN_ENV, TOKEN)
    monkeypatch.setenv(fe.INSTANCIA_ENV, "compulibra")


class ClienteFalso:
    """Un `httpx.Client` de mentira que registra lo que se le pidió.

    Se inyecta en `PuenteFacturacion` en vez de parchear `httpx` entero: así el
    test ve el request tal como sale —URL, headers y cuerpo— que es justamente
    lo que hay que fijar de un integrador.
    """

    def __init__(self, status=201, cuerpo=None, excepcion=None):
        self.status = status
        self.cuerpo = cuerpo if cuerpo is not None else {"id": 7, "creado": True}
        self.excepcion = excepcion
        self.llamadas = []

    def post(self, url, json=None, headers=None, timeout=None):
        self.llamadas.append({"url": url, "json": json, "headers": headers,
                              "timeout": timeout})
        if self.excepcion is not None:
            raise self.excepcion
        return httpx.Response(
            self.status, json=self.cuerpo,
            request=httpx.Request("POST", url),
        )


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
    """Reemplaza el cliente HTTP del puente ya montado en la app."""
    client.app.state.puente_facturacion._cliente_http = falso
    return falso


# ── Sin configurar ───────────────────────────────────────────────────────────

def test_sin_las_variables_el_puente_dice_que_no_esta_configurado(client):
    r = client.get("/api/facturacion/estado")
    assert r.status_code == 200
    assert r.json()["configurado"] is False


def test_sin_configurar_enviar_da_409_y_no_registra_nada(client):
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)

    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})
    assert r.status_code == 409
    assert "Contalibra" in r.json()["detail"]
    assert client.get("/api/facturacion/estado").json()["envios"] == []


def test_con_solo_la_url_sigue_sin_estar_configurado(client, monkeypatch):
    """Media configuración no alcanza: sin token el otro lado devolvería 401 y
    el usuario vería un error de red donde el problema es el compose."""
    monkeypatch.setenv(fe.URL_ENV, URL)
    assert client.get("/api/facturacion/estado").json()["configurado"] is False


# ── El secreto ───────────────────────────────────────────────────────────────

def test_el_token_no_sale_por_la_api(client, configurado):
    """Ni el token ni la URL. `configurado` es un booleano y nada más."""
    cuerpo = client.get("/api/facturacion/estado").text
    assert TOKEN not in cuerpo
    assert URL not in cuerpo

    cuerpo = client.get("/api/facturacion/pendientes").text
    assert TOKEN not in cuerpo


def test_el_token_viaja_en_el_header_y_no_en_la_url(client, configurado):
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    falso = _con_puente_falso(client, ClienteFalso())

    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [remito["id"]]})

    llamada = falso.llamadas[0]
    assert llamada["headers"][fe.HEADER_TOKEN] == TOKEN
    assert TOKEN not in llamada["url"]
    assert llamada["url"] == f"{URL}/api/comprobantes-pendientes"
    assert llamada["timeout"] == fe.TIMEOUT


# ── Lo que se manda ──────────────────────────────────────────────────────────

def test_el_payload_lleva_lo_que_la_bandeja_espera(client, configurado):
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    falso = _con_puente_falso(client, ClienteFalso())

    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [remito["id"]]})

    payload = falso.llamadas[0]["json"]
    assert payload["origen_producto"] == "libradesk"
    assert payload["origen_instancia"] == "compulibra"
    assert payload["origen_tipo"] == "remito"
    # El id LOCAL, no el número: el número lo puede reasignar una renumeración
    # y es la mitad de la clave con la que el otro lado desduplica.
    assert payload["origen_id"] == str(remito["id"])
    assert payload["cliente_razon"] == "Ferretería San Martín"
    assert payload["items"] == [
        {"description": "Mano de obra", "qty": 2.0, "unit_price": 5000.0,
         "iva_rate": 0.21},
    ]


def test_el_iva_viaja_por_item(client, configurado):
    """No se aplasta de este lado: `armar_prefill` del otro lo hace avisando,
    y decidirlo acá sería elegir por el que está por emitir."""
    cliente_id = _cliente_final(client)
    r = client.post("/api/remitos", json={"client_id": cliente_id, "items": [
        {"description": "Servicio", "qty": 1, "unit_price": 100, "tax_rate": 0.21},
        {"description": "Otro", "qty": 1, "unit_price": 100, "tax_rate": 0.105},
    ]})
    assert r.status_code == 201, r.text
    falso = _con_puente_falso(client, ClienteFalso())

    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [r.json()["id"]]})

    alicuotas = [i["iva_rate"] for i in falso.llamadas[0]["json"]["items"]]
    assert sorted(alicuotas) == [0.105, 0.21]


# ── Ningún presupuesto se manda: el único origen es el remito ────────────────
#
# Antes del 2026-08-13 se mandaban los presupuestos `aceptado`. El problema no
# era sólo contable: `convertir_a_remito()` deja el presupuesto EN `aceptado` y
# linkeado al remito, así que el presupuesto y su propio remito eran dos filas
# mandables por el mismo trabajo — y del otro lado el UNIQUE de desduplicación
# incluye `origen_tipo`, o sea que entraban como dos borradores distintos y
# debitaban dos veces en la cuenta corriente del cliente.


@pytest.mark.parametrize("estado", ["borrador", "enviado", "aceptado", "rechazado", "vencido"])
def test_ningun_presupuesto_se_manda_ni_siquiera_el_aceptado(client, configurado, estado):
    """`aceptado` está en la lista a propósito: es el que ANTES sí se mandaba,
    y es el único caso donde una regresión pasaría desapercibida."""
    cliente_id = _cliente_final(client)
    presupuesto = _presupuesto(client, cliente_id, status=estado)
    falso = _con_puente_falso(client, ClienteFalso())

    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "presupuesto", "ids": [presupuesto["id"]]})

    assert r.status_code == 422, r.text
    assert falso.llamadas == [], "no tendría que haber salido ningún request"


def test_los_pendientes_no_ofrecen_presupuestos(client, configurado):
    cliente_id = _cliente_final(client)
    _presupuesto(client, cliente_id, status="borrador")
    _presupuesto(client, cliente_id, status="aceptado")
    remito = _remito(client, cliente_id)

    items = client.get("/api/facturacion/pendientes").json()["items"]

    assert [i["origen_tipo"] for i in items] == ["remito"]
    assert [i["id"] for i in items] == [remito["id"]]


def test_un_presupuesto_llega_a_la_bandeja_convirtiendose_en_remito(client, configurado):
    """El camino que reemplaza al que se sacó: convertir y mandar el remito.

    Y **una sola fila**, aunque el presupuesto siga en `aceptado` después de
    convertirse: eso es lo que antes duplicaba.
    """
    cliente_id = _cliente_final(client)
    presupuesto = _presupuesto(client, cliente_id, status="aceptado")

    r = client.post(f"/api/presupuestos/{presupuesto['id']}/convertir-en-remito")
    assert r.status_code == 201, r.text
    remito = r.json()

    items = client.get("/api/facturacion/pendientes").json()["items"]
    assert [(i["origen_tipo"], i["id"]) for i in items] == [("remito", remito["id"])]

    falso = _con_puente_falso(client, ClienteFalso())
    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})
    assert r.json()["resultados"][0]["estado"] == "enviado"
    assert len(falso.llamadas) == 1


def test_un_remito_en_cero_no_se_manda(client, configurado):
    """Del otro lado el paso siguiente es emitir con CAE, y una factura en cero
    no existe. Es lo que ataja un remito recién generado desde una incidencia,
    cuyos importes todavía no cargó nadie."""
    cliente_id = _cliente_final(client)
    creado = client.post("/api/remitos", json={
        "client_id": cliente_id,
        "items": [{"description": "Mano de obra", "qty": 1, "unit_price": 0}],
    })
    assert creado.status_code == 201, creado.text
    falso = _con_puente_falso(client, ClienteFalso())

    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [creado.json()["id"]]})

    assert r.json()["resultados"][0]["estado"] == "no_facturable"
    assert falso.llamadas == [], "no tendría que haber salido ningún request"


# ── Cuando el otro lado falla ────────────────────────────────────────────────

def test_contalibra_caido_queda_registrado_como_error_y_no_rompe(client, configurado):
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso(
        excepcion=httpx.ConnectError("no se pudo conectar"),
    ))

    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})

    assert r.status_code == 200
    resultado = r.json()["resultados"][0]
    assert resultado["estado"] == "error"
    assert "no se pudo conectar" in resultado["detalle"]


def test_un_409_del_otro_lado_no_es_un_error_a_reintentar(client, configurado):
    """El otro lado ya lo facturó o lo descartó. Es la señal para dejar de
    insistir, no un fallo."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso(
        status=409, cuerpo={"detail": "El comprobante remito:1 ya esta facturado"},
    ))

    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [remito["id"]]})

    resultado = r.json()["resultados"][0]
    assert resultado["estado"] == "resuelto_remoto"
    assert "ya esta facturado" in resultado["detalle"]


def test_mandar_varios_y_que_falle_uno_no_pierde_a_los_otros(client, configurado):
    """Fallar la request entera dejaría al usuario sin saber cuáles llegaron."""
    cliente_id = _cliente_final(client)
    uno = _remito(client, cliente_id)
    dos = _remito(client, cliente_id)

    class FallaElSegundo(ClienteFalso):
        def post(self, url, json=None, headers=None, timeout=None):
            self.llamadas.append({"url": url, "json": json, "headers": headers,
                                  "timeout": timeout})
            if len(self.llamadas) == 2:
                raise httpx.ReadTimeout("tardo demasiado")
            return httpx.Response(201, json={"id": 7, "creado": True},
                                  request=httpx.Request("POST", url))

    _con_puente_falso(client, FallaElSegundo())

    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [uno["id"], dos["id"]]})

    estados = [x["estado"] for x in r.json()["resultados"]]
    assert estados == ["enviado", "error"]


def test_reintentar_actualiza_la_fila_y_no_agrega_otra(client, configurado):
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)

    _con_puente_falso(client, ClienteFalso(excepcion=httpx.ConnectError("caido")))
    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [remito["id"]]})
    assert client.get("/api/facturacion/estado").json()["envios"][0]["estado"] == "error"

    _con_puente_falso(client, ClienteFalso())
    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [remito["id"]]})

    envios = client.get("/api/facturacion/estado").json()["envios"]
    assert len(envios) == 1, "el reintento tiene que actualizar, no duplicar"
    assert envios[0]["estado"] == "enviado"
    assert envios[0]["comprobante_remoto_id"] == 7


def test_un_reintento_fallido_no_borra_el_id_remoto_del_envio_que_si_llego(
    client, configurado,
):
    """Ese id es con lo que después se pregunta en qué quedó. Pisarlo con
    `None` dejaría el envío huérfano justo cuando hay algo que consultar."""
    cliente_id = _cliente_final(client)
    remito = _remito(client, cliente_id)

    _con_puente_falso(client, ClienteFalso())
    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [remito["id"]]})

    _con_puente_falso(client, ClienteFalso(excepcion=httpx.ConnectError("caido")))
    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [remito["id"]]})

    envio = client.get("/api/facturacion/estado").json()["envios"][0]
    assert envio["estado"] == "error"
    assert envio["comprobante_remoto_id"] == 7


# ── Lo que ve la pantalla ────────────────────────────────────────────────────

def test_los_pendientes_marcan_lo_ya_enviado(client, configurado):
    cliente_id = _cliente_final(client)
    enviado = _remito(client, cliente_id)
    sin_enviar = _remito(client, cliente_id)
    _con_puente_falso(client, ClienteFalso())
    client.post("/api/facturacion/enviar",
                json={"origen_tipo": "remito", "ids": [enviado["id"]]})

    por_id = {i["id"]: i for i in client.get("/api/facturacion/pendientes").json()["items"]}
    assert por_id[enviado["id"]]["envio"]["estado"] == "enviado"
    assert por_id[sin_enviar["id"]]["envio"] is None


def test_un_comprobante_que_no_existe_da_404(client, configurado):
    _con_puente_falso(client, ClienteFalso())
    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "remito", "ids": [99999]})
    assert r.status_code == 404


def test_un_origen_tipo_desconocido_da_422(client, configurado):
    r = client.post("/api/facturacion/enviar",
                    json={"origen_tipo": "lo_que_sea", "ids": [1]})
    assert r.status_code == 422


# ── Quién puede ──────────────────────────────────────────────────────────────

def test_sin_sesion_no_se_puede_ni_mirar(client_sin_login):
    assert client_sin_login.get("/api/facturacion/estado").status_code == 401
    assert client_sin_login.post(
        "/api/facturacion/enviar", json={"origen_tipo": "remito", "ids": [1]},
    ).status_code == 401
