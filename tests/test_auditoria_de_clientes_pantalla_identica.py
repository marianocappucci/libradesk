"""La pantalla de Logs de un cliente es la MISMA con las escrituras por el motor (ADR-013).

Hasta el 2026-10-12 el CRUD de clientes era por SQLAlchemy y el log lo escribia el listener de
`flush` de `libraauth`. Ahora escribe `libracore.db.clients` y el log lo escribe el
`registrador_dbapi` que el motor llama dentro de la misma transaccion. Este archivo fija que
**lo que se ve no cambio**: `ESPERADO` se genero corriendo este mismo guion contra el codigo
anterior (el de `flush`), con `develop` de ese dia, y se pego tal cual. Si una diferencia se
acepta algun dia, se cambia aca a proposito y con su explicacion; si aparece sola, es una
regresion de la pantalla.

Se compara lo que muestra la pantalla --usuario, accion, entidad, id, descripcion y el diff
EN SU ORDEN--, sin `id` ni `ts`, que son del momento.
"""
CLIENTE = {
    "nombre": "Ana Pérez", "empresa": "Pérez SRL", "email": "ana@x.com", "telefono": "11-5555",
    "ciudad": "Rosario", "cuit": "20-12345678-9", "condicion_iva": "Responsable Inscripto",
    "domicilio": "Calle 1", "observaciones": "VIP", "tipo_facturacion": "por_servicio",
    "price_list_id": None, "activo": True,
}

#: (accion, entidad_id, descripcion, cambios), del mas viejo al mas nuevo. El `usuario` es
#: siempre `admin` y la entidad `cliente`.
ESPERADO = [
    ("crear", "1", "Cliente — Ana Pérez", None),
    ("editar", "1", "Cliente — Ana Pérez SA", {
        "nombre": ["Ana Pérez", "Ana Pérez SA"], "email": ["ana@x.com", "ana@y.com"],
        "telefono": ["11-5555", "11-6666"], "cuit": ["20-12345678-9", "20-98765432-1"],
        "condicion_iva": ["Responsable Inscripto", "Monotributista"], "price_list_id": [None, 3],
    }),
    ("editar", "1", "Cliente — Ana Pérez SA", {"ciudad": ["Rosario", None]}),
    ("editar", "1", "Cliente — Ana Pérez SA", {"activo": [1, 0]}),
    ("editar", "1", "Cliente — Ana Pérez SA", {"activo": [0, 1]}),
    ("borrar", "1", "Cliente — Ana Pérez SA", None),
    ("crear", "2", "Cliente — Solo nombre", None),
]


def _login(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text


def _guion(client):
    """Alta -> edicion -> edicion sin cambios -> vaciar un campo -> desactivar -> activar ->
    borrar, y despues un alta con sólo el nombre."""
    cid = client.post("/api/clientes", json=CLIENTE).json()["id"]
    actual = dict(CLIENTE)
    for cambios in (
        {"nombre": "Ana Pérez SA", "telefono": "11-6666", "email": "ana@y.com", "price_list_id": 3,
         "cuit": "20-98765432-1", "condicion_iva": "Monotributista"},
        {},  # un PUT que no cambia nada no deja fila
        {"ciudad": None},  # vaciar un campo desde la pantalla
    ):
        actual.update(cambios)
        r = client.put(f"/api/clientes/{cid}", json=actual)
        assert r.status_code == 200, r.text
    assert client.post(f"/api/clientes/{cid}/desactivar").status_code == 200
    assert client.post(f"/api/clientes/{cid}/activar").status_code == 200
    assert client.delete(f"/api/clientes/{cid}").status_code == 204
    assert client.post("/api/clientes", json={"nombre": "Solo nombre"}).status_code == 201
    return cid


def test_la_pantalla_de_logs_de_un_cliente_es_identica_a_la_del_flush(client):
    _login(client)
    _guion(client)
    datos = client.get("/api/logs", params={"entidad": "cliente"}).json()

    vistas = [
        (f["accion"], f["entidad_id"], f["descripcion"], f["cambios"])
        for f in reversed(datos["actividad"])
    ]
    assert vistas == ESPERADO
    assert {f["usuario"] for f in datos["actividad"]} == {"admin"}
    assert {f["entidad"] for f in datos["actividad"]} == {"cliente"}
    assert datos["total"] == len(ESPERADO)
    # El orden de las claves del diff es parte de lo que se ve: el JSON se guarda en el orden
    # en que se escribio.
    ediciones = [f["cambios"] for f in reversed(datos["actividad"]) if f["cambios"]]
    assert list(ediciones[0]) == ["nombre", "email", "telefono", "cuit", "condicion_iva", "price_list_id"]


def test_el_filtro_de_entidades_sigue_ofreciendo_cliente(client):
    """`Cliente` salio de `AUDITABLES` (ahora lo audita el motor) y la pantalla tiene que
    seguir ofreciendolo, ahora y antes de que haya actividad."""
    _login(client)
    entidades = client.get("/api/logs").json()["entidades"]
    assert "cliente" in entidades
    assert entidades == sorted(set(entidades))
