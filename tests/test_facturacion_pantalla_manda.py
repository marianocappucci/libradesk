"""La pantalla de Configuración → Facturación manda sobre el entorno.

Hasta el 2026-08-18 no mandaba: `ConfiguracionFacturacion` la usaba únicamente
su propio router, y el camino de envío —`destino()`, `esta_configurado()` y el
adaptador de SOS— leía **sólo `os.environ`**. La pantalla guardaba usuario,
contraseña e `idcuit` en `config_facturacion` y no cambiaba nada.

Se encontró en la instancia `lagrace`: la fila `sos` habilitada y cargada en la
base a las 19:51, y la pantalla insistiendo con que la instancia *"no está
enlazada con Contalibra"* — el nombre del destino que la instancia **no** usa.

El archivo cubre las dos mitades: quién decide el destino, y de dónde salen las
credenciales.
"""
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.services import facturacion_externa as fe
from app.services import facturacion_sos as sos
from app.services.facturacion_config import (
    ConfiguracionFacturacion,
    configurar_lectura,
)

SOS_COMPLETO = {"usuario": "api@lagrace.test", "password": "clave-de-sos",
                "idcuit": "30953", "puntoventa": "15"}


@pytest.fixture
def config(url_de_base, monkeypatch):
    """La configuración sobre la base del test, ya enchufada al camino de envío.

    El `configurar_lectura(None)` del teardown no es decorativo: el global lo
    comparte todo el proceso, así que dejarlo apuntando a una base que
    `url_de_base` está por dropear haría explotar al test siguiente, y lejos de
    su causa. (En `conftest` hay además una fixture autouse que lo resetea; ésta
    es la del archivo que sí lo usa.)
    """
    # De `SECRET_KEY` se deriva la clave con la que se cifran los secretos.
    # Sin ella el servicio falla cerrado, que es lo correcto en produccion y
    # una dependencia oculta acá: el `client` de conftest la pone, y estos
    # tests no lo usan porque prueban el servicio, no el router.
    monkeypatch.setenv("SECRET_KEY", "una-clave-de-sesion-larga-para-la-prueba")
    engine = create_engine(url_de_base)
    c = ConfiguracionFacturacion(sessionmaker(engine))
    configurar_lectura(c)
    yield c
    configurar_lectura(None)
    engine.dispose()


@pytest.fixture
def secret_key(monkeypatch):
    """De `SECRET_KEY` se deriva la clave que cifra los secretos guardados.

    La piden los tests que van por HTTP: el `client` de conftest arma la app
    pero no pone esta variable, y sin ella `guardar()` falla cerrado con 409 --
    que es lo correcto en produccion y una dependencia oculta aca. Se setea en
    el cuerpo del test y no al construir la app porque se lee en cada llamada,
    no al importar.
    """
    monkeypatch.setenv("SECRET_KEY", "una-clave-de-sesion-larga-para-la-prueba")


@pytest.fixture
def sin_entorno(monkeypatch):
    """Ninguna variable de las dos familias. Lo que quede tiene que salir de la
    base: si alguna sobreviviera, un test podría pasar por el motivo viejo."""
    for var in (fe.DESTINO_ENV, fe.URL_ENV, fe.TOKEN_ENV, fe.INSTANCIA_ENV,
                sos.USUARIO_ENV, sos.PASSWORD_ENV, sos.IDCUIT_ENV,
                sos.PUNTOVENTA_ENV, sos.LETRA_ENV, sos.BASE_URL_ENV,
                sos.TIPO_OPERACION_ENV, sos.PRODUCTO_FIJO_ENV):
        monkeypatch.delenv(var, raising=False)


# ── 1. Quién decide el destino ──────────────────────────────────────────────

def test_el_destino_tildado_en_la_pantalla_gana(config, sin_entorno):
    """🔴 El caso de `lagrace`, exacto: SOS tildado en la base, ninguna variable
    de entorno, y la pantalla nombrando a Contalibra."""
    config.guardar("sos", habilitado=True, valores=SOS_COMPLETO)

    assert fe.destino() == fe.DESTINO_SOS
    assert fe.nombre_destino() == "SOS Contador"


