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
# Los mismos de la landing (libradesk.com.ar) desde el 2026-08-18: el humano
# fijó el Premium en 180.000 y los otros dos en la proporción que ya tenían.
# Hasta el 2026-09-11 acá seguían los de antes (15.000/25.000/40.000), así que
# la pantalla desde la que se da de alta a un cliente decía otra cosa que la web.
PLAN_PRECIOS = {
    "basico":    70000,
    "estandar": 115000,
    "premium":  180000,
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
# Los tres del bloque comercial (2026-08-12), que siguen a `stock` y le dan a
# LibraDesk la forma que ya tiene Contalibra — **sin emisión de factura**, que
# la hace SOS Contador:
#
# - `compras`: órdenes de compra, recepción de mercadería y egresos con estado
#   de pago. Gate propio y no colgado de `stock` porque se puede llevar
#   inventario sin registrar a quién se le compró. Al revés no: una recepción
#   necesita un depósito donde entrar, así que quien contrata `compras` tiene
#   `stock` — lo garantiza este archivo, no el código.
# - `ventas`: el comprobante interno de venta más los recibos.
# - `cuenta_corriente`: saldo por cliente, y las listas de precios, que viajan
#   en el mismo router.
#
# `insumos` (2026-08-24) es el consumo del parque del cliente: qué tóner le
# entró a cada máquina, quién se lo entregó y con qué contador se puso. Se gatea
# con el mismo criterio que los anteriores —una mesa de ayuda que sólo
# diagnostica no lleva el consumo de nadie— y tiene con `stock` la misma
# relación que `compras`: **elegir el insumo se hace contra el catálogo**, así
# que quien contrata `insumos` tiene `stock`, y lo garantiza este archivo.
#
# 🔑 **Lo que NO implica es `alquileres`**, y vale la pena dejarlo escrito
# porque los dos hablan de equipos alquilados. Acá el equipo se lo alquila un
# TERCERO al cliente y nosotros atendemos el parque; en `alquileres` el equipo
# es nuestro y se lo entregamos al cliente. Son las dos direcciones de la misma
# relación, y ninguna necesita a la otra.
#
# Las **sucursales** no están acá a propósito: no se gatean. Son estructura de
# la empresa, como los sectores y las categorías.
#
# ⚠️ Y una consecuencia de agregar un módulo acá: `ModuleRepository.
# ensure_seeded()` inserta en el próximo arranque toda entrada nueva de
# `TODOS_LOS_MODULOS` **con `habilitado=True`**, en todas las instancias. Con
# `alquileres` eso le hizo aparecer una entrada de menú a un cliente que no la
# había pedido (ver la página de LibraDesk en el wiki).
#
# 🔴 **Y esta vez sí cambia algo visible.** La nota que estaba acá decía que
# `stock` "no tiene router ni pantalla, así que la fila se crea y no cambia nada
# visible" — quedó vieja el mismo día en que se escribió. Hoy los cuatro módulos
# tienen router **y** pantalla, así que al desplegar esto
# **`libradesk-compulibra`, que es un cliente real, ve cuatro entradas nuevas de
# menú** si nadie las apaga antes. Se decide antes del deploy, no después.
_PREMIUM = _ESTANDAR | {
    "remitos", "presupuestos", "alquileres", "facturacion_externa", "stock",
    "compras", "ventas", "cuenta_corriente", "insumos",
}

PLAN_MODULOS = {
    "basico":   set(_BASICO),
    "estandar": set(_ESTANDAR),
    "premium":  set(_PREMIUM),
}


def modulos_de_plan(plan: str) -> set[str]:
    """Los módulos habilitados para un plan (vacío si el plan es desconocido)."""
    return set(PLAN_MODULOS.get(plan, set()))


# Add-ons opcionales: módulos que se habilitan **por instancia** y NO
# pertenecen a ningún plan. No entran en `PLAN_MODULOS` ni en
# `TODOS_LOS_MODULOS`, así que ni `apply_plan` (motor) ni `aplicar_plan_en_db`
# los tocan: un add-on prendido **sobrevive a subir o bajar de plan**.
# `libracore.db.modulos.apply_plan` lee este set con
# `getattr(plans, "ADDONS", set())`. Mismo patrón que `mayorista` en Contalibra.
#
# 🔑 **Y por eso `modo_simple` va acá y NO en un plan.** `ensure_seeded()`
# inserta toda entrada nueva de `TODOS_LOS_MODULOS` **con `habilitado=True` en
# todas las instancias** en el próximo arranque — es exactamente lo que pasó con
# `alquileres`, que le apareció en el menú a un cliente que no lo había pedido.
# Como add-on nace apagado en todos lados y se prende sólo donde se quiere.
#
#   - modo_simple: la experiencia reducida que pidió Lagrace (2026-09-09).
#     Ficha de reclamo con lo mínimo, sin Agenda ni Dashboard, home en el
#     listado de pendientes y vocabulario "Reclamos" en vez de "Incidencias".
#     **No apaga el core de tickets**: elige cómo se dibuja, no si existe.
#   - resguardo_externo: la copia de los backups a la nube del cliente (Google
#     Drive, Dropbox), con el enlace que monta `libracore.resguardo_enlace`
#     (LibraCore v1.93.0) en `/api/config/resguardo-externo/enlace`. Es el
#     único add-on que se gatea con `require_module`, y por eso
#     `ModuleRepository.is_enabled` trata los add-ons aparte: sin fila, apagado.
ADDONS = {"modo_simple", "resguardo_externo"}

# Superset de todos los módulos gateables = los del plan más alto.
#
# ⚠️ Los add-ons quedan afuera **a propósito** (ver `ADDONS`). Sumarlos acá los
# prendería solos en todas las instancias en el próximo arranque.
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
        # `- ADDONS`: aplicar un plan nunca toca un add-on. Hoy es equivalente
        # (ya estan afuera de `TODOS_LOS_MODULOS`), pero deja la invariante
        # escrita — mismo criterio que Contalibra.
        all_modules=TODOS_LOS_MODULOS - ADDONS, plan=plan,
    )
