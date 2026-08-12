"""
Definición única de los planes comerciales de LibraDesk y qué módulos habilita
cada uno. Fuente de verdad compartida entre:

- `app.services.modules.ModuleRepository` (aplica el plan dentro de la
  instancia de un cliente).
- `libracore.provisioning.nuevo_cliente` (asigna el plan al dar de alta).

Mismo patrón que `plans.py` de Contalibra/Restolibra/Gestiolibra/MedLibra/
VentaLibra, adaptado al catálogo de LibraDesk. Se agregó el 2026-08-02, al
normalizar los seis productos: LibraDesk era el único sin módulos, sin planes y
sin provisioning, y por eso el único que su backoffice no podía administrar
igual que al resto.

**El core de tickets no se gatea.** Clientes, equipos, incidencias, técnicos y
sectores son lo que define al producto: un LibraDesk sin incidencias no es un
plan más barato, es otra cosa. Mismo criterio que "turnos" en Contalibra y
"catálogo/turnos/clientes" en Gestiolibra.
"""

PLANES = ["basico", "estandar", "premium"]

PLAN_LABELS = {
    "basico":   "Básico",
    "estandar": "Estándar",
    "premium":  "Premium",
}

# Precio mensual de referencia (informativo, para mostrar en el backoffice).
# Alineado con Gestiolibra por decisión del 2026-08-02.
PLAN_PRECIOS = {
    "basico":   15000,
    "estandar": 25000,
    "premium":  40000,
}

# Básico: el core de tickets completo — clientes, equipos, incidencias,
# técnicos, sectores y la config de empresa. No son módulos gateables.
_BASICO: set[str] = set()

# Estándar = Básico + visibilidad: el tablero y los reportes exportables.
_ESTANDAR = _BASICO | {"dashboard", "reportes"}

# Premium = Estándar + lo comercial: lo que LibraDesk reusa de LibraCore
# (`libracore.db.remitos_presupuestos` y sus PDF) más el alquiler y cesión de
# equipos, agregado el 2026-08-04.
#
# `alquileres` cubre los DOS routers del módulo (activos y contratos) a
# propósito: un inventario de stock propio no le sirve a quien no puede
# entregarlo bajo contrato, así que gatearlos por separado ofrecería media
# funcionalidad. Va acá y no en el core —a diferencia de reparaciones, que es la
# continuación de `equipos`— porque es funcionalidad comercial: un LibraDesk sin
# alquileres sigue siendo LibraDesk.
#
# `facturacion_externa` (2026-08-08) es el puente que manda lo facturable a la
# instancia de Contalibra del mismo cliente. Módulo propio y no colgado de
# `remitos`: lo que habilita no es emitir un comprobante más, es que **dos
# sistemas contratados se vean**. Un cliente premium sin Contalibra tiene el
# módulo prendido y el puente apagado igual, porque sin la configuración de
# emparejamiento no hay a dónde mandar nada — ver
# `app/services/facturacion_externa.py`.
#
# `stock` (2026-08-12) es el inventario de consumibles, y sale de LibraCommerce
# en vez de código propio — ver `app/services/inventario.py`.
# Va en premium con el mismo criterio que `alquileres`: **un LibraDesk sin
# stock sigue siendo LibraDesk**. Una mesa de ayuda que sólo diagnostica no
# mueve materiales; la que sí los mueve hace algo más que soporte.
#
# ⚠️ El motor se adopta SIEMPRE —sus tablas se crean en toda instancia, la
# contrate o no— y lo que el plan enciende es el módulo. La asimetría es a
# propósito: ramificar el schema por plan dejaría dos formas distintas de base
# en producción, y ni el backup ni las migraciones podrían asumir cuál tienen
# delante.
#
# ⚠️ Y una consecuencia de agregar un módulo acá: `ModuleRepository.
# ensure_seeded()` inserta en el próximo arranque toda entrada nueva de
# `TODOS_LOS_MODULOS` **con `habilitado=True`**, en todas las instancias. Con
# `alquileres` eso le hizo aparecer una entrada de menú a un cliente que no la
# había pedido (ver la página de LibraDesk en el wiki). Hoy `stock` no tiene
# router ni pantalla, así que la fila se crea y no cambia nada visible; **el
# día que se construya la UI hay que decidir a quién se le enciende antes de
# desplegarla**, no después.
_PREMIUM = _ESTANDAR | {
    "remitos", "presupuestos", "alquileres", "facturacion_externa", "stock",
}

PLAN_MODULOS = {
    "basico":   set(_BASICO),
    "estandar": set(_ESTANDAR),
    "premium":  set(_PREMIUM),
}


def modulos_de_plan(plan: str) -> set[str]:
    """Los módulos habilitados para un plan (vacío si el plan es desconocido)."""
    return set(PLAN_MODULOS.get(plan, set()))


# Superset de todos los módulos gateables = los del plan más alto.
TODOS_LOS_MODULOS = set(PLAN_MODULOS["premium"])


def aplicar_plan_en_db(db_path: str, plan: str) -> None:
    """Aplica un plan escribiendo el estado de módulos directo en la base SQLite
    de un cliente (`clientes/<slug>/data/libradesk.db`). Lo usa el provisioning
    para asignar el plan de una instancia sin depender del contenedor.

    Shim sobre `libracore.provisioning.apply_plan_modules`, igual que en los
    otros cinco productos. Requiere que la tabla `modulos` ya exista — la crea
    la cadena de Alembic (`migrations/`) al arrancar la instancia, junto con el
    resto del schema propio. Hasta el 2026-08-03 la creaba
    `Base.metadata.create_all()`; ver `app/schema.py`.
    """
    if plan not in PLAN_MODULOS:
        raise ValueError(f"Plan desconocido: {plan!r}")
    from libracore.provisioning import apply_plan_modules

    apply_plan_modules(
        db_path, active_modules=modulos_de_plan(plan),
        all_modules=TODOS_LOS_MODULOS, plan=plan,
    )
