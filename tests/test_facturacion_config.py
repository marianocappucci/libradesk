"""La configuración del puente, editable desde la pantalla.

Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que la credencial no se guarde en claro.** El motivo entero de que esto
   esté cifrado es que `config.json` y el `pg_dump` viajan en el respaldo que el
   cliente se baja.
2. 🔴 **Que la credencial no salga por la API**, ni siquiera enmascarada.
3. 🔴 **Que una instancia configurada por entorno siga andando** sin tocar nada.
4. Que guardar sin repetir el secreto no lo borre.
5. Que sin configuración completa el destino no se considere usable.
"""
import json

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services import facturacion_config as fc


@pytest.fixture
def sf(monkeypatch, url_de_base):
    """La PostgreSQL propia del test, con el schema ya construido por la cadena.

    Antes armaba un SQLite y llamaba `Base.metadata.create_all()`. Con SQLite
    retirado (2026-08-12) eso dejo de funcionar, y de la forma menos obvia: el
    `create_all()` emite el DDL de **todo** el metadata, incluida la tabla
    `clients`, cuyo default de `created_at` es una expresion de PostgreSQL
    (`to_char(... AT TIME ZONE 'UTC', ...)`). SQLite la rechaza con
    *near "AT": syntax error* — 22 tests de estos dos archivos, por una tabla
    que ni siquiera usan.

    Pedir `url_de_base` ademas evita el `create_all()`: la plantilla ya trae
    el schema en head, que es el mismo que corre en produccion.
    """
    monkeypatch.setenv("SECRET_KEY", "una-clave-de-sesion-larga-para-la-prueba")
    engine = create_engine(url_de_base)
    yield sessionmaker(engine)
    # 🔴 `dispose()` obligatorio: `url_de_base` dropea la base en su teardown y
    # `DROP DATABASE` falla con *"is being accessed by other users"* si queda
    # una conexion viva en el pool. El error sale en el TEARDOWN del test
    # siguiente, no en el que dejo la conexion abierta.
    engine.dispose()


@pytest.fixture
def config(sf):
    return fc.ConfiguracionFacturacion(sf)


SOS = {"usuario": "api@estudio.test", "password": "la-contrasena-secreta",
       "idcuit": "135060", "puntoventa": "3", "letra": "C"}


# ── 1. El secreto no se guarda en claro ─────────────────────────────────────

def test_la_password_no_queda_en_claro_en_la_base(config, sf):
    """🔴 El respaldo que se baja el cliente lleva esta tabla adentro."""
    config.guardar("sos", True, SOS)

    with sf() as s:
        fila = s.scalar(select(fc.ConfigFacturacion).where(
            fc.ConfigFacturacion.destino == "sos"))
        crudo = f"{fila.parametros}{fila.secretos_cifrados}"

    assert "la-contrasena-secreta" not in crudo
    assert fila.secretos_cifrados, "el secreto tiene que estar guardado, cifrado"
    # Y el usuario sí, que no es secreto y hace falta para mostrarlo.
    assert "api@estudio.test" in fila.parametros


def test_se_puede_leer_de_vuelta(config):
    """Cifrado no sirve de nada si después el puente no puede usarlo."""
    config.guardar("sos", True, SOS)
    assert config.leer("sos")["password"] == "la-contrasena-secreta"


def test_con_otra_secret_key_el_secreto_no_se_recupera(config, sf, monkeypatch):
    """🔴 Es el punto: un backup restaurado en otra instancia no entrega la
    credencial. Molesto a propósito."""
    config.guardar("sos", True, SOS)
    monkeypatch.setenv("SECRET_KEY", "otra-clave-distinta-de-la-original")

    with pytest.raises(fc.SecretoIlegible):
        config.leer("sos")

    # Y la pantalla lo dice en vez de romperse.
    vista = config.ver("sos")
    assert vista["secretos_ilegibles"] is True
    assert config.esta_configurado("sos") is False


# ── 2. El secreto no sale por la API ────────────────────────────────────────

