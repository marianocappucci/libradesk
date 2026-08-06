"""Monta el router /auth (login/logout/me) que expone `libraauth`."""
from libraauth.session_auth import build_json_api_auth_router

# `incluir_demo=True` NO enciende nada por si solo: `POST /auth/demo` se
# registra unicamente si la instancia ademas tiene `DEMO_MODE` y
# `DEMO_USERNAME` puestas. En las instancias de cliente la ruta no existe —
# es un 404, no un 403. Ver `_demo_username` en libraauth.
router = build_json_api_auth_router(incluir_password_reset=True, incluir_demo=True)
