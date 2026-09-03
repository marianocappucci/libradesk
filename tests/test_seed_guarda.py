"""La guarda del seed: contra qué instancias se puede correr.

Un seed sobre la instancia de un cliente le mete datos inventados entre los
reales, y de ahí no se vuelve fácil — hay que distinguir a mano fila por fila.
La guarda es lo único que lo impide, así que conviene que no tenga agujeros.

🔴 **La versión anterior comparaba substrings** (`"dev" in url`). Con eso, una
instancia de cliente llamada `demoliciones.libradesk.com.ar` habría pasado. Es
un agujero improbable pero silencioso: nada avisa, el seed corre y los datos
quedan mezclados.
"""
import pathlib
import re

import pytest

from app.routers.clientes import ClienteIn
from app.routers.incidencias import IncidenciaIn
from app.services.incidencias import ESTADOS_VALIDOS
from scripts import seed_dev
from scripts.seed_dev import (
    CAMPOS_CLIENTE,
    CAMPOS_INCIDENCIA,
    CIERRES,
    DOMICILIOS,
    url_no_productiva,
)


@pytest.mark.parametrize("url", [
    "https://dev.libradesk.com.ar",
    "https://demo.libradesk.com.ar",
    "https://prueba.libradesk.com.ar",
    "http://localhost:8086",
    "http://127.0.0.1:8000",
])
def test_las_instancias_donde_si_se_puede_sembrar(url):
    assert url_no_productiva(url) is True


@pytest.mark.parametrize("url", [
    "https://compulibra.libradesk.com.ar",
    "https://libradesk.com.ar",
    "https://www.libradesk.com.ar",
    "https://admin.libradesk.com.ar",
])
def test_las_instancias_donde_NO(url):
    assert url_no_productiva(url) is False


@pytest.mark.parametrize("url", [
    "https://demoliciones.libradesk.com.ar",
    "https://desarrollosur.libradesk.com.ar",
    "https://devoto.libradesk.com.ar",
])
def test_un_cliente_cuyo_nombre_empieza_igual_NO_pasa(url):
    """🔴 El agujero que tenía la comparación por substring. Son nombres
    verosímiles de cliente: una demoledora, una constructora, una empresa del
    barrio de Devoto."""
    assert url_no_productiva(url) is False


def test_el_subdominio_va_al_principio_no_en_el_medio():
    """`dev` como parte del dominio de otro, no como su primera etiqueta."""
    assert url_no_productiva("https://libradesk.dev.com.ar") is False


def test_no_se_confunde_con_la_ruta_ni_el_query():
    """Si mirara la URL entera, cualquier ruta que dijera `dev` alcanzaría."""
    assert url_no_productiva("https://compulibra.libradesk.com.ar/dev") is False
    assert url_no_productiva("https://compulibra.libradesk.com.ar/?x=demo") is False


def test_no_distingue_mayusculas():
    assert url_no_productiva("https://DEMO.libradesk.com.ar") is True


def test_una_url_sin_host_no_pasa():
    """Un argumento mal escrito no tiene que abrir la puerta."""
    assert url_no_productiva("") is False
    assert url_no_productiva("no-es-una-url") is False


# ── Los estados que el seed deja sembrados ──────────────────────────────────
#
# El 2026-08-13, al pintar la píldora de Estado con el color del semáforo, la
# demo no tenía **ningún** ticket en `resuelta`: el verde no se veía en ninguna
# pantalla. No era un defecto del producto, era el seed — y como el seed no
# falla por no sembrar un estado, sólo se nota mirando.
#
# Estos tests miran los DATOS del seed, no su ejecución: son constantes de
# módulo, así que no hace falta una instancia contra la cual correrlo.

def test_el_seed_deja_un_ticket_en_cada_estado_terminal():
    """`cerrado` **y** `resuelta`, no sólo el primero.

    Los dos son terminales para el producto (`ESTADOS_CERRADOS` en
    `app/services/informes.py`) y las dos pantallas los pintan distinto.
    """
    estados = {estado for _, estado, *_ in CIERRES}
    assert "cerrado" in estados
    assert "resuelta" in estados


def test_los_estados_del_seed_son_validos():
    """Un typo acá deja un PUT rechazado y un estado sin ejemplo en la demo."""
    for titulo, estado, *_ in CIERRES:
        assert estado in ESTADOS_VALIDOS, f"«{titulo}» tiene estado «{estado}»"


def test_no_hay_dos_cierres_para_el_mismo_ticket():
    """El segundo se saltearía en silencio.

    El bucle corta con `continue` cuando el ticket ya está terminado, así que
    una entrada duplicada no falla: deja de aplicarse y el estado que traía se
    pierde sin que nada avise.
    """
    titulos = [titulo for titulo, *_ in CIERRES]
    assert len(titulos) == len(set(titulos))