def test_la_vista_publica_no_trae_la_password(config):
    """🔴 Ni el valor ni una máscara: el largo de una máscara ya es un dato."""
    config.guardar("sos", True, SOS)
    vista = config.ver("sos")

    assert "password" not in vista
    assert vista["password_cargado"] is True
    assert "la-contrasena-secreta" not in json.dumps(vista)
    # Lo no secreto sí se ve, que es para lo que sirve la pantalla.
    assert vista["usuario"] == "api@estudio.test"
    assert vista["puntoventa"] == "3"


def test_sin_password_cargada_lo_dice(config):
    config.guardar("sos", True, {k: v for k, v in SOS.items() if k != "password"})
    vista = config.ver("sos")
    assert vista["password_cargado"] is False
    assert vista["configurado"] is False


# ── 3. Compatibilidad con el entorno ────────────────────────────────────────

def test_una_instancia_configurada_por_entorno_sigue_andando(config, monkeypatch):
    """🔴 `compulibra` está así hoy. Actualizar no puede dejarla sin puente."""
    monkeypatch.setenv("SOS_USUARIO", "del@entorno.test")
    monkeypatch.setenv("SOS_PASSWORD", "clave-del-entorno")
    monkeypatch.setenv("SOS_IDCUIT", "135060")
    monkeypatch.setenv("SOS_PUNTOVENTA", "3")

    assert config.esta_configurado("sos") is True
    assert config.leer("sos")["password"] == "clave-del-entorno"
    assert config.ver("sos")["desde_entorno"] is True


def test_guardar_desde_la_pantalla_arrastra_lo_que_habia_en_el_entorno(config, monkeypatch):
    """Abrir la pantalla y cambiar la letra no puede dejar sin credencial a una
    instancia que la tenía en el compose."""
    monkeypatch.setenv("SOS_USUARIO", "del@entorno.test")
    monkeypatch.setenv("SOS_PASSWORD", "clave-del-entorno")
    monkeypatch.setenv("SOS_IDCUIT", "135060")
    monkeypatch.setenv("SOS_PUNTOVENTA", "3")

    config.guardar("sos", True, {"letra": "A"})

    datos = config.leer("sos")
    assert datos["letra"] == "A"
    assert datos["password"] == "clave-del-entorno"
    assert datos["usuario"] == "del@entorno.test"


def test_la_base_le_gana_al_entorno(config, monkeypatch):
    monkeypatch.setenv("SOS_PUNTOVENTA", "3")
    config.guardar("sos", True, dict(SOS, puntoventa="7"))
    assert config.leer("sos")["puntoventa"] == "7"


# ── 4. Guardar sin repetir el secreto ───────────────────────────────────────

def test_guardar_sin_mandar_la_password_no_la_borra(config):
    """La pantalla nunca recibe el valor actual, así que tampoco lo devuelve."""
    config.guardar("sos", True, SOS)
    config.guardar("sos", True, {"letra": "B"})

    datos = config.leer("sos")
    assert datos["password"] == "la-contrasena-secreta"
    assert datos["letra"] == "B"


def test_borrar_el_secreto_a_proposito_si_se_puede(config):
    config.guardar("sos", True, SOS)
    vista = config.borrar_secreto("sos", "password")
    assert vista["password_cargado"] is False


# ── 5. Falla cerrado y habilitación ─────────────────────────────────────────

def test_deshabilitado_no_esta_configurado_aunque_tenga_todo(config):
    config.guardar("sos", False, SOS)
    assert config.esta_configurado("sos") is False


def test_faltando_un_obligatorio_no_esta_configurado(config):
    config.guardar("sos", True, {k: v for k, v in SOS.items() if k != "idcuit"})
    assert config.esta_configurado("sos") is False


def test_habilitados_devuelve_los_usables_en_orden(config):
    config.guardar("sos", True, SOS)
    config.guardar("contalibra", True, {"url": "https://c.test", "token": "t"})
    assert config.habilitados() == ["contalibra", "sos"]

    config.guardar("contalibra", False, {})
    assert config.habilitados() == ["sos"]


def test_un_destino_desconocido_no_se_guarda(config):
    with pytest.raises(ValueError):
        config.guardar("inventado", True, {})
