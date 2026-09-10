"""Enterarse de que el comprobante ya no está del otro lado.

El caso real (2026-09-09): en "Enviar a facturar" varios remitos mostraban
**"En la bandeja"** y, al consultar, *"No se pudo leer"*. Eran remitos de prueba
cuyas ventas se habían borrado en SOS. Las dos mitades del problema:

1. La consulta **no distinguía** "SOS contestó que no existe" de "no pude
   preguntarle a SOS". Los dos salían como el mismo `ErrorSOS` y la pantalla los
   pintaba con el mismo cartel, que además no llevaba a ninguna acción.
2. La consulta **no escribía nada**, así que el envío quedaba en `enviado` para
   siempre. Del otro lado nadie avisa cuando borran un comprobante: el momento
   de la consulta es el único en que LibraDesk puede enterarse.

Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que un error de comunicación NO reescriba el estado local.** Es la
   dirección cara del error: marcar "ya no está allá" un comprobante que sí
   está lleva a mandarlo de nuevo y **duplicarlo del lado del contador**, que es
   el único lugar donde duplicar cuesta plata.
2. 🔴 Que una confirmación de que no está sí lo reescriba, y que la pantalla
   reciba las dos cosas por campos distintos (`ausente` vs `error`).
3. Que un cambio de forma en la API de SOS caiga del lado seguro ("no pude
   leer"), no del lado que escribe.
"""
import httpx
import pytest

from app.services import facturacion_externa as fe
from app.services import facturacion_sos as sos


@pytest.fixture
def sos_configurado(monkeypatch):
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    monkeypatch.setenv(sos.USUARIO_ENV, "api@test")
    monkeypatch.setenv(sos.PASSWORD_ENV, "clave")
    monkeypatch.setenv(sos.IDCUIT_ENV, "30953")
    monkeypatch.setenv(sos.PUNTOVENTA_ENV, "15")
    monkeypatch.setenv(sos.LETRA_ENV, "A")


