"""El healthcheck que declaran los composes, verificado POR ROTURA.

**Por qué existe este archivo.** Hasta el 2026-08-12 el healthcheck de las
instancias era `urllib.request.urlopen('.../health')` a secas, y tenía los dos
defectos que este archivo fija:

1. La ruta. En ese momento el router declaraba **sólo** `@router.get(
   "/api/health")` y `/health` a secas no existía: lo contestaba el fallback de
   la SPA de `app/asgi.py` (`/{full_path:path}` → index.html), o sea que el
   chequeo medía que hubiera estáticos, no que la API estuviera viva.

   > Desde el 2026-08-12 el router sirve `/health`, la misma que los otros
   > cinco productos, y los composes de acá la piden. `/api/health` fue alias de
   > transición ese día y ya no existe — o sea que **la ruta vieja volvió a ser
   > una de las que contesta el catch-all**, que es lo que este archivo mide.
2. **La aserción, que es lo de fondo.** Con el `dist/` horneado, *cualquier*
   ruta devuelve 200. Un chequeo que sólo llama a `urlopen()` no puede fallar
   mientras uvicorn conteste algo — ni siquiera apuntado a una ruta inventada.
   Corregir la ruta y dejar el `urlopen()` pelado habría movido el chequeo de
   una ruta inexistente a una existente sin darle, en ningún caso, la
   capacidad de ponerse en rojo.

Por eso los tests de acá abajo se leen como un par: el declarado da verde con
la app arriba y **rojo** contra una ruta que no existe, y el de sólo código
HTTP da verde en los dos casos. El segundo es la contraprueba: sin él, el
primero no prueba que la aserción sea la que hace el trabajo.

Es la misma familia de falso verde que el `curl` contra una ruta gateada
(2026-08-05) — un chequeo que no puede fallar no es un chequeo.

**Las dos puntas, atadas.** Los tests de ruta no comparan contra un literal
escrito acá: sacan las rutas de `app.routers.health` y exigen que la del
compose —y la que el provisioning le va a estampar a la próxima instancia—
esté entre ellas. Un literal repetido en el test es una tercera copia que
puede divergir igual que las otras dos; derivarlo del router hace que mover la
ruta rompa el test **en el mismo commit** en vez de en el próximo alta. Es lo
que faltaba: hasta el 2026-08-12 el desvío se arreglaba en cada consumidor por
separado, y ninguno miraba al otro.
"""
import importlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest
import uvicorn

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPOSES = {
    "dev": REPO_ROOT / "docker-compose.yml",
    "cliente": REPO_ROOT / "clientes.example.yml",
}
# La ruta inventada de la contraprueba: cae en el fallback de la SPA, que es
# justamente lo que la vuelve un buen control. Tiene que seguir siendo una que
# el router NO declare — `/health` dejó de servir para esto el 2026-08-12,
# cuando pasó a existir. El assert de `_rutas_de_salud()` lo verifica en vez de
# confiar en que quien la lea se acuerde.
RUTA_INEXISTENTE = "/api/health-que-no-existe"


def _rutas_de_salud() -> set[str]:
    """Las rutas que el router de salud sirve **de verdad**, leídas de él.

    Se importa sólo el router y no la app entera: no hace falta base ni
    semillas para saber qué paths declara, y así este helper sirve también en
    los tests que no levantan uvicorn.
    """
    from app.routers import health

    rutas = {r.path for r in health.router.routes}
    assert rutas, "el router de salud no declara ninguna ruta"
    return rutas


def _ruta_del_chequeo(fuente: str) -> str:
    """La ruta que el comando del healthcheck pide, sacada del literal."""
    m = re.search(r"http://localhost:8000(/[^']*)'", fuente)
    assert m, f"no se pudo leer la ruta del chequeo: {fuente}"
    return m.group(1)


