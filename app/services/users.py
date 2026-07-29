"""Usuarios — shim sobre `libraauth`, mismo patron que
`gestiolibra/app/services/users.py` sobre `libracore.db.usuarios`."""
from libraauth.repository import UserRepository
from libraauth.bootstrap import ensure_default_admin as _ensure_default_admin


def ensure_default_admin(repo: UserRepository) -> None:
    _ensure_default_admin(repo, env_prefix="LIBRADESK")
