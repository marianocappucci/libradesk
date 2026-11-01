"""Que audita LibraDesk — la lista blanca y nada mas.

El mecanismo (los listeners del `flush`, el diff, el ContextVar del usuario, el
repositorio de lectura) vive en `libraauth.auditoria` desde su v0.9.0. Nacio
aca el 2026-08-05 y se extrajo al dia siguiente, al ir a repetirlo en
Gestiolibra, MedLibra y VentaLibra: era el mismo codigo salvo esta lista.

Lo que queda en el producto es lo unico que el producto sabe: **cuales de sus
modelos vale la pena auditar**.

**Los clientes tienen el otro camino** (ADR-013, 2026-10-12). `clients` es una tabla del
motor y se escribe por `libracore.db.clients`, que no pasa por el `flush`: el motor le
avisa cada escritura a `libracore.auditoria` y este modulo le arma el registrador, que es
el `registrador_dbapi` de `libraauth` (mismo formato de fila, mismo usuario, misma tabla).
Por eso `Cliente` ya no esta en `AUDITABLES`: con las dos cosas, cada cambio dejaria dos
filas.
"""
from dataclasses import replace

from libraauth.auditoria import (  # noqa: F401 — re-export para el router y los tests
    BORRAR,
    CREAR,
    EDITAR,
    AuditoriaRepository,
    registrador_dbapi,
)

# {nombre de la clase del modelo: nombre logico}. Se indexa por nombre y no por
# la clase para no importar los 12 modulos de servicio desde aca — varios de
# ellos terminarian importando a este.
AUDITABLES: dict[str, str] = {
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
    # El numero con el que un tercero llama al equipo (2026-08-24). Se audita
    # por lo mismo que el `Contrato`: es un dato chico, se carga y se corrige a
    # mano, y de el depende algo caro — con el numero equivocado el proveedor
    # despacha el insumo para otra maquina.
    #
    # `EquipoInsumo` NO entra, y por el criterio de mas abajo: es historial y la
    # ficha del equipo ya lo muestra, asi que auditarlo pondria el mismo hecho
    # dos veces en la misma pantalla.
    "EquipoReferencia": "referencia_de_equipo",
    # El contrato con el proveedor (fase 2, mismo dia). Mismo criterio que
    # `Contrato`: es lo que se corrige a mano —una fecha de fin, un "incluye
    # insumos"— y de eso depende si un insumo se paga o se discute. Sus LINEAS
    # de cobertura quedan afuera, igual que las de `contratos`: son historial y
    # la ficha del contrato ya las muestra.
    "ContratoProveedor": "contrato_de_proveedor",
}

#: Lo que se audita por el camino del motor: `{tabla: nombre logico}`. Hoy sólo `clients`.
ENTIDADES_DEL_MOTOR: dict[str, str] = {"clients": "cliente"}

#: Lo que se audita por el repositorio de LibraCommerce (`RepositorioAuditado`): `{tabla: nombre
#: logico}`. Hoy sólo `catalog_items`, que cubre productos, consumibles y servicios del catálogo.
ENTIDADES_DEL_CATALOGO: dict[str, str] = {"catalog_items": "producto"}

#: Todo lo que la pantalla de Logs ofrece en el filtro de entidades. Router de `libraauth`
#: arma ese selector con `sorted(set(auditables.values()))`: sólo mira los valores, así que
#: mezclar las dos listas (clases del ORM y tablas del motor) alcanza.
ENTIDADES_DEL_LOG: dict[str, str] = {**AUDITABLES, **ENTIDADES_DEL_MOTOR, **ENTIDADES_DEL_CATALOGO}


def registrador_del_motor():
    """El registrador de `libracore.auditoria` para las escrituras de `clients`.

    - `atributos`: la columna `name` se muestra como `nombre`, `phone` como `telefono`, etc.
      Sale del mapeo de `Cliente` (`atributos_por_columna`) y no de una tabla a mano, para
      que una columna nueva del modelo se vea con su nombre sin tocar esto.
    - Sin `columnas_ocultas` propias: el ORM tampoco las tenia, y `libraauth` ya tapa las
      suyas (contrasenas, tokens, secretos).
    - El diff sale en **el orden de las columnas del modelo**, como salia del `flush`; el
      motor entrega la fila en el orden de la tabla, que no es el mismo, y la pantalla
      muestra las claves en el orden en que llegan.
    """
    from .services.clientes import atributos_por_columna, columnas_por_atributo

    registrar = registrador_dbapi(
        ENTIDADES_DEL_MOTOR, atributos={"clients": atributos_por_columna()},
    )
    orden = list(columnas_por_atributo().values())

    def _ordenada(fila):
        if fila is None:
            return None
        return {**{c: fila[c] for c in orden if c in fila}, **fila}

    def registrador(conn, cambio) -> None:
        registrar(conn, replace(cambio, antes=_ordenada(cambio.antes), despues=_ordenada(cambio.despues)))

    return registrador


def registrador_del_catalogo():
    """El registrador de las escrituras de `catalog_items` (altas, ediciones y bajas del catalogo).

    Es el `registrador_dbapi` de `libraauth` --mismo formato de fila, mismo usuario, misma
    tabla-- con las opciones de LibraCommerce (`opciones_del_registrador`: sin `created_at`,
    etiqueta por `name`, colecciones resumidas). Lo enchufa `RepositorioAuditado`, que lo llama
    en la misma transaccion que la escritura.
    """
    from libracommerce.db import auditoria as aud

    return registrador_dbapi(ENTIDADES_DEL_CATALOGO, **aud.opciones_del_registrador())


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
# ✅ **Cerrado el 2026-11-01 (ADR-020)**: el catalogo de LibraCommerce que reemplazo a
# `servicios` --`catalog_items`, donde vive el precio de lista-- se audita por el tercer
# camino: el repositorio de LibraCommerce envuelto en `RepositorioAuditado`
# (`services/inventario._repo`), con `registrador_del_catalogo()`. Como `clients`, no esta en
# `AUDITABLES`: con las dos cosas cada cambio dejaria dos filas.

# Las tablas que YA son historial quedan afuera a proposito:
# `equipos_movimientos`, `incidencias_estados_log` y `actividades_incidencia`.
# La ficha del equipo y la de la incidencia ya las muestran, y auditarlas
# pondria el mismo hecho dos veces en la misma pantalla.
#
# Por lo mismo quedan afuera `contratos_actas` y sus lineas (fase 3): un acta no
# se edita —se emite o se anula, y la anulacion queda escrita en la propia
# fila—, asi que auditarla registraria dos veces el unico cambio que tiene. Lo
# que si se audita es el `Contrato`, que es lo que se corrige a mano.
