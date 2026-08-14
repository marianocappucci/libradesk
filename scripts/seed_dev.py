#!/usr/bin/env python3
"""Carga datos de ejemplo en una instancia de **dev**, por la API.

**Para qué.** Una pantalla vacía no se puede revisar: no se ve el layout, ni los
estados, ni si los filtros hacen algo. El 2026-08-04 se desplegaron a dev las
fases 1 y 4 del módulo de alquileres y quedaron con `activos: 0` y
`contratos: 0`, o sea invisibles. Pedido explícito del usuario: que todo lo que
se despliegue a dev quede con ejemplos cargados.

**Por la API y no por SQL**, a propósito: así los datos pasan por las mismas
validaciones y los mismos servicios que usa la pantalla. Un seed por SQL puede
crear estados que la aplicación nunca produciría —un activo `colocado` sin línea
de contrato, por ejemplo— y entonces lo que se revisa no es el producto.

**No cubre sólo el caso feliz.** Deja a propósito los estados que las pantallas
distinguen: una línea de contrato cerrada y una vigente, un precio vencido y el
vigente, un equipo en service y otro disponible, un ticket on-site y otro
remoto. Si todo estuviera en el mismo estado, media pantalla quedaría sin
mirarse. La agenda (fase B del pedido 42) sigue el mismo criterio: dos trabajos
**pegados** en el mismo equipo —uno termina 11:00, el otro empieza 11:00—, dos
**equipos distintos a la misma hora**, y un ticket **sin agendar**.

> El 2026-08-13 se agregó un ticket en **`resuelta`**: era el único de los
> cuatro estados de incidencia que el seed no producía, así que el verde del
> semáforo —el punto de la grilla y, desde ese día, la píldora de Estado— no
> se veía nunca en la demo. Falta todavía uno en **`en_progreso`**.

**Es idempotente por nombre**: si el registro ya existe no lo duplica, así que
se puede correr después de cada deploy sin ensuciar.

> 🔴 **Nunca contra la instancia de un cliente.** Se planta si la URL no es la
> de dev. Los datos de `compulibra` son reales.

Uso:
    python scripts/seed_dev.py --url http://127.0.0.1:8086 --usuario admin --password ...
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta
from http.cookiejar import CookieJar

HOY = date.today()

#: Todos los campos de `IncidenciaIn`, para reenviarlos en un PUT.
#:
#: `PUT /api/incidencias/{id}` **reemplaza**, no parchea: lo que no viaja se
#: pierde contra el default del modelo. Este script hace dos PUT parciales —el
#: que completa la agenda de un ticket viejo y el que lo da por terminado— y
#: los dos tienen que reenviar el resto.
#:
#: 🔴 **Esta lista estaba escrita a mano y le faltaban cuatro campos**
#: (`estado_facturacion`, `nro_cds`, `reclamante`, `activo`), justo debajo de un
#: comentario que advertía *"hay que reenviar todo lo demás o se borra"*. El
#: 2026-08-13, al correr el seed sobre la demo, el PUT de la agenda le borró el
#: `estado_facturacion` a "Cambio de switch en el rack" y la pantalla de
#: facturación se quedó sin ejemplo de `no_facturable`. **No falló nada.**
#:
#: Los tres que faltan a propósito —`id`, `fecha_creacion`, `fecha_cierre`— son
#: de `IncidenciaOut`: los pone el producto y no se mandan de vuelta.
#:
#: `test_la_lista_de_campos_no_se_queda_atras_del_modelo` la compara contra
#: `IncidenciaIn`, así que agregar un campo nuevo al modelo pone el test en rojo
#: en vez de dejar que el seed lo borre en silencio.
CAMPOS_INCIDENCIA = (
    "cliente_id", "equipo_id", "activo_id", "tecnico_id",
    "recepcionista_id", "vendedor_id", "modalidad",
    "fecha_programada", "duracion_minutos", "equipo_trabajo_id",
    "sector_id", "categoria_id", "titulo", "descripcion",
    "nro_cds", "reclamante", "estado", "prioridad",
    "horas_invertidas", "notas", "resolucion", "estado_facturacion",
    "activo",
)

#: Los tickets que el seed deja **terminados**, por título.
#:
#: `(título, estado, horas, resolución, estado_facturacion)`.
#:
#: A nivel de módulo y no adentro de `sembrar()` para que se pueda mirar sin
#: correr el seed contra una instancia — ver `tests/test_seed_guarda.py`.
#:
#: 🔴 **Por título y no por índice de la lista.** Hasta el 2026-08-13 esto era
#: `(0, ...)`, `(1, ...)`, `(2, ...)` sobre lo que devolviera
#: `GET /api/incidencias`, que **no promete orden y no contiene sólo lo que
#: siembra este script**. En la demo, cargada además con tickets para la
#: presentación, los índices 0-2 cayeron en otros tres: quedó "Revisión de
#: cableado" con la resolución *"Se reemplazó la fuente y se probó 24 h."* y
#: "Instalación de access point" con *"Actualización de firmware y prueba de
#: impresión"*. Nada fallaba; la demo mostraba resoluciones que no tenían nada
#: que ver con su ticket.
#:
#: `resuelta` entra en la misma tanda porque es el mismo movimiento —el producto
#: trata `resuelta` y `cerrado` como los dos estados terminales, ver
#: `ESTADOS_CERRADOS` en `app/services/informes.py`— y porque era el único de
#: los cuatro estados que el seed no producía.
#: El numero del talonario de Comprobante de Servicios de cada ticket on-site.
#:
#: Va sobre los tres que quedan **cerrados** y del mismo cliente, que son
#: justamente los que se pueden agrupar en un remito: sin esto, agruparlos daba
#: tres renglones sin el numero y la feature parecia a medio hacer. El de
#: "Cambio de disco" queda afuera a proposito —esta en `resuelta`, no se
#: agrupa— y ademas hace falta que **algun** ticket no tenga papel, porque un
#: reclamo resuelto en remoto no lo tiene y la linea del remito tiene que poder
#: salir con el numero de ticket a secas.
CDS_POR_TITULO = {
    "Se corta el teléfono en recepción": "0001-00041996",
    "La impresora no toma papel": "0001-00041997",
    "Cambio de switch en el rack": "0001-00041998",
}

CIERRES = [
    ("Se corta el teléfono en recepción", "cerrado", 2.5,
     "Se reemplazó la fuente y se probó 24 h.", None),
    ("La impresora no toma papel", "cerrado", 1.0,
     "Actualización de firmware y prueba de impresión.", "facturado"),
    ("Cambio de switch en el rack", "cerrado", 4.0,
     "Recableado del rack y etiquetado.", "no_facturable"),
    ("Cambio de disco en el servidor de archivos", "resuelta", 3.0,
     "Disco reemplazado y RAID reconstruido. A la espera de que el cliente "
     "confirme para cerrar.", None),
]


class Api:
    def __init__(self, base: str):
        self.base = base.rstrip("/")
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(CookieJar())
        )

    def _pedir(self, metodo: str, ruta: str, cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        req = urllib.request.Request(
            f"{self.base}{ruta}", data=datos, method=metodo,
            headers={"Content-Type": "application/json"},
        )
        try:
            with self.opener.open(req, timeout=30) as r:
                crudo = r.read()
                return json.loads(crudo) if crudo else None
        except urllib.error.HTTPError as e:
            detalle = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"{metodo} {ruta} → {e.code}: {detalle}") from None

    get = lambda self, ruta: self._pedir("GET", ruta)  # noqa: E731
    post = lambda self, ruta, cuerpo=None: self._pedir("POST", ruta, cuerpo)  # noqa: E731
    put = lambda self, ruta, cuerpo: self._pedir("PUT", ruta, cuerpo)  # noqa: E731


def buscar(items, clave, valor):
    return next((i for i in items if i.get(clave) == valor), None)


def obtener_o_crear(api: Api, ruta: str, clave: str, valor: str, cuerpo: dict):
    """Idempotencia por nombre: correr el seed dos veces no duplica nada."""
    existente = buscar(api.get(ruta) or [], clave, valor)
    if existente:
        return existente, False
    return api.post(ruta, cuerpo), True


def sembrar(api: Api) -> None:
    creados: dict[str, int] = {}

    def contar(k: str, nuevo: bool):
        if nuevo:
            creados[k] = creados.get(k, 0) + 1

    # ── Personal con los tres roles (pedido 41) ────────────────────────────
    # Uno de cada rol, y uno con DOS: es el caso que motivó que los roles sean
    # banderas y no un campo `rol` único.
    personal = [
        ("Lucía Fernández", {"es_recepcionista": True, "es_tecnico": False}),
        ("Diego Ramos", {"es_tecnico": True}),
        ("Sofía Núñez", {"es_tecnico": True, "es_vendedor": True}),
        ("Martín Paz", {"es_tecnico": False, "es_vendedor": True}),
        # Responsable Y técnico: el caso que motivó que los roles sean banderas
        # y no un campo único (pedido 42).
        ("Rubén Actis", {"es_tecnico": True, "es_responsable": True}),
        ("Carla Vega", {"es_tecnico": True, "es_responsable": True}),
    ]
    gente: dict[str, dict] = {}
    for nombre, roles in personal:
        p, nuevo = obtener_o_crear(
            api, "/api/tecnicos", "nombre", nombre,
            {"nombre": nombre, "activo": True, **roles},
        )
        gente[nombre] = p
        contar("personal", nuevo)

    clientes = api.get("/api/clientes") or []
    if not clientes:
        raise RuntimeError("No hay clientes en esta instancia: nada que sembrar.")
    cliente = clientes[0]
    otro = clientes[1] if len(clientes) > 1 else cliente

    # ── Depósitos: propios y de cliente (pedido 35) ────────────────────────
    depositos = api.get("/api/depositos") or []
    for nombre, cliente_id, desc in (
        ("Taller", None, "Mesa de trabajo, fondo del local"),
        ("Depósito central", None, "Estantería A, equipos listos para entregar"),
        ("Pañol", cliente["id"], "Subsuelo, al lado del tablero"),
        ("Sala de racks", otro["id"], "Piso 2"),
    ):
        if buscar(depositos, "nombre", nombre):
            continue
        api.post("/api/depositos", {
            "nombre": nombre, "cliente_id": cliente_id, "descripcion": desc,
        })
        contar("depositos", True)

    # ── Equipos de trabajo y flota (pedido 42, fase A) ─────────────────────
    # Deja los tres estados que la pantalla distingue: un vehículo asignado
    # (que es la respuesta a "en qué sale el equipo"), uno libre y uno en
    # taller. Con los tres iguales, media pantalla quedaría sin mirarse.
    equipos_spec = [
        ("Cuadrilla Norte", "Rubén Actis", ["Diego Ramos", "Sofía Núñez"],
         "Zona norte y centro"),
        ("Cuadrilla Sur", "Carla Vega", ["Diego Ramos"], "Zona sur"),
    ]
    # `cuadrillas` y no `equipos`: más abajo `equipos` son los **equipos del
    # cliente** (`/api/equipos`), otra entidad entera. El nombre estaba usado
    # para las dos cosas a cien líneas de distancia, y la segunda pisaba a la
    # primera sin que se notara hasta necesitarla después.
    equipos_ya = api.get("/api/equipos-trabajo") or []
    cuadrillas: dict[str, dict] = {e["nombre"]: e for e in equipos_ya}
    for nombre, jefe, integrantes, obs in equipos_spec:
        if nombre in cuadrillas:
            continue
        cuadrillas[nombre] = api.post("/api/equipos-trabajo", {
            "nombre": nombre,
            "responsable_id": gente[jefe]["id"],
            "integrantes": [gente[n]["id"] for n in integrantes],
            "observaciones": obs,
        })
        contar("equipos_trabajo", True)

    vehiculos_spec = [
        ("AB123CD", "Renault", "Kangoo", 2019, "disponible"),
        ("CD456EF", "Volkswagen", "Partner", 2021, "disponible"),
        ("EF789GH", "Fiat", "Fiorino", 2017, "en_taller"),
    ]
    vehiculos_ya = api.get("/api/equipos-trabajo/vehiculos") or []
    vehiculos: dict[str, dict] = {v["patente"]: v for v in vehiculos_ya}
    for patente, marca, modelo, anio, estado in vehiculos_spec:
        if patente in vehiculos:
            continue
        vehiculos[patente] = api.post("/api/equipos-trabajo/vehiculos", {
            "patente": patente, "marca": marca, "modelo": modelo,
            "anio": anio, "estado": estado,
        })
        contar("vehiculos", True)

    # La asignación: es lo que contesta el pedido. Sólo si el vehículo sigue
    # libre, para que correr el seed dos veces no explote con un 409.
    kangoo = vehiculos["AB123CD"]
    if kangoo.get("equipo_id") is None and kangoo["estado"] == "disponible":
        api.post(f"/api/equipos-trabajo/vehiculos/{kangoo['id']}/asignar",
                 {"equipo_id": cuadrillas["Cuadrilla Norte"]["id"]})
        contar("asignaciones", True)

    proveedores = api.get("/api/proveedores") or []
    proveedor = proveedores[0] if proveedores else api.post(
        "/api/proveedores", {"nombre": "Compu Service SRL", "telefono": "11-5555-0000"},
    )

    # ── Catalogo de servicios (item 3) ────────────────────────────────────
    #
    # Sin esto, Configuracion -> Servicios abre vacia y el buscador del
    # formulario de comprobante no sugiere nada: la feature se ve como si no
    # existiera. Uno va SIN descripcion a proposito, para que se vea que en
    # ese caso el texto que va al comprobante es el nombre.
    #
    # 🔴 **El ultimo va marcado como valor hora.** Es el precio con el que se
    # cotiza el trabajo de un reclamo al generarle el remito. Sin ninguno
    # marcado, agrupar reclamos da un remito con la mano de obra en CERO: es el
    # comportamiento correcto, pero se ve como si la funcion estuviera rota, y
    # ademas la bandeja de facturacion se niega a mandar un remito en cero. La
    # demo tiene que mostrar la feature andando, no su caso degradado.
    servicios_spec = [
        ("Mantenimiento preventivo",
         "Mantenimiento preventivo de equipo, incluye limpieza interna y cambio "
         "de pasta térmica", 18000, False),
        ("Instalación de puesto de trabajo",
         "Instalación y configuración de puesto de trabajo completo", 25000, False),
        ("Visita técnica", "", 12000, False),
        ("Backup y migración de datos",
         "Resguardo y migración de datos a equipo nuevo", 30000, False),
        ("Configuración de red",
         "Configuración de router, switch y puntos de acceso", 40000, False),
        ("Hora de servicio técnico",
         "Hora de trabajo de servicio técnico", 15000, True),
    ]
    existentes_srv = api.get("/api/servicios?incluir_inactivos=true") or []
    for nombre, descripcion, precio, es_valor_hora in servicios_spec:
        ya = buscar(existentes_srv, "nombre", nombre)
        if ya:
            # Mismo criterio que los tickets de mas abajo: no se duplica, pero
            # SI se completa lo que falta. Una instancia sembrada antes de que
            # existiera el valor hora tiene el servicio y no la marca; el seed
            # diria "nada nuevo" —cierto— y el ejemplo quedaria incompleto.
            if es_valor_hora and not ya.get("es_valor_hora"):
                api.put(f"/api/servicios/{ya['id']}", {
                    "nombre": ya["nombre"], "descripcion": ya["descripcion"],
                    "precio": ya["precio"], "iva_rate": ya["iva_rate"],
                    "activo": ya["activo"], "es_valor_hora": True,
                })
                contar("servicios_completados", True)
            else:
                contar("servicios", False)
            continue
        api.post("/api/servicios", {
            "nombre": nombre, "descripcion": descripcion, "precio": precio,
            "es_valor_hora": es_valor_hora,
        })
        contar("servicios", True)

    # ── Activos, con los estados que la pantalla distingue (fase 1) ────────
    activos_spec = [
        ("Central telefónica", "Yeastar", "S20", "YS-2411-0087", 180000, 250000),
        ("Teléfono IP", "Grandstream", "GXP1625", "GS-A1174", 45000, 60000),
        ("Teléfono IP", "Grandstream", "GXP1625", "GS-B2290", 45000, 60000),
        ("Router", "TP-Link", "ER605", "TP-9931", 95000, 120000),
        ("Access point", "Ubiquiti", "U6-Lite", "UB-4417", 130000, 160000),
    ]
    activos: dict[str, dict] = {}
    existentes = api.get("/api/activos") or []
    for tipo, marca, modelo, serial, costo, reposicion in activos_spec:
        ya = buscar(existentes, "serial", serial)
        if ya:
            activos[serial] = ya
            continue
        activos[serial] = api.post("/api/activos", {
            "tipo": tipo, "marca": marca, "modelo": modelo, "serial": serial,
            "costo_compra": costo, "valor_reposicion": reposicion,
            "fecha_compra": (HOY - timedelta(days=400)).isoformat(),
            "garantia_vence": (HOY + timedelta(days=180)).isoformat(),
        })
        contar("activos", True)

    # ── Un contrato de alquiler con historia (fases 1 y 4) ─────────────────
    contratos = api.get("/api/contratos") or []
    if not contratos:
        inicio = HOY - timedelta(days=120)
        contrato = api.post("/api/contratos", {
            "tipo_contrato": "alquiler", "cliente_id": cliente["id"],
            "fecha_inicio": inicio.isoformat(), "estado": "activo",
            "importe": 45000, "dia_vencimiento": 10, "periodicidad": "mensual",
            "metodo_actualizacion": "porcentaje",
            "domicilio_instalacion": "Sucursal Centro — Av. San Martín 1240",
            "responsable": "Sofía Núñez",
        })
        contar("contratos", True)

        # La central, puesta desde el principio y todavía instalada.
        api.post(f"/api/contratos/{contrato['id']}/equipos", {
            "activo_id": activos["YS-2411-0087"]["id"],
            "fecha_instalacion": inicio.isoformat(),
            "ubicacion": "Rack sala de servidores",
        })
        # Un teléfono que se REEMPLAZÓ y se mandó a service: deja una línea
        # cerrada y una vigente, que es lo que la ficha tiene que mostrar.
        linea = api.post(f"/api/contratos/{contrato['id']}/equipos", {
            "activo_id": activos["GS-A1174"]["id"],
            "fecha_instalacion": inicio.isoformat(), "ubicacion": "Recepción",
        })
        cambio = HOY - timedelta(days=20)
        api.post(f"/api/contratos/equipos/{linea['id']}/reemplazar", {
            "activo_nuevo_id": activos["GS-B2290"]["id"],
            "fecha": cambio.isoformat(),
            "estado_activo_retirado": "en_reparacion",
            "service": {
                "proveedor_id": proveedor["id"],
                "fecha_envio": cambio.isoformat(),
                "remito_salida": "0001-00000318", "rma": "RMA-4471",
                "en_garantia": True,
            },
        })
        # Un aumento con vigencia: deja el precio viejo cerrado y el nuevo
        # vigente, que es el punto del histórico.
        api.post(f"/api/contratos/{contrato['id']}/precios", {
            "importe": 55000,
            "vigencia_desde": (HOY - timedelta(days=30)).isoformat(),
            "motivo": "porcentaje",
        })

        # Un comodato, para que se vea una modalidad sin cuota.
        comodato = api.post("/api/contratos", {
            "tipo_contrato": "comodato", "cliente_id": otro["id"],
            "fecha_inicio": (HOY - timedelta(days=60)).isoformat(),
            "estado": "activo",
            "observaciones": "Router entregado sin cargo mientras contrate el enlace.",
        })
        contar("contratos", True)
        api.post(f"/api/contratos/{comodato['id']}/equipos", {
            "activo_id": activos["TP-9931"]["id"],
            "fecha_instalacion": (HOY - timedelta(days=60)).isoformat(),
            "ubicacion": "Rack principal",
        })

    # ── Incidencias con modalidad, los tres papeles y agenda ───────────────
    # (pedidos 37, 41 y 42 fase B)
    #
    # Las agendadas van **al próximo lunes**, no a "hoy + N": si cayeran un
    # domingo la agenda del día laboral siguiente se vería vacía, que es
    # justamente lo que el usuario abre para revisar. Y las horas están
    # elegidas para que la pantalla muestre los tres casos que distingue:
    # bloques seguidos en un mismo equipo, dos equipos a la misma hora, y un
    # ticket sin agendar.
    # 🔴 El cliente de ejemplo no tenía NINGÚN equipo, y el seed nunca se lo
    # creaba. Consecuencia: los tickets de ejemplo quedaban con `equipo_id`
    # null, y el ingreso a reparación "del inventario" (pedido 43) directamente
    # no se podía sembrar — el caso que muestra el copiado de datos desde
    # `equipos` era el único que faltaba, justo el que hay que mirar.
    #
    # Lo tapaba que `equipo_id = ... if equipos else None` es una expresión
    # perfectamente válida que no falla ni avisa: seguía sembrando todo lo
    # demás y reportando éxito.
    equipos = api.get(f"/api/equipos?cliente_id={cliente['id']}") or []
    if not equipos:
        equipos = [api.post("/api/equipos", {
            "cliente_id": cliente["id"], "tipo": "Notebook", "marca": "Lenovo",
            "modelo": "ThinkPad T14", "serial": "LN-EJEMPLO-01",
            "ubicacion_oficina": "Administración",
        })]
        contar("equipos", True)
    equipo_id = equipos[0]["id"]
    lunes = HOY + timedelta(days=(7 - HOY.weekday()) % 7 or 7)

    def turno(hora: int, minuto: int = 0) -> str:
        return datetime.combine(lunes, time(hora, minuto)).isoformat()

    norte = cuadrillas["Cuadrilla Norte"]["id"]
    sur = cuadrillas["Cuadrilla Sur"]["id"]
    tickets = [
        # título, modalidad, recepcionó, técnico, vendedor, desde, minutos, equipo
        ("Se corta el teléfono en recepción", "remoto", "Lucía Fernández",
         "Diego Ramos", "Sofía Núñez", None, None, None),
        ("La impresora no toma papel", "on_site", "Lucía Fernández",
         "Sofía Núñez", None, turno(9), 120, norte),
        # Pegado al anterior: termina 11:00, éste empieza 11:00. Es el caso que
        # una comparación de intervalos mal hecha rechazaría.
        ("Cambio de switch en el rack", "on_site", "Lucía Fernández",
         "Diego Ramos", None, turno(11), 90, norte),
        # Misma hora que el primero, otro equipo: dos cuadrillas trabajan a la
        # vez, y la pantalla lo tiene que mostrar en dos columnas.
        ("Instalación de access point", "on_site", "Lucía Fernández",
         "Sofía Núñez", "Sofía Núñez", turno(9), 60, sur),
        ("Revisión de cableado", "on_site", "Lucía Fernández",
         "Diego Ramos", None, turno(14, 30), 180, sur),
        # Éste queda en `resuelta` (ver `cierres`), que es el único de los
        # cuatro estados que el seed no producía: había abiertas y cerradas y
        # nada en el medio, así que el verde del semáforo no se veía nunca —
        # ni el punto de la grilla ni la píldora de Estado.
        ("Cambio de disco en el servidor de archivos", "on_site",
         "Lucía Fernández", "Diego Ramos", None, turno(16), 120, norte),
    ]
    # 🔴 La idempotencia por título tiene un costo que se pagó de verdad: un
    # ticket de ejemplo cargado por un seed VIEJO no se entera de los campos que
    # se agregan después. Al desplegar la fase B, "La impresora no toma papel"
    # ya existía sin agendar, así que el bloque pegado 09:00–11:00 —el caso que
    # el seed quiere mostrar— no aparecía en la agenda. El seed decía "nada
    # nuevo" y era cierto; lo que no era cierto es que el ejemplo estuviera
    # completo.
    #
    # Por eso, además de no duplicar, **completa lo que está en null**. Sólo
    # eso: nunca pisa un valor cargado, así que si alguien movió el turno a mano
    # para probar algo, el seed no se lo deshace.
    existentes = {i["titulo"]: i for i in (api.get("/api/incidencias") or [])}
    for titulo, modalidad, recep, tecnico, vendedor, desde, minutos, equipo in tickets:
        ya = existentes.get(titulo)
        if ya is not None:
            faltantes = {
                campo: valor
                for campo, valor in (
                    ("fecha_programada", desde),
                    ("duracion_minutos", minutos),
                    ("equipo_trabajo_id", equipo),
                    ("modalidad", modalidad),
                    ("nro_cds", CDS_POR_TITULO.get(titulo)),
                )
                if valor is not None and ya.get(campo) is None
            }
            if faltantes:
                # El PUT lleva el objeto entero, así que hay que reenviar todo
                # lo demás o se borra. La lista está en `CAMPOS_INCIDENCIA`,
                # con un test que la compara contra el modelo.
                previos = {campo: ya.get(campo) for campo in CAMPOS_INCIDENCIA}
                api.put(f"/api/incidencias/{ya['id']}", {**previos, **faltantes})
                contar("incidencias_completadas", True)
            continue
        api.post("/api/incidencias", {
            "cliente_id": cliente["id"], "equipo_id": equipo_id,
            "titulo": titulo, "modalidad": modalidad,
            "recepcionista_id": gente[recep]["id"],
            "tecnico_id": gente[tecnico]["id"],
            "vendedor_id": gente[vendedor]["id"] if vendedor else None,
            "fecha_programada": desde,
            "duracion_minutos": minutos,
            "equipo_trabajo_id": equipo,
            # El numero del comprobante en papel, para los que lo tienen. Es lo
            # que encabeza la linea del reclamo cuando se lo agrupa en un remito.
            "nro_cds": CDS_POR_TITULO.get(titulo),
            "descripcion": "Cargada como ejemplo para revisar la pantalla.",
        })
        contar("incidencias", True)

    # ── Ingresos a reparación (pedido 43) ─────────────────────────────────
    # Los tres estados que la pantalla distingue: uno en el taller **con equipo
    # del inventario**, uno **de mostrador** (sin `equipo_id`, que es el caso
    # que justifica que la FK sea opcional) y uno **ya entregado**, con sus dos
    # comprobantes. Con los tres iguales media pantalla queda sin mirarse.
    ingresos_spec = [
        {
            "del_inventario": True,
            "contacto": "Marta Ríos", "contacto_telefono": "3514567890",
            "accesorios": "Cargador original, funda negra",
            "estado_fisico": "Tapa rayada en la esquina inferior derecha",
            "falla_declarada": "No enciende. Dice que se le cayó agua encima.",
            "observaciones": "Faltan dos tornillos de la base (preexistente)",
            "entregado_por": "Marta Ríos",
            "entrega": None,
        },
        {
            "del_inventario": False,
            "equipo_tipo": "Impresora", "equipo_marca": "HP",
            "equipo_modelo": "LaserJet M404", "equipo_serial": "HP-77120",
            "contacto": "Jorge Peña",
            "accesorios": "Cable de poder. Sin cable USB.",
            "estado_fisico": "Bandeja delantera floja",
            "falla_declarada": "Atasca el papel todo el tiempo",
            "entregado_por": "Jorge Peña",
            "entrega": None,
        },
        {
            "del_inventario": False,
            "equipo_tipo": "Router", "equipo_marca": "TP-Link",
            "equipo_modelo": "ER605", "equipo_serial": "TP-40881",
            "contacto": "Marta Ríos",
            "accesorios": "Fuente y patch cord",
            "estado_fisico": "Sin daños visibles",
            "falla_declarada": "Se reinicia solo cada dos horas",
            "entregado_por": "Marta Ríos",
            "entrega": {
                "retirado_por": "Marta Ríos",
                "trabajo_realizado": "Se actualizó el firmware y se cambió la fuente.",
                "observaciones_entrega": "Se probó 48 h sin reinicios.",
                # Se completa el técnico también acá: sin esto el comprobante de
                # entrega sale con "Técnico: —" y el ejemplo no muestra el campo.
                "tecnico": "Sofía Núñez",
            },
        },
    ]
    # Idempotencia por número de serie: es lo único que identifica al equipo
    # recibido, y los comprobantes no tienen nombre.
    ya_ingresados = {
        i["equipo_serial"] for i in (api.get("/api/ingresos-reparacion") or [])
    }
    for spec in ingresos_spec:
        cuerpo = {
            "cliente_id": cliente["id"],
            "tecnico_id": gente["Lucía Fernández"]["id"],
            **{k: v for k, v in spec.items()
               if k not in ("del_inventario", "entrega")},
        }
        if spec["del_inventario"]:
            cuerpo["equipo_id"] = equipo_id
            # Del inventario salen tipo/marca/modelo/serie, así que el serial
            # con el que se chequea la idempotencia es el de ese equipo.
            serial = equipos[0].get("serial")
        else:
            serial = spec["equipo_serial"]
        if serial and serial in ya_ingresados:
            continue
        creado = api.post("/api/ingresos-reparacion", cuerpo)
        contar("ingresos_reparacion", True)
        if spec["entrega"]:
            entrega = {k: v for k, v in spec["entrega"].items() if k != "tecnico"}
            entrega["tecnico_entrega_id"] = gente[spec["entrega"]["tecnico"]]["id"]
            api.post(f"/api/ingresos-reparacion/{creado['id']}/entregar", entrega)
            contar("entregas", True)

    # ── Categorias de incidencia y sectores del cliente ───────────────────
    # Estaban vacios en la demo: son los dos catalogos que alimentan los
    # desplegables de una incidencia, y sin ellos la pantalla ofrece una lista
    # vacia que parece rota.
    categorias = api.get("/api/categorias") or []
    for nombre in ("Redes", "Impresión", "Puestos de trabajo", "Servidores"):
        if buscar(categorias, "nombre", nombre):
            continue
        api.post("/api/categorias", {"nombre": nombre})
        contar("categorias", True)

    sectores = api.get("/api/sectores") or []
    for cli, nombre in ((cliente, "Administración"), (cliente, "Guardia"),
                        (otro, "Depósito"), (otro, "Recepción")):
        if any(s.get("nombre") == nombre and s.get("cliente_id") == cli["id"]
               for s in sectores):
            continue
        api.post("/api/sectores", {"cliente_id": cli["id"], "nombre": nombre})
        contar("sectores", True)

    # ── Presupuestos y remitos, con su PDF ────────────────────────────────
    # 🔴 Son las dos pantallas que un interesado abre para ver "como se ve un
    # comprobante", y estaban vacias: sin una fila no hay PDF que descargar, y
    # el modulo entero parece no existir. Pedido explicito del humano
    # (2026-08-06).
    #
    # Los items salen del catalogo de servicios sembrado arriba, no de texto
    # inventado acá: asi el ejemplo muestra el flujo real —elegir del catalogo
    # y que se complete precio y alicuota— y no un presupuesto que ningun
    # usuario podria haber armado.
    servicios = api.get("/api/servicios") or []
    if servicios:
        def item(srv, qty):
            return {"description": srv["nombre"], "qty": qty,
                    "unit_price": srv.get("precio") or 1000,
                    "tax_rate": srv.get("iva_rate")}

        # Tres estados distintos a proposito: la pantalla los pinta distinto y
        # con uno solo no se ve la diferencia.
        presupuestos_spec = [
            ("borrador", [item(servicios[0], 2)], "Sujeto a disponibilidad de repuestos."),
            ("enviado", [item(s, 1) for s in servicios[:3]],
             "Incluye traslado dentro del casco urbano."),
            ("aceptado", [item(servicios[1], 4), item(servicios[0], 1)],
             "Aceptado por mail el 04/08."),
        ]
        ya = {p.get("observations") for p in (api.get("/api/presupuestos") or [])}
        for estado, items, obs in presupuestos_spec:
            if obs in ya:
                continue
            api.post("/api/presupuestos", {
                "client_id": cliente["id"] if estado != "aceptado" else otro["id"],
                "status": estado, "items": items, "observations": obs,
            })
            contar("presupuestos", True)

        remitos_spec = [
            ([item(servicios[0], 1)], "Entregado en mano, conforme."),
            ([item(s, 2) for s in servicios[:2]], "Retira el cliente por depósito."),
        ]
        ya_r = {r.get("observations") for r in (api.get("/api/remitos") or [])}
        for items, obs in remitos_spec:
            if obs in ya_r:
                continue
            api.post("/api/remitos", {
                "client_id": cliente["id"], "items": items, "observations": obs,
            })
            contar("remitos", True)

    # ── Equipos en TODOS los depositos, y garantias a distintas distancias ──
    # 🔴 Tres cosas se arreglan acá, y las tres salieron de MEDIR los reportes
    # contra la demo, no de leer el codigo:
    #
    # 1. Los depositos estaban vacios. Un deposito sin equipos es una pantalla
    #    que existe y no muestra nada — y son cuatro: dos propios y dos del
    #    cliente.
    # 2. El reporte de **garantias** daba 0 filas: consulta
    #    `Equipo.garantia_vence <= hoy + dias` y ningun equipo tenia esa fecha.
    #    Por eso hay vencidas, por vencer y lejanas: el reporte por defecto
    #    mira 60 dias, y con una sola distancia no se ve para que sirve.
    # 3. Los reportes de equipos/equipamiento/movimientos traian 1 o 2 filas.
    depositos = {d["nombre"]: d for d in (api.get("/api/depositos") or [])}
    por_id = {c["id"]: c for c in clientes}

    def dentro_de(dias: int) -> str:
        return (date.today() + timedelta(days=dias)).isoformat()

    equipos_spec = [
        # (deposito, cliente_id, tipo, marca, modelo, serial, garantia, estado)
        ("Taller", cliente["id"], "Notebook", "Lenovo", "ThinkPad E14", "LN-77120", dentro_de(-40), "en_reparacion"),
        ("Taller", otro["id"], "Impresora", "Brother", "HL-L2360", "BR-55231", dentro_de(21), "en_reparacion"),
        ("Depósito central", cliente["id"], "PC de escritorio", "Dell", "OptiPlex 3080", "DL-90114", dentro_de(45), "operativo"),
        ("Depósito central", otro["id"], "Monitor", "Samsung", "S24R650", "SM-31007", dentro_de(210), "operativo"),
        ("Depósito central", cliente["id"], "UPS", "APC", "BX1500M", "APC-6621", dentro_de(-120), "operativo"),
        # Los dos depositos que son del cliente: sus equipos son de ese cliente.
        ("Pañol", 1, "Switch", "TP-Link", "TL-SG1024", "TPS-4410", dentro_de(9), "operativo"),
        ("Pañol", 1, "Access Point", "Ubiquiti", "U6-Lite", "UBQ-8802", dentro_de(365), "operativo"),
        ("Sala de racks", 2, "Servidor", "HP", "ProLiant ML30", "HP-10233", dentro_de(30), "operativo"),
        ("Sala de racks", 2, "NAS", "Synology", "DS220+", "SYN-7741", None, "operativo"),
    ]
    ya_serie = {e.get("serial") for e in (api.get("/api/equipos") or [])}
    for dep, cli_id, tipo, marca, modelo, serial, garantia, estado in equipos_spec:
        if serial in ya_serie or dep not in depositos:
            continue
        if cli_id not in por_id:
            continue
        api.post("/api/equipos", {
            "cliente_id": cli_id, "tipo": tipo, "marca": marca, "modelo": modelo,
            "serial": serial, "deposito_id": depositos[dep]["id"],
            "estado": estado, "garantia_vence": garantia,
            "observaciones": f"Ingresado al {dep.lower()}.",
        })
        contar("equipos_deposito", True)

    # Un par de traslados: los movimientos NO se crean solos, salen de cambiar
    # el deposito o el estado de un equipo (ver services/equipos.py). Sin esto
    # el reporte de movimientos se queda con las dos filas de los ingresos.
    inventario = api.get("/api/equipos") or []
    # 🔴 El destino no es libre: el producto rechaza guardar un equipo en el
    # depósito de OTRO cliente (422, y con razón). Así que un equipo del
    # cliente sólo se puede mover a un depósito propio de la empresa o al
    # suyo. Lo encontró este mismo seed al correr — leyendo el modelo no
    # aparecía.
    traslados = [("DL-90114", "Taller"), ("SM-31007", "Sala de racks")]
    for serial, destino in traslados:
        eq = buscar(inventario, "serial", serial)
        if not eq or destino not in depositos:
            continue
        if eq.get("deposito_id") == depositos[destino]["id"]:
            continue
        api.put(f"/api/equipos/{eq['id']}", {
            **{k: eq.get(k) for k in ("cliente_id", "tipo", "marca", "modelo",
                                      "serial", "estado", "garantia_vence",
                                      "ubicacion_oficina", "sector", "observaciones")},
            "deposito_id": depositos[destino]["id"],
        })
        contar("traslados", True)

    # ── Incidencias terminadas: alimentan el reporte de facturacion ─────────
    # El reporte pide `estado == "cerrado"` sobre clientes `por_servicio`, y el
    # seed no cerraba ninguna: daba 0 filas. `fecha_cierre` no se puede mandar
    # en el alta — la pone el producto al pasar a cerrado, asi que se cierra
    # con un PUT, que es lo que hace un usuario.
    #
    # Con los tres estados de facturacion a la vez (sin facturar, facturado y
    # no facturable) el filtro de la pantalla tiene las tres opciones con
    # resultados; con una sola no se ve que el filtro haga algo.
    #
    # La tabla vive en `CIERRES`, a nivel de modulo, con el porque de que sea
    # **por titulo y no por indice**. El titulo es la misma clave que usa la
    # idempotencia de mas arriba.
    por_titulo = {i["titulo"]: i for i in (api.get("/api/incidencias") or [])}
    for titulo, estado, horas, resolucion, estado_fact in CIERRES:
        inc = por_titulo.get(titulo)
        # Si no esta, es que la lista de `tickets` y esta lista se
        # desincronizaron: se avisa en vez de seguir en silencio, que es como
        # se llega a una demo con un estado sin ejemplos.
        if inc is None:
            print(f"  ⚠️  no se encontró el ticket «{titulo}» para dejarlo {estado}")
            continue
        if inc.get("estado") in ("cerrado", "resuelta"):
            continue
        # Mismo criterio que el PUT de la agenda: se reenvía el objeto entero.
        # Esta lista era todavía más corta —nueve campos— así que cerrar un
        # ticket le borraba de paso el `recepcionista_id`, el `vendedor_id` y
        # los tres campos de la agenda, que este mismo seed acababa de poner.
        api.put(f"/api/incidencias/{inc['id']}", {
            **{k: inc.get(k) for k in CAMPOS_INCIDENCIA},
            "estado": estado,
            "horas_invertidas": horas,
            "resolucion": resolucion,
            "estado_facturacion": estado_fact,
        })
        contar("incidencias_cerradas", True)

    # El logo del negocio, para que los comprobantes salgan como los de un
    # cliente y no con un hueco arriba.
    _cargar_logo(api, "Compulibra Servicios IT", "C", (79, 70, 229), contar)

    print("Sembrado:", creados or "nada nuevo (ya estaba todo)")


#: Los subdominios que NO son de un cliente. Se compara contra la **primera
#: etiqueta** del host, no como substring de la URL entera — ver
#: `url_no_productiva`.
_HOSTS_NO_PRODUCTIVOS = ("dev", "demo", "prueba", "localhost", "127.0.0.1")



def _cargar_logo(api: Api, nombre: str, inicial: str, color: tuple, contar) -> None:
    """Dibuja el logo del negocio y lo sube a Configuración.

    🔴 **Se genera, no se commitea.** PIL viene en la imagen del producto, así
    que el seed lo dibuja en el momento: no hay binarios en el repo y cambiar
    el color es cambiar una línea. Mismo criterio que el resto del seed — el
    estado limpio es código, no un archivo guardado a mano.

    Sin logo, los PDF de la demo salen con un hueco arriba: el interesado ve
    dónde iría el suyo pero no cómo se ve. Con uno, el comprobante se lee como
    el que va a emitir él.
    """
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        # En un entorno sin PIL el seed sigue: un logo faltante no vale
        # abortar la carga de datos.
        print("  (sin PIL: se saltea el logo)")
        return

    # Idempotencia tolerante: la clave del logo cambió de nombre entre
    # productos, así que se busca cualquiera que lo mencione en vez de fijar
    # una — un nombre equivocado acá haría que el logo se resuba en cada
    # corrida sin que se note.
    actual = api.get("/api/config/empresa") or {}
    if any("logo" in clave and valor for clave, valor in actual.items()):
        contar("logo", False)
        return

    ANCHO, ALTO = 520, 160
    imagen = Image.new("RGBA", (ANCHO, ALTO), (255, 255, 255, 0))
    dibujo = ImageDraw.Draw(imagen)
    # Cuadrado redondeado con la inicial, y el nombre al lado: es la forma que
    # tienen los logos de la familia y la que mejor sobrevive achicada en un
    # encabezado de PDF.
    dibujo.rounded_rectangle((8, 20, 128, 140), radius=24, fill=color)
    dibujo.text((52, 60), inicial, fill=(255, 255, 255))
    dibujo.text((150, 55), nombre, fill=(30, 30, 30))
    dibujo.line((150, 95, 150 + min(340, len(nombre) * 11), 95), fill=color, width=4)

    # 🔴 La subida es multipart a mano, así que necesita la URL y el opener del
    # `Api` real. La suite corre el seed contra un doble que habla directo con
    # la app y no tiene ninguno de los dos: sin esta guarda, `api.base`
    # reventaba con AttributeError y se llevaba puestos **11 tests** del seed
    # entero, no sólo el del logo.
    if not getattr(api, "base", None) or not getattr(api, "opener", None):
        return

    import io
    buffer = io.BytesIO()
    imagen.save(buffer, format="PNG")
    contenido = buffer.getvalue()

    limite = "----seed" + "0" * 12
    cuerpo = (
        f"--{limite}\r\n"
        # 🔴 El campo se llama `logo`, no `file`: con `file` la API contesta
        # 422. Leído del openapi de la instancia.
        'Content-Disposition: form-data; name="logo"; filename="logo.png"\r\n'
        "Content-Type: image/png\r\n\r\n"
    ).encode() + contenido + f"\r\n--{limite}--\r\n".encode()

    import urllib.request
    pedido = urllib.request.Request(
        f"{api.base}/api/config/empresa/logo", data=cuerpo, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={limite}"},
    )
    try:
        api.opener.open(pedido, timeout=30)
        contar("logo", True)
    except Exception as e:
        print(f"  -- logo: {e}")


def url_no_productiva(url: str) -> bool:
    """Si la URL apunta a una instancia donde se puede sembrar.

    🔴 **Compara la primera etiqueta del host, no un substring de la URL.** La
    versión anterior hacía `"dev" in url`, y con eso una instancia de cliente
    llamada `demoliciones.libradesk.com.ar` —o cualquiera cuyo nombre
    contuviera "dev"— habría pasado la guarda y recibido datos inventados entre
    los reales. De ahí no se vuelve fácil.
    """
    from urllib.parse import urlparse

    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    # El host entero **o** su primera etiqueta. Lo primero es para las IP y
    # `localhost`, que no tienen subdominio: partir `127.0.0.1` por el punto
    # da `127`, que no matchea con nada.
    return host in _HOSTS_NO_PRODUCTIVOS or host.split(".")[0] in _HOSTS_NO_PRODUCTIVOS


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--usuario", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument(
        "--force", action="store_true",
        help="Correr contra una URL que no parece de dev ni de demo. No usar.",
    )
    args = ap.parse_args()

    # La guarda. Un seed sobre la instancia de un cliente le mete datos
    # inventados entre los reales, y de ahí no se vuelve fácil.
    if not url_no_productiva(args.url) and not args.force:
        print(f"ERROR: {args.url} no parece una instancia de dev ni de demo.",
              file=sys.stderr)
        print("Este script NO se corre contra la instancia de un cliente.",
              file=sys.stderr)
        return 2

    api = Api(args.url)
    api.post("/auth/login", {"username": args.usuario, "password": args.password})
    sembrar(api)
    return 0


if __name__ == "__main__":
    sys.exit(main())