def _healthcheck_declarado(compose: Path) -> list[str]:
    """El `test:` del healthcheck de la app, tal cual está escrito en el YAML.

    Se lee con `json.loads` porque la lista está en formato de flujo y eso es
    JSON válido. Si alguien la reescribe en bloque, este parser falla y hay que
    volver a pasar por acá — que es lo que se quiere: el comando no se cambia
    sin re-verificarlo.
    """
    for linea in compose.read_text(encoding="utf-8").splitlines():
        m = re.match(r"\s*test:\s*(\[.*\])\s*$", linea)
        if m:
            return json.loads(m.group(1))
    raise AssertionError(f"{compose.name} no declara un healthcheck en formato de lista")


def _fuente_del_chequeo(cmd: list[str]) -> str:
    assert cmd[:3] == ["CMD", "python3", "-c"], f"forma inesperada del healthcheck: {cmd[:3]}"
    return cmd[3]


def _correr(fuente: str, puerto: int, ruta: str | None = None) -> subprocess.CompletedProcess:
    """Corre el chequeo contra la app de verdad, opcionalmente cambiándole la ruta."""
    fuente = fuente.replace("http://localhost:8000", f"http://127.0.0.1:{puerto}")
    if ruta is not None:
        fuente = re.sub(r"(http://127\.0\.0\.1:\d+)/[^']*", rf"\g<1>{ruta}", fuente)
    return subprocess.run([sys.executable, "-c", fuente], capture_output=True, text=True, timeout=30)


@pytest.fixture(scope="module")
def app_arriba(tmp_path_factory):
    """La app real servida por uvicorn, con un `dist/` presente.

    El `dist/` no es decorado: sin él no hay fallback de SPA y desaparece
    justamente el escenario que hace vacuo al chequeo viejo. Se fabrica uno
    mínimo si el checkout no lo tiene (el job de tests del CI no lo construye)
    y se borra sólo si lo creamos nosotros.
    """
    dist = REPO_ROOT / "frontend" / "dist"
    creado = not dist.is_dir()
    if creado:
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text("<!doctype html><title>LibraDesk</title>", encoding="utf-8")

    datos = tmp_path_factory.mktemp("datos")
    previo = {v: os.environ.get(v) for v in ("ENV", "DATA_DIR", "DATABASE_URL")}
    os.environ["ENV"] = "development"
    os.environ["DATA_DIR"] = str(datos)
    # 🔴 Antes acá iba `os.environ.pop("DATABASE_URL")`: la app caía a un
    # default SQLite dentro del DATA_DIR. Ese default se retiró el 2026-08-12
    # junto con SQLite —una instancia sin la variable puesta **arrancaba contra
    # una base vacía recién creada y se veía sana**—, así que ahora `app.asgi`
    # aborta el import si falta. Se le da una PostgreSQL propia del módulo.
    #
    # La base se crea acá y no con la fixture `url_de_base` del conftest porque
    # aquella es de alcance función y este servidor de uvicorn se levanta una
    # vez por módulo.
    from conftest import _sql_admin, _url_de

    base = "ld_healthcheck_contenedor"
    _sql_admin(f'DROP DATABASE IF EXISTS "{base}"', f'CREATE DATABASE "{base}"')
    os.environ["DATABASE_URL"] = _url_de(base)

    sys.modules.pop("app.asgi", None)
    asgi = importlib.import_module("app.asgi")
    assert asgi.FRONTEND_DIST.is_dir(), "sin dist no hay fallback de SPA y el test no mide nada"

    server = uvicorn.Server(uvicorn.Config(asgi.app, host="127.0.0.1", port=0, log_level="warning"))
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()
    limite = time.monotonic() + 30
    while not server.started:
        if time.monotonic() > limite or not hilo.is_alive():
            server.should_exit = True
            raise AssertionError("la app no llegó a levantar")
        time.sleep(0.05)
    puerto = server.servers[0].sockets[0].getsockname()[1]

    yield puerto

    server.should_exit = True
    hilo.join(timeout=15)
    sys.modules.pop("app.asgi", None)
    for var, valor in previo.items():
        if valor is None:
            os.environ.pop(var, None)
        else:
            os.environ[var] = valor
    if creado:
        shutil.rmtree(dist, ignore_errors=True)