def test_los_tres_estados_de_facturacion_siguen_representados():
    """Sin facturar, facturado y no facturable.

    Es lo que hace que el filtro de la pantalla de facturación tenga las tres
    opciones con resultados. Estaba escrito en un comentario del seed y no lo
    sostenía nada.
    """
    facturacion = {fact for *_, fact in CIERRES}
    assert {None, "facturado", "no_facturable"} <= facturacion


def test_toda_incidencia_terminada_explica_como_se_resolvio():
    """Una resolución vacía en la demo es una ficha a medio llenar."""
    for titulo, _, horas, resolucion, _ in CIERRES:
        assert resolucion and resolucion.strip(), f"«{titulo}» sin resolución"
        assert horas and horas > 0, f"«{titulo}» sin horas"


# ── El PUT que reemplaza ────────────────────────────────────────────────────
#
# `PUT /api/incidencias/{id}` **reemplaza**, no parchea: lo que no viaja en el
# cuerpo se pierde contra el default del modelo. El seed hace dos PUT parciales
# y reenvía el resto desde una lista.
#
# 🔴 La lista estaba escrita a mano y le faltaban cuatro campos, justo debajo de
# un comentario que advertía "hay que reenviar todo lo demás o se borra". El
# 2026-08-13 el PUT de la agenda le borró el `estado_facturacion` a "Cambio de
# switch en el rack" sobre la demo, y la pantalla de facturación se quedó sin
# ejemplo de `no_facturable`. No falló nada: el PUT devolvió 200.

def test_la_lista_de_campos_no_se_queda_atras_del_modelo():
    """El que agrega un campo a `IncidenciaIn` se entera acá, no en la demo.

    Es la única forma de que esto no se repita: mientras la lista se mantenga a
    mano y nada la compare contra el modelo, el próximo campo nuevo se va a
    borrar igual y tampoco va a fallar nada.
    """
    del_modelo = set(IncidenciaIn.model_fields)
    de_la_lista = set(CAMPOS_INCIDENCIA)
    assert de_la_lista == del_modelo, (
        f"faltan en el seed: {sorted(del_modelo - de_la_lista)}; "
        f"sobran: {sorted(de_la_lista - del_modelo)}"
    )


def test_no_se_reenvian_los_campos_que_pone_el_producto():
    """`id`, `fecha_creacion` y `fecha_cierre` son de `IncidenciaOut`.

    Hoy Pydantic los ignoraría, pero apoyarse en eso es apoyarse en un default
    que se puede cambiar — y `fecha_cierre` la calcula el producto al pasar a
    un estado terminal: mandarla de vuelta sería pisarla.
    """
    for campo in ("id", "fecha_creacion", "fecha_cierre"):
        assert campo not in CAMPOS_INCIDENCIA


def test_no_hay_campos_repetidos_en_la_lista():
    assert len(CAMPOS_INCIDENCIA) == len(set(CAMPOS_INCIDENCIA))


# ── El PUT del cliente, que es más peligroso que el de la incidencia ────────

def test_la_lista_de_campos_del_cliente_no_se_queda_atras_del_modelo():
    """Misma guarda que la de la incidencia, y por un motivo peor.

    Dos defaults de `ClienteIn` **no son `None`**: `activo=True` y
    `tipo_facturacion="por_servicio"`. Un campo que le falte a esta lista no
    deja un dato en blanco: **reactiva un cliente dado de baja** y le cambia
    cómo se lo factura, sin que falle nada.
    """
    del_modelo = set(ClienteIn.model_fields)
    de_la_lista = set(CAMPOS_CLIENTE)
    assert de_la_lista == del_modelo, (
        f"faltan en el seed: {sorted(del_modelo - de_la_lista)}; "
        f"sobran: {sorted(de_la_lista - del_modelo)}"
    )


def test_el_cliente_no_reenvia_lo_que_pone_el_producto():
    """`iva_discriminado` lo **deriva** el producto de `condicion_iva`.

    Mandarlo de vuelta sería escribir un valor calculado, y el día que la regla
    de quién discrimina cambie, el seed la estaría pisando con la anterior.
    """
    for campo in ("id", "fecha_creacion", "iva_discriminado"):
        assert campo not in CAMPOS_CLIENTE


def test_no_hay_campos_repetidos_en_la_lista_del_cliente():
    assert len(CAMPOS_CLIENTE) == len(set(CAMPOS_CLIENTE))


