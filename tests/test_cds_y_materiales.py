"""El N° CDS, el reclamante, y los materiales en la orden de trabajo.

Las tres cosas salen del **Comprobante de Servicios** de
[[lagrace-comunicaciones]] (`wiki/sources/lagrace-relevamiento-whatsapp.md`):
un talonario preimpreso que el técnico completa en la visita y el cliente
firma. El número de ese papel se tipea en el reclamo y es lo único que ata la
conformidad con el ticket del sistema.

Lo que se verifica acá es el efecto observable —que el dato viaje, que
sobreviva a otra edición y que salga impreso—, no que las columnas existan:
de eso ya se ocupa `test_alembic.py`.
"""
from io import BytesIO

import pytest
from pypdf import PdfReader


def _login(client) -> None:
    assert client.post("/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200


def _texto_pdf(contenido: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)


@pytest.fixture
def ticket(client):
    """Un reclamo con su comprobante en papel ya cargado."""
    _login(client)
    cliente_id = client.post("/api/clientes", json={
        "nombre": "Neumyser S.A.", "email": "n@t.com", "ciudad": "Chivilcoy",
    }).json()["id"]

    r = client.post("/api/incidencias", json={
        "cliente_id": cliente_id,
        "titulo": "Tienen problemas con las líneas",
        "descripcion": "Se revisó el cableado de la línea telefónica.",
        "prioridad": "media",
        "nro_cds": "0001-00041996",
        "reclamante": "FACUNDO",
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_el_numero_de_comprobante_y_el_reclamante_viajan(ticket, client):
    assert ticket["nro_cds"] == "0001-00041996"
    assert ticket["reclamante"] == "FACUNDO"

    # Y vuelven al releer, que es lo que prueba que se guardaron y no que el
    # POST devolvió lo que le mandaron.
    leido = client.get(f"/api/incidencias/{ticket['id']}").json()
    assert leido["nro_cds"] == "0001-00041996"
    assert leido["reclamante"] == "FACUNDO"


def test_un_reclamo_sin_papel_los_deja_en_null(client):
    """Un reclamo resuelto en remoto no tiene comprobante, y eso es válido.

    Si la columna hubiera salido `NOT NULL` con default vacío, «no
    corresponde» y «todavía no se cargó» serían indistinguibles.
    """
    _login(client)
    cliente_id = client.post("/api/clientes", json={
        "nombre": "Verde Siembra S.A.", "email": "v@t.com",
    }).json()["id"]

    r = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "titulo": "Consulta por teléfono",
    })
    assert r.status_code == 201
    assert r.json()["nro_cds"] is None and r.json()["reclamante"] is None


def test_editar_otro_campo_no_borra_el_comprobante(ticket, client):
    """🔴 El PUT recibe el objeto entero y **lo que no viaja vuelve a null**.

    Es el defecto que ya se pagó una vez con los tres campos de la agenda:
    cambiarle la prioridad a un ticket lo desagendaba en silencio. Este test
    existe para que no vuelva a pasar con el número del papel firmado, que es
    el peor dato posible para perder sin aviso.
    """
    r = client.put(f"/api/incidencias/{ticket['id']}", json={
        **ticket, "prioridad": "alta",
    })
    assert r.status_code == 200, r.text

    leido = client.get(f"/api/incidencias/{ticket['id']}").json()
    assert leido["prioridad"] == "alta"
    assert leido["nro_cds"] == "0001-00041996", "se perdió el N° CDS"
    assert leido["reclamante"] == "FACUNDO", "se perdió el reclamante"


def test_la_orden_de_trabajo_imprime_el_comprobante_y_el_reclamante(ticket, client):
    """Se lee el texto del PDF de vuelta, no el `Content-Type`.

    Un PDF vacío pasa igual un assert sobre el status y sobre la firma `%PDF`;
    lo único que prueba que el dato salió impreso es leerlo.
    """
    r = client.get(f"/api/incidencias/{ticket['id']}/pdf")
    assert r.status_code == 200, r.text

    texto = _texto_pdf(r.content)
    assert "0001-00041996" in texto
    assert "FACUNDO" in texto


def test_la_orden_de_trabajo_lista_los_materiales_consumidos(ticket, client):
    """La columna «Materiales Utilizados» del comprobante de ellos.

    El dato ya lo guardaba `incidencias_materiales` desde el PR #98; lo que
    faltaba era que el PDF lo leyera. Se verifica con **dos** materiales de
    cantidades distintas: con uno solo, un bug que imprimiera siempre la
    primera fila pasaría inadvertido.
    """
    deposito = client.post("/api/depositos-stock", json={
        "nombre": "AA630PK", "es_default": True,
    }).json()
    plug = client.post("/api/consumibles", json={
        "nombre": "PLUG RJ 45 CAT 6", "costo": 95,
    }).json()
    cable = client.post("/api/consumibles", json={
        "nombre": "CABLE UTP CAT 6 EXTERIOR", "costo": 780,
    }).json()

    for item, cantidad in ((plug, 40), (cable, 12)):
        assert client.post(f"/api/consumibles/{item['id']}/ajuste", json={
            "deposito_id": deposito["id"], "cantidad": cantidad + 10,
            "nota": "carga inicial",
        }).status_code == 200
        assert client.post(f"/api/incidencias/{ticket['id']}/materiales", json={
            "item_id": item["id"], "deposito_id": deposito["id"],
            "cantidad": cantidad,
        }).status_code == 201

    texto = _texto_pdf(client.get(f"/api/incidencias/{ticket['id']}/pdf").content)
    assert "PLUG RJ 45 CAT 6" in texto
    assert "CABLE UTP CAT 6 EXTERIOR" in texto
    # Las cantidades, no sólo los nombres: sin esto el test pasaría con una
    # tabla que imprime la descripción y se olvida la columna que importa.
    assert "40" in texto and "12" in texto


def test_un_material_devuelto_no_sale_en_el_comprobante(ticket, client):
    """Lo que volvió al depósito no se usó.

    Un comprobante que lo listara estaría documentando un consumo que no
    ocurrió — y en el circuito de ellos ese papel es lo que respalda el cobro.
    """
    deposito = client.post("/api/depositos-stock", json={
        "nombre": "DEPOSITO CENTRAL", "es_default": True,
    }).json()
    item = client.post("/api/consumibles", json={
        "nombre": "PATCHERA 24 BOCAS CAT 6", "costo": 38000,
    }).json()
    client.post(f"/api/consumibles/{item['id']}/ajuste", json={
        "deposito_id": deposito["id"], "cantidad": 5, "nota": "carga",
    })
    material = client.post(f"/api/incidencias/{ticket['id']}/materiales", json={
        "item_id": item["id"], "deposito_id": deposito["id"], "cantidad": 2,
    }).json()

    assert "PATCHERA 24 BOCAS CAT 6" in _texto_pdf(
        client.get(f"/api/incidencias/{ticket['id']}/pdf").content
    ), "el material puesto tiene que salir — si no, el resto del test no prueba nada"

    assert client.delete(
        f"/api/incidencias/{ticket['id']}/materiales/{material['id']}"
    ).status_code == 204

    assert "PATCHERA 24 BOCAS CAT 6" not in _texto_pdf(
        client.get(f"/api/incidencias/{ticket['id']}/pdf").content
    )


def test_sin_materiales_no_hay_seccion_vacia(ticket, client):
    """La sección no se dibuja si no hay nada, a diferencia de Descripción.

    La mayoría de los tickets de una mesa de ayuda no consumen material, y un
    encabezado con un guión en todos ellos entrena a saltear la sección justo
    en los que sí la tienen.
    """
    texto = _texto_pdf(client.get(f"/api/incidencias/{ticket['id']}/pdf").content).upper()
    assert "MATERIALES UTILIZADOS" not in texto
    # Control: el PDF sí se generó y tiene las secciones que siempre van. Sin
    # esto, un PDF roto o vacío pasaría este test.
    assert "RESOLUCIÓN" in texto or "RESOLUCION" in texto
