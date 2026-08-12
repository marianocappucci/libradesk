"""El healthcheck que declaran los composes, verificado POR ROTURA.

**Por qué existe este archivo.** Hasta el 2026-08-12 el healthcheck de las
instancias era `urllib.request.urlopen('.../health')` a secas, y tenía los dos
defectos que este archivo fija:

1. La ruta. El router de este producto declara `@router.get("/api/health")`;
   `/health` a secas no existe. Lo contestaba el fallback de la SPA de
   `app/asgi.py` (`/{full_path:path}` → index.html), o sea que el chequeo
   medía que hubiera estáticos, no que la API estuviera viva.
2. **La aserción, que es lo de fondo.** Con el `dist/` horneado, *cualquier*
   ruta devuelve 200. Un chequeo que sólo llama a `urlopen()` no puede fallar
   mientras uvicorn conteste algo — ni siquiera apuntado a una ruta inventada.
   Corregir la ruta y dejar el `urlopen()` pelado habría movido el chequeo de
   una ruta inexistente a una existente sin darle, en ningún caso, la
   capacidad de ponerse en rojo.

Por eso los cuatro tests de acá abajo se leen como un par: el declarado da
verde con la app arriba y **rojo** contra una ruta que no existe, y el de sólo
código HTTP da verde en los dos casos. El segundo es la contraprueba: sin él,
el primero no prueba que la aserción sea la que hace el trabajo.

Es la misma familia de falso verde que el `curl` contra una ruta gateada
(2026-08-05) — un chequeo que no puede fallar no es un chequeo.
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
# La ruta inventada de la contraprueba. Cae en el fallback de la SPA igual que
# `/health`, que es justamente lo que la vuelve un buen control.
RUTA_INEXISTENTE = "/api/health-que-no-existe"


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
    os.environ.pop("DATABASE_URL", None)

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
    assert "/api/health" in _fuente_del_chequeo(cmd), "el healthcheck no apunta a la ruta del router"

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
    viejo = "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health', timeout=3)"

    assert _correr(viejo, app_arriba).returncode == 0
    assert _correr(viejo, app_arriba, ruta=RUTA_INEXISTENTE).returncode == 0