def test_ningun_equipo_de_ejemplo_lleva_un_id_de_cliente_literal():
    """🔴 Lee el fuente, y es a propósito.

    `equipos_spec` se arma **adentro** de `sembrar()`, así que no se puede
    importar para mirarlo. Y el defecto que este test previene no se ve en
    ninguna otra parte: las filas de arriba de la lista usaban `cliente["id"]`
    y las de abajo un `1` y un `2` escritos a mano, asumiendo que `clientes[0]`
    y `clientes[1]` son los ids 1 y 2.

    **No lo son.** `ClienteRepository.list()` ordena **por nombre**, así que la
    posición en la lista no tiene nada que ver con el id. En dev `otro` era el
    id 4, el equipo salía con `cliente_id=2` hacia un depósito del 4, y el
    producto lo rechazaba con 422 — **matando el seed entero** y dejando sin
    sembrar todo lo que viene después.

    El test lee el archivo porque el error es sintáctico: un número donde tenía
    que haber una expresión.

    ⚠️ **La primera versión de este test era vacua y pasaba con el defecto
    puesto.** Buscaba `equipos_spec` y había **dos variables con ese nombre** en
    el archivo —la de las cuadrillas y la de los equipos del cliente, a
    cuatrocientas líneas de distancia—, así que medía la lista equivocada. El
    archivo ya advertía de esa colisión en un comentario. Se resolvió
    renombrando la de las cuadrillas a `cuadrillas_spec`; el `assert` de abajo
    verifica que quedó **una sola**, para que el test no vuelva a medir otra
    cosa en silencio.
    """
    fuente = pathlib.Path(seed_dev.__file__).read_text(encoding="utf-8")
    assert fuente.count("equipos_spec = [") == 1, (
        "hay más de una variable `equipos_spec`: este test mediría la que "
        "encuentre primero, que es como la versión anterior pasaba en falso."
    )
    bloque = re.search(r"equipos_spec = \[(.*?)\n    \]", fuente, re.S)
    assert bloque, "no se encontró `equipos_spec`: ¿se renombró?"
    assert "Sala de racks" in bloque.group(1), (
        "el bloque encontrado no es el de los equipos del cliente"
    )

    literales = re.findall(
        r'^\s*\("[^"]+",\s*(\d+)\s*,', bloque.group(1), re.M,
    )
    assert not literales, (
        f"hay ids de cliente escritos a mano en equipos_spec: {literales}. "
        "Tienen que salir de cliente['id'] / otro['id'], que es de donde sale "
        "el dueño del depósito."
    )


def test_los_domicilios_de_ejemplo_no_repiten_la_ciudad_adentro():
    """La forma en que el producto espera el par domicilio/ciudad.

    Si un domicilio de ejemplo trajera su ciudad adentro, el seed estaría
    sembrando justo el caso que `direccion()` tiene que desarmar — y el ejemplo
    de dev mostraría la excepción en vez de la forma normal.
    """
    for domicilio, ciudad in DOMICILIOS:
        assert ciudad.lower() not in domicilio.lower(), (
            f"'{domicilio}' ya contiene '{ciudad}'"
        )


def test_hay_domicilios_de_ejemplo_suficientes_para_no_repetir_de_a_dos():
    """Se reparten por índice (`i % len`), así que con pocos se repiten pronto.

    No es cosmético: dos paradas de la misma cuadrilla en el mismo domicilio se
    leen como un error de carga cuando se mira la hoja de ruta.
    """
    assert len(DOMICILIOS) >= 8
    assert len({d for d, _ in DOMICILIOS}) == len(DOMICILIOS)


def test_LA_FECHA_NO_SE_RESUELVE_AL_IMPORTAR(monkeypatch):
    """🔴 La guarda del defecto que puso en rojo el CI de Restolibra el 2026-08-29.

    `HOY` era un `date.today()` a nivel de módulo: quedaba congelado en el
    instante del import. Un proceso que importa antes de medianoche y siembra
    después —la suite tarda minutos, y el seed se vuelve a correr sobre
    procesos que viven días— siembra para AYER, y después la agenda abre vacía
    el día que alguien la mira.

    Pega en los ~15 lugares de este seed que fechan algo relativo a `HOY`:
    garantías, contratos, el circuito comercial y la agenda en rango.

    No se prueba llamando a `sembrar()`: eso es una corrida entera contra la
    base --de eso se ocupa `test_seed_corre.py`--. Se prueba la pieza que
    decide la fecha, que es donde vivía el defecto.
    """
    import datetime

    # Se mueve el reloj DESPUÉS de que el módulo ya está importado, que es
    # exactamente el cruce de medianoche a mitad de corrida.
    otro_dia = datetime.date(2031, 7, 4)

    class RelojMovido(datetime.date):
        @classmethod
        def today(cls):
            return otro_dia

    monkeypatch.setattr(seed_dev, "date", RelojMovido)

    assert seed_dev._fijar_hoy() == otro_dia, (
        "la fecha sigue viniendo del import: mover el reloj no la cambió"
    )
    # Y deja el módulo consistente: los sembradores leen `seed_dev.HOY`, no el
    # valor devuelto.
    assert seed_dev.HOY == otro_dia, (
        "`_fijar_hoy` devolvió la fecha nueva pero no actualizó `HOY`, que es "
        "la que usan los sembradores"
    )
