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
mirarse.

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
from datetime import date, timedelta
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

    # ── Incidencias con modalidad y los tres papeles (pedidos 37 y 41) ─────
    equipos = api.get(f"/api/equipos?cliente_id={cliente['id']}") or []
    equipo_id = equipos[0]["id"] if equipos else None
    tickets = [
        ("Se corta el teléfono en recepción", "remoto", "Lucía Fernández",
         "Diego Ramos", "Sofía Núñez"),
        ("La impresora no toma papel", "on_site", "Lucía Fernández",
         "Sofía Núñez", None),
    ]
    ya_cargadas = {i["titulo"] for i in (api.get("/api/incidencias") or [])}
    for titulo, modalidad, recep, tecnico, vendedor in tickets:
        if titulo in ya_cargadas:
            continue
        api.post("/api/incidencias", {
            "cliente_id": cliente["id"], "equipo_id": equipo_id,
            "titulo": titulo, "modalidad": modalidad,
            "recepcionista_id": gente[recep]["id"],
            "tecnico_id": gente[tecnico]["id"],
            "vendedor_id": gente[vendedor]["id"] if vendedor else None,
            "descripcion": "Cargada como ejemplo para revisar la pantalla.",
        })
        contar("incidencias", True)

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
