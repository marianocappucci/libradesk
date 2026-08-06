#!/usr/bin/env python3
"""Carga los datos de la demo pública de LibraDesk — ítem 8 de los pendientes
transversales de Libra.

**Por qué existe además de `seed_dev.py`.** Aquél asume que la instancia ya
tiene clientes: se planta con *"No hay clientes en esta instancia"*. Tiene
sentido para dev, que se pobló a mano hace meses; no lo tiene para una demo,
que se recrea vacía todas las madrugadas. Este script crea la cartera de
clientes primero y después delega en `seed_dev.sembrar()` para todo lo demás —
así los datos de ejemplo no se duplican en dos archivos que se van a
desincronizar.

> 🔴 **Nunca contra la instancia de un cliente.** Se planta si el host no es de
> dev, demo, prueba o local — misma guarda que `seed_dev.py`, importada de ahí.

Uso:
    python scripts/seed_demo.py --url https://demo.libradesk.com.ar \\
        --usuario admin --password ...
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from seed_dev import Api, obtener_o_crear, sembrar as sembrar_dev, url_no_productiva  # noqa: E402

#: La cartera de la demo. Una empresa de soporte técnico atiende a clientes de
#: rubros distintos, y las pantallas de LibraDesk se leen mejor así: un cliente
#: con muchos equipos, otro chico, uno con contrato de alquiler.
#:
#: Las condiciones frente al IVA están repartidas a propósito — es lo que
#: decide si el presupuesto sale con el IVA discriminado o con el precio final
#: (ítem 2, `app/services/iva.py`). Con todos iguales, esa mitad no se ve.
CLIENTES = [
    {"nombre": "Clínica del Sol", "empresa": "Clínica del Sol SA",
     "email": "sistemas@example.com.ar", "telefono": "11 4832-7700",
     "ciudad": "CABA", "cuit": "30-71455666-2",
     "condicion_iva": "Responsable Inscripto",
     "domicilio": "Av. Pueyrredón 1640, CABA"},
    {"nombre": "Colegio San José", "empresa": "Asociación Educativa San José",
     "email": "administracion@example.com.ar", "telefono": "11 4671-2200",
     "ciudad": "Ramos Mejía", "cuit": "30-71222888-4",
     "condicion_iva": "IVA Exento",
     "domicilio": "Av. Rivadavia 14200, Ramos Mejía"},
    {"nombre": "Distribuidora Norte", "empresa": "Distribuidora Norte SRL",
     "email": "compras@example.com.ar", "telefono": "11 4747-9900",
     "ciudad": "Vicente López", "cuit": "30-70998877-1",
     "condicion_iva": "Responsable Inscripto",
     "domicilio": "Av. Maipú 2800, Vicente López"},
    {"nombre": "Farmacia San Martín", "empresa": "Farmacia San Martín",
     "email": "farmacia@example.com.ar", "telefono": "11 4555-3322",
     "ciudad": "San Martín", "cuit": "27-25987654-3",
     "condicion_iva": "Monotributista"},
    {"nombre": "Estudio Pereyra & Asociados", "empresa": "Pereyra & Asociados",
     "email": "estudio@example.com.ar", "telefono": "11 4383-1100",
     "ciudad": "CABA"},
]


def sembrar(api: Api) -> None:
    """Crea la cartera y después todo lo que ya sabe hacer el seed de dev."""
    print("Clientes…")
    creados = 0
    for c in CLIENTES:
        _, nuevo = obtener_o_crear(api, "/api/clientes", "nombre", c["nombre"], c)
        creados += int(nuevo)
    print(f"  clientes     {creados} creados, {len(CLIENTES) - creados} ya estaban")
    print()

    sembrar_dev(api)


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
