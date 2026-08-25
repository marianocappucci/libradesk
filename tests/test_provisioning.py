"""El provisioning de este producto, atado al código que corre.

Este archivo nace el 2026-08-24, del incidente de LibraCargo: su deploy salió
con **código 0** y dejó las dos instancias con el código nuevo sobre el esquema
viejo, porque el producto nunca había declarado `migraciones` y el default del
motor es vacío. Acá había 36 revisiones en la misma situación — las bases están
al día sólo porque alguien las corrió a mano en cada deploy.
"""

import importlib
import json
import pathlib
import re

import pytest


@pytest.mark.parametrize("script", ["nuevo_cliente", "panel_admin"])
def test_el_deploy_declara_las_migraciones_que_este_repo_tiene(script):
    """Un producto con revisiones de Alembic tiene que declararlas, y bien.

    Se prueban los **dos** scripts por separado y con `reload`: `configure()`
    pisa un `_cfg` global y `libracore.admin.services` importa los dos en el
    mismo proceso, así que manda el último import. Mirar uno solo dejaría al
    otro desviarse sin que nada lo dijera.

    🔑 **Se aserta lo que el DEPLOY hace con el valor, no el valor.** Compararlo
    contra la tupla que uno escribió tres líneas más arriba en el otro archivo
    se cumple por construcción y no prueba nada: la primera versión de este
    guard, en LibraCargo, pasaba en verde con una forma que `cmd_actualizar` no
    sabe ejecutar.

    La condición sale **del repo**, no de un literal: si hay revisiones en
    `migrations/versions/`, tiene que haber comandos. Si algún día este producto
    deja de usar Alembic, el test deja de exigir solo.
    """
    from libracore.provisioning import get_config

    raiz = pathlib.Path(__file__).parent.parent
    revisiones = sorted((raiz / "migrations" / "versions").glob("*.py"))

    importlib.reload(importlib.import_module(f"scripts.{script}"))
    declarados = get_config().migraciones

    if not revisiones:
        return  # sin cadena propia no hay nada que correr

    assert declarados, (
        f"este repo tiene {len(revisiones)} revisiones de Alembic y "
        f"scripts/{script}.py no declara `migraciones`: el deploy las va a "
        "saltear en silencio y la instancia va a quedar con el código nuevo "
        "sobre el esquema viejo."
    )

    # Textualmente lo que hace `cmd_actualizar` por cada comando: lo imprime
    # con `" ".join(...)` y lo splatea en el `compose run`. Con la forma plana
    # —`("alembic", "upgrade", "head")` en vez de anidada— el `join` revienta
    # acá, que es donde tiene que reventar.
    for comando in declarados:
        assert not isinstance(comando, str), (
            f"scripts/{script}.py declara {declarados!r} en forma PLANA. El "
            "deploy la iteraría carácter por carácter. Anidala: "
            "migraciones=((...),)"
        )
        " ".join(comando)

    assert any("alembic" in c for c in declarados), (
        f"scripts/{script}.py declara {declarados!r}, que no incluye el "
        "`alembic` de la cadena propia de este repo."
    )


def test_los_dos_scripts_configuran_LO_MISMO():
    """El desvío que el comentario de los dos archivos promete que no existe.

    No alcanza con que cada uno sea válido por su lado: como comparten el `_cfg`
    global, dos configuraciones distintas hacen que el resultado dependa del
    orden de los imports — o sea que la misma operación salga distinta según
    qué se haya importado antes en ese proceso.

    **Este test nace en rojo.** Al escribirlo, `panel_admin.py` pasaba
    `backup_zip=True` y `nuevo_cliente.py` no. Los otros productos lo tienen
    desde hace tiempo y por eso no divergieron; acá faltaba, y divergieron.

    Se compara la configuración **entera** con `asdict`, no campo por campo: un
    test que mirara sólo `backup_zip` dejaría pasar el próximo desvío, que va a
    ser en otro campo.
    """
    from dataclasses import asdict

    from libracore.provisioning import get_config

    def config_de(script):
        importlib.reload(importlib.import_module(f"scripts.{script}"))
        return asdict(get_config())

    uno = config_de("nuevo_cliente")
    otro = config_de("panel_admin")

    distintos = {k: (uno[k], otro[k]) for k in uno if uno[k] != otro[k]}
    assert not distintos, f"los dos scripts configuran distinto: {distintos}"


