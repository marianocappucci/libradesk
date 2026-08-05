"""Logs para la SPA: actividad del sistema y accesos, en una sola pantalla.

**Admin-only**, gateado en `main.py` con `require_admin` — es la pantalla que
dice quien borro que y desde que IP entro cada uno.

Dos fuentes distintas y a proposito separadas en la respuesta:

- **actividad** — `actividad_log`, lo escribe el flush de SQLAlchemy
  (`services/auditoria.py`).
- **accesos** — `auth_log`, lo escribe el router de login del motor
  (`libraauth.auth_events`, v0.8.0).

Mismo contrato de respuesta que `/api/logs` de Contalibra (`actividad` +
`auth_log` + `total` + `total_pages` + el diccionario de metadatos por tipo),
para que la pantalla se parezca a la que el usuario ya conoce.
"""
from fastapi import APIRouter, Depends

from libraauth.auth_events import AuthEventRepository

from ..dependencies import get_auditoria_repository, get_auth_events_repository
from ..services.auditoria import AUDITABLES, BORRAR, CREAR, EDITAR, AuditoriaRepository

router = APIRouter(prefix="/api/logs", tags=["logs"])

PAGE_SIZE = 100

# El color lo elige el backend, igual que en Contalibra: la lista de entidades
# auditables vive en `auditoria.AUDITABLES` y una entidad nueva no deberia
# obligar a tocar el frontend para que se vea.
ACCION_META = {
    CREAR: {"label": "Creado", "color": "#198754"},
    EDITAR: {"label": "Editado", "color": "#0d6efd"},
    BORRAR: {"label": "Borrado", "color": "#dc3545"},
}


@router.get("")
def listar(
    entidad: str = "",
    accion: str = "",
    usuario: str = "",
    desde: str = "",
    hasta: str = "",
    page: int = 1,
    auditoria: AuditoriaRepository = Depends(get_auditoria_repository),
    accesos: AuthEventRepository = Depends(get_auth_events_repository),
):
    page = max(1, page)
    filtros = dict(entidad=entidad, accion=accion, usuario=usuario, desde=desde, hasta=hasta)
    total = auditoria.contar(**filtros)
    return {
        "actividad": auditoria.listar(**filtros, limit=PAGE_SIZE, offset=(page - 1) * PAGE_SIZE),
        "total": total,
        "total_pages": max(1, (total + PAGE_SIZE - 1) // PAGE_SIZE),
        "page": page,
        "entidades": sorted(set(AUDITABLES.values())),
        "acciones": ACCION_META,
        "usuarios": auditoria.usuarios(),
        # Los accesos no se paginan ni se filtran: son la segunda mitad de la
        # pantalla, no su contenido principal, y 100 filas cubren varios dias
        # de una instancia con un puñado de usuarios.
        "accesos": accesos.listar(limit=100),
    }