def test_la_base_le_gana_al_entorno(config, sin_entorno, monkeypatch):
    """La base manda, que es lo que dice el módulo desde que existe la pantalla.
    Sin esto, un compose viejo seguiría decidiendo por encima de lo que el
    usuario acaba de tildar, y no habría forma de cambiarlo desde adentro."""
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_CONTALIBRA)
    config.guardar("sos", habilitado=True, valores=SOS_COMPLETO)

    assert fe.destino() == fe.DESTINO_SOS


def test_destindo_destildado_devuelve_la_decision_al_entorno(config, monkeypatch):
    """Destildar no es "elegir Contalibra": es "yo no decido". Con el compose
    diciendo `sos`, la instancia sigue mandando a SOS."""
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    config.guardar("sos", habilitado=False, valores=SOS_COMPLETO)

    assert fe.destino() == fe.DESTINO_SOS


def test_con_los_dos_tildados_decide_el_entorno(config, monkeypatch):
    """No se adivina: mandarle los comprobantes de un cliente al sistema
    equivocado es peor que no elegir."""
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    config.guardar("sos", habilitado=True, valores=SOS_COMPLETO)
    config.guardar("contalibra", habilitado=True,
                   valores={"url": "https://x.test", "token": "t"})

    assert fe.destino() == fe.DESTINO_SOS


def test_con_los_dos_tildados_y_sin_entorno_queda_el_default(config, sin_entorno):
    """El mismo empate sin nadie que lo desempate. `contalibra` es el default
    del módulo desde siempre; lo que importa es que sea determinista."""
    config.guardar("sos", habilitado=True, valores=SOS_COMPLETO)
    config.guardar("contalibra", habilitado=True,
                   valores={"url": "https://x.test", "token": "t"})

    assert fe.destino() == fe.DESTINO_CONTALIBRA


def test_sin_pantalla_el_destino_sigue_saliendo_del_entorno(sin_entorno, monkeypatch):
    """🔴 La garantía de adopción, medida con la lectura APAGADA (que es como
    queda una instancia que nunca abrió la pantalla): nadie cambia de destino
    por actualizar."""
    configurar_lectura(None)
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    assert fe.destino() == fe.DESTINO_SOS
    monkeypatch.delenv(fe.DESTINO_ENV)
    assert fe.destino() == fe.DESTINO_CONTALIBRA


# ── 2. De dónde salen las credenciales ──────────────────────────────────────

def test_sos_configurado_solo_por_pantalla(config, sin_entorno):
    """🔴 La otra mitad del caso de `lagrace`: aunque el destino fuera el
    correcto, `esta_configurado()` leía el entorno y decía que no."""
    config.guardar("sos", habilitado=True, valores=SOS_COMPLETO)

    assert fe.esta_configurado() is True
    cfg = sos.configuracion()
    assert cfg["usuario"] == "api@lagrace.test"
    assert cfg["idcuit"] == "30953"
    assert cfg["puntoventa"] == "15"
    assert cfg["password"] == "clave-de-sos"


def test_a_sos_le_falta_el_idcuit_y_no_esta_configurado(config, sin_entorno):
    """Falla cerrado, igual que antes. Es el estado real en que estaba
    `lagrace`: tildada, con usuario y contraseña, y el `idcuit` vacío."""
    config.guardar("sos", habilitado=True,
                   valores={**SOS_COMPLETO, "idcuit": ""})

    assert fe.destino() == fe.DESTINO_SOS, "el destino sale del tilde, no de estar completo"
    assert fe.esta_configurado() is False


def test_un_campo_que_la_pantalla_no_cargo_cae_al_entorno(config, monkeypatch):
    """Mezcla: la pantalla trae lo que guardó y el compose lo que no.

    Es el caso de una instancia configurada por entorno que abre la pantalla
    para cambiar UNA cosa. Se mira campo por campo justamente por esto.
    """
    monkeypatch.setenv(sos.LETRA_ENV, "A")
    config.guardar("sos", habilitado=True, valores={**SOS_COMPLETO, "letra": ""})

    assert sos.configuracion()["letra"] == "A"


def test_contalibra_tambien_sale_de_la_pantalla(config, sin_entorno):
    """El otro destino: no se arregló sólo el que dio el problema."""
    config.guardar("contalibra", habilitado=True, valores={
        "url": "https://cliente.contalibra.com.ar/", "instancia": "lagrace",
        "token": "token-de-servicio",
    })

    url, token, instancia = fe.configuracion()
    assert url == "https://cliente.contalibra.com.ar", "la barra final se recorta"
    assert token == "token-de-servicio"
    assert instancia == "lagrace"
    assert fe.esta_configurado() is True


