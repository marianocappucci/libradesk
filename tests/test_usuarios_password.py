"""El ABM de usuarios cambiando contraseñas ajenas, y el correo del alta.

Los dos llegaron juntos el 2026-08-18 y por el mismo agujero: un usuario de
`lagrace` olvidó su contraseña y **no había ningún camino para recuperarla**.
Ni propio —`/auth/forgot-password` estaba encendido, pero el ABM nunca cargaba
un correo al que mandar el mail— ni del administrador, que no tenía forma de
ponerle una nueva. La única salida fue entrar al contenedor a mano.
"""
from fastapi.testclient import TestClient


def _login(client, username: str = "admin", password: str = "admin") -> None:
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200


def _otro_cliente(client) -> TestClient:
    """Un cliente HTTP nuevo contra la MISMA app.

    Hace falta porque `client` ya tiene la cookie del admin: probar el login del
    usuario al que se le cambió la clave sobre esa misma sesión la pisaría, y
    los tests que vienen después la querrían de vuelta. `https://` porque la
    cookie se crea con `secure=True` — sobre http el cliente la descarta y todo
    vuelve 401 (ver la fixture `client` de conftest).
    """
    return TestClient(client.app, base_url="https://testserver")


def _alta_de_staff(client, **extra) -> dict:
    body = {"username": "cristina", "name": "Cristina", "password": "vieja123",
            "role": "staff"}
    body.update(extra)
    r = client.post("/api/usuarios", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def test_el_admin_le_cambia_la_contrasena_a_otro_usuario(client):
    """El caso que originó todo esto, de punta a punta.

    Se asiertan **las dos** puntas: que la vieja deja de entrar y que la nueva
    entra. Con sólo la segunda, un endpoint que no hiciera nada y un login que
    aceptara cualquier cosa darían el mismo verde.
    """
    _login(client)
    creado = _alta_de_staff(client)

    r = client.put(f"/api/usuarios/{creado['id']}/password", json={"password": "nueva456"})
    assert r.status_code == 204

    otro = _otro_cliente(client)
    assert otro.post("/auth/login", json={
        "username": "cristina", "password": "vieja123"}).status_code == 401
    assert otro.post("/auth/login", json={
        "username": "cristina", "password": "nueva456"}).status_code == 200


def test_la_contrasena_vacia_se_rechaza_y_no_cambia_nada(client):
    """No alcanza con asertar el 422: un endpoint que devolviera 422 *después*
    de haber hasheado el vacío daría el mismo código y la cuenta quedaría
    abierta. Lo que prueba la guarda es que la contraseña anterior sigue
    entrando."""
    _login(client)
    creado = _alta_de_staff(client)

    for vacia in ("", "   "):
        r = client.put(f"/api/usuarios/{creado['id']}/password", json={"password": vacia})
        assert r.status_code == 422, f"{vacia!r} tendría que rechazarse"

    otro = _otro_cliente(client)
    assert otro.post("/auth/login", json={
        "username": "cristina", "password": "vieja123"}).status_code == 200


def test_no_hay_minimo_de_longitud(client):
    """Deliberado, y por eso tiene test: el endpoint existe para destrabar a
    alguien que quedó afuera, y un mínimo que el administrador no puede cumplir
    en el momento lo manda de vuelta a la base de datos. Si algún día se agrega
    una política de complejidad, que sea una decisión y no un descuido — este
    test se va a poner rojo."""
    _login(client)
    creado = _alta_de_staff(client)

    assert client.put(
        f"/api/usuarios/{creado['id']}/password", json={"password": "x"},
    ).status_code == 204
    assert _otro_cliente(client).post("/auth/login", json={
        "username": "cristina", "password": "x"}).status_code == 200


def test_contrasena_de_usuario_inexistente_devuelve_404(client):
    """Se asierta **el cuerpo**, no sólo el código.

    Este producto sirve la SPA con un catch-all, así que una ruta que no existe
    también contesta 404 o 200 con el `index.html`: un assert sobre el status
    daba verde con el endpoint sin escribir, y de hecho fue el único de este
    archivo que no se puso rojo al probarlo contra el código viejo. El `detail`
    del router es lo que prueba que la que contestó fue la ruta.
    """
    _login(client)
    r = client.put("/api/usuarios/9999/password", json={"password": "loquesea"})
    assert r.status_code == 404
    assert r.json() == {"detail": "usuario not found"}


def test_staff_no_puede_cambiarle_la_contrasena_a_nadie(client):
    """El router entero cuelga de `require_admin_o_servicio`, así que la ruta
    nueva hereda el gate. Se cubre igual: el día que alguien monte este
    endpoint aparte, el gate se pierde sin que nada avise."""
    _login(client)
    victima = _alta_de_staff(client, username="victima")
    _alta_de_staff(client, username="staff1", password="staff123")

    staff = _otro_cliente(client)
    _login(staff, "staff1", "staff123")
    r = staff.put(f"/api/usuarios/{victima['id']}/password", json={"password": "tomada"})
    assert r.status_code == 403


def test_el_email_del_alta_se_guarda_y_se_devuelve(client):
    _login(client)
    creado = _alta_de_staff(client, email="cristina@lagrace.com.ar")
    assert creado["email"] == "cristina@lagrace.com.ar"

    listado = client.get("/api/usuarios").json()
    guardado = next(u for u in listado if u["username"] == "cristina")
    assert guardado["email"] == "cristina@lagrace.com.ar"


def test_editar_nombre_o_rol_no_borra_el_email(client):
    """La razón por la que `UsuarioUpdate.email` es `None` y no `""`.

    El toggle de activo/inactivo de la grilla manda el cuerpo entero sin tocar
    el correo. Con un default vacío, desactivar a alguien le borraba el mail en
    silencio — y el mail es justamente lo que hace que
    `/auth/forgot-password` pueda mandarle algo.
    """
    _login(client)
    creado = _alta_de_staff(client, email="cristina@lagrace.com.ar")

    r = client.put(f"/api/usuarios/{creado['id']}", json={
        "name": "Cristina G.", "role": "staff", "active": False})
    assert r.status_code == 200
    assert r.json()["email"] == "cristina@lagrace.com.ar"
    assert r.json()["name"] == "Cristina G."


def test_el_email_se_puede_vaciar_pidiendolo(client):
    """La contracara del test anterior: `""` explícito sí lo borra. Sin esto,
    un correo cargado mal no se podría sacar nunca."""
    _login(client)
    creado = _alta_de_staff(client, email="mal@escrito.com")

    r = client.put(f"/api/usuarios/{creado['id']}", json={
        "name": "Cristina", "role": "staff", "active": True, "email": ""})
    assert r.status_code == 200
    assert r.json()["email"] == ""
