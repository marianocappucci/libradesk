"""El provisioning de este producto, atado al código que corre.

Este archivo nace el 2026-08-24, del incidente de LibraCargo: su deploy salió
con **código 0** y dejó las dos instancias con el código nuevo sobre el esquema
viejo, porque el producto nunca había declarado `migraciones` y el default del
motor es vacío. Acá había 36 revisiones en la misma situación — las bases están
al día sólo porque alguien las corrió a mano en cada deploy.
"""

import importlib
import pathlib

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
