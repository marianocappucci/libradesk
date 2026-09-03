"""Bloque de incidencias: pedidos 37, 38, 39, 40 y 41 (2026-08-04).

Los cinco salieron del usuario usando el producto, y cuatro son de la misma
pantalla. Lo que cubren estos tests:

- **41** — los tres papeles alrededor del ticket (recepciona / ejecuta / vende)
  salen del **mismo catálogo** de personal, con roles como banderas
  independientes.
- **37** — `modalidad` on-site / remoto, que es válido dejar sin definir.
- **39** — el PDF de una incidencia sola.
- **38 y 40** son de UI y los cubren los tests de frontend; acá se verifica lo
  que el backend tiene que sostener.
"""
import os

import pytest


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin."""
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def escenario(client):
    cliente = client.post("/api/clientes", json={"nombre": "Estudio Sur"}).json()
    # Una persona con DOS roles: es el caso que motivó no usar un campo `rol`.
    ana = client.post("/api/tecnicos", json={
        "nombre": "Ana", "es_tecnico": True, "es_vendedor": True,
    }).json()
    beto = client.post("/api/tecnicos", json={
        "nombre": "Beto", "es_tecnico": False, "es_recepcionista": True,
    }).json()
    equipo = client.post("/api/equipos", json={
        "cliente_id": cliente["id"], "tipo": "Notebook", "marca": "Lenovo",
    }).json()
    return {"cliente": cliente, "ana": ana, "beto": beto, "equipo": equipo}


# ── 41: un catálogo, roles como banderas ───────────────────────────────────

def test_una_persona_puede_tener_varios_roles(client, escenario):
    """El caso que descarta un campo `rol`: en una empresa chica la misma
    persona ejecuta y vende. Con un único rol habría que cargarla dos veces y su
    historial quedaría partido."""
    assert escenario["ana"]["roles"] == ["tecnico", "vendedor"]
    assert escenario["beto"]["roles"] == ["recepcionista"]


def test_una_persona_sin_ningun_rol_se_rechaza(client):
    """Quedaría cargada y fuera de los tres selectores: invisible, que se lee
    como un bug del sistema y no como un dato mal puesto."""
    r = client.post("/api/tecnicos", json={
        "nombre": "Nadie", "es_tecnico": False,
        "es_recepcionista": False, "es_vendedor": False,
    })
    assert r.status_code == 409
    assert "al menos un rol" in r.json()["detail"]


def test_no_se_puede_dejar_sin_roles_editando(client, escenario):
    r = client.put(f"/api/tecnicos/{escenario['ana']['id']}", json={
        "nombre": "Ana", "activo": True, "es_tecnico": False,
        "es_recepcionista": False, "es_vendedor": False,
    })
    assert r.status_code == 409


def test_filtrar_el_personal_por_rol(client, escenario):
    """Es lo que alimenta cada selector del ticket: el de recepcionista sólo
    ofrece recepcionistas."""
    tecnicos = client.get("/api/tecnicos?rol=tecnico").json()
    recep = client.get("/api/tecnicos?rol=recepcionista").json()
    vendedores = client.get("/api/tecnicos?rol=vendedor").json()

    assert [t["nombre"] for t in tecnicos] == ["Ana"]
    assert [t["nombre"] for t in recep] == ["Beto"]
    assert [t["nombre"] for t in vendedores] == ["Ana"]


def test_rol_invalido(client):
    assert client.get("/api/tecnicos?rol=gerente").status_code == 422


def test_los_que_ya_existian_quedan_como_tecnicos(client):
    """Un alta sin roles explícitos se comporta como antes del pedido 41 — que
    es la misma garantía que da la migración para las filas viejas."""
    t = client.post("/api/tecnicos", json={"nombre": "Legacy"}).json()
    assert t["es_tecnico"] is True
    assert t["roles"] == ["tecnico"]


def test_el_ticket_guarda_los_tres_papeles(client, escenario):
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "No arranca",
        "recepcionista_id": escenario["beto"]["id"],
        "tecnico_id": escenario["ana"]["id"],
        "vendedor_id": escenario["ana"]["id"],
    })
    assert ticket.status_code == 201, ticket.text
    t = ticket.json()
    assert t["recepcionista_id"] == escenario["beto"]["id"]
    assert t["tecnico_id"] == escenario["ana"]["id"]
    # La misma persona en dos papeles del mismo ticket: es válido.
    assert t["vendedor_id"] == escenario["ana"]["id"]


def test_borrar_una_persona_desasigna_LOS_TRES_papeles(client, escenario):
    """El `ondelete` no corre nunca (el pragma de FK está apagado), así que la
    desasignación es explícita. Cubrir sólo `tecnico_id` —que era lo que había—
    dejaría las otras dos columnas apuntando a un id inexistente."""
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "x",
        "recepcionista_id": escenario["beto"]["id"],
        "tecnico_id": escenario["ana"]["id"],
        "vendedor_id": escenario["ana"]["id"],
    }).json()

    assert client.delete(f"/api/tecnicos/{escenario['ana']['id']}").status_code == 204

    despues = client.get(f"/api/incidencias/{ticket['id']}").json()
    assert despues["tecnico_id"] is None
    assert despues["vendedor_id"] is None
    # Beto no se borró: su asignación sigue.
    assert despues["recepcionista_id"] == escenario["beto"]["id"]


# ── 37: on-site / remoto ───────────────────────────────────────────────────

def test_modalidad_on_site_y_remoto(client, escenario):
    for modalidad in ("on_site", "remoto"):
        r = client.post("/api/incidencias", json={
            "cliente_id": escenario["cliente"]["id"], "titulo": "x",
            "modalidad": modalidad,
        })
        assert r.status_code == 201
        assert r.json()["modalidad"] == modalidad


def test_modalidad_sin_definir_es_valida(client, escenario):
    """Los tickets anteriores al pedido no saben cómo se atendieron, y ponerles
    `on_site` sería inventar el dato. Por eso no hay default."""
    r = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "x",
    })
    assert r.status_code == 201
    assert r.json()["modalidad"] is None


def test_modalidad_invalida(client, escenario):
    r = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "x",
        "modalidad": "telepatia",
    })
    assert r.status_code == 409
    assert "Modalidad inválida" in r.json()["detail"]


def test_modalidad_invalida_al_editar(client, escenario):
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "x",
    }).json()
    r = client.put(f"/api/incidencias/{ticket['id']}", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "x",
        "modalidad": "telepatia",
    })
    assert r.status_code == 409


def test_filtrar_incidencias_por_modalidad_no_rompe_el_listado(client, escenario):
    """El listado tiene que seguir trayendo los que no tienen modalidad: son la
    mayoría en una base que ya existía."""
    client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "vieja",
    })
    client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "nueva",
        "modalidad": "remoto",
    })
    todas = client.get("/api/incidencias").json()
    assert len(todas) == 2
    assert {i["modalidad"] for i in todas} == {None, "remoto"}


# ── 39: el PDF de una incidencia ───────────────────────────────────────────

def test_el_pdf_de_una_incidencia(client, escenario):
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"],
        "equipo_id": escenario["equipo"]["id"],
        "titulo": "La notebook no arranca",
        "descripcion": "Enciende y queda en el logo",
        "recepcionista_id": escenario["beto"]["id"],
        "tecnico_id": escenario["ana"]["id"],
        "modalidad": "on_site",
    }).json()
    client.post(f"/api/incidencias/{ticket['id']}/actividades", json={
        "descripcion": "Se cambió la fuente",
    })

    r = client.get(f"/api/incidencias/{ticket['id']}/pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"
    # `inline`: lo normal es mirarlo y mandarlo a la impresora, no bajarlo.
    assert "inline" in r.headers["content-disposition"]


def test_el_pdf_dice_lo_que_tiene_que_decir(client, escenario):
    """Se lee el texto de vuelta con pypdf, no sólo la firma `%PDF`: un PDF
    vacío pasa igual el chequeo de firma. Mismo criterio que el informe."""
    from io import BytesIO

    from pypdf import PdfReader

    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"],
        "equipo_id": escenario["equipo"]["id"],
        "titulo": "La notebook no arranca",
        "recepcionista_id": escenario["beto"]["id"],
        "tecnico_id": escenario["ana"]["id"],
        "modalidad": "remoto",
        "resolucion": "Se reemplazó el disco",
    }).json()

    contenido = client.get(f"/api/incidencias/{ticket['id']}/pdf").content
    texto = "\n".join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)

    assert f"#{ticket['id']}" in texto
    assert "Estudio Sur" in texto
    # Los tres papeles, que es lo que el pedido 41 quería ver.
    assert "Beto" in texto
    assert "Ana" in texto
    assert "Remoto" in texto
    assert "Notebook Lenovo" in texto
    assert "Se reemplazó el disco" in texto


def test_el_pdf_no_se_cae_con_tipografia_de_word(client, escenario):
    """El título y la descripción los escribe el usuario, y pegar desde Word
    alcanza para meter un guión largo. Antes de `_TextoSeguroPDF` eso tumbaba la
    request con `UnicodeEncodeError`."""
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"],
        "titulo": "Impresora — no responde…",
        "descripcion": "El cliente dice “no imprime” y ya probó reiniciar",
    }).json()
    r = client.get(f"/api/incidencias/{ticket['id']}/pdf")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_el_pdf_de_una_incidencia_inexistente(client):
    assert client.get("/api/incidencias/999/pdf").status_code == 404


# ── 38 y 40: lo que el backend tiene que sostener ──────────────────────────

def test_crear_un_equipo_y_usarlo_en_el_ticket_sin_recargar(client, escenario):
    """El atajo del pedido 38: el alta de equipo devuelve el objeto completo, y
    con eso alcanza para dejarlo elegido sin volver a pedir la lista."""
    creado = client.post("/api/equipos", json={
        "cliente_id": escenario["cliente"]["id"], "tipo": "Impresora",
        "marca": "HP", "modelo": "M404",
    })
    assert creado.status_code == 201
    equipo = creado.json()
    assert equipo["id"] and equipo["tipo"] == "Impresora"

    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "x",
        "equipo_id": equipo["id"],
    })
    assert ticket.status_code == 201
    assert ticket.json()["equipo_id"] == equipo["id"]


def test_el_put_conserva_los_campos_que_no_se_tocan(client, escenario):
    """El guardado automático de la ficha manda el objeto entero en cada
    cambio. Si un campo nuevo no viajara en ese payload, tocar cualquier otra
    cosa lo borraría — y el usuario no tendría forma de notarlo."""
    ticket = client.post("/api/incidencias", json={
        "cliente_id": escenario["cliente"]["id"], "titulo": "x",
        "recepcionista_id": escenario["beto"]["id"],
        "vendedor_id": escenario["ana"]["id"],
        "modalidad": "on_site",
    }).json()

    # Cambia sólo el título, mandando el resto tal como lo hace la pantalla.
    actualizado = client.put(f"/api/incidencias/{ticket['id']}", json={
        **{k: ticket[k] for k in (
            "cliente_id", "equipo_id", "activo_id", "tecnico_id",
            "recepcionista_id", "vendedor_id", "modalidad", "sector_id",
            "categoria_id", "descripcion", "estado", "prioridad",
            "horas_invertidas", "notas", "resolucion",
        )},
        "titulo": "otro título",
    }).json()

    assert actualizado["titulo"] == "otro título"
    assert actualizado["recepcionista_id"] == escenario["beto"]["id"]
    assert actualizado["vendedor_id"] == escenario["ana"]["id"]
    assert actualizado["modalidad"] == "on_site"
