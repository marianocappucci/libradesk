"""La salud de la instancia. Sin auth y sin lógica de negocio — la consumen el
`HEALTHCHECK` del contenedor, el panel de salud del backoffice y el monitoreo
externo, nunca el frontend (no hay una sola referencia en `frontend/src`).

**`/health`, la misma que los otros cinco productos de la familia.** Hasta el
2026-08-12 este producto la servía sólo en `/api/health`, siguiendo el prefijo
de sus otros 24 routers, y era el único que se desviaba. Ese desvío se pagaba en
dos lugares que existían por él: una env propia en el backoffice (`HEALTH_PATH`)
y un `health_path` propio en el generador de instancias de LibraCore. Los dos ya
no existen.

El argumento a favor del prefijo era la consistencia interna, y no se sostenía:
Contalibra y Restolibra tienen la misma forma —API bajo `/api` más el catch-all
de la SPA— y sirven `/health` en la raíz sin problema. La ruta explícita se
registra antes que el catch-all y le gana.

> ⚠️ `/api/health` existió como alias de transición entre el 2026-08-12 y esta
> misma fecha, y **ya no**. Ojo con lo que eso significa acá: como la SPA está
> horneada, pedirla hoy **no da 404** — la contesta el catch-all con el
> `index.html` y un `200`. Cualquier chequeo que haya quedado apuntado ahí y
> mire sólo el código HTTP va a seguir diciendo "ok" para siempre sin tocar la
> app. Los que miran el cuerpo —que son todos los de esta familia desde
> LibraCore v1.34.0— se ponen en rojo, que es lo correcto.
"""
from datetime import datetime, timezone

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}
