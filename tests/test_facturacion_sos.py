"""El adaptador de SOS Contador.

Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que un rechazo no se registre como envío exitoso.** SOS contesta
   HTTP 200 siempre, y el alta rechazada devuelve `{"id": -4}` sin la clave
   `error`. Las dos formas de falso verde se comieron una verificación real el
   2026-08-11 antes de que existiera este archivo.
2. 🔴 **Que `obtienecae` sea `False` siempre.** Es lo único irreversible del
   circuito: pedir el CAE emite ante ARCA.
3. 🔴 **Que sin configurar no mande nada** — misma garantía de adopción que el
   puente a Contalibra.
4. Que el `uniqueid` sea estable entre reintentos del mismo comprobante, que es
   lo que hace seguro reenviar.
5. Que la numeración se lea del punto de venta correcto.
"""
import pytest

from app.services import facturacion_sos as sos


@pytest.fixture
def configurado(monkeypatch):
    monkeypatch.setenv(sos.USUARIO_ENV, "api@ejemplo.test")
    monkeypatch.setenv(sos.PASSWORD_ENV, "secreta")
    monkeypatch.setenv(sos.IDCUIT_ENV, "135060")
    monkeypatch.setenv(sos.PUNTOVENTA_ENV, "3")
    monkeypatch.setenv(sos.LETRA_ENV, "C")


class RespuestaFalsa:
    def __init__(self, cuerpo, status=200):
        self._cuerpo = cuerpo
        self.status_code = status
        self.text = str(cuerpo)

    def json(self):
        if isinstance(self._cuerpo, str):
            raise ValueError("no es json")
        return self._cuerpo


class ClienteFalso:
    """Responde por ruta. Registra lo que se le pidió, que es lo que hay que
    fijar de un integrador: URL, headers y cuerpo tal como salen."""

    def __init__(self, respuestas: dict):
        self.respuestas = respuestas
        self.llamadas = []

    def request(self, metodo, url, json=None, headers=None, timeout=None):
        self.llamadas.append({"metodo": metodo, "url": url, "json": json,
                              "headers": headers or {}})
        for fragmento, cuerpo in self.respuestas.items():
            if fragmento in url:
                if callable(cuerpo):
                    return RespuestaFalsa(cuerpo(json))
                return RespuestaFalsa(cuerpo)
        return RespuestaFalsa({"error": f"ruta no simulada: {url}"})


def _respuestas_base(alta):
    """El camino feliz hasta el alta, con `alta` como respuesta del PUT."""
    # El orden importa: `ClienteFalso` devuelve la primera clave que aparece en
    # la URL, así que las rutas más largas van antes que sus prefijos
    # (`/cliente/listado` antes que `/cliente`).
    return {
        "/login": {"jwt": "jwt-usuario", "cuits": [{"id": 135060}]},
        "/cuit/credentials/": {"jwt": "jwt-de-cuit"},
        "/cliente/listado": {"items": [{"id": 555, "cuit": "20111111112"}]},
        "/producto/listado": {"items": [
            {"id": 14152102, "producto": "Mano de obra"},
            {"id": 14152103, "producto": "Repuesto"},
        ]},
        "/venta/consulta": {"items": []},
        "/venta/0": alta,
    }


PAYLOAD = {
    "cliente_cuit": "20-11111111-2",
    "cliente_razon": "Cliente de Prueba",
    "cliente_domicilio": "Belgrano 448",
    "fecha_sugerida": "2026-08-11",
    "concepto": "Remito REM-00000012",
    "observaciones": "Service de agosto",
    "uniqueid": "el-uniqueid",
    "items": [
        {"description": "Mano de obra", "qty": 2, "unit_price": 5000, "iva_rate": 0.21},
        {"description": "Repuesto", "qty": 1, "unit_price": 1500, "iva_rate": 0.21},
    ],
}


# ── 1. Los dos falsos verdes ────────────────────────────────────────────────

