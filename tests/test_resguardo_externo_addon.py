"""El add-on `resguardo_externo`: el enlace a la nube del cliente para la copia
externa de los backups.

El router sale de LibraCore v1.93.0 (`libracore.resguardo_enlace`) y monta
`GET`/`DELETE ""`, `POST "/{proveedor}"` y `GET "/callback"` bajo
`/api/config/resguardo-externo/enlace`. LibraDesk lo cuelga con dos guardas:
admin, y el add-on.

## El defecto que este archivo existe para atajar

🔴 `ModuleRepository.is_enabled` devolvía `True` para todo módulo que no
estuviera en `TODOS_LOS_MODULOS`. Los add-ons quedan afuera de ese set **a
propósito** —si no, `ensure_seeded()` los prendería en todas las instancias—,
así que `require_module("resguardo_externo")` no cortaba nunca: el enlace
quedaba abierto en todas las instancias, con add-on o sin él. Y **no se veía**:
un admin que entra a la pantalla ve la tarjeta y puede conectar una cuenta, que
es exactamente lo que hace el que sí lo tiene.

`modo_simple` no chocaba con esto porque nunca se gatea con `require_module`:
se lee con `get_modulos()` para dibujar la interfaz. Los tests de regresión de
abajo fijan que ese camino no se movió.
"""
import pytest
from fastapi.testclient import TestClient

RUTA = "/api/config/resguardo-externo/enlace"


def _login(client, usuario="admin", clave="admin") -> None:
    r = client.post("/auth/login", json={"username": usuario, "password": clave})
    assert r.status_code == 200, r.text


def _staff(client) -> TestClient:
    """Un segundo cliente logueado como staff, sobre la misma app."""
    r = client.post("/api/usuarios", json={
        "username": "tecnico-1", "name": "Técnico", "password": "tecnico-pass", "role": "staff",
    })
    assert r.status_code in (200, 201), r.text
    otro = TestClient(client.app, base_url="https://testserver")
    _login(otro, "tecnico-1", "tecnico-pass")
    return otro


def _sin_fila(modulo: str) -> None:
    from sqlalchemy import text

    from app import database

    with database.get_engine().begin() as conn:
        conn.execute(text("DELETE FROM modulos WHERE modulo = :m"), {"m": modulo})


def _fila(modulo: str, habilitado: bool) -> None:
    """Escribe la fila por SQL, sin pasar por el shim: así el caso
    `habilitado=False` no depende de cómo lo escriba `set_addon`."""
    from sqlalchemy import text

    from app import database

    with database.get_engine().begin() as conn:
        conn.execute(
            text("INSERT INTO modulos (modulo, habilitado, plan) VALUES "
                 "(:m, :h, 'addon') ON CONFLICT (modulo) DO UPDATE "
                 "SET habilitado = :h"),
            {"m": modulo, "h": habilitado},
        )


# ── El catálogo ────────────────────────────────────────────────────────────

def test_resguardo_externo_es_un_addon_y_no_esta_en_ningun_plan():
    """(g) Si estuviera en un plan, `ensure_seeded()` lo prendería en todas las
    instancias en el próximo arranque — y con él, el permiso de subir los
    backups a una cuenta externa."""
    import plans

    assert "resguardo_externo" in plans.ADDONS
    for plan, modulos in plans.PLAN_MODULOS.items():
        assert "resguardo_externo" not in modulos, plan
    assert "resguardo_externo" not in plans.TODOS_LOS_MODULOS


def test_la_ruta_existe_de_verdad(client):
    """Guarda contra el falso verde: `asgi.py` monta un fallback de SPA, así
    que una ruta inventada devuelve 200 con HTML. Si el router no estuviera
    montado, los 403 de abajo se podrían estar midiendo contra otra cosa."""
    assert RUTA in client.app.openapi()["paths"]


# ── El gate del add-on ─────────────────────────────────────────────────────

def test_sin_fila_el_addon_esta_apagado(client):
    """(a) 🔴 El caso que el defecto dejaba abierto: una instancia que nunca vio
    el add-on no tiene la fila, y eso tiene que ser **apagado**."""
    _sin_fila("resguardo_externo")
    _login(client)

    assert client.get(RUTA).status_code == 403
    assert client.app.state.modules.is_enabled("resguardo_externo") is False


def test_las_cuatro_rutas_quedan_detras_del_gate(client):
    """(a) El callback incluido: queda detrás del mismo gate a propósito (la
    cookie `SameSite=Lax` viaja en la redirección del proveedor)."""
    _sin_fila("resguardo_externo")
    _login(client)

    assert client.get(RUTA).status_code == 403
    assert client.post(f"{RUTA}/drive").status_code == 403
    assert client.get(f"{RUTA}/callback", params={"state": "x", "code": "y"}).status_code == 403
    assert client.delete(RUTA).status_code == 403


