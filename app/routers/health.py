"""La salud de la instancia. Sin auth y sin lógica de negocio — la consumen el
`HEALTHCHECK` del contenedor, el panel de salud del backoffice y el monitoreo
externo, nunca el frontend (no hay una sola referencia en `frontend/src`).

**Por qué hay dos rutas.** La canónica es `/health`, que es donde la sirven los
otros cinco productos de la familia. LibraDesk la servía sólo en `/api/health`
siguiendo el prefijo de sus otros 24 routers, y ese desvío se pagó dos veces:
una env propia en el backoffice (`HEALTH_PATH`) y un `health_path` propio en el
generador de instancias de LibraCore, los dos existiendo por este único
producto. Contalibra y Restolibra tienen exactamente la misma forma —API bajo
`/api` más el catch-all de la SPA— y sirven `/health` en la raíz sin problema:
la ruta explícita se registra antes que el catch-all y le gana.

`/api/health` queda como alias mientras los consumidores sigan apuntando ahí
(el `docker-compose.yml` de este repo, el `HEALTH_PATH` del backoffice y el
`health_path` del provisioning). Se saca cuando no quede ninguno.
"""
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


def _estado() -> dict:
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/health")
def health():
    return _estado()


# Alias de transición. Al borrarlo, borrar también los asserts que lo nombran
# en la suite (`grep -rn '/api/health' tests/`).
@router.get("/api/health", include_in_schema=False)
def health_alias():
    return _estado()
