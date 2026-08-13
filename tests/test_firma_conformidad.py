"""La conformidad del cliente: brecha 7 del backlog de Lagrace.

En su comprobante en papel, el pie dice que **la firma certifica la conformidad
del trabajo** y que el pago va a 15 días de la factura. Hoy ese respaldo vive
sólo en el talonario archivado.

Lo que se prueba acá es lo que puede fallar en producción: que la validación
rechace lo que no es un PNG (una columna `Text` acepta cualquier cosa), que
firmar de nuevo reemplace en vez de acumular, y que la firma **salga impresa**
en la orden de trabajo.
"""
import base64
import struct
import zlib
from io import BytesIO

import pytest
from pypdf import PdfReader

PREFIJO = "data:image/png;base64,"


def _login(client) -> None:
    assert client.post("/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200


def _png(ancho: int = 40, alto: int = 20) -> bytes:
    """Un PNG mínimo y **válido**, armado a mano.

    No se usa un base64 pegado en el archivo: uno querría cambiarle el tamaño
    para probar el tope y terminaría con una cadena que no decodifica, que es
    justo lo que la validación tiene que atajar — y el test pasaría por el
    motivo equivocado.
    """
    def chunk(tipo: bytes, datos: bytes) -> bytes:
        return (struct.pack(">I", len(datos)) + tipo + datos
                + struct.pack(">I", zlib.crc32(tipo + datos) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", ancho, alto, 8, 2, 0, 0, 0)
    # Una fila por línea: byte de filtro + RGB por píxel.
    crudo = b"".join(b"\x00" + b"\x20\x20\x20" * ancho for _ in range(alto))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(crudo)) + chunk(b"IEND", b""))


def _data_url(png: bytes | None = None) -> str:
    return PREFIJO + base64.b64encode(png if png is not None else _png()).decode()


def _texto_pdf(contenido: bytes) -> str:
    return "\n".join(p.extract_text() for p in PdfReader(BytesIO(contenido)).pages)


@pytest.fixture
def ticket(client):
    _login(client)
    cliente_id = client.post("/api/clientes", json={
        "nombre": "Neumyser S.A.", "email": "n@t.com",
    }).json()["id"]
    r = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "titulo": "Revisión de líneas",
        "nro_cds": "0001-00041996",
    })
    assert r.status_code == 201
    return r.json()


def test_sin_firmar_da_404(ticket, client):
    """404 y no `null` con 200: la pantalla necesita distinguir «sin firmar» de
    «no pude leerla»."""
    assert client.get(f"/api/incidencias/{ticket['id']}/firma").status_code == 404


def test_se_firma_y_se_relee(ticket, client):
    r = client.put(f"/api/incidencias/{ticket['id']}/firma", json={
        "imagen": _data_url(), "firmante": "Facundo Pérez",
        "observaciones": "Conforme. Quedó pendiente revisar el interno 12.",
    })
    assert r.status_code == 200, r.text

    leido = client.get(f"/api/incidencias/{ticket['id']}/firma").json()
    assert leido["firmante"] == "Facundo Pérez"
    assert leido["observaciones"].startswith("Conforme")
    assert leido["imagen"].startswith(PREFIJO)
    assert leido["firmado_at"] is not None


@pytest.mark.parametrize("imagen, motivo", [
    ("data:text/html;base64," + base64.b64encode(b"<script>").decode(), "no es PNG"),
    ("no-es-un-data-url", "no es data url"),
    (PREFIJO + "esto no es base64 %%%", "base64 inválido"),
    # 🔴 El caso que importa: prefijo correcto, base64 correcto, contenido que
    # NO es un PNG. Pasa los dos primeros chequeos y rompe el PDF al imprimir,
    # que es el peor momento para enterarse.
    (PREFIJO + base64.b64encode(b"GIF89a" + b"\x00" * 40).decode(), "es un GIF disfrazado"),
])
def test_lo_que_no_es_un_png_se_rechaza(ticket, client, imagen, motivo):
    r = client.put(f"/api/incidencias/{ticket['id']}/firma", json={"imagen": imagen})
    assert r.status_code == 422, f"se aceptó algo que {motivo}: {r.status_code}"
    # Y no quedó guardado a medias.
    assert client.get(f"/api/incidencias/{ticket['id']}/firma").status_code == 404