def test_con_la_fila_apagada_da_403(client):
    """(b) La fila existe pero el backoffice lo destildó."""
    _fila("resguardo_externo", False)
    _login(client)

    assert client.get(RUTA).status_code == 403


def test_prendido_responde_el_estado(client):
    """(c) Prendido por el mismo camino que usa el backoffice."""
    from app.database import set_addon

    set_addon("resguardo_externo", True)
    _login(client)

    r = client.get(RUTA)
    assert r.status_code == 200, r.text
    cuerpo = r.json()
    assert "proveedores" in cuerpo
    assert "enlace" in cuerpo
    # Nada conectado todavía en una instancia recién creada.
    assert cuerpo["enlace"] is None


def test_prender_y_apagar_tiene_efecto_inmediato(client):
    """El gate relee la base en cada request: apagarlo desde el backoffice
    corta sin reiniciar el contenedor."""
    from app.database import set_addon

    _login(client)
    set_addon("resguardo_externo", True)
    assert client.get(RUTA).status_code == 200
    set_addon("resguardo_externo", False)
    assert client.get(RUTA).status_code == 403


def test_el_enlace_vive_en_la_carpeta_de_los_backups(client):
    """🔑 El router lee el MISMO `backups_dir` que el de backup.

    Del otro lado, el subidor del host sube lo que deja el backup con el
    `rclone.conf` que escribe este router. Si los dos routers apuntaran a
    carpetas distintas, la pantalla diría "conectado" y la copia no saldría.
    """
    import json

    from libracore.resguardo_enlace import CONF, DIRECTORIO, ENLACE

    from app.database import set_addon

    d = client.data_dir / "backups" / DIRECTORIO
    d.mkdir(parents=True, exist_ok=True)
    (d / CONF).write_text("[resguardo]\ntype = drive\n", encoding="utf-8")
    (d / ENLACE).write_text(
        json.dumps({"proveedor": "drive", "nombre": "Google Drive", "cuenta": "x@y.com"}),
        encoding="utf-8",
    )

    set_addon("resguardo_externo", True)
    _login(client)

    enlace = client.get(RUTA).json()["enlace"]
    assert enlace is not None
    assert enlace["cuenta"] == "x@y.com"


# ── Admin ──────────────────────────────────────────────────────────────────

def test_un_usuario_no_admin_no_entra(client):
    """(d) Con el add-on prendido: lo que corta es el rol. Conectar una cuenta
    es entregarle a la instancia un permiso sobre la nube del cliente."""
    from app.database import set_addon

    set_addon("resguardo_externo", True)
    _login(client)
    staff = _staff(client)

    assert staff.get(RUTA).status_code in (401, 403)
    assert staff.post(f"{RUTA}/drive").status_code in (401, 403)
    assert staff.delete(RUTA).status_code in (401, 403)


def test_sin_sesion_no_entra(client):
    from app.database import set_addon

    set_addon("resguardo_externo", True)

    assert client.get(RUTA).status_code in (401, 403)


# ── Regresión: lo que NO tenía que cambiar ─────────────────────────────────

def test_un_modulo_de_plan_sin_fila_sigue_habilitado(client):
    """(e) La garantía de adopción de `test_modulos_y_planes.py`: sin plan
    asignado todo lo del plan queda habilitado. La rama de add-ons no puede
    llevársela puesta."""
    _sin_fila("dashboard")
    _login(client)

    assert client.app.state.modules.is_enabled("dashboard") is True
    assert client.get("/api/dashboard").status_code != 403


def test_un_modulo_no_gateable_sigue_habilitado(client):
    """(e) El core de tickets no se gatea, con fila o sin ella."""
    assert client.app.state.modules.is_enabled("incidencias") is True


def test_modo_simple_se_sigue_leyendo_por_get_modulos(client):
    """(f) `modo_simple` se lee con `get_modulos()` —para la interfaz y para
    `/auth/me`—, no con `is_enabled`. Ese camino no se movió: apagado sin fila,
    prendido cuando el backoffice lo prende."""
    from app.database import get_modulos, set_addon

    _sin_fila("modo_simple")
    assert get_modulos().get("modo_simple", False) is False
    _login(client)
    assert "modo_simple" not in client.get("/auth/me").json()["modulos"]

    set_addon("modo_simple", True)
    assert get_modulos()["modo_simple"] is True
    assert "modo_simple" in client.get("/auth/me").json()["modulos"]


@pytest.mark.parametrize("addon", ["modo_simple", "resguardo_externo"])
def test_is_enabled_de_un_addon_sigue_a_la_fila(client, addon):
    """Los dos add-ons se comportan igual en `is_enabled`: sin fila apagado,
    y después lo que diga `habilitado`."""
    modules = client.app.state.modules

    _sin_fila(addon)
    assert modules.is_enabled(addon) is False
    _fila(addon, True)
    assert modules.is_enabled(addon) is True
    _fila(addon, False)
    assert modules.is_enabled(addon) is False
