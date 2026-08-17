"""Catálogo de servicios reutilizables — ítem 3.

> *"Lista de servicios para poder reutilizar en los presupuestos (que se pueda
> usar campo libre o items que ya esten preformateados)."*

Lo que fijan estos tests, en orden de lo que se rompe sin que se note:

1. 🔴 **Que el campo libre no se pierda.** Es la mitad del pedido y la que
   nadie reclama hasta que la necesita: un comprobante con un ítem que no está
   en el catálogo tiene que seguir guardándose igual que antes.
2. 🔴 **Que el comprobante NO referencie al servicio.** Si lo hiciera, cambiar
   el precio del catálogo cambiaría el total de presupuestos ya enviados — y
   eso no se descubre hasta que un cliente reclama.
3. Que el buscador encuentre por nombre y por descripción, y que no ofrezca
   inactivos.
4. Que el staff pueda buscar aunque no pueda administrar.
"""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin."""
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return client


def _servicio(client, nombre="Mantenimiento preventivo", descripcion="", precio=15000):
    r = client.post("/api/servicios", json={
        "nombre": nombre, "descripcion": descripcion, "precio": precio,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _cliente(client, nombre="Compulibra"):
    r = client.post("/api/clientes", json={"nombre": nombre})
    assert r.status_code == 201, r.text
    return r.json()


def _presupuesto(client, items):
    cliente = _cliente(client)
    r = client.post("/api/presupuestos", json={
        "client_id": cliente["id"], "items": items,
    })
    assert r.status_code == 201, r.text
    return r.json()


# ── 🔴 El campo libre sigue existiendo ────────────────────────────────────

def test_se_puede_cargar_un_item_que_no_esta_en_el_catalogo(client):
    """La mitad del pedido que nadie reclama hasta que la necesita: «que se
    pueda usar campo libre **o** ítems ya preformateados»."""
    _servicio(client)

    p = _presupuesto(client, [
        {"description": "Algo que no está en la lista", "qty": 1, "unit_price": 999},
    ])

    assert p["items"][0]["description"] == "Algo que no está en la lista"
    assert p["items"][0]["unit_price"] == 999


def test_un_presupuesto_sin_ningun_servicio_cargado_funciona_igual(client):
    """El catálogo vacío es el estado inicial de toda instancia. Si el
    comprobante lo necesitara, el producto se rompería al desplegar."""
    p = _presupuesto(client, [{"description": "Reparación", "qty": 1, "unit_price": 5000}])
    assert p["items"][0]["description"] == "Reparación"


# ── 🔴 El comprobante no queda atado al catálogo ──────────────────────────

def test_cambiar_el_precio_del_servicio_no_cambia_un_presupuesto_ya_hecho(client):
    """El escenario que justifica copiar en vez de referenciar: se cotizó a un
    precio, el catálogo se actualiza, y **el presupuesto enviado tiene que
    seguir diciendo lo que se acordó**."""
    servicio = _servicio(client, precio=15000)
    p = _presupuesto(client, [
        {"description": servicio["texto"], "qty": 2, "unit_price": servicio["precio"]},
    ])
    total_original = p["total"]

    r = client.put(f"/api/servicios/{servicio['id']}", json={
        "nombre": servicio["nombre"], "descripcion": "", "precio": 99000, "activo": True,
    })
    assert r.status_code == 200, r.text

    vuelto = client.get(f"/api/presupuestos/{p['id']}").json()
    assert vuelto["items"][0]["unit_price"] == 15000
    assert vuelto["total"] == total_original


def test_borrar_el_servicio_no_toca_el_presupuesto(client):
    servicio = _servicio(client)
    p = _presupuesto(client, [
        {"description": servicio["texto"], "qty": 1, "unit_price": servicio["precio"]},
    ])

    assert client.delete(f"/api/servicios/{servicio['id']}").status_code == 204

    vuelto = client.get(f"/api/presupuestos/{p['id']}").json()
    assert vuelto["items"][0]["description"] == servicio["texto"]
    assert vuelto["total"] == p["total"]


# ── El buscador ───────────────────────────────────────────────────────────

def test_busca_por_nombre(client):
    _servicio(client, "Mantenimiento preventivo")
    _servicio(client, "Instalación de red")

    res = client.get("/api/servicios/buscar?q=manten").json()
    assert [s["nombre"] for s in res] == ["Mantenimiento preventivo"]


def test_busca_tambien_por_descripcion(client):
    """El nombre es como lo llama quien carga el catálogo; la descripción, lo
    que lee el cliente. Quien arma el presupuesto puede acordarse de
    cualquiera de los dos."""
    _servicio(client, "Service anual", descripcion="Limpieza interna y cambio de pasta térmica")

    res = client.get("/api/servicios/buscar?q=pasta").json()
    assert len(res) == 1
    assert res[0]["nombre"] == "Service anual"


def test_con_texto_vacio_no_devuelve_el_catalogo_entero(client):
    """El desplegable aparece al escribir, no al enfocar el campo: devolver
    todo haría que se abriera solo cada vez que se toca la descripción."""
    _servicio(client)
    assert client.get("/api/servicios/buscar?q=").json() == []
    assert client.get("/api/servicios/buscar").json() == []


def test_un_servicio_inactivo_no_se_sugiere(client):
    """Dejar de ofrecer algo es desactivarlo. Si siguiera apareciendo, la
    desactivación no serviría para nada."""
    servicio = _servicio(client, "Servicio discontinuado")
    client.put(f"/api/servicios/{servicio['id']}", json={
        "nombre": servicio["nombre"], "descripcion": "", "precio": 0, "activo": False,
    })

    assert client.get("/api/servicios/buscar?q=discontinuado").json() == []


def test_pero_sigue_en_el_listado_de_administracion(client):
    """Para poder reactivarlo. Si desapareciera del ABM, desactivar sería un
    borrado sin vuelta atrás."""
    servicio = _servicio(client, "Servicio discontinuado")
    client.put(f"/api/servicios/{servicio['id']}", json={
        "nombre": servicio["nombre"], "descripcion": "", "precio": 0, "activo": False,
    })

    assert client.get("/api/servicios").json() == []
    con_inactivos = client.get("/api/servicios?incluir_inactivos=true").json()
    assert [s["nombre"] for s in con_inactivos] == ["Servicio discontinuado"]


# ── El texto que va al comprobante ────────────────────────────────────────

def test_sin_descripcion_el_texto_es_el_nombre(client):
    s = _servicio(client, "Mantenimiento", descripcion="")
    assert s["texto"] == "Mantenimiento"


def test_con_descripcion_el_texto_es_la_descripcion(client):
    """El caso real: un nombre corto para buscarlo y un texto largo para el
    comprobante."""
    s = _servicio(client, "Service", descripcion="Service anual, incluye limpieza y pasta térmica")
    assert s["texto"] == "Service anual, incluye limpieza y pasta térmica"


# ── ABM ───────────────────────────────────────────────────────────────────

def test_alta_edicion_y_baja(client):
    s = _servicio(client, "Uno", precio=100)

    editado = client.put(f"/api/servicios/{s['id']}", json={
        "nombre": "Uno corregido", "descripcion": "con detalle", "precio": 250, "activo": True,
    }).json()
    assert editado["nombre"] == "Uno corregido"
    assert editado["precio"] == 250
    assert editado["texto"] == "con detalle"

    # 🔑 **Desde el 2026-08-16 la baja es LÓGICA, no física**, y el motivo es
    # que el servicio se mudó al catálogo del motor: allá **sí** puede estar
    # referenciado —una línea de venta lo apunta por `item_id`, y desde ese
    # mismo día también un cargo de mano de obra—. Borrarlo de verdad dejaría
    # esas filas apuntando a un id que no existe.
    #
    # El gesto del usuario no cambia: la pantalla ya ofrecía desactivar antes
    # que borrar, y el servicio **desaparece del listado** igual. Lo que cambia
    # es que ya no hay forma de romper una venta vieja sin querer.
    assert client.delete(f"/api/servicios/{s['id']}").status_code == 204
    assert client.get(f"/api/servicios/{s['id']}").json()["activo"] is False
    assert not [
        x for x in client.get("/api/servicios").json() if x["id"] == s["id"]
    ], "y no se ofrece más: el listado sólo trae los activos"


def test_un_servicio_que_no_existe_da_404_y_no_500(client):
    assert client.get("/api/servicios/9999").status_code == 404
    assert client.delete("/api/servicios/9999").status_code == 404


def test_el_precio_no_puede_ser_negativo(client):
    r = client.post("/api/servicios", json={"nombre": "X", "precio": -1})
    assert r.status_code == 422


def test_el_nombre_no_puede_estar_vacio(client):
    assert client.post("/api/servicios", json={"nombre": ""}).status_code == 422


# ── Permisos ──────────────────────────────────────────────────────────────

def test_el_staff_puede_buscar(client):
    """Quien arma un presupuesto es staff, y el catálogo existe para que lo
    use. Cerrarlo dejaría una lista cargada que nadie puede consultar."""
    _servicio(client, "Mantenimiento")
    creado = client.post("/api/usuarios", json={
        "username": "tecnico-1", "name": "Técnico", "password": "tecnico-pass", "role": "staff",
    })
    assert creado.status_code in (200, 201), creado.text

    staff = TestClient(client.app, base_url="https://testserver")
    r = staff.post("/auth/login", json={"username": "tecnico-1", "password": "tecnico-pass"})
    assert r.status_code == 200, r.text

    assert staff.get("/api/servicios/buscar?q=manten").status_code == 200


# ── Un servicio es un ítem del catálogo, y tiene que seguir siéndolo ───────
#
# 🔑 Estos dos venían de `test_servicios_al_catalogo.py`, que se fue con la
# revisión `0031` junto a la copia de arranque que probaba. **No eran tests de
# la copia**: son propiedades del servicio como ítem del catálogo, y se
# quedaron sin cobertura al borrar aquel archivo. Se rescatan acá, escritos
# contra la API —que es como nace un servicio hoy— en vez de contra la tabla
# vieja.

def test_editar_por_la_pantalla_de_servicios_no_lo_vuelve_producto(client):
    """El camino del `PUT /api/servicios/{id}`, que pasa por
    `ServicioCatalogoRepository.actualizar`."""
    s = _servicio(client, "Instalación de central", precio=60000)

    r = client.put(f"/api/servicios/{s['id']}", json={
        "nombre": "Instalación (renombrada)", "descripcion": "", "precio": 80000,
    })
    assert r.status_code == 200, r.text

    assert s["id"] in [i["id"] for i in client.get("/api/servicios").json()], (
        "editarlo no puede sacarlo de los servicios"
    )
    # `GET /api/consumibles` filtra por `PRODUCT`: si el tipo se hubiera pisado,
    # el ítem aparecería acá.
    assert s["id"] not in [p["id"] for p in client.get("/api/consumibles").json()], (
        "y tampoco puede aparecer entre los consumibles"
    )


def test_editar_item_no_vuelve_producto_a_un_servicio(client):
    """🔴 **El defecto que esto fija ya ocurrió**, y el test de arriba NO lo
    cubre — se comprobó por mutación.

    `inventario.editar_item()` forzaba `CatalogItemType.PRODUCT`, así que editar
    un servicio por ahí lo convertía en producto: desaparecía de los servicios,
    aparecía entre los consumibles y entraba a las órdenes de compra.

    Se llama a `editar_item()` directamente y no por el `PUT` de servicios
    porque **ése no pasa por acá**: `actualizar()` guarda con
    `save_catalog_item()` por su cuenta. Poner la mutación y ver que la suite
    seguía en verde fue lo que lo mostró; sin eso, este archivo habría quedado
    con un test que parecía cubrir el defecto y no lo tocaba.
    """
    from app.services import inventario

    s = _servicio(client, "Instalación de central", precio=60000)

    inventario.editar_item(s["id"], nombre="Instalación (renombrada)",
                           precio=80000.0)

    assert s["id"] in [i["id"] for i in client.get("/api/servicios").json()], (
        "editarlo no puede sacarlo de los servicios"
    )
    assert s["id"] not in [p["id"] for p in client.get("/api/consumibles").json()], (
        "y tampoco puede aparecer entre los consumibles"
    )


def test_un_servicio_no_es_comprable(client):
    """Se vende, no se compra. Sin esto aparecería en las órdenes de compra al
    lado de los cables.

    Se lee de la base y no de la API porque `purchasable` **no se expone**: es
    una propiedad del ítem que ninguna pantalla muestra y por eso mismo nada la
    defendería si se cayera.
    """
    from libracommerce.domain.catalog import CatalogItemType
    from libracore.db import core as libracore_core

    s = _servicio(client, "Hora de servicio técnico", precio=25000)

    with libracore_core.get_connection() as conn:
        fila = conn.execute(
            "SELECT purchasable, item_type FROM catalog_items WHERE id = ?",
            (s["id"],),
        ).fetchone()

    assert fila is not None, "el servicio tiene que estar en el catálogo del motor"
    assert fila["item_type"] == str(CatalogItemType.SERVICE)
    assert not fila["purchasable"]