def test_la_spa_contesta_200_en_cualquier_ruta(app_arriba):
    """La premisa de todo el archivo, medida y no supuesta.

    Si esto alguna vez da 404, el fallback dejó de estar y conviene enterarse
    acá y no cuando un healthcheck vuelva a mentir.
    """
    import urllib.request

    with urllib.request.urlopen(f"http://127.0.0.1:{app_arriba}{RUTA_INEXISTENTE}", timeout=5) as r:
        assert r.status == 200
        assert b"<!doctype html" in r.read(64).lower()


@pytest.mark.parametrize("nombre", sorted(COMPOSES))
def test_el_healthcheck_declarado_da_verde_con_la_app_arriba(nombre, app_arriba):
    cmd = _healthcheck_declarado(COMPOSES[nombre])
    ruta = _ruta_del_chequeo(_fuente_del_chequeo(cmd))
    assert ruta in _rutas_de_salud(), (
        f"{nombre}: el healthcheck pide {ruta}, que el router de salud no sirve. "
        "Con la SPA horneada eso NO se ve como un 404: lo contesta el catch-all."
    )

    r = _correr(_fuente_del_chequeo(cmd), app_arriba)
    assert r.returncode == 0, f"{nombre}: el chequeo falló con la app sana\n{r.stderr}"


@pytest.mark.parametrize("nombre", sorted(COMPOSES))
def test_el_healthcheck_declarado_da_rojo_contra_una_ruta_que_no_existe(nombre, app_arriba):
    """La rotura. Es el test que hace que el de arriba signifique algo."""
    cmd = _healthcheck_declarado(COMPOSES[nombre])

    r = _correr(_fuente_del_chequeo(cmd), app_arriba, ruta=RUTA_INEXISTENTE)
    assert r.returncode != 0, (
        f"{nombre}: el chequeo da verde contra {RUTA_INEXISTENTE}, o sea que no puede fallar "
        "mientras la app sirva estáticos"
    )


def test_un_chequeo_de_solo_codigo_http_no_distingue(app_arriba):
    """La contraprueba: el chequeo viejo da verde en los dos escenarios.

    Fija POR QUÉ el declarado mira el cuerpo. Si algún día esto empieza a
    fallar, el fallback de la SPA cambió y hay que releer el archivo entero.
    """
    viejo = "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=3)"

    assert _correr(viejo, app_arriba).returncode == 0
    assert _correr(viejo, app_arriba, ruta=RUTA_INEXISTENTE).returncode == 0


def test_la_ruta_inventada_del_control_sigue_sin_existir():
    """El control no vale si la ruta que usa pasa a existir.

    `/health` fue exactamente eso hasta el 2026-08-12: servía de control
    justamente porque no existía, y dejó de servir el día que se agregó. Esto
    lo verifica en vez de confiar en el comentario de arriba.
    """
    assert RUTA_INEXISTENTE not in _rutas_de_salud()


@pytest.mark.parametrize("script", ["nuevo_cliente", "panel_admin"])
def test_el_health_path_del_provisioning_es_una_ruta_que_el_router_sirve(script):
    """🔴 La otra punta: lo que el ALTA le va a estampar a la próxima instancia.

    Es el test que faltaba. El compose de la demo nació apuntando a una ruta
    que este producto no servía y nadie se enteró hasta medirlo a mano dentro
    del contenedor, porque el catch-all de la SPA contesta 200 igual. Acá se
    exige que el `health_path` efectivo del provisioning esté entre las rutas
    que el router declara.

    Se prueban los **dos** scripts por separado y con `reload`: `configure()`
    pisa un `_cfg` global y `libracore.admin.services` los importa a los dos en
    el mismo proceso, así que el que gane el último import es el que manda. Si
    sólo se mirara uno, el otro podría desviarse sin que nada lo dijera — que
    es precisamente la trampa que documentan sus comentarios.
    """
    from libracore.provisioning import get_config

    modulo = importlib.import_module(f"scripts.{script}")
    importlib.reload(modulo)  # re-ejecuta su `configure()`, gane quien gane antes

    efectivo = get_config().health_path
    assert efectivo in _rutas_de_salud(), (
        f"scripts/{script}.py configura health_path={efectivo!r}, que el router "
        "de salud no sirve: toda instancia nueva nacería unhealthy para siempre."
    )