def test_sin_pantalla_las_credenciales_siguen_saliendo_del_entorno(monkeypatch):
    """La contraparte del anterior, con la lectura apagada."""
    configurar_lectura(None)
    monkeypatch.setenv(fe.URL_ENV, "https://viejo.contalibra.com.ar")
    monkeypatch.setenv(fe.TOKEN_ENV, "token-del-compose")

    url, token, _ = fe.configuracion()
    assert url == "https://viejo.contalibra.com.ar"
    assert token == "token-del-compose"


# ── 3. El listado de CUITs ──────────────────────────────────────────────────

class HttpFalso:
    """Cliente HTTP de mentira, con las respuestas medidas contra la API real
    el 2026-08-18."""

    def __init__(self, login=None, listado=None):
        self._login = login if login is not None else {"jwt": "JWT", "idusuario": 97244}
        self._listado = listado if listado is not None else {"items": [
            {"id": 30953, "cuit": "30659034014", "habilitado": 1,
             "razonsocial": "Adolfo Lagrace Comunicaciones", "owner": False},
        ]}
        self.rutas = []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def _resp(self, cuerpo):
        return httpx.Response(200, json=cuerpo, request=httpx.Request("GET", "https://x"))

    def post(self, url, **kw):
        self.rutas.append(url)
        return self._resp(self._login)

    def get(self, url, **kw):
        self.rutas.append(url)
        return self._resp(self._listado)


def test_listar_cuits_devuelve_el_id_interno(config, sin_entorno, monkeypatch):
    """Lo que hace que el `idcuit` deje de buscarse con un script."""
    config.guardar("sos", habilitado=True, valores=SOS_COMPLETO)
    falso = HttpFalso()
    monkeypatch.setattr(sos.httpx, "Client", lambda **kw: falso)

    cuits = sos.listar_cuits()

    assert cuits == [{"idcuit": "30953", "cuit": "30659034014",
                      "razonsocial": "Adolfo Lagrace Comunicaciones",
                      "habilitado": True}]
    assert any(r.endswith("/cuit/listado") for r in falso.rutas)


def test_listar_cuits_acepta_la_lista_pelada(config, sin_entorno, monkeypatch):
    """La colección Postman de SOS —de 2021— documenta la lista sin envolver.
    La API real devuelve `items`. No hay forma de saber cuál sirve cada
    instancia, así que se aceptan las dos."""
    config.guardar("sos", habilitado=True, valores=SOS_COMPLETO)
    monkeypatch.setattr(sos.httpx, "Client", lambda **kw: HttpFalso(
        listado=[{"id": 7, "cuit": "20111111112", "razonsocial": "Otra"}]))

    assert sos.listar_cuits()[0]["idcuit"] == "7"


def test_listar_cuits_usa_lo_tipeado_antes_de_guardar(config, sin_entorno, monkeypatch):
    """El botón se aprieta MIENTRAS se carga la pantalla, antes del primer
    Guardar — que además no se puede completar sin el `idcuit`."""
    falso = HttpFalso()
    enviados = {}

    def post(url, json=None, **kw):
        enviados.update(json or {})
        return falso._resp(falso._login)

    falso.post = post
    monkeypatch.setattr(sos.httpx, "Client", lambda **kw: falso)

    sos.listar_cuits("tipeado@test", "clave-tipeada")

    assert enviados["usuario"] == "tipeado@test"
    assert enviados["password"] == "clave-tipeada"


def test_sin_credenciales_no_se_consulta_nada(config, sin_entorno, monkeypatch):
    """No es un lugar para averiguar si una cuenta existe: sin credenciales ni
    siquiera se sale a la red."""
    llamadas = []
    monkeypatch.setattr(sos.httpx, "Client",
                        lambda **kw: llamadas.append(1) or HttpFalso())

    assert sos.listar_cuits() == []
    assert llamadas == []


