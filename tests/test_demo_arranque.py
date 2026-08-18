"""El arranque de una instancia demo crea al visitante.

🔴 **El par que esto fija.** `incluir_demo=True` en el router hace que
`POST /auth/demo` exista; `ensure_demo_user` en el arranque hace que haya a
quién loguear. Son dos cableados distintos y **los conecta el producto, cada
uno por su lado**: que los dos miren las mismas variables de entorno no obliga
a nadie a llamar a los dos.

Estuvo roto de verdad: las tres primeras demos que se levantaron el 2026-08-06
contestaban `503 demo user not provisioned` — la ruta respondía, y respondía
que le faltaba el usuario.

Un test que sólo mirara la ruta habría pasado igual. Éste mira **el efecto del
arranque sobre la base**.

🔑 **Desde `libraauth v0.26.0` los cableados son TRES**, no dos: la ruta, el
usuario y el **repositorio de códigos de acceso** (`app.state.demo_codigos`).
El tercero tiene el mismo modo de falla que tuvo el segundo, pero al revés de
grave: sin él la demo no deja entrar a nadie —falla cerrado a propósito— y el
síntoma es `503 demo access codes not configured`, que se lee como un problema
del visitante y es un cableado que falta.
"""
import pytest

@pytest.fixture
def auth_recargable():
    """Devuelve `app/routers/auth.py` a como estaba al terminar el test.

    Sin esto, el router queda con `POST /auth/demo` montado para todo lo que
    corra despues en el mismo proceso, y los tests que fijan que esa ruta NO
    existe en la instancia de un cliente pasarian a depender del orden.
    """
    import importlib
    from app.routers import auth as auth_router
    yield
    importlib.reload(auth_router)


def _cliente(armar_cliente):
    """Un cliente logueado sobre una instancia recién arrancada.

    El arranque es lo que se está probando, así que la app se arma **dentro
    del test** con `armar_cliente` (ver conftest.py) y no en una fixture: el
    entorno de la demo tiene que estar puesto antes de que corra
    `ensure_demo_user`, y una fixture se resolvería demasiado temprano.
    """
    _, c = armar_cliente()
    r = c.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return c


def _router_de_auth_con(monkeypatch, **entorno):
    """Deja `/auth/demo` montado (o no) segun el entorno que se le pase.

    🔴 **Hace falta porque el router se arma al IMPORTAR el modulo.**
    `app/routers/auth.py` llama a `build_json_api_auth_router(incluir_demo=
    True)` a nivel de modulo, y esa funcion decide si registra `POST
    /auth/demo` mirando `DEMO_MODE` + `DEMO_USERNAME` **en ese instante**. En
    la suite el modulo ya esta importado cuando corre el `monkeypatch.setenv`,
    asi que sin recargarlo la ruta no aparece y el test mide otra cosa.

    Es el mismo import-time que en produccion ocurre con el `.env` ya puesto:
    recargar aca reproduce el arranque real, no lo esquiva.
    """
    import importlib
    from app.routers import auth as auth_router

    for k, v in entorno.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    importlib.reload(auth_router)
    return auth_router


def _usuarios(cliente) -> set[str]:
    r = cliente.get("/api/usuarios")
    assert r.status_code == 200, r.text
    return {u["username"] for u in r.json()}


def test_el_arranque_crea_al_visitante(armar_cliente, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")

    assert "visitante" in _usuarios(_cliente(armar_cliente))


def test_el_visitante_no_es_admin(armar_cliente, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")

    cliente = _cliente(armar_cliente)
    visitante = next(u for u in cliente.get("/api/usuarios").json()
                     if u["username"] == "visitante")

    assert visitante["role"] != "admin"


def test_sin_configuracion_no_se_crea_nadie_de_mas(armar_cliente, monkeypatch):
    """En la instancia de un cliente. Un usuario de más no rompe nada visible,
    y por eso nadie lo encontraría."""
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("DEMO_USERNAME", raising=False)

    assert "visitante" not in _usuarios(_cliente(armar_cliente))


# ── El tercer cableado: los códigos de acceso (libraauth v0.26.0) ──────────

def test_una_demo_monta_el_abm_de_codigos(armar_cliente, monkeypatch):
    """La ruta por la que el backoffice emite los códigos."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")

    cliente = _cliente(armar_cliente)

    r = cliente.get("/admin/demo-codigos")
    assert r.status_code == 200, r.text
    assert r.json() == {"codigos": []}


def test_en_la_instancia_de_un_cliente_el_abm_no_existe(armar_cliente, monkeypatch):
    """La otra mitad. Sin ésta, el 200 de arriba podría venir de una ruta
    montada en todas las instancias — y ahí el ABM existiría en el sistema de
    un cliente, donde no significa nada."""
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("DEMO_USERNAME", raising=False)

    cliente = _cliente(armar_cliente)

    assert cliente.get("/admin/demo-codigos").status_code == 404


def test_el_codigo_emitido_deja_entrar(armar_cliente, monkeypatch, auth_recargable):
    """🔴 El circuito completo, de punta a punta y por los dos endpoints
    reales: se emite por donde emite el backoffice y se entra por donde entra
    el visitante.

    Es lo que hace que los dos tests de arriba signifiquen algo: sin esto,
    "la ruta contesta 200" y "la ruta no existe" se cumplen igual con un ABM
    que escribe filas que nadie puede usar."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")
    _router_de_auth_con(monkeypatch)
    cliente = _cliente(armar_cliente)

    codigo = cliente.post(
        "/admin/demo-codigos", json={"etiqueta": "Estudio Pérez"}).json()["codigo"]
    cliente.post("/auth/logout")

    r = cliente.post("/auth/demo", json={"codigo": codigo})
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "visitante"


def test_sin_codigo_ya_no_se_entra(armar_cliente, monkeypatch, auth_recargable):
    """🔴 El pedido entero, en una línea: la demo dejó de abrirse sola.

    Es la llamada exacta que hacía el frontend hasta la v0.25.0 y la que va a
    seguir haciendo cualquier bundle viejo que quede servido después del
    deploy."""
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")
    _router_de_auth_con(monkeypatch)
    cliente = _cliente(armar_cliente)
    cliente.post("/auth/logout")

    assert cliente.post("/auth/demo").status_code == 401


def test_un_codigo_inventado_tampoco(armar_cliente, monkeypatch, auth_recargable):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")
    _router_de_auth_con(monkeypatch)
    cliente = _cliente(armar_cliente)
    cliente.post("/auth/logout")

    assert cliente.post(
        "/auth/demo", json={"codigo": "ZZZZ-ZZZZ-ZZZZ"}).status_code == 401
