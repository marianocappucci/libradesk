"""Session auth para la SPA de LibraDesk — shim sobre `libraauth`, mismo
patron que `gestiolibra/app/auth.py` sobre `libracore.auth`."""
from libraauth.session_auth import (
    SessionAuth,
    json_api_get_current_user as get_current_user,
    json_api_get_session_auth as get_session_auth,
    json_api_require_admin as require_admin,
    # Rol admin **o** token de servicio (libraauth v0.7.0). Lo usa el router de
    # usuarios, que es lo unico del backoffice de la suite que no puede salir
    # del motor: el router de usuarios es propio de cada producto. Sin
    # `LIBRA_SERVICE_TOKEN` en el entorno se comporta igual que `require_admin`.
    json_api_require_admin_o_servicio as require_admin_o_servicio,
    json_api_require_role as require_role,
    json_api_require_staff as require_staff,
)

from libraauth.repository import UserRepository


def build_session_auth(users: UserRepository) -> SessionAuth:
    return SessionAuth(
        dev_secret_fallback="libradesk-dev-secret-not-for-prod",
        get_user_by_username=users.get_by_username,
        check_credentials=users.check_credentials,
        cookie_name="ld_session",
    )
