"""Coherencia fiscal del comprobante que sale hacia SOS.

Los cuatro defectos que destapó el primer envío real de Lagrace, el 2026-08-18.
El comprobante salió con letra **A**, condición **Consumidor Final** y CUIT
**0** — tres campos que se contradicen entre sí, cada uno traído de un lugar
distinto:

1. `resolver_cliente` buscaba en `pagina=1&registros=500` creyendo que traía
   todo. SOS **ignora `registros` y tapa en 50**: en la cuenta de Lagrace eso es
   la primera de 35 páginas, 50 de 1.737 clientes. Un cliente que ya existía más
   allá no se encontraba y se le creaba un **duplicado al contador**.
2. La condición de IVA del receptor **nunca viajaba**: el remito no la guarda, y
   el default silencioso la resolvía a Consumidor Final para todos.
3. La letra era un valor **fijo de la instancia**, no del receptor.
4. Nada impedía mandar un comprobante que no se puede emitir.

Los cuatro se tocan en el mismo camino, así que se prueban juntos.
"""
import httpx
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.services import facturacion_externa as fe
from app.services import facturacion_sos as sos

COMPROBANTE = {
    "id": 12,
    "number": "REM-00000012",
    "client_id": 1,
    "client_name": "Clínica del Sol SA",
    "client_cuit": "",
    "client_address": "CABA",
    "date": "2026-08-12",
    "observations": "Service de agosto",
    "items": [{"description": "Mano de obra", "qty": 2, "unit_price": 5000,
               "tax_rate": 0.21}],
}


@pytest.fixture
def puente(url_de_base):
    engine = create_engine(url_de_base)
    yield fe.PuenteFacturacion(sessionmaker(engine))
    engine.dispose()


@pytest.fixture
def cliente_en_la_base(url_de_base):
    """Da de alta una ficha de cliente y devuelve una función para editarla.

    Hace falta una fila real porque lo que se prueba es justamente que el puente
    **vaya a buscarla**: con un mock del repositorio, el test pasaría aunque el
    puente siguiera leyendo el comprobante.
    """
    engine = create_engine(url_de_base)
    def _poner(iva_condition="", cuit_dni=""):
        with engine.begin() as con:
            con.execute(text("DELETE FROM clients WHERE id = 1"))
            # `tipo_facturacion` va explícito: es NOT NULL y su default lo pone
            # el ABM, no la base.
            con.execute(
                text("INSERT INTO clients (id, name, iva_condition, cuit_dni, "
                     "tipo_facturacion) VALUES (1, :n, :c, :d, 'mensual')"),
                {"n": "Clínica del Sol SA", "c": iva_condition, "d": cuit_dni},
            )
    yield _poner
    engine.dispose()


@pytest.fixture
def sos_configurado(monkeypatch):
    """SOS como destino, con la letra A puesta — o sea emisor Responsable
    Inscripto, que es la configuración de `lagrace`."""
    monkeypatch.setenv(fe.DESTINO_ENV, fe.DESTINO_SOS)
    monkeypatch.setenv(sos.USUARIO_ENV, "api@test")
    monkeypatch.setenv(sos.PASSWORD_ENV, "clave")
    monkeypatch.setenv(sos.IDCUIT_ENV, "30953")
    monkeypatch.setenv(sos.PUNTOVENTA_ENV, "15")
    monkeypatch.setenv(sos.LETRA_ENV, "A")
    monkeypatch.delenv(sos.CONDICION_EMISOR_ENV, raising=False)


class AdaptadorFalso:
    def __init__(self):
        self.payloads = []

    def enviar_venta(self, payload):
        self.payloads.append(payload)
        return 900492665


# ── 1. La letra sale del receptor ───────────────────────────────────────────

@pytest.mark.parametrize("receptor,esperada", [
    ("responsable_inscripto", "A"),
    ("Responsable Inscripto", "A"),
    ("consumidor_final", "B"),
    ("monotributo", "B"),
    ("exento", "B"),
])
def test_un_emisor_ri_emite_A_al_inscripto_y_B_al_resto(receptor, esperada):
    assert sos.letra_para(receptor, {"letra": "A", "condicion_emisor": ""}) == esperada


@pytest.mark.parametrize("receptor", ["responsable_inscripto", "consumidor_final", ""])
def test_un_emisor_monotributista_emite_siempre_C(receptor):
    """🔴 El control que hace que este cambio no toque `compulibra`.

    Esa instancia tiene `letra = C`, o sea emisor monotributista, y una C es C
    para cualquier receptor. Si esto se rompiera, el cambio le movería la letra
    a una instancia que hoy factura bien.
    """
    assert sos.letra_para(receptor, {"letra": "C", "condicion_emisor": ""}) == "C"


