"""
Logs: actividad del sistema (quién creó, editó o borró qué) y accesos.

Lo que fijan estos tests, en orden de lo que se rompe sin que se note:

1. Que la escritura quede registrada **sin que el repositorio haga nada** — es
   toda la premisa del diseño: el registro cuelga del `flush`, así que un
   método de escritura nuevo lo hereda sin acordarse de nada.
2. Que la fila diga **quién** fue, y no "Sistema", cuando hay sesión.
3. Que un `PUT` que no cambia nada **no** deje una fila: un log lleno de
   "editado" vacíos es un log que nadie lee.
4. Que la pantalla sea admin-only. Es la que dice desde qué IP entró cada uno.
5. Que la contraseña no aparezca en el log de accesos.
"""


RUTA = "/api/logs"


# `client` sale de conftest.py.


def _login(client, username="admin", password="admin") -> None:
    r = client.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text


def _crear_cliente(client, nombre="Compulibra") -> dict:
    r = client.post("/api/clientes", json={"nombre": nombre})
    assert r.status_code == 201, r.text
    return r.json()


def _logs(client, **params) -> dict:
    r = client.get(RUTA, params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _de(client, entidad: str) -> list[dict]:
    return [f for f in _logs(client)["actividad"] if f["entidad"] == entidad]


# ── Que se registre sola ──────────────────────────────────────────────────

def test_crear_deja_una_fila_sin_que_el_repositorio_haga_nada(client):
    """`ClienteRepository.create` no llama a nada de auditoría: el registro
    cuelga del flush. Si esto se rompe, se rompe para las 13 entidades a la
    vez."""
    _login(client)
    creado = _crear_cliente(client)
    fila = _de(client, "cliente")[0]
    assert fila["accion"] == "crear"
    assert fila["entidad_id"] == creado["id"]
    assert "Compulibra" in fila["descripcion"]


def test_la_fila_dice_quien_fue(client):
    _login(client)
    _crear_cliente(client)
    assert _de(client, "cliente")[0]["usuario"] == "admin"


def test_editar_guarda_el_antes_y_el_despues(client):
    _login(client)
    creado = _crear_cliente(client, "Nombre viejo")
    r = client.put(f"/api/clientes/{creado['id']}", json={"nombre": "Nombre nuevo"})
    assert r.status_code == 200, r.text

    edicion = [f for f in _de(client, "cliente") if f["accion"] == "editar"][0]
    assert edicion["cambios"]["nombre"] == ["Nombre viejo", "Nombre nuevo"]


def test_editar_sin_cambios_reales_no_deja_fila(client):
    """Un PUT con los mismos valores es un objeto que alguien tocó y dejó
    igual. Registrarlo llenaría el log de 'editado' vacíos."""
    _login(client)
    creado = _crear_cliente(client, "Sin cambios")
    client.put(f"/api/clientes/{creado['id']}", json={"nombre": "Sin cambios"})
    assert [f for f in _de(client, "cliente") if f["accion"] == "editar"] == []


def test_borrar_conserva_el_id_y_la_etiqueta(client):
    """Es el caso que motiva toda la pantalla: después del borrado la fila ya
    no está en su tabla, así que si el log no guardó el id y el nombre, no
    quedó nada."""
    _login(client)
    creado = _crear_cliente(client, "Cliente borrado")
    assert client.delete(f"/api/clientes/{creado['id']}").status_code in (200, 204)

    borrado = [f for f in _de(client, "cliente") if f["accion"] == "borrar"][0]
    assert borrado["entidad_id"] == creado["id"]
    assert "Cliente borrado" in borrado["descripcion"]


def test_una_entidad_distinta_del_cliente_tambien_se_audita(client):
    """La lista blanca son 13 entidades; si el mecanismo dependiera de algo
    propio de `clientes`, esto lo muestra."""
    _login(client)
    cliente = _crear_cliente(client)
    r = client.post("/api/equipos", json={"cliente_id": cliente["id"], "tipo": "Notebook", "marca": "Dell"})
    assert r.status_code == 201, r.text
    assert _de(client, "equipo")[0]["accion"] == "crear"


def test_los_historiales_no_se_auditan(client):
    """`equipos_movimientos` ya es historial y se ve en la ficha del equipo.
    Auditarlo mostraría el mismo hecho dos veces en la misma pantalla."""
    _login(client)
    cliente = _crear_cliente(client)
    client.post("/api/equipos", json={"cliente_id": cliente["id"], "tipo": "Notebook"})
    entidades = {f["entidad"] for f in _logs(client)["actividad"]}
    assert "equipomovimiento" not in entidades
    assert entidades <= set(_logs(client)["entidades"])


# ── Filtros y paginación ──────────────────────────────────────────────────

def test_filtra_por_entidad_y_por_accion(client):
    _login(client)
    cliente = _crear_cliente(client)
    client.post("/api/equipos", json={"cliente_id": cliente["id"], "tipo": "Notebook"})
    client.put(f"/api/clientes/{cliente['id']}", json={"nombre": "Otro nombre"})

    assert {f["entidad"] for f in _logs(client, entidad="equipo")["actividad"]} == {"equipo"}
    assert {f["accion"] for f in _logs(client, accion="editar")["actividad"]} == {"editar"}


def test_el_total_respeta_el_filtro(client):
    """El total alimenta el paginador: si contara sin filtrar, la pantalla
    ofrecería páginas vacías."""
    _login(client)
    cliente = _crear_cliente(client)
    client.post("/api/equipos", json={"cliente_id": cliente["id"], "tipo": "Notebook"})
    assert _logs(client, entidad="equipo")["total"] == 1
    assert _logs(client)["total"] == 2


def test_lo_mas_reciente_primero(client):
    _login(client)
    _crear_cliente(client, "Primero")
    _crear_cliente(client, "Segundo")
    assert "Segundo" in _logs(client)["actividad"][0]["descripcion"]


# ── Accesos ───────────────────────────────────────────────────────────────

def test_el_login_queda_registrado(client):
    _login(client)
    accesos = _logs(client)["accesos"]
    assert accesos[0]["evento"] == "login"
    assert accesos[0]["username"] == "admin"


def test_el_intento_fallido_queda_con_el_usuario_tipeado(client):
    client.post("/auth/login", json={"username": "fantasma", "password": "x"})
    _login(client)
    fallidos = [a for a in _logs(client)["accesos"] if a["evento"] == "login_fallido"]
    assert fallidos[0]["username"] == "fantasma"


def test_la_contrasena_no_aparece_en_ningun_lado(client):
    client.post("/auth/login", json={"username": "admin", "password": "clave-secretisima"})
    _login(client)
    assert "secretisima" not in str(_logs(client))


# ── Permisos ──────────────────────────────────────────────────────────────

def test_staff_no_ve_los_logs(client):
    """Es la pantalla que dice desde qué IP entró cada uno; el staff no tiene
    por qué ver la actividad de sus compañeros."""
    _login(client)
    r = client.post("/api/usuarios", json={
        "username": "tecnico1", "name": "Técnico", "password": "tecnico1", "role": "staff",
    })
    assert r.status_code == 201, r.text
    client.post("/auth/logout")
    _login(client, "tecnico1", "tecnico1")
    assert client.get(RUTA).status_code == 403


def test_sin_sesion_no_hay_logs(client):
    assert client.get(RUTA).status_code == 401


def test_lo_que_escribe_el_staff_queda_a_su_nombre(client):
    """El usuario sale de la cookie de cada request: si quedara pegado del
    contexto anterior, el trabajo del técnico aparecería como del admin."""
    _login(client)
    r = client.post("/api/usuarios", json={
        "username": "tecnico2", "name": "Técnico", "password": "tecnico2", "role": "staff",
    })
    assert r.status_code == 201, r.text
    client.post("/auth/logout")
    _login(client, "tecnico2", "tecnico2")
    _crear_cliente(client, "Alta del técnico")
    client.post("/auth/logout")
    _login(client)

    fila = [f for f in _de(client, "cliente") if "Alta del técnico" in f["descripcion"]][0]
    assert fila["usuario"] == "tecnico2"
