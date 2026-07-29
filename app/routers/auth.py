"""Monta el router /auth (login/logout/me) que expone `libraauth`."""
from libraauth.session_auth import build_json_api_auth_router

router = build_json_api_auth_router()