def test_la_condicion_del_emisor_explicita_le_gana_a_la_letra():
    """La letra configurada es una *deducción* de la condición del emisor, para
    las instancias que ya existían. Cuando alguien la declara, manda ella."""
    cfg = {"letra": "C", "condicion_emisor": "ri"}
    assert sos.letra_para("responsable_inscripto", cfg) == "A"
    assert sos.letra_para("consumidor_final", cfg) == "B"


# ── 2. La ficha fiscal del cliente viaja ────────────────────────────────────

def test_la_condicion_sale_de_la_ficha_aunque_el_remito_no_la_lleve(
    puente, cliente_en_la_base, sos_configurado,
):
    """🔴 El defecto que producía el "consumidor final" de todos los envíos.

    El remito **no guarda** la condición de IVA, así que el payload salía vacío
    y el default la resolvía a Consumidor Final — incluso para los clientes que
    tenían "Responsable Inscripto" cargado.
    """
    cliente_en_la_base(iva_condition="Responsable Inscripto", cuit_dni="30659034014")
    adaptador = AdaptadorFalso()
    puente._adaptador_sos = adaptador

    puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)

    enviado = adaptador.payloads[0]
    assert enviado["cliente_condicion_iva"] == "Responsable Inscripto"
    assert enviado["cliente_cuit"] == "30659034014", "el CUIT también sale de la ficha"


def test_el_cuit_del_remito_le_gana_al_de_la_ficha(
    puente, cliente_en_la_base, sos_configurado,
):
    """El snapshot es con lo que se entregó el remito. La ficha es el respaldo
    para el remito viejo, emitido antes de cargarle el CUIT al cliente."""
    cliente_en_la_base(iva_condition="Responsable Inscripto", cuit_dni="20111111112")
    puente._adaptador_sos = AdaptadorFalso()

    puente.enviar(fe.ORIGEN_REMITO, {**COMPROBANTE, "client_cuit": "30659034014"})

    assert puente._adaptador_sos.payloads[0]["cliente_cuit"] == "30659034014"


# ── 3. La guarda ────────────────────────────────────────────────────────────

def test_sin_condicion_de_iva_no_se_manda(puente, cliente_en_la_base, sos_configurado):
    """Y lo que se afirma es que **el adaptador no se llamó**: una guarda que
    cortara después de haber mandado dejaría el comprobante del otro lado igual,
    y el rojo de la pantalla sería mentira."""
    cliente_en_la_base(iva_condition="", cuit_dni="")
    adaptador = AdaptadorFalso()
    puente._adaptador_sos = adaptador

    with pytest.raises(fe.OrigenNoFacturable) as e:
        puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)

    assert "condición de IVA" in str(e.value)
    assert "Clínica del Sol SA" in str(e.value), "el mensaje nombra la ficha a corregir"
    assert adaptador.payloads == []


def test_un_inscripto_sin_cuit_no_se_manda(puente, cliente_en_la_base, sos_configurado):
    """Una A lleva el CUIT del receptor. Es el caso exacto del envío del
    2026-08-18."""
    cliente_en_la_base(iva_condition="Responsable Inscripto", cuit_dni="")
    adaptador = AdaptadorFalso()
    puente._adaptador_sos = adaptador

    with pytest.raises(fe.OrigenNoFacturable) as e:
        puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)

    assert "CUIT" in str(e.value)
    assert adaptador.payloads == []


def test_un_consumidor_final_sin_cuit_SI_se_manda(
    puente, cliente_en_la_base, sos_configurado,
):
    """🔴 El control que evita que la guarda sea "siempre hace falta CUIT".

    A un consumidor final le corresponde una B, y una B no lleva el CUIT del
    receptor. Con el criterio plano, este envío legítimo quedaría bloqueado —
    y hoy son la mayoría de las fichas del parque.
    """
    cliente_en_la_base(iva_condition="Consumidor Final", cuit_dni="")
    adaptador = AdaptadorFalso()
    puente._adaptador_sos = adaptador

    envio = puente.enviar(fe.ORIGEN_REMITO, COMPROBANTE)

    assert envio["estado"] == fe.ESTADO_ENVIADO
    assert len(adaptador.payloads) == 1


# ── 4. El listado de clientes se pagina ─────────────────────────────────────

