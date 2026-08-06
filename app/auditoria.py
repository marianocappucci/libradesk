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
    # El precio de lista de lo que se cotiza: lo cambia un admin a mano y se
    # arrastra a todo presupuesto que se arme despues.
    "Servicio": "servicio",
}

# Las tablas que YA son historial quedan afuera a proposito:
# `equipos_movimientos`, `incidencias_estados_log` y `actividades_incidencia`.
# La ficha del equipo y la de la incidencia ya las muestran, y auditarlas
# pondria el mismo hecho dos veces en la misma pantalla.