@pytest.mark.parametrize("codigo,esperado", [
    (-1, "uniqueid"),
    (-4, "número de comprobante ya existe"),
])
def test_un_id_negativo_es_rechazo_no_un_alta(configurado, codigo, esperado):
    """🔴 `{"id": -4}` no trae la clave `error` y no creó nada.

    Es el que se comió la verificación del 2026-08-11: el chequeo era "el
    cuerpo no tiene `error`", y eso lo daba por bueno.
    """
    cliente = ClienteFalso(_respuestas_base({"id": codigo}))
    adaptador = sos.AdaptadorSOS(cliente_http=cliente)

    with pytest.raises(sos.ErrorSOS) as e:
        adaptador.enviar_venta(PAYLOAD)

    assert esperado in str(e.value).lower()


def test_un_error_con_http_200_es_error(configurado):
    """🔴 SOS nunca usa el status para fallar: el 200 tapa todo."""
    cliente = ClienteFalso(_respuestas_base(
        {"error": "TypeError: Cannot read properties of null (reading 'split')"}
    ))
    adaptador = sos.AdaptadorSOS(cliente_http=cliente)

    with pytest.raises(sos.ErrorSOS, match="TypeError"):
        adaptador.enviar_venta(PAYLOAD)


def test_el_alta_exitosa_devuelve_el_id(configurado):
    """El contraste del test de arriba: con un id positivo sí es un alta.

    Sin este test los dos anteriores pasarían con un adaptador que rechaza
    todo.
    """
    cliente = ClienteFalso(_respuestas_base({"id": 900492665}))
    adaptador = sos.AdaptadorSOS(cliente_http=cliente)

    assert adaptador.enviar_venta(PAYLOAD) == 900492665


def test_id_cero_tambien_es_rechazo(configurado):
    """`0` no es un id: el DELETE devuelve `{"id": 0}` cuando no borró nada."""
    cliente = ClienteFalso(_respuestas_base({"id": 0}))
    adaptador = sos.AdaptadorSOS(cliente_http=cliente)

    with pytest.raises(sos.ErrorSOS):
        adaptador.enviar_venta(PAYLOAD)


# ── 2. Lo irreversible ──────────────────────────────────────────────────────

def test_obtienecae_siempre_false(configurado):
    """🔴 Pedir el CAE emite ante ARCA y no es una decisión de LibraDesk."""
    cliente = ClienteFalso(_respuestas_base({"id": 900492665}))
    sos.AdaptadorSOS(cliente_http=cliente).enviar_venta(PAYLOAD)

    alta = [ll for ll in cliente.llamadas if ll["url"].endswith("/venta/0")][0]
    assert alta["json"]["obtienecae"] is False


def test_la_password_no_viaja_fuera_del_login(configurado):
    """La credencial va en el cuerpo del login y en ningún otro lado."""
    cliente = ClienteFalso(_respuestas_base({"id": 900492665}))
    sos.AdaptadorSOS(cliente_http=cliente).enviar_venta(PAYLOAD)

    for llamada in cliente.llamadas:
        if llamada["url"].endswith("/login"):
            continue
        assert "secreta" not in str(llamada["json"])
        assert "secreta" not in str(llamada["headers"])


# ── 3. Falla cerrado ────────────────────────────────────────────────────────

def test_sin_configurar_no_manda_nada(monkeypatch):
    """🔴 Una instancia que no contrató SOS se comporta como antes."""
    for var in (sos.USUARIO_ENV, sos.PASSWORD_ENV, sos.IDCUIT_ENV, sos.PUNTOVENTA_ENV):
        monkeypatch.delenv(var, raising=False)

    cliente = ClienteFalso(_respuestas_base({"id": 1}))
    with pytest.raises(sos.SOSNoConfigurado):
        sos.AdaptadorSOS(cliente_http=cliente).enviar_venta(PAYLOAD)

    assert cliente.llamadas == [], "no se debe contactar a SOS sin configuración"
    assert sos.esta_configurado() is False


# ── 4. Idempotencia ─────────────────────────────────────────────────────────

def test_el_uniqueid_es_estable_para_el_mismo_comprobante():
    """Reintentar el mismo remito manda el mismo `uniqueid`, y SOS lo rechaza
    con -1 en vez de duplicar la venta."""
    a = sos.uniqueid_de("remito", 12, "compulibra")
    b = sos.uniqueid_de("remito", 12, "compulibra")
    assert a == b