@pytest.fixture
def puente(url_de_base):
    """Un puente sobre la base propia del test. Mismo patrón —y mismo
    `dispose()` obligatorio— que `test_facturacion_destino.py`."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    engine = create_engine(url_de_base)
    yield fe.PuenteFacturacion(sessionmaker(engine))
    engine.dispose()


class HttpDetalle:
    """Contesta el login y después el cuerpo que le pidan para `/venta/detalle`.

    El login se responde aparte porque `estado_venta` saca el token primero: si
    el falso no lo contempla, el test falla por la autenticación y no por lo que
    quiere medir.
    """

    def __init__(self, cuerpo=None, excepcion=None):
        self.cuerpo = cuerpo
        self.excepcion = excepcion

    def request(self, metodo, url, json=None, headers=None, timeout=None):
        if "/login" in url or "/cuit/credentials/" in url:
            return httpx.Response(200, json={"jwt": "J"},
                                  request=httpx.Request("GET", "https://x"))
        if self.excepcion:
            raise self.excepcion
        return httpx.Response(200, json=self.cuerpo,
                              request=httpx.Request("GET", "https://x"))


def _estado(cuerpo=None, excepcion=None):
    return sos.AdaptadorSOS(
        cliente_http=HttpDetalle(cuerpo, excepcion)).estado_venta(906683730)


# ── 1. Qué es "ya no está" y qué no ─────────────────────────────────────────

#: El texto **real**, copiado de la respuesta de SOS medida el 2026-09-10 contra
#: las ventas borradas de `lagrace` y contra un id inventado. Va como constante
#: propia porque es el único caso de la lista que existe de verdad: los demás
#: son formas plausibles por si SOS cambia el texto.
MENSAJE_REAL_DE_SOS = "Error: Imposible cargar detalles de la venta"


def test_el_mensaje_real_de_sos_se_clasifica_como_venta_inexistente(sos_configurado):
    """🔴 El caso de producción, y el que faltaba.

    La primera versión de esto salió sin poder medir qué contesta SOS, con una
    lista de frases plausibles —"no existe", "inexistente", "not found"…—. **SOS
    no usa ninguna**: dice *"Imposible cargar detalles de la venta"*, que suena a
    falla interna. Resultado: en `lagrace` los tres remitos cuya venta estaba
    borrada mostraban "No se pudo preguntar" y el envío seguía en "En la
    bandeja". El código hacía lo correcto —caer del lado seguro— sin servir para
    nada.

    Que ese texto signifique *ese id no resuelve* está establecido con un par de
    controles, no por lectura: una venta viva devuelve `cabecera` completa y un
    id inventado devuelve exactamente este mensaje. Ver
    `FRASES_VENTA_INEXISTENTE`.
    """
    with pytest.raises(sos.VentaInexistente):
        _estado({"error": MENSAJE_REAL_DE_SOS})


@pytest.mark.parametrize("mensaje", [
    "La venta no existe",
    "Comprobante inexistente",
    "No se encontró el comprobante",
    "not found",
    "El comprobante fue eliminado",
    "Comprobante anulado",
])
def test_las_formas_plausibles_tambien_caen_ahi(sos_configurado, mensaje):
    """La red por si SOS cambia el texto. **Ninguna de éstas está medida** — la
    medida es `MENSAJE_REAL_DE_SOS`."""
    with pytest.raises(sos.VentaInexistente):
        _estado({"error": mensaje})


@pytest.mark.parametrize("cuerpo", [
    {},
    {"cabecera": None},
    {"cabecera": None, "items": []},
    {"cabecera": {}},
])
def test_una_respuesta_vacia_tambien_es_venta_inexistente(sos_configurado, cuerpo):
    """Contestó por ese id y no tiene nada que mostrar."""
    with pytest.raises(sos.VentaInexistente):
        _estado(cuerpo)


def test_un_cuerpo_con_contenido_pero_sin_cabecera_no_es_venta_inexistente(
    sos_configurado,
):
    """🔴 El caso que separa "no está" de "cambió la API".

    Si SOS renombrara `cabecera`, tratar eso como "no está" marcaría ausente a
    **todos** los comprobantes de la instancia de un saque. Cae del lado seguro:
    `ErrorSOS` pelado, que no habilita a escribir nada.
    """
    with pytest.raises(sos.ErrorSOS) as e:
        _estado({"encabezado": {"id": 1, "cae": None}, "items": [{"x": 1}]})
    assert not isinstance(e.value, sos.VentaInexistente)


@pytest.mark.parametrize("mensaje", [
    "Token expirado",
    "Usuario o clave no válidos",
    "Error interno del servidor",
    "Error",
])
def test_otros_errores_de_sos_no_son_venta_inexistente(sos_configurado, mensaje):
    """No sabemos nada de la venta, y no saber no es saber que no está.

    El `"Error"` pelado del final marca el borde: el mensaje medido **empieza**
    con "Error:", así que un matcher que se aflojara hasta esa palabra
    clasificaría como ausente cualquier cosa que SOS conteste.
    """
    with pytest.raises(sos.ErrorSOS) as e:
        _estado({"error": mensaje})
    assert not isinstance(e.value, sos.VentaInexistente)


def test_un_comprobante_que_esta_se_sigue_leyendo_igual(sos_configurado):
    """El control positivo: el camino feliz no se movió."""
    estado = _estado({"cabecera": {"id": 906683730, "fcncnd": "F", "letra": "A",
                                   "puntoventa": 15, "numero": 1, "cae": None}})
    assert estado["emitido"] is False
    assert estado["comprobante"] == "FA 0015-00000001"


# ── 1b. El reintento ────────────────────────────────────────────────────────
#
# `GET /venta/detalle` de SOS es intermitente (medido el 2026-09-10: el mismo id
# cortó a los 15,5 s y contestó a los 3,7 s). Lo que fijan estos tests es qué se
# reintenta y qué no: el silencio sí, una respuesta nunca.

CABECERA = {"cabecera": {"id": 906683730, "fcncnd": "F", "letra": "A",
                         "puntoventa": 15, "numero": 1, "cae": None}}


class HttpSecuencia:
    """Como `HttpDetalle`, pero cada pregunta por `/venta/detalle` saca la
    respuesta siguiente de la lista —un cuerpo o una excepción— y las cuenta.

    Los tests dejan **una respuesta de más** al final a propósito: si el código
    preguntara una vez más de lo debido, la consumiría y el resultado cambiaría,
    en vez de fallar por una lista vacía que no dice nada."""

    def __init__(self, *respuestas):
        self.respuestas = list(respuestas)
        self.preguntas = 0

    def request(self, metodo, url, json=None, headers=None, timeout=None):
        if "/login" in url or "/cuit/credentials/" in url:
            return httpx.Response(200, json={"jwt": "J"},
                                  request=httpx.Request("GET", "https://x"))
        self.preguntas += 1
        respuesta = self.respuestas.pop(0)
        if isinstance(respuesta, Exception):
            raise respuesta
        return httpx.Response(200, json=respuesta,
                              request=httpx.Request("GET", "https://x"))


def _estado_en_secuencia(*respuestas):
    http = HttpSecuencia(*respuestas)
    adaptador = sos.AdaptadorSOS(cliente_http=http)
    return adaptador, http


def test_un_corte_de_sos_se_reintenta_y_la_segunda_respuesta_manda(sos_configurado):
    """🔴 El caso medido: el primer intento corta, el segundo contesta bien."""
    adaptador, http = _estado_en_secuencia(httpx.ReadTimeout("corte de SOS"),
                                           CABECERA)

    estado = adaptador.estado_venta(906683730)

    assert estado["comprobante"] == "FA 0015-00000001"
    assert http.preguntas == 2


def test_un_corte_seguido_del_mensaje_real_es_venta_inexistente(sos_configurado):
    """Lo que pasó con las ventas borradas de `lagrace`: timeout y después la
    frase medida. Sin reintento esa fila quedaba en "No se pudo preguntar"."""
    adaptador, http = _estado_en_secuencia(httpx.ReadTimeout("corte de SOS"),
                                           {"error": MENSAJE_REAL_DE_SOS},
                                           CABECERA)

    with pytest.raises(sos.VentaInexistente):
        adaptador.estado_venta(906683730)
    assert http.preguntas == 2


def test_un_error_de_sos_tambien_se_reintenta(sos_configurado):
    adaptador, http = _estado_en_secuencia({"error": "Error interno del servidor"},
                                           CABECERA)

    assert adaptador.estado_venta(906683730)["emitido"] is False
    assert http.preguntas == 2


def test_venta_inexistente_no_se_reintenta(sos_configurado):
    """🔴 "Ya no está" es SOS contestando, no SOS callado. Si se reintentara, la
    cabecera que queda en la lista la haría aparecer como viva."""
    adaptador, http = _estado_en_secuencia({"error": MENSAJE_REAL_DE_SOS},
                                           CABECERA)

    with pytest.raises(sos.VentaInexistente):
        adaptador.estado_venta(906683730)
    assert http.preguntas == 1


def test_la_respuesta_buena_no_se_reintenta(sos_configurado):
    adaptador, http = _estado_en_secuencia(CABECERA, CABECERA)

    adaptador.estado_venta(906683730)

    assert http.preguntas == 1


def test_si_todos_los_intentos_cortan_sale_el_error_y_con_tope(sos_configurado):
    """Con el tope fijo. La ruta recorre las filas de a una, así que cada
    intento de más es un corte de SOS más por fila en el peor caso."""
    cortes = [httpx.ReadTimeout("corte de SOS")] * sos.INTENTOS_ESTADO_VENTA
    adaptador, http = _estado_en_secuencia(*cortes, CABECERA)

    with pytest.raises(httpx.TransportError):
        adaptador.estado_venta(906683730)
    assert http.preguntas == sos.INTENTOS_ESTADO_VENTA


# ── 2. La escritura de vuelta, sobre la base ────────────────────────────────

def _envio_enviado(puente, origen_id=12, remoto=906683730):
    return puente._registrar(fe.ORIGEN_REMITO, origen_id, fe.ESTADO_ENVIADO,
                             comprobante_remoto_id=remoto)


def test_marcar_ausente_deja_el_estado_y_conserva_el_id_remoto(puente):
    _envio_enviado(puente)

    envio = puente.marcar_ausente_remoto(fe.ORIGEN_REMITO, 12, detalle="ya no está")

    assert envio["estado"] == fe.ESTADO_AUSENTE_REMOTO
    # El rastro de a dónde había ido no se borra: sirve para discutir qué pasó.
    assert envio["comprobante_remoto_id"] == 906683730


def test_si_reaparece_vuelve_a_enviado(puente):
    _envio_enviado(puente)
    puente.marcar_ausente_remoto(fe.ORIGEN_REMITO, 12)

    envio = puente.desmarcar_ausente_remoto(fe.ORIGEN_REMITO, 12)

    assert envio["estado"] == fe.ESTADO_ENVIADO


def test_desmarcar_no_toca_un_estado_que_no_sea_ausente(puente):
    """`resuelto_remoto` significa "ya lo facturaron o lo descartaron". Que la
    reconciliación lo pisara con `enviado` volvería a ofrecerlo como pendiente."""
    puente._registrar(fe.ORIGEN_REMITO, 12, fe.ESTADO_RESUELTO_REMOTO,
                      comprobante_remoto_id=906683730)

    assert puente.desmarcar_ausente_remoto(fe.ORIGEN_REMITO, 12) is None
    envio = puente.get_envio(fe.ORIGEN_REMITO, 12)
    assert envio.estado == fe.ESTADO_RESUELTO_REMOTO


# ── 3. La ruta, de punta a punta ────────────────────────────────────────────

class PuenteFalso:
    """Lo mínimo que la ruta le pide al puente, con las escrituras anotadas."""

    def __init__(self, envios):
        self.envios = envios
        self.marcados = []
        self.desmarcados = []

    def listar(self):
        return self.envios

    def marcar_ausente_remoto(self, origen_tipo, origen_id, detalle=""):
        self.marcados.append((origen_tipo, origen_id, detalle))
        return {}

    def desmarcar_ausente_remoto(self, origen_tipo, origen_id):
        self.desmarcados.append((origen_tipo, origen_id))
        return None


class AdaptadorFalso:
    def __init__(self, excepcion=None, estado=None):
        self.excepcion = excepcion
        self.estado = estado or {"emitido": False, "cae": "",
                                 "comprobante": "FA 0015-00000001"}

    def estado_venta(self, idventa):
        if self.excepcion:
            raise self.excepcion
        return dict(self.estado)


@pytest.fixture
def client(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def bandeja(client, monkeypatch, sos_configurado):
    """La ruta con un envío ya mandado y el adaptador de SOS intervenido."""
    falso = PuenteFalso([{"origen_tipo": fe.ORIGEN_REMITO, "origen_id": 12,
                          "comprobante_remoto_id": 906483888}])
    client.app.state.puente_facturacion = falso

    def montar(adaptador):
        monkeypatch.setattr(sos, "AdaptadorSOS", lambda *a, **k: adaptador)
        return client.post("/api/facturacion/estados-sos")

    return falso, montar


def test_una_venta_borrada_se_marca_y_la_fila_lo_dice(bandeja):
    puente, montar = bandeja

    r = montar(AdaptadorFalso(sos.VentaInexistente("SOS ya no tiene la venta 906483888")))

    assert r.status_code == 200, r.text
    fila = r.json()["items"][0]
    assert fila["ausente"] is True
    assert "error" not in fila, "no es un error: es una respuesta"
    assert puente.marcados == [
        (fe.ORIGEN_REMITO, 12, "SOS ya no tiene la venta 906483888")]


def test_sos_caido_no_reescribe_nada(bandeja):
    """🔴 El test que sostiene toda la función.

    Si alguien ensancha el `except` y agarra `ErrorSOS` donde va
    `VentaInexistente`, esta afirmación se pone roja: un SOS caído marcaría como
    ausentes a todos los comprobantes de la instancia, y el operador los
    volvería a mandar sobre los que ya están.
    """
    puente, montar = bandeja

    r = montar(AdaptadorFalso(sos.ErrorSOS("detalle de la venta: Token expirado")))

    assert r.status_code == 200, r.text
    fila = r.json()["items"][0]
    assert "Token expirado" in fila["error"]
    assert fila.get("ausente") is None
    assert puente.marcados == [], "no se pudo preguntar: no se escribe nada"


def test_una_venta_que_esta_desmarca_por_las_dudas(bandeja):
    """Si estaba anotada como ausente y reapareció, se corrige sola."""
    puente, montar = bandeja

    r = montar(AdaptadorFalso())

    assert r.json()["items"][0]["emitido"] is False
    assert puente.desmarcados == [(fe.ORIGEN_REMITO, 12)]
    assert puente.marcados == []


def test_un_timeout_de_red_tampoco_reescribe(bandeja):
    """`httpx.HTTPError` entra por la otra rama del mismo `except`."""
    puente, montar = bandeja

    r = montar(AdaptadorFalso(httpx.ConnectTimeout("timeout")))

    assert "error" in r.json()["items"][0]
    assert puente.marcados == []