class HttpPaginado:
    """Un SOS de mentira con 3 páginas de 50 clientes. El buscado está en la 3.

    Las formas —`items`, `paginas`, el tope de 50 aunque se pidan 500— son las
    medidas contra la API real el 2026-08-18.
    """

    CUIT_BUSCADO = "30677237119"

    def __init__(self):
        self.paginas_pedidas = []
        self.altas = []

    def request(self, metodo, url, json=None, headers=None, timeout=None):
        if "/login" in url:
            return self._r({"jwt": "JWT-USUARIO"})
        if "/cuit/credentials/" in url:
            return self._r({"jwt": "JWT-CUIT"})
        if "/cliente/listado" in url:
            pagina = int(url.split("pagina=")[1].split("&")[0])
            self.paginas_pedidas.append(pagina)
            filas = [{"id": 1000 + pagina * 100 + i, "cuit": f"2000000{pagina}{i:02d}"}
                     for i in range(50)]
            if pagina == 3:
                filas[7] = {"id": 10679427, "cuit": self.CUIT_BUSCADO}
            return self._r({"items": filas, "paginas": 3})
        if url.endswith("/cliente"):
            self.altas.append(json)
            return self._r({"id": 999999})
        return self._r({})

    @staticmethod
    def _r(cuerpo):
        return httpx.Response(200, json=cuerpo, request=httpx.Request("GET", "https://x"))


def test_al_cliente_de_la_pagina_3_lo_encuentra_y_no_lo_duplica(sos_configurado):
    """🔴 El defecto más caro de los cuatro: ensuciaba el sistema del contador.

    Con la búsqueda de una sola página, este cliente —que existe— no aparecía y
    se le creaba un duplicado. Se comprobó mutando el adaptador para que sólo
    mire la página 1: el caso se pone rojo por el alta que no debería existir.
    """
    falso = HttpPaginado()
    adaptador = sos.AdaptadorSOS(cliente_http=falso)

    idclipro = adaptador.resolver_cliente(HttpPaginado.CUIT_BUSCADO, "Autopistas del Sol SA")

    assert idclipro == 10679427
    assert falso.altas == [], "no se debe crear un cliente que ya existe"
    assert falso.paginas_pedidas == [1, 2, 3], "se recorren las páginas hasta encontrarlo"


def test_deja_de_pedir_paginas_apenas_lo_encuentra(sos_configurado):
    """La pieza que hace que paginar no cueste 35 requests por envío."""
    falso = HttpPaginado()
    # El primer CUIT que genera la página 1, con la misma fórmula que el falso.
    de_la_pagina_1 = f"2000000{1}{0:02d}"
    adaptador = sos.AdaptadorSOS(cliente_http=falso)

    adaptador.resolver_cliente(de_la_pagina_1, "El primero")

    assert falso.paginas_pedidas == [1]


def test_al_que_no_esta_en_ninguna_pagina_lo_crea(sos_configurado):
    falso = HttpPaginado()
    adaptador = sos.AdaptadorSOS(cliente_http=falso)

    idclipro = adaptador.resolver_cliente("27999999993", "Cliente Nuevo SA",
                                          condicion_iva="responsable_inscripto")

    assert idclipro == 999999
    assert falso.paginas_pedidas == [1, 2, 3], "se agotan las páginas antes de crear"
    assert falso.altas[0]["cuit"] == "27999999993"
    assert falso.altas[0]["idtipocondicioniva"] == 1, "responsable inscripto"


# ── 5. El estado del comprobante, leído de vuelta ───────────────────────────

class HttpDetalle:
    def __init__(self, cae=None):
        self.cae = cae

    def request(self, metodo, url, json=None, headers=None, timeout=None):
        if "/login" in url or "/cuit/credentials/" in url:
            return httpx.Response(200, json={"jwt": "J"},
                                  request=httpx.Request("GET", "https://x"))
        cuerpo = {"cabecera": {"id": 906683730, "fcncnd": "F", "letra": "A",
                               "puntoventa": 15, "numero": 1, "total": 36300,
                               "cae": self.cae, "caevencimiento": None}}
        return httpx.Response(200, json=cuerpo, request=httpx.Request("GET", "https://x"))


def test_un_comprobante_sin_cae_se_lee_como_no_emitido(sos_configurado):
    estado = sos.AdaptadorSOS(cliente_http=HttpDetalle(cae=None)).estado_venta(906683730)

    assert estado["emitido"] is False
    assert estado["cae"] == ""
    assert estado["comprobante"] == "FA 0015-00000001"


def test_cuando_el_contador_emite_aparece_el_cae(sos_configurado):
    estado = sos.AdaptadorSOS(cliente_http=HttpDetalle(cae="71234567890123")).estado_venta(1)

    assert estado["emitido"] is True
    assert estado["cae"] == "71234567890123"


