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
    equipos = api.get(f"/api/equipos?cliente_id={cliente['id']}") or []
    equipo_id = equipos[0]["id"] if equipos else None
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
                )
                if valor is not None and ya.get(campo) is None
            }
            if faltantes:
                # El PUT lleva el objeto entero, así que hay que reenviar todo
                # lo demás o se borra. Los campos se listan explícitamente y no
                # se manda `ya` crudo: trae `id`, `fecha_creacion` y
                # `fecha_cierre`, que no son de `IncidenciaIn` — hoy Pydantic
                # los ignora, pero apoyarse en eso es apoyarse en un default
                # que se puede cambiar.
                previos = {
                    campo: ya.get(campo) for campo in (
                        "cliente_id", "equipo_id", "activo_id", "tecnico_id",
                        "recepcionista_id", "vendedor_id", "modalidad",
                        "fecha_programada", "duracion_minutos",
                        "equipo_trabajo_id", "sector_id", "categoria_id",
                        "titulo", "descripcion", "estado", "prioridad",
                        "horas_invertidas", "notas", "resolucion",
                    )
                }
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
            if not equipos:
                continue
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
            api.post(f"/api/ingresos-reparacion/{creado['id']}/entregar",
                     spec["entrega"])
            contar("entregas", True)

    print("Sembrado:", creados or "nada nuevo (ya estaba todo)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True)
    ap.add_argument("--usuario", required=True)
    ap.add_argument("--password", required=True)
    ap.add_argument(
        "--force", action="store_true",
        help="Correr contra una URL que no parece de dev. No usar.",
    )
    args = ap.parse_args()

    # La guarda. Un seed sobre la instancia de un cliente le mete datos
    # inventados entre los reales, y de ahí no se vuelve fácil.
    pistas = ("dev", "localhost", "127.0.0.1")
    if not any(p in args.url for p in pistas) and not args.force:
        print(f"ERROR: {args.url} no parece una instancia de dev.", file=sys.stderr)
        print("Este script NO se corre contra la instancia de un cliente.", file=sys.stderr)
        return 2

    api = Api(args.url)
    api.post("/auth/login", {"username": args.usuario, "password": args.password})
    sembrar(api)
    return 0


if __name__ == "__main__":
    sys.exit(main())
