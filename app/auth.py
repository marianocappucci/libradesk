"""Session auth para la SPA de LibraDesk — shim sobre `libraauth`, mismo
patron que `gestiolibra/app/auth.py` sobre `libracore.auth`."""
from libraauth.session_auth import (
    SessionAuth,
    json_api_get_current_user as get_current_user,
    json_api_get_session_auth as get_session_auth,
    json_api_require_admin as require_admin,
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
