"""La guarda del seed: contra qué instancias se puede correr.

Un seed sobre la instancia de un cliente le mete datos inventados entre los
reales, y de ahí no se vuelve fácil — hay que distinguir a mano fila por fila.
La guarda es lo único que lo impide, así que conviene que no tenga agujeros.

🔴 **La versión anterior comparaba substrings** (`"dev" in url`). Con eso, una
instancia de cliente llamada `demoliciones.libradesk.com.ar` habría pasado. Es
un agujero improbable pero silencioso: nada avisa, el seed corre y los datos
quedan mezclados.
"""
import pytest

from app.services.incidencias import ESTADOS_VALIDOS
from scripts.seed_dev import CIERRES, url_no_productiva


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