# ── 6. La letra derivada llega al cuerpo que sale ───────────────────────────
#
# 🔴 Este bloque existe porque faltaba, y se notó midiendo: mutando
# `enviar_venta` para que volviera a usar la letra fija de la instancia, los 19
# casos de arriba seguían en verde. `letra_para` estaba cubierta como función y
# **nadie afirmaba que su resultado llegara al comprobante** — que es lo único
# que le importa a ARCA.


class HttpQueGuardaLaVenta:
    """Un SOS de mentira que anota el cuerpo del `PUT /venta/0`.

    El cliente y el producto se resuelven a ids fijos para que el caso hable de
    la letra y de nada más.
    """

    def __init__(self, ultimo_numero_por_etiqueta=None):
        self.venta = None
        self.numeros_consultados = []
        self._ultimos = ultimo_numero_por_etiqueta or {}

    def request(self, metodo, url, json=None, headers=None, timeout=None):
        if "/login" in url or "/cuit/credentials/" in url:
            return self._r({"jwt": "J"})
        if "/cliente/listado" in url:
            return self._r({"items": [{"id": 555, "cuit": "30659034014"}], "paginas": 1})
        if "/producto/listado" in url or url.endswith("/producto"):
            return self._r({"items": [], "id": 777})
        if "/venta/ultimo" in url or "/venta/numero" in url or "/comprobante" in url:
            self.numeros_consultados.append(url)
            return self._r({"items": []})
        if url.endswith("/venta/0"):
            self.venta = json
            return self._r({"id": 900000001})
        return self._r({"items": []})

    @staticmethod
    def _r(cuerpo):
        return httpx.Response(200, json=cuerpo, request=httpx.Request("GET", "https://x"))


def _payload(condicion):
    return {
        "cliente_cuit": "30659034014",
        "cliente_razon": "Clínica del Sol SA",
        "cliente_domicilio": "CABA",
        "cliente_condicion_iva": condicion,
        "concepto": "Remito 0001-00000001",
        "observaciones": "",
        "fecha_sugerida": "2026-08-12",
        "uniqueid": "u-1",
        "items": [{"description": "Mano de obra", "qty": 1, "unit_price": 30000,
                   "tax_rate": 0.21}],
    }


@pytest.mark.parametrize("condicion,esperada", [
    ("Responsable Inscripto", "A"),
    ("Consumidor Final", "B"),
])
def test_la_letra_del_cuerpo_sale_de_la_condicion_del_receptor(
    sos_configurado, monkeypatch, condicion, esperada,
):
    """El caso que la mutación destapó: no alcanza con que `letra_para` acierte,
    tiene que **viajar**."""
    falso = HttpQueGuardaLaVenta()
    adaptador = sos.AdaptadorSOS(cliente_http=falso)
    # La numeración se consulta contra SOS y no es lo que se está probando.
    monkeypatch.setattr(type(adaptador), "proximo_numero",
                        lambda self, pv, letra, fcncnd="F": 1)
    monkeypatch.setattr(type(adaptador), "resolver_items", lambda self, p: [{"id": 777}])

    adaptador.enviar_venta(_payload(condicion))

    assert falso.venta["letra"] == esperada
    assert falso.venta["fcncnd"] == "F"


def test_el_numero_se_pide_para_LA_MISMA_letra_que_se_manda(sos_configurado, monkeypatch):
    """🔴 Cada letra lleva su propia secuencia en el punto de venta.

    Pedirle el número a una letra y mandar otra deja el comprobante con un
    número que en esa serie ya existe, y SOS lo rechaza —o peor, lo acepta
    duplicado—. Es la clase de defecto que sólo aparece cuando la instancia
    empieza a emitir dos letras, o sea justo cuando este cambio entra.
    """
    pedidos = []
    falso = HttpQueGuardaLaVenta()
    adaptador = sos.AdaptadorSOS(cliente_http=falso)
    monkeypatch.setattr(type(adaptador), "proximo_numero",
                        lambda self, pv, letra, fcncnd="F": pedidos.append(letra) or 7)
    monkeypatch.setattr(type(adaptador), "resolver_items", lambda self, p: [{"id": 777}])

    adaptador.enviar_venta(_payload("Consumidor Final"))

    assert pedidos == ["B"], "el número se pidió para la letra que se va a mandar"
    assert falso.venta["letra"] == "B"
    assert falso.venta["numero"] == 7


