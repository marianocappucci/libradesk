"""El router de usuarios, ahora sobre `libraauth.usuarios.build_users_router()`
(ADR-018, libraauth v0.43.1) -- reemplaza la copia propia que tenía
`app/routers/users.py` (ABM admin-only escrito a mano).

El ciclo completo (listar → alta → editar → releer por `GET /{id}` →
resetear contraseña → borrar) que ejerce el backoffice ya no se prueba a mano
acá: lo corre `libraauth.testing.verificar_contrato_de_usuarios`, con los
MISMOS modelos públicos que usa la factory, así que este test y
`build_users_router()` no pueden divergir entre sí.

Lo que el helper NO prueba -- las reglas de negocio de la factory (rol
inválido, username duplicado, protecciones del único admin) -- las prueba
`libraauth` una sola vez para toda la familia (ver su README, sección "Router
de usuarios unificado"). Lo que sigue abajo es lo propio de LibraDesk:

- Que la tupla `roles=("admin", "staff")` y el guard `require_admin_o_servicio`
  con los que se armó el router acá son los correctos -- vía el contrato,
  corrido dos veces: con sesión de admin y con el token de servicio del
  backoffice (`admin.libradesk.com.ar`, el único cliente que entra sin ser
  usuario del producto).
- `GET /{id}`: ruta que la factory SUMA -- el router propio de este producto
  nunca la tuvo, sólo listaba.
- Las protecciones del único admin activo, TODAS nuevas en este producto:
  antes de esta migración se podía degradar, desactivar o borrar al último
  admin sin que nada lo impidiera.

Lo que sigue viviendo en `test_usuarios_password.py`: el correo del alta (que
ya cubría antes de la factory) y las dos aserciones de reset de contraseña que
el helper no ejerce (rechazo de la cadena vacía, y que el 422 del mínimo de 6
no hashea nada a mitad de camino). Y en `test_token_de_servicio.py`: el borde
del gate (`require_admin_o_servicio`) que sigue siendo el mismo, sin tocar,
tras esta migración.
"""
from fastapi.testclient import TestClient
from libraauth.session_auth import SERVICE_TOKEN_ENV, SERVICE_TOKEN_HEADER
from libraauth.testing import verificar_contrato_de_usuarios

RUTA = "/api/usuarios"


def _login(client, username: str = "admin", password: str = "admin") -> None:
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200


def _otro_cliente(client) -> TestClient:
    """Ver el mismo helper en `test_usuarios_password.py`: hace falta
    `https://` porque la cookie de sesión se crea con `secure=True`."""
    return TestClient(client.app, base_url="https://testserver")


def _id_del_admin(client) -> str:
    return next(u["id"] for u in client.get(RUTA).json() if u["username"] == "admin")


# ── Contrato compartido (ADR-018, libraauth v0.43.1) ────────────────────────


def test_contrato_de_usuarios_con_sesion_de_admin(client):
    """El ciclo que ejerce el backoffice cuando entra con la sesión de un
    admin del producto."""
    _login(client)
    verificar_contrato_de_usuarios(client, RUTA, role="staff")


def test_contrato_de_usuarios_con_token_de_servicio(client, monkeypatch):
    """El MISMO ciclo, pero como entra el backoffice de la suite en
    producción: sin sesión de usuario, con el header del token de servicio
    (`json_api_require_admin_o_servicio`, libraauth v0.7.0)."""
    monkeypatch.setenv(SERVICE_TOKEN_ENV, "token-de-contrato")
    client.headers[SERVICE_TOKEN_HEADER] = "token-de-contrato"
    verificar_contrato_de_usuarios(client, RUTA, role="staff", username="contrato-token")


def test_create_response_never_leaks_the_password(client):
    """`verificar_contrato_de_usuarios` no lo mira -- comparte los mismos
    modelos públicos que el router, así que un campo que la factory agregara
    al modelo de salida se colaría en los dos lados por igual."""
    _login(client)
    body = client.post(RUTA, json={
        "username": "staff-1", "name": "Empleada",
        "password": "s3cret", "role": "staff",
    }).json()
    assert "password" not in body
    assert "password_hash" not in body


# ── GET /{id}: ruta que la factory suma ──────────────────────────────────────
#
# El router propio de LibraDesk nunca la tuvo -- sólo `GET /api/usuarios`
# (listar). `verificar_contrato_de_usuarios` la ejerce releyendo tras el PUT;
# acá se deja también el 404 directo, que el helper no cubre.


def test_get_por_id_404_si_no_existe(client):
    _login(client)
    assert client.get(f"{RUTA}/9999").status_code == 404


def test_get_por_id_devuelve_el_usuario(client):
    _login(client)
    creado = client.post(RUTA, json={
        "username": "staff-1", "name": "Empleada",
        "password": "s3cret", "role": "staff",
    }).json()
    r = client.get(f"{RUTA}/{creado['id']}")
    assert r.status_code == 200
    assert r.json()["username"] == "staff-1"


# ── Rol inválido en la EDICIÓN: LibraDesk ya lo tenía, se preserva ──────────
#
# El router viejo lo daba por el `Literal["admin", "staff"]` de
# `UsuarioUpdate.role`; la factory lo valida contra la tupla `roles` de la
# instancia. Mismo 422, otra fuente -- se deja como regresión.