def test_el_uniqueid_cambia_por_comprobante_y_por_instancia():
    base = sos.uniqueid_de("remito", 12, "compulibra")
    assert sos.uniqueid_de("remito", 13, "compulibra") != base
    assert sos.uniqueid_de("presupuesto", 12, "compulibra") != base
    # Dos LibraDesk facturando a la misma CUIT no se pisan.
    assert sos.uniqueid_de("remito", 12, "lagrace") != base


# ── 5. Numeración ───────────────────────────────────────────────────────────

def test_proximo_numero_sigue_al_ultimo_del_punto_de_venta(configurado):
    """`numero` es NOT NULL del lado de SOS: lo lleva el emisor.

    El listado devuelve `numero` y `letra` en `null`; los tres datos sólo
    vienen juntos en `factura` ("FA-0003-00009001"), así que se parsea de ahí.
    """
    cliente = ClienteFalso({
        "/login": {"jwt": "j", "cuits": [{"id": 1}]},
        "/cuit/credentials/": {"jwt": "j"},
        "/venta/consulta": {"items": [
            {"factura": "FC-0003-00000007"},
            {"factura": "FC-0003-00000009"},
            {"factura": "FC-0004-00000900"},   # otro punto de venta
            {"factura": "FA-0003-00005000"},   # otra letra
            {"factura": "NCC-0003-00007000"},  # nota de crédito C, no factura
            {"factura": "roto"},
        ]},
    })
    assert sos.AdaptadorSOS(cliente_http=cliente).proximo_numero(3, "C") == 10


def test_sin_ventas_previas_empieza_en_uno(configurado):
    cliente = ClienteFalso({
        "/login": {"jwt": "j", "cuits": [{"id": 1}]},
        "/cuit/credentials/": {"jwt": "j"},
        "/venta/consulta": {"items": []},
    })
    assert sos.AdaptadorSOS(cliente_http=cliente).proximo_numero(3, "C") == 1


# ── 6. Traducción del payload ───────────────────────────────────────────────

def test_el_alta_siempre_lleva_productos(configurado):
    """🔴 Sin `productos`, SOS crea el comprobante **vacío**: descarta las
    imputaciones y deja el total en `null`, pero devuelve un id positivo igual.

    Medido el 2026-08-11 comparando las dos formas del alta. Es el falso verde
    más caro de esta API: el envío queda registrado como bueno y el contador
    abre un borrador en cero.
    """
    cliente = ClienteFalso(_respuestas_base({"id": 900492665}))
    sos.AdaptadorSOS(cliente_http=cliente).enviar_venta(PAYLOAD)

    cuerpo = [ll for ll in cliente.llamadas if ll["url"].endswith("/venta/0")][0]["json"]
    assert cuerpo["productos"], "sin `productos` el comprobante queda vacío"
    assert len(cuerpo["productos"]) == 2
    assert cuerpo["imputaciones"] == [{"i": "neto", "a": 0, "v": 11500.0}]


def test_un_comprobante_sin_items_no_se_manda(configurado):
    """Falla acá, con un detalle que se entiende, en vez de crear un cascarón."""
    cliente = ClienteFalso(_respuestas_base({"id": 900492665}))
    with pytest.raises(sos.ErrorSOS, match="ítems"):
        sos.AdaptadorSOS(cliente_http=cliente).enviar_venta(dict(PAYLOAD, items=[]))

    assert not [ll for ll in cliente.llamadas if ll["url"].endswith("/venta/0")]


def test_el_iva_se_convierte_de_fraccion_a_porcentaje(configurado):
    """LibraDesk guarda 0.21; SOS espera 21.00."""
    cliente = ClienteFalso(_respuestas_base({"id": 1}))
    sos.AdaptadorSOS(cliente_http=cliente).enviar_venta(PAYLOAD)

    cuerpo = [ll for ll in cliente.llamadas if ll["url"].endswith("/venta/0")][0]["json"]
    assert cuerpo["productos"][0]["fa"] == 21.0


def test_un_producto_fijo_evita_llenarle_el_catalogo_al_contador(configurado, monkeypatch):
    """`SOS_IDPRODUCTO` manda todos los ítems contra un producto genérico."""
    monkeypatch.setenv(sos.PRODUCTO_FIJO_ENV, "14152102")
    cliente = ClienteFalso(_respuestas_base({"id": 1}))
    sos.AdaptadorSOS(cliente_http=cliente).enviar_venta(PAYLOAD)

    cuerpo = [ll for ll in cliente.llamadas if ll["url"].endswith("/venta/0")][0]["json"]
    assert [p["id"] for p in cuerpo["productos"]] == [14152102, 14152102]
    assert not [ll for ll in cliente.llamadas
                if ll["metodo"] == "POST" and ll["url"].endswith("/producto")]