def test_una_firma_gigante_se_rechaza(ticket, client):
    """Una columna `Text` acepta 10 MB sin quejarse. Una firma real pesa entre
    5 y 40 KB."""
    enorme = _data_url(_png(ancho=1200, alto=1200) + b"\x00" * 1_200_000)
    r = client.put(f"/api/incidencias/{ticket['id']}/firma", json={"imagen": enorme})
    assert r.status_code == 422


def test_firmar_de_nuevo_reemplaza_y_no_acumula(ticket, client):
    """Una firma mal tomada se corrige volviendo a firmar delante del cliente.

    Guardar las dos obligaría a elegir cuál vale, y la respuesta siempre sería
    «la última».
    """
    primera = _data_url(_png(40, 20))
    segunda = _data_url(_png(60, 20))

    client.put(f"/api/incidencias/{ticket['id']}/firma", json={
        "imagen": primera, "firmante": "Quien no era",
    })
    client.put(f"/api/incidencias/{ticket['id']}/firma", json={
        "imagen": segunda, "firmante": "Facundo Pérez",
    })

    leido = client.get(f"/api/incidencias/{ticket['id']}/firma").json()
    assert leido["firmante"] == "Facundo Pérez"
    assert leido["imagen"] == segunda


def test_se_puede_rehacer_la_conformidad(ticket, client):
    client.put(f"/api/incidencias/{ticket['id']}/firma", json={"imagen": _data_url()})
    assert client.delete(f"/api/incidencias/{ticket['id']}/firma").status_code == 204
    assert client.get(f"/api/incidencias/{ticket['id']}/firma").status_code == 404
    # Y el ticket sigue existiendo: se borró la conformidad, no el trabajo.
    assert client.get(f"/api/incidencias/{ticket['id']}").status_code == 200


def test_firmar_un_ticket_inexistente_da_404(client):
    """404 y no un 500 de integridad: la FK lo atajaría igual, pero con un
    error que no se entiende."""
    _login(client)
    assert client.put("/api/incidencias/999999/firma",
                      json={"imagen": _data_url()}).status_code == 404


def test_la_conformidad_sale_impresa_en_la_orden_de_trabajo(ticket, client):
    """El nombre de quien firmó y sus observaciones, en el PDF.

    La **imagen** no se puede afirmar leyendo texto —pypdf extrae texto, no
    dibujos— así que lo que se verifica es que el PDF crezca al agregarla: sin
    eso, un `pdf.image()` que fallara en silencio dejaría el bloque con el
    nombre y sin la firma, que es un comprobante que no prueba nada.
    """
    antes = client.get(f"/api/incidencias/{ticket['id']}/pdf").content
    texto_antes = _texto_pdf(antes).upper()
    assert "CONFORMIDAD DEL CLIENTE" not in texto_antes, (
        "sin firma no tiene que haber sección — si no, el PDF se vuelve un "
        "formulario para firmar a mano, que es lo que esto reemplaza"
    )

    client.put(f"/api/incidencias/{ticket['id']}/firma", json={
        "imagen": _data_url(_png(300, 90)), "firmante": "Facundo Pérez",
        "observaciones": "Trabajo conforme.",
    })

    despues = client.get(f"/api/incidencias/{ticket['id']}/pdf").content
    texto = _texto_pdf(despues)
    assert "CONFORMIDAD DEL CLIENTE" in texto.upper()
    assert "Facundo Pérez" in texto
    assert "Trabajo conforme." in texto
    assert len(despues) > len(antes), "el PDF no creció: la imagen no se embebió"