def test_editar_con_rol_invalido_devuelve_422(client):
    _login(client)
    creado = client.post(RUTA, json={
        "username": "staff-1", "name": "Empleada",
        "password": "s3cret", "role": "staff",
    }).json()
    r = client.put(f"{RUTA}/{creado['id']}", json={
        "name": "Empleada", "role": "gerente", "active": True,
    })
    assert r.status_code == 422


# ── Protecciones del único admin activo: NUEVAS en este producto ───────────
#
# Antes de esta migración no existía ninguna de las tres filas de la tabla
# (ver `libraauth.usuarios.build_users_router.__doc__`): se podía degradar,
# desactivar o borrar al único admin activo sin que nada lo impidiera. Las
# trae la factory; acá se confirma que llegan wireadas en esta instancia.
#
# Las protecciones de "uno mismo" (no desactivarse/degradarse/borrarse) se
# chequean ANTES que las del "único admin" en la factory (ver su código): con
# un solo admin, ese admin actuando sobre sí mismo siempre pega primero el
# camino de "uno mismo" (409), nunca el del "único admin activo" (422). Para
# ejercer el 422 hace falta un actor que NO sea la fila que edita -- acá, el
# token de servicio, cuya identidad no tiene `id` (ver el docstring de
# `_es_uno_mismo` en la factory) y por eso nunca cuenta como "uno mismo".


def test_un_admin_no_se_puede_desactivar_a_si_mismo(client):
    _login(client)
    admin_id = _id_del_admin(client)
    r = client.put(f"{RUTA}/{admin_id}", json={
        "name": "Admin", "role": "admin", "active": False,
    })
    assert r.status_code == 409, r.text
    assert client.get(f"{RUTA}/{admin_id}").json()["active"] is True


def test_un_admin_no_se_puede_sacar_el_rol_de_admin_a_si_mismo(client):
    _login(client)
    admin_id = _id_del_admin(client)
    r = client.put(f"{RUTA}/{admin_id}", json={
        "name": "Admin", "role": "staff", "active": True,
    })
    assert r.status_code == 409, r.text
    assert client.get(f"{RUTA}/{admin_id}").json()["role"] == "admin"


def test_un_admin_no_se_puede_borrar_a_si_mismo(client):
    """Chequeado con un SOLO admin en la instancia (el default), para dejar
    claro que este 409 es el de "uno mismo" y no el 422 del único admin (ver
    el comentario de arriba) -- son dos protecciones distintas."""
    _login(client)
    admin_id = _id_del_admin(client)
    r = client.delete(f"{RUTA}/{admin_id}")
    assert r.status_code == 409, r.text
    assert client.get(f"{RUTA}/{admin_id}").status_code == 200


def test_token_de_servicio_no_puede_desactivar_al_unico_admin_activo(client, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, "token-de-contrato")
    client.headers[SERVICE_TOKEN_HEADER] = "token-de-contrato"
    admin_id = _id_del_admin(client)

    r = client.put(f"{RUTA}/{admin_id}", json={
        "name": "Admin", "role": "admin", "active": False,
    })
    assert r.status_code == 422, r.text
    assert client.get(f"{RUTA}/{admin_id}").json()["active"] is True


def test_token_de_servicio_no_puede_degradar_al_unico_admin_activo(client, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, "token-de-contrato")
    client.headers[SERVICE_TOKEN_HEADER] = "token-de-contrato"
    admin_id = _id_del_admin(client)

    r = client.put(f"{RUTA}/{admin_id}", json={
        "name": "Admin", "role": "staff", "active": True,
    })
    assert r.status_code == 422, r.text
    assert client.get(f"{RUTA}/{admin_id}").json()["role"] == "admin"


def test_token_de_servicio_no_puede_borrar_al_unico_admin(client, monkeypatch):
    monkeypatch.setenv(SERVICE_TOKEN_ENV, "token-de-contrato")
    client.headers[SERVICE_TOKEN_HEADER] = "token-de-contrato"
    admin_id = _id_del_admin(client)

    r = client.delete(f"{RUTA}/{admin_id}")
    assert r.status_code == 422, r.text
    assert client.get(f"{RUTA}/{admin_id}").status_code == 200


def test_con_dos_admins_si_se_puede_degradar_al_otro(client):
    """La contracara de las de arriba: la protección es del ÚLTIMO admin
    activo, no de "cualquier admin" -- con dos, degradar a uno de los dos
    (que no sea uno mismo) sigue andando."""
    _login(client)
    segundo = client.post(RUTA, json={
        "username": "admin2", "name": "Segundo Admin",
        "password": "clave-12", "role": "admin",
    }).json()

    r = client.put(f"{RUTA}/{segundo['id']}", json={
        "name": "Segundo Admin", "role": "staff", "active": True,
    })
    assert r.status_code == 200, r.text


def test_con_dos_admins_si_se_puede_borrar_al_otro(client):
    _login(client)
    segundo = client.post(RUTA, json={
        "username": "admin2", "name": "Segundo Admin",
        "password": "clave-12", "role": "admin",
    }).json()

    assert client.delete(f"{RUTA}/{segundo['id']}").status_code == 204