def test_un_producto_que_no_esta_en_el_catalogo_se_crea(configurado):
    cliente = ClienteFalso(dict(_respuestas_base({"id": 1}),
                                **{"/producto/listado": {"items": []},
                                   "/producto": {"id": 14400001}}))
    idprod = sos.AdaptadorSOS(cliente_http=cliente).resolver_producto("Mano de obra", 0.21)

    assert idprod == 14400001
    alta = [ll for ll in cliente.llamadas
            if ll["metodo"] == "POST" and ll["url"].endswith("/producto")][0]
    assert alta["json"]["producto"] == "Mano de obra"
    assert alta["json"]["tasaiva"] == 21.0
    # El precio del comprobante no se escribe en la ficha del catálogo.
    assert alta["json"]["precio1"] == 0.0


def test_un_producto_existente_se_reusa_por_nombre(configurado):
    cliente = ClienteFalso(dict(_respuestas_base({"id": 1}), **{
        "/producto/listado": {"items": [{"id": 14152102, "producto": "Mano de Obra"}]},
    }))
    idprod = sos.AdaptadorSOS(cliente_http=cliente).resolver_producto("mano de obra")

    assert idprod == 14152102
    assert not [ll for ll in cliente.llamadas
                if ll["metodo"] == "POST" and ll["url"].endswith("/producto")]


def test_la_fecha_nunca_va_en_null(configurado):
    """Con `fecha: null` el backend de SOS revienta con un TypeError, aunque el
    ejemplo de la colección Postman de 2021 la mande así."""
    cliente = ClienteFalso(_respuestas_base({"id": 1}))
    sin_fecha = dict(PAYLOAD, fecha_sugerida="")
    sos.AdaptadorSOS(cliente_http=cliente).enviar_venta(sin_fecha)

    cuerpo = [ll for ll in cliente.llamadas if ll["url"].endswith("/venta/0")][0]["json"]
    assert cuerpo["fecha"] and len(cuerpo["fecha"]) == 10


@pytest.mark.parametrize("guardado,esperado", [
    ("responsable_inscripto", 1),
    ("Monotributo", 3),
    ("consumidor final", 5),
    ("exento", 2),
    ("cualquier cosa", 5),
    (None, 5),
])
def test_mapeo_de_condicion_iva(guardado, esperado):
    """El id de SOS no es el código de AFIP: Monotributo es id 3 y código 6."""
    assert sos.condicion_iva_sos(guardado) == esperado


# ── 7. Clientes ─────────────────────────────────────────────────────────────

def test_el_cliente_se_busca_por_cuit_y_se_reusa(configurado):
    """Buscar por nombre fallaría: se escribe distinto de los dos lados."""
    cliente = ClienteFalso(_respuestas_base({"id": 1}))
    idclipro = sos.AdaptadorSOS(cliente_http=cliente).resolver_cliente(
        "20-11111111-2", "Cliente De Prueba S.A.")

    assert idclipro == 555
    assert not [ll for ll in cliente.llamadas
                if ll["metodo"] == "POST" and ll["url"].endswith("/cliente")]


def test_si_el_cliente_no_esta_se_crea(configurado):
    cliente = ClienteFalso(dict(_respuestas_base({"id": 1}),
                                **{"/cliente/listado": {"items": []},
                                   "/cliente": {"id": 67875793}}))
    idclipro = sos.AdaptadorSOS(cliente_http=cliente).resolver_cliente(
        "30-99999999-7", "Nuevo Cliente", condicion_iva="responsable_inscripto")

    assert idclipro == 67875793
    alta = [ll for ll in cliente.llamadas
            if ll["metodo"] == "POST" and ll["url"].endswith("/cliente")][0]
    # Al crear el campo se llama `idtipocondicioniva`; al leer, `idcondicioniva`.
    assert alta["json"]["idtipocondicioniva"] == 1
    assert alta["json"]["cuit"] == "30999999997"