def test_un_emisor_monotributista_manda_C_aunque_el_receptor_sea_inscripto(
    sos_configurado, monkeypatch,
):
    """El control de `compulibra`, pero medido sobre el cuerpo que sale."""
    monkeypatch.setenv(sos.LETRA_ENV, "C")
    falso = HttpQueGuardaLaVenta()
    adaptador = sos.AdaptadorSOS(cliente_http=falso)
    monkeypatch.setattr(type(adaptador), "proximo_numero",
                        lambda self, pv, letra, fcncnd="F": 1)
    monkeypatch.setattr(type(adaptador), "resolver_items", lambda self, p: [{"id": 777}])

    adaptador.enviar_venta(_payload("Responsable Inscripto"))

    assert falso.venta["letra"] == "C"


# ── 7. La numeración mira TODAS las páginas ─────────────────────────────────
#
# 🔴 Este bloque salió de un rechazo en producción, el 2026-08-18, con el resto
# ya desplegado: *"SOS rechazó el alta: el número de comprobante ya existe en
# ese punto de venta y letra"*.
#
# `proximo_numero` pedía `pagina=1&registros=500` y daba por hecho que traía
# todo. La cuenta de Lagrace tiene **815 ventas del año**, casi todas del
# estudio en sus propios puntos de venta: entre las 500 primeras no había
# **ninguna** del punto 15, que es el de LibraDesk. El máximo salía 0, se pedía
# el número 1 —que ya existía— y SOS rechazaba.
#
# Y el consejo del mensaje, *"reintentar toma el siguiente número libre"*, era
# **falso**: reintentar volvía a calcular 1. Es el mismo defecto que el del
# listado de clientes, en el otro endpoint, y no se vio al arreglar aquél.


class HttpVentasEnDosPaginas:
    """815 ventas del año en dos páginas de 500. La del punto 15 está en la 2.

    Es la forma medida contra la API real: `/venta/consulta` **no trae un campo
    `paginas`** —a diferencia de `/cliente/listado`—, así que la única señal de
    que se llegó al final es una página más corta que lo pedido.
    """

    TOTAL = 815

    def __init__(self):
        self.paginas_pedidas = []

    def request(self, metodo, url, json=None, headers=None, timeout=None):
        if "/login" in url or "/cuit/credentials/" in url:
            return self._r({"jwt": "J"})
        if "/venta/consulta" in url:
            pagina = int(url.split("pagina=")[1].split("&")[0])
            registros = int(url.split("registros=")[1].split("&")[0])
            self.paginas_pedidas.append(pagina)
            desde = (pagina - 1) * registros
            hasta = min(desde + registros, self.TOTAL)
            filas = []
            for i in range(desde, max(desde, hasta)):
                # Casi todo del punto 13, el del estudio.
                filas.append({"factura": f"FA-0013-{i + 1:08d}"})
            # La nuestra, la única del punto 15, cae en la segunda página.
            if desde <= 700 < hasta:
                filas[700 - desde] = {"factura": "FA-0015-00000001"}
            return self._r({"items": filas})
        return self._r({"items": []})

    @staticmethod
    def _r(cuerpo):
        return httpx.Response(200, json=cuerpo, request=httpx.Request("GET", "https://x"))


def test_el_numero_siguiente_ve_el_comprobante_de_la_pagina_2(sos_configurado):
    """El caso exacto del rechazo: nuestra única venta está fuera de las 500
    primeras."""
    falso = HttpVentasEnDosPaginas()
    adaptador = sos.AdaptadorSOS(cliente_http=falso)

    assert adaptador.proximo_numero(15, "A") == 2
    assert falso.paginas_pedidas == [1, 2], "se pide la segunda página"


def test_la_pagina_corta_corta_el_recorrido(sos_configurado):
    """No hay `paginas` que consultar: una página más corta que lo pedido es la
    última. Sin este corte, el loop seguiría pidiendo páginas vacías hasta el
    tope."""
    falso = HttpVentasEnDosPaginas()
    sos.AdaptadorSOS(cliente_http=falso).proximo_numero(15, "A")

    assert falso.paginas_pedidas == [1, 2], "no se pide una tercera"


def test_el_punto_de_venta_ajeno_no_adelanta_la_numeracion(sos_configurado):
    """Las 814 ventas del estudio están en el punto 13 y llegan al número
    800-y-pico. Si se contaran, el próximo número saldría por las nubes y
    dejaría un hueco enorme en la numeración de LibraDesk."""
    falso = HttpVentasEnDosPaginas()
    adaptador = sos.AdaptadorSOS(cliente_http=falso)

    assert adaptador.proximo_numero(15, "A") == 2, "sólo cuenta el punto 15"
