"""El estado de un reclamo se llama igual en el backend y en la pantalla.

## Qué defiende

La pantalla dice «reclamo» (masculino), pero el backend imprimía «Abierta» y
«Cerrada» —femenino, de cuando se llamaba «incidencia»— mientras el frontend
decía «Abierto» y «Cerrado». El mismo reclamo salía con dos géneros según
miraras la grilla o el PDF.

Hay una sola tabla en el backend (`incidencias.ESTADO_LABELS`: la usan el PDF,
el aviso y los reportes) y su copia en `frontend/src/api.ts`, que existe porque
la pantalla necesita las etiquetas tipadas para el filtro. Este test cruza las
dos para que no vuelvan a divergir. Los valores guardados (`resuelta` incluido)
no se tocan: sólo se compara lo que se muestra.
"""
import re
from pathlib import Path

from app.services import incidencias, reporte_vista

RAIZ = Path(__file__).resolve().parents[1]
API_TS = RAIZ / "frontend" / "src" / "api.ts"

MASCULINO = {
    "abierto": "Abierto", "en_progreso": "En progreso",
    "resuelta": "Resuelto", "cerrado": "Cerrado",
}


def _etiquetas_del_frontend() -> dict[str, str]:
    fuente = API_TS.read_text(encoding="utf-8")
    bloque = re.search(
        r"export const ESTADO_LABELS: Record<EstadoIncidencia, string> = \{(.*?)\n\}",
        fuente, re.S,
    )
    assert bloque, "no encontré ESTADO_LABELS en frontend/src/api.ts"
    return dict(re.findall(r"(\w+):\s*'([^']+)'", bloque.group(1)))


def test_el_backend_y_el_frontend_dicen_lo_mismo():
    assert _etiquetas_del_frontend() == incidencias.ESTADO_LABELS


def test_cubren_todos_los_estados_y_en_masculino():
    assert tuple(incidencias.ESTADO_LABELS) == incidencias.ESTADOS_VALIDOS
    assert incidencias.ESTADO_LABELS == MASCULINO


def test_los_reportes_toman_la_misma_tabla():
    for estado, etiqueta in incidencias.ESTADO_LABELS.items():
        assert reporte_vista.ESTADO_LABEL[estado] == etiqueta