def test_un_login_sin_jwt_es_un_error_de_sos(config, sin_entorno, monkeypatch):
    """La credencial equivocada tiene que llegar a la pantalla como un error, no
    como una lista vacía: "no tenés CUITs" y "la clave está mal" se arreglan de
    maneras distintas."""
    config.guardar("sos", habilitado=True, valores=SOS_COMPLETO)
    monkeypatch.setattr(sos.httpx, "Client",
                        lambda **kw: HttpFalso(login={"error": "Usuario o clave no válidos"}))

    with pytest.raises(sos.ErrorSOS):
        sos.listar_cuits()


# ── 4. A través de la app, que es donde se vio el defecto ───────────────────
#
# Los de arriba prueban los servicios. Éstos van por HTTP contra la app armada
# por `create_app`, así que además ejercitan el `configurar_lectura` del app
# factory: sin esa línea la pantalla vuelve a ser decorativa y estos casos se
# ponen rojos, que es exactamente lo que no pasó durante los siete días en que
# el defecto estuvo vivo.


def _login(client, username="admin", password="admin"):
    assert client.post("/auth/login", json={"username": username,
                                            "password": password}).status_code == 200


def test_configurar_sos_por_la_api_cambia_lo_que_dice_la_pantalla(client, secret_key):
    """🔴 El síntoma que reportó el humano, reproducido de punta a punta.

    *"en lagrace habilité SOS Contador y me sigue apareciendo: Esta instancia
    no está enlazada con Contalibra"*. Antes de este arreglo, el PUT guardaba y
    `/api/facturacion/estado` seguía contestando `contalibra`.
    """
    _login(client)

    antes = client.get("/api/facturacion/estado").json()
    assert antes["destino"] == "contalibra", "control: sin configurar, el default"

    r = client.put("/api/facturacion/config/sos", json={
        "habilitado": True, "valores": SOS_COMPLETO,
    })
    assert r.status_code == 200, r.text

    despues = client.get("/api/facturacion/estado").json()
    assert despues["destino"] == "sos"
    assert despues["destino_nombre"] == "SOS Contador"
    assert despues["configurado"] is True


def test_el_endpoint_de_cuits_devuelve_el_listado(client, secret_key, monkeypatch):
    _login(client)
    client.put("/api/facturacion/config/sos",
               json={"habilitado": True, "valores": SOS_COMPLETO})
    monkeypatch.setattr(sos.httpx, "Client", lambda **kw: HttpFalso())

    r = client.post("/api/facturacion/config/sos/cuits", json={})

    assert r.status_code == 200, r.text
    assert r.json()["cuits"][0]["idcuit"] == "30953"


def test_el_endpoint_de_cuits_no_devuelve_credenciales(client, secret_key, monkeypatch):
    """Lo que sale son id, CUIT y razón social. Nada más: es una respuesta que
    pasa por el navegador de quien configura."""
    _login(client)
    client.put("/api/facturacion/config/sos",
               json={"habilitado": True, "valores": SOS_COMPLETO})
    monkeypatch.setattr(sos.httpx, "Client", lambda **kw: HttpFalso())

    cuerpo = client.post("/api/facturacion/config/sos/cuits", json={}).text

    assert SOS_COMPLETO["password"] not in cuerpo
    assert SOS_COMPLETO["usuario"] not in cuerpo


def test_una_credencial_mala_llega_como_409_y_no_como_lista_vacia(client, monkeypatch):
    """"No tenés CUITs" y "la clave está mal" se arreglan de maneras distintas,
    así que no pueden verse igual en la pantalla."""
    _login(client)
    monkeypatch.setattr(sos.httpx, "Client", lambda **kw: HttpFalso(
        login={"error": "Usuario o clave no válidos"}))

    r = client.post("/api/facturacion/config/sos/cuits",
                    json={"usuario": "quien@sea", "password": "mal"})

    assert r.status_code == 409


def test_staff_no_puede_pedir_las_cuits(client):
    """El router entero exige admin; la ruta nueva lo hereda. Se cubre igual:
    el día que alguien la monte aparte, el gate se pierde sin que nada avise."""
    _login(client)
    client.post("/api/usuarios", json={"username": "staff1", "name": "Staff",
                                       "password": "staff123", "role": "staff"})
    otro = TestClient(client.app, base_url="https://testserver")
    _login(otro, "staff1", "staff123")

    assert otro.post("/api/facturacion/config/sos/cuits", json={}).status_code == 403
