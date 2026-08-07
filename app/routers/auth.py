"""Monta el router /auth (login/logout/me) que expone `libraauth`."""
from libraauth.session_auth import build_json_api_auth_router

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
router = build_json_api_auth_router(
    incluir_verify=True, incluir_password_reset=True, incluir_demo=True,
)
