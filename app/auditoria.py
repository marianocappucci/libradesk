"""Que audita LibraDesk — la lista blanca y nada mas.

El mecanismo (los listeners del `flush`, el diff, el ContextVar del usuario, el
repositorio de lectura) vive en `libraauth.auditoria` desde su v0.9.0. Nacio
aca el 2026-08-05 y se extrajo al dia siguiente, al ir a repetirlo en
Gestiolibra, MedLibra y VentaLibra: era el mismo codigo salvo esta lista.

Lo que queda en el producto es lo unico que el producto sabe: **cuales de sus
modelos vale la pena auditar**.
"""
from libraauth.auditoria import (  # noqa: F401 — re-export para el router y los tests
    BORRAR,
    CREAR,
    EDITAR,
    AuditoriaRepository,
)

# {nombre de la clase del modelo: nombre logico}. Se indexa por nombre y no por
# la clase para no importar los 12 modulos de servicio desde aca — varios de
# ellos terminarian importando a este.
AUDITABLES: dict[str, str] = {
    "Cliente": "cliente",
    "Equipo": "equipo",
    "Incidencia": "incidencia",
    "Contrato": "contrato",
    "Activo": "activo",
    "Deposito": "deposito",
    "Proveedor": "proveedor",
    "Tecnico": "tecnico",
    "Sector": "sector",
    "CategoriaIncidencia": "categoria",
    "Reparacion": "reparacion",
    "EquipoTrabajo": "equipo_trabajo",
    "Vehiculo": "vehiculo",
}

# 🔴 Aca vivia `"Servicio": "servicio"`, con el comentario "el precio de lista de
# lo que se cotiza". Se fue el 2026-08-19: la revision `0031` dropeo la tabla
# `servicios` y borro el modelo el 2026-08-17, y la entrada quedo dos dias
# afirmando que ese precio se auditaba.
#
# **Una entrada muerta no rompe nada**, y por eso sobrevive: la lista se indexa
# por nombre de clase justamente para no importar los modelos, asi que un nombre
# que ya no existe simplemente nunca matchea. Lo que si hace es salir en la
# pantalla: `build_logs_router` arma el selector de entidades con
# `sorted(set(auditables.values()))` --y no con un `SELECT DISTINCT` sobre el
# log, a proposito, para ofrecer entidades sin actividad todavia--, o sea que el
# filtro "servicio" se ofrecia y no podia devolver nada nunca.
#
# Lo cuida `tests/test_auditables.py`, que es el guard del patron: la proxima
# tabla que se dropee no deja el mismo resto.
#
# ⚠️ **Queda abierto, y es una decision de producto**: el catalogo de
# LibraCommerce que reemplazo a `servicios` --`catalog_items`, donde hoy vive el
# precio de lista-- **no se audita en ningun lado**. Sus modelos son del motor,
# no de este producto, asi que sumarlo no es agregar una linea aca.

# Las tablas que YA son historial quedan afuera a proposito:
# `equipos_movimientos`, `incidencias_estados_log` y `actividades_incidencia`.
# La ficha del equipo y la de la incidencia ya las muestran, y auditarlas
# pondria el mismo hecho dos veces en la misma pantalla.
#
# Por lo mismo quedan afuera `contratos_actas` y sus lineas (fase 3): un acta no
# se edita —se emite o se anula, y la anulacion queda escrita en la propia
# fila—, asi que auditarla registraria dos veces el unico cambio que tiene. Lo
# que si se audita es el `Contrato`, que es lo que se corrige a mano.
