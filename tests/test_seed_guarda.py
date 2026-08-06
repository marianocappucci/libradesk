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

from scripts.seed_dev import url_no_productiva


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
