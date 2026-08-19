"""Que `AUDITABLES` no nombre modelos que ya no existen.

La lista blanca de `app/auditoria.py` se indexa **por nombre de clase**, no por
la clase, para no importar los doce módulos de servicio desde ahí. El precio de
esa decisión —que es correcta— es que una entrada muerta **no rompe nada**:
nunca matchea, no hay `ImportError`, no hay atributo que falte. Se queda ahí
diciendo que algo se audita.

🔴 **Y no es sólo un comentario mentiroso: se ve en la pantalla.** El router de
logs de LibraAuth arma el selector de entidades con
`sorted(set(auditables.values()))` y **no** con un `SELECT DISTINCT` sobre el
log — a propósito, para ofrecer entidades que todavía no tuvieron actividad. O
sea que una entrada muerta aparece como filtro y **no puede devolver nada
nunca**, indistinguible de "todavía no se usó".

Pasó de verdad: la revisión `0031` dropeó la tabla `servicios` el 2026-08-17 y
borró el modelo, y `"Servicio": "servicio"` siguió en la lista **dos días**,
afirmando que el precio de lista de lo que se cotiza se auditaba.

Este archivo existe para que la próxima tabla que se dropee no deje el mismo
resto. Es el guard del patrón, no el arreglo de la instancia.
"""
from app.auditoria import AUDITABLES
from app.database import Base


def _modelos_vivos() -> set[str]:
    """Los nombres de clase de los modelos mapeados de este producto.

    Se pide `client` en los tests para que la app esté construida: los modelos
    se registran al importarse los módulos de servicio, y `create_app` los
    importa todos.
    """
    return {mapper.class_.__name__ for mapper in Base.registry.mappers}


def test_toda_entrada_de_auditables_nombra_un_modelo_que_existe(client):
    muertas = sorted(set(AUDITABLES) - _modelos_vivos())
    assert not muertas, (
        f"`AUDITABLES` nombra {len(muertas)} modelo(s) que ya no existen: "
        f"{muertas}. Una entrada muerta no rompe nada —la lista se indexa por "
        f"nombre de clase— pero deja su entidad ofrecida como filtro en la "
        f"pantalla de Logs, donde no puede devolver nada nunca. Si se dropeó el "
        f"modelo, sacá también su entrada."
    )


def test_el_guard_puede_fallar(client):
    """Control positivo: sin esto, el test de arriba pasaría igual con la lista
    vacía, con `_modelos_vivos()` devolviendo el universo, o con cualquier bug
    que haga que la resta dé siempre vacía."""
    vivos = _modelos_vivos()
    assert "Incidencia" in vivos, "el registro de modelos no se pobló"
    assert sorted({"ModeloQueNoExiste", "Incidencia"} - vivos) == ["ModeloQueNoExiste"]


def test_la_lista_no_quedo_vacia(client):
    """La otra forma de que el guard de arriba pase sin decir nada: que alguien
    vacíe `AUDITABLES`. Trece entidades al 2026-08-19."""
    assert len(AUDITABLES) >= 13, AUDITABLES