def _bloque_del_servicio_de_dev() -> str:
    """El bloque del servicio `*-dev` del compose del repo, como texto.

    Sin `yaml`: no es dependencia de este repo ni de sus tests, y sumar una
    para leer una línea sería peor que recortar el bloque a mano. El corte es
    por indentación —un servicio arranca con dos espacios y su cuerpo tiene
    más—, que es exactamente lo que el archivo garantiza.
    """
    raiz = pathlib.Path(__file__).parent.parent
    lineas = (raiz / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    servicios = [i for i, linea in enumerate(lineas)
                 if re.match(r"^  [A-Za-z0-9_.-]+:\s*$", linea)]
    inicio = next((i for i in servicios
                   if lineas[i].strip().rstrip(":").endswith("-dev")), None)
    assert inicio is not None, (
        "el compose del repo no declara ningún servicio `*-dev`: este test "
        "está mirando un archivo que ya no tiene la forma que supone.")
    fin = next((i for i in servicios if i > inicio), len(lineas))
    return "\n".join(lineas[inicio:fin])


def _comando_de_arranque_de_dev() -> str:
    """El **valor** del `command:` del servicio de dev, y nada más.

    🔴 **La primera versión de este test buscaba en el bloque entero, y eso
    pasaba en verde con el paso de migraciones sacado del `command:` y dejado
    en un comentario.** Medido el 2026-08-25, no supuesto: un comentario que
    menciona `alembic upgrade head` no lo corre. Buscar en el bloque también
    dejaba que un `ports: - "8086:8000"` satisficiera un token del comando de
    arranque, que es la misma clase de falso verde.

    Un comentario no matchea `^\s+command:` porque el `#` va antes de la clave.
    """
    bloque = _bloque_del_servicio_de_dev()
    m = re.search(r"^\s+command:\s*(\S.*)$", bloque, re.MULTILINE)
    assert m, (
        "el servicio de dev del compose no declara `command:`. Si el arranque "
        "pasó a otra forma, este test hay que reescribirlo — no borrarlo.")
    return m.group(1).strip()


@pytest.mark.parametrize("script", ["nuevo_cliente", "panel_admin"])
def test_la_instancia_de_dev_corre_las_mismas_migraciones_que_el_deploy(script):
    """El otro camino, el que `cmd_actualizar` no toca.

    🔴 **La declaración de `migraciones` no cubre `dev`.** El motor corre esos
    comandos al actualizar las instancias de cliente y la demo, que son las que
    el panel administra. La de `dev` la levanta el `docker-compose.yml` de este
    repo, y hasta el 2026-08-25 ahí no había ningún paso de Alembic en ninguno
    de los cinco productos de la familia que usan Alembic. Se descubrió porque
    `libracargo-dev` apareció con la base una revisión atrás del código, con el
    chequeo de salud en 200.

    Lo que se aserta es que las dos puntas digan **lo mismo y en el mismo
    orden**. El modo de fallar de esto no es que alguien borre el `command:`,
    es que agregue una segunda cadena en `scripts/` y se olvide del compose:
    ahí `dev` migraría de menos y el error culparía a la revisión equivocada.

    Se lee el compose como texto y no se compara contra un literal escrito acá:
    un literal sería una tercera copia, con exactamente el mismo problema.
    """
    from libracore.provisioning import get_config

    importlib.reload(importlib.import_module(f"scripts.{script}"))
    declarados = get_config().migraciones
    if not declarados:
        return  # sin cadena declarada no hay nada que exigirle al compose

    arranque = _comando_de_arranque_de_dev()
    cursor = 0
    for comando in declarados:
        texto = " ".join(comando)
        pos = arranque.find(texto, cursor)
        assert pos != -1, (
            f"scripts/{script}.py declara `{texto}` y el servicio de dev del "
            "compose no lo corre" + (" en ese orden" if cursor else "") + ": "
            "la instancia de dev va a quedar con el código nuevo sobre el "
            "esquema viejo, que es lo que le pasó a LibraCargo el 2026-08-25."
        )
        cursor = pos + len(texto)


def test_el_arranque_del_compose_de_dev_no_se_desvia_del_CMD_de_la_imagen():
    """La copia del comando de arranque, atada a su original.

    🔴 **Existe porque la alternativa no funciona.** El servicio de dev de este
    repo es el único de los cinco productos con Alembic que NO override el
    comando: usa el `CMD` del Dockerfile. Para anteponerle las migraciones se
    probó `entrypoint: ["sh","-c","... && exec \"$0\" \"$@\""]`, que en
    teoría conserva el `CMD` sea cual sea — y **Compose borra el `CMD` de la
    imagen cuando el servicio declara `entrypoint:` sin `command:`**. Medido
    sobre el contenedor real: `.Config.Cmd` en `null`, `$0` vacío, crash loop.

    Así que el comando está copiado en el compose, y esto es lo que impide que
    se desvíe: se leen los tokens del `CMD` del Dockerfile y se exige que estén,
    **en orden**, dentro del `command:` del servicio de dev. Cambiar el puerto o
    el módulo en el Dockerfile y olvidarse del compose pone esto en rojo.
    """
    raiz = pathlib.Path(__file__).parent.parent
    dockerfile = (raiz / "Dockerfile").read_text(encoding="utf-8")

    crudo = re.search(r"^CMD\s+(\[.*\])\s*$", dockerfile, re.MULTILINE)
    assert crudo, "el Dockerfile no declara un CMD en forma de lista JSON"
    tokens = json.loads(crudo.group(1))
    assert tokens, "el CMD del Dockerfile está vacío"

    # 🔴 Sobre el COMANDO, no sobre el bloque. Con el bloque entero, el
    # `8000` del `ports: - "8086:8000"` satisfacía el último token del CMD:
    # cambiarle el puerto al `command:` daba verde igual. Medido.
    arranque = _comando_de_arranque_de_dev()
    cursor = 0
    for token in tokens:
        pos = arranque.find(token, cursor)
        assert pos != -1, (
            f"el `command:` del servicio de dev no contiene `{token}`, que el "
            f"CMD del Dockerfile sí trae ({' '.join(tokens)}). Las dos copias "
            "del arranque se desviaron: la instancia de dev va a levantar "
            "distinto de la imagen que se despliega."
        )
        cursor = pos + len(token)
