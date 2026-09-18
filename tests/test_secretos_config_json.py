"""Los secretos de `config.json` viven cifrados, no en el archivo (2026-09-17).

LibraDesk no monta `mp_config_router` (no integra MercadoPago), pero sí usa
`config_manager` para el resto de la configuración de la instancia y el email
de presupuestos pasa por `smtp_efectivo()`, que puede caer a
`email_smtp_password`. Se engancha igual, por consistencia con el resto de la
familia: `libracore.config_manager.CLAVES_SECRETAS` es la misma lista en todo
el ecosistema, se use o no cada clave.

**Estos tests miran el `config.json` CRUDO y la tabla en la base**, no lo que
devuelve `config_manager.load()`. Es a proposito: `load()` devuelve el secreto
en claro por diseño —para que los consumidores no cambien— así que un assert
sobre `load()` da verde igual con la implementación vieja, la que escribía el
token en el archivo. Lo único que distingue una de otra es que quedó en el
disco.

Y se mide a través del enganche REAL del producto (`app.database`), no
armando un almacén a mano: lo que este archivo fija es que LibraDesk lo haya
enchufado, que es la mitad que LibraCore no puede garantizar.
"""
import json
import os

import pytest
from libracore import config_manager as lc_config_manager
from sqlalchemy import text

from app import database

TOKEN = "APP_USR-1234567890123456-091712-abcdef0123456789-3392230021"


def _crudo():
    with open(lc_config_manager.CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def _escribir_crudo(datos):
    """Escribe el archivo como lo dejaba la version vieja, sin pasar por
    `save()` —que ya enruta al almacén y no dejaría el secreto en el
    archivo—."""
    with open(lc_config_manager.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(datos, f)


def _filas_de_secretos():
    with database._engine.connect() as c:
        return dict(c.execute(text("select clave, valor_cifrado from secretos_instancia")).all())


@pytest.fixture(autouse=True)
def _limpio(client):
    """Sin secretos en la base ni en el archivo, antes y despues.

    Pide `client` a propósito: es el fixture que arma la base de cero y
    dispara el arranque REAL de la app —`schema.ensure_schema`,
    `exigir_schema_al_dia`, y ahora el enganche + migración de secretos—. Sin
    él, `secretos_instancia` no existe: la crea la revisión `0002` de
    libraauth, no un `create_all` al importar.
    """
    def limpiar():
        for clave in lc_config_manager.CLAVES_SECRETAS:
            database._secretos.delete(clave)
        if os.path.exists(lc_config_manager.CONFIG_PATH):
            os.unlink(lc_config_manager.CONFIG_PATH)
    limpiar()
    yield
    limpiar()


def test_el_producto_enchufo_el_almacen():
    """Sin esto, todo lo demás es la implementación vieja: `config_manager`
    sin almacén escribe el secreto en el JSON, exactamente como antes."""
    assert lc_config_manager.almacen_de_secretos() is database._secretos


def test_guardar_el_token_no_lo_deja_en_el_archivo():
    cfg = lc_config_manager.load()
    cfg["mp_access_token"] = TOKEN
    cfg["empresa_nombre"] = "LibraDesk SRL"
    lc_config_manager.save(cfg)

    crudo = _crudo()
    assert crudo["mp_access_token"] == ""
    # Control positivo del mismo barrido: lo que no es secreto sí quedo escrito.
    assert crudo["empresa_nombre"] == "LibraDesk SRL"
    # Y para los consumidores no cambio nada.
    assert lc_config_manager.load()["mp_access_token"] == TOKEN


def test_en_la_base_tampoco_esta_en_claro():
    cfg = lc_config_manager.load()
    cfg["mp_access_token"] = TOKEN
    lc_config_manager.save(cfg)

    filas = _filas_de_secretos()
    assert "mp_access_token" in filas
    assert TOKEN not in filas["mp_access_token"]
    assert filas["mp_access_token"].startswith("v1:")


def test_el_arranque_migra_lo_que_la_version_vieja_dejo_en_el_archivo():
    """🔑 El caso de las instancias vivas: el archivo tiene los secretos en
    claro, se despliega esta version, y el arranque los mueve solo."""
    _escribir_crudo({
        "empresa_nombre": "LibraDesk SRL",
        "mp_access_token": TOKEN,
        "mp_webhook_secret": "firma-del-webhook",
        "email_smtp_password": "la-contrasena",
    })
    assert _crudo()["mp_access_token"] == TOKEN          # el punto de partida

    informe = database.migrar_secretos()

    assert sorted(informe["migradas"]) == [
        "email_smtp_password", "mp_access_token", "mp_webhook_secret",
    ]
    crudo = _crudo()
    for clave in lc_config_manager.CLAVES_SECRETAS:
        assert crudo[clave] == "", f"{clave} sigue en el archivo"
    assert crudo["empresa_nombre"] == "LibraDesk SRL"
    assert lc_config_manager.load()["mp_access_token"] == TOKEN
    assert lc_config_manager.load()["mp_webhook_secret"] == "firma-del-webhook"


def test_la_migracion_es_idempotente():
    _escribir_crudo({"mp_access_token": TOKEN})
    database.migrar_secretos()
    antes = _filas_de_secretos()["mp_access_token"]

    informe = database.migrar_secretos()

    assert informe == {"migradas": [], "ya_estaban": [], "fallaron": {}}
    # No se reescribio: el blob es el mismo, con el mismo nonce.
    assert _filas_de_secretos()["mp_access_token"] == antes


def test_el_arranque_de_la_app_corre_la_migracion(data_dir, url_de_base):
    """El enganche en `create_app()` y no sólo la función: sin la llamada, la
    migración existe y nadie la corre.

    Construye la app directo (no vía `client`, que ya la construyó una vez
    para la fixture `_limpio` de arriba) para verificar que CADA
    `create_app()` -- que es el "arranque" de LibraDesk, no tiene un
    `@app.on_event("startup")` separado -- vuelve a correrla.
    """
    from tests.conftest import construir_app

    _escribir_crudo({"mp_access_token": TOKEN})
    # Cierra el engine que armó `client` (vía `_limpio`) antes de reemplazarlo:
    # dos engines abiertos contra la misma base de test dejan una conexión
    # colgada que el teardown de `url_de_base` no ve (sólo dispone el engine
    # ACTUAL) y el DROP DATABASE final falla con "is being accessed by other
    # users".
    database.get_engine().dispose()
    construir_app(data_dir, url_de_base)
    assert _crudo()["mp_access_token"] == ""
    assert lc_config_manager.load()["mp_access_token"] == TOKEN
