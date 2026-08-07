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
"""
from fastapi.testclient import TestClient


def _cliente(tmp_path, monkeypatch):
    """Un cliente con la app reconstruida desde cero.

    LibraDesk no tiene una fixture `admin_client` como los otros tres, y la
    suya se construye al empezar el test — así que el entorno de la demo hay
    que dejarlo puesto **antes** de llamar a esto, no después.
    """
    monkeypatch.setenv("ENV", "development")
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import sys
    for mod in list(sys.modules):
        if mod == "app" or mod.startswith("app."):
            del sys.modules[mod]
    from app.asgi import app
    c = TestClient(app, base_url="https://testserver")
    r = c.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return c


def _usuarios(cliente) -> set[str]:
    r = cliente.get("/api/usuarios")
    assert r.status_code == 200, r.text
    return {u["username"] for u in r.json()}


def test_el_arranque_crea_al_visitante(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")

    assert "visitante" in _usuarios(_cliente(tmp_path, monkeypatch))


def test_el_visitante_no_es_admin(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_MODE", "1")
    monkeypatch.setenv("DEMO_USERNAME", "visitante")

    cliente = _cliente(tmp_path, monkeypatch)
    visitante = next(u for u in cliente.get("/api/usuarios").json()
                     if u["username"] == "visitante")

    assert visitante["role"] != "admin"


def test_sin_configuracion_no_se_crea_nadie_de_mas(tmp_path, monkeypatch):
    """En la instancia de un cliente. Un usuario de más no rompe nada visible,
    y por eso nadie lo encontraría."""
    monkeypatch.delenv("DEMO_MODE", raising=False)
    monkeypatch.delenv("DEMO_USERNAME", raising=False)

    assert "visitante" not in _usuarios(_cliente(tmp_path, monkeypatch))
