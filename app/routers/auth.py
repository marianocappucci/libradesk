"""Monta el router /auth (login/logout/me) que expone `libraauth`."""
from libraauth.session_auth import build_json_api_auth_router
from libracore import config_manager


def _empresa_nombre(_request) -> str | None:
    """El nombre de la empresa de esta instancia, para el subtitulo del sidebar.

    Sale de la config de LibraCore —la misma que edita `/api/config/empresa` y
    que imprimen los PDF—, no de una tabla nueva: si hubiera dos lugares donde
    escribirlo, el encabezado del remito y el pie del menu terminarian diciendo
    cosas distintas de la misma empresa.

    Se lee **en cada request** y no al importar: `config_manager.CONFIG_PATH` lo
    apunta `remitos_presupuestos.configure()` al arrancar, asi que resolverlo
    antes seria leer la ruta equivocada. Y de paso, cambiar el nombre en
    Configuracion se ve en el proximo login sin reiniciar nada.

    `load()` no puede fallar: sin archivo devuelve los defaults, donde
    `empresa_nombre` es "". El `or None` convierte ese vacio en ausencia, que es
    lo que hace que el sidebar **no dibuje** un subtitulo en blanco.
    """
    return (config_manager.load().get("empresa_nombre") or "").strip() or None


# `incluir_demo=True` NO enciende nada por si solo: `POST /auth/demo` se
# registra unicamente si la instancia ademas tiene `DEMO_MODE` y
# `DEMO_USERNAME` puestas. En las instancias de cliente la ruta no existe —
# es un 404, no un 403. Ver `_demo_username` en libraauth.
#
# `incluir_verify=True` (2026-08-06): es el chequeo stateless con secreto
# compartido que usa el login de `/docs/` de la landing. Estaba apagado porque
# libradesk.com.ar era la unica de las seis sin documentacion; ahora la tiene,
# y sin este endpoint el login de `/docs/` no puede validar contra la
# instancia del cliente. No crea sesion: solo responde si el par
# usuario/contrasena es valido.
#
# `POST /auth/change-password` viene sin flag (libraauth v0.25.0): es la unica
# forma de cambiar la propia clave estando adentro, y no depende de SMTP.
router = build_json_api_auth_router(
    incluir_verify=True, incluir_password_reset=True, incluir_demo=True,
    get_empresa_nombre=_empresa_nombre,
)
