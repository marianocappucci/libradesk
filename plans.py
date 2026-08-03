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

# Premium = Estándar + lo comercial, que es justo lo que LibraDesk reusa de
# LibraCore (`libracore.db.remitos_presupuestos` y sus PDF).
_PREMIUM = _ESTANDAR | {"remitos", "presupuestos"}

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
