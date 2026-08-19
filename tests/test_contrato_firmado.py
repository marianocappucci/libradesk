"""El contrato firmado escaneado — el primer camino de subida del producto.

`contratos.archivo_pdf` existe desde la fase 1 del módulo de alquiler con un
comentario que dice "cargarlo es fase 3". La fase 3 se construyó el 2026-08-17
y **el archivo siguió sin camino**, porque el producto no tenía ninguno: los
tres routers que reciben archivos salen de LibraCore.

Lo que este archivo defiende, en orden de importancia:

1. **Lo que se sube se puede volver a leer.** Es todo el punto: el papel que el
   cliente firmó vuelve al sistema.
2. **Lo que entra es un PDF de verdad.** Un `.pdf` que no lo es se abre en
   blanco, y eso se descubre el día de la discusión con el cliente.
3. **Un upload que falla no se lleva puesto al que ya estaba.** El contrato
   firmado de un cliente es un documento que no se puede volver a generar.
4. 🔴 **El firmado entra en el backup.** Vive sólo en el volumen: un backup que
   no lo lleve se descarga igual, pesa parecido, y al restaurar deja las fichas
   apuntando a archivos que no están. Incompleto se ve igual que completo.
"""
import io
import os
import zipfile
from datetime import date

import pytest

from app.services import archivos

INICIO = date(2026, 8, 1)


def _pdf(relleno: int = 200) -> bytes:
    """Un PDF mínimo: lo único que el guard mira es la firma del principio."""
    return b"%PDF-1.4\n" + b"0" * relleno + b"\n%%EOF\n"


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
def contrato(client) -> dict:
    cliente = client.post("/api/clientes", json={
        "nombre": "Estudio Sur", "cuit": "30-71234567-9",
    }).json()
    r = client.post("/api/contratos", json={
        "tipo_contrato": "alquiler", "cliente_id": cliente["id"],
        "fecha_inicio": INICIO.isoformat(), "estado": "activo",
        "importe": 45000, "dia_vencimiento": 10,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _subir(client, contrato_id, contenido, nombre="firmado.pdf"):
    return client.post(
        f"/api/contratos/{contrato_id}/archivo",
        files={"archivo": (nombre, contenido, "application/pdf")},
    )


# -- 1. Lo que se sube se puede volver a leer ------------------------------

def test_sube_el_firmado_y_se_lee_igual(client, contrato):
    contenido = _pdf()
    r = _subir(client, contrato["id"], contenido)
    assert r.status_code == 200, r.text
    assert r.json()["bytes"] == len(contenido)

    r = client.get(f"/api/contratos/{contrato['id']}/archivo")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    # `inline` y no `attachment`: lo normal es mirarlo, igual que el acta.
    assert r.headers["content-disposition"].startswith("inline")
    # Byte a byte. Que el status sea 200 no dice que el archivo sea el mismo
    # que se subió — podría estar truncado por el loop de chunks.
    assert r.content == contenido

    # Y la ficha lo refleja: sin esto la pantalla no tiene cómo saber que hay
    # algo que ofrecer.
    ficha = client.get(f"/api/contratos/{contrato['id']}").json()
    assert ficha["archivo_pdf"]


def test_volver_a_subir_reemplaza_y_no_acumula(client, contrato, data_dir):
    _subir(client, contrato["id"], _pdf(100))
    segundo = _pdf(300)
    assert _subir(client, contrato["id"], segundo).status_code == 200

    assert client.get(f"/api/contratos/{contrato['id']}/archivo").content == segundo
    # Un archivo por contrato. Si el nombre saliera del `filename` del cliente,
    # acá habría dos y la ficha apuntaría a uno solo.
    assert os.listdir(data_dir / "contratos") == [f"contrato_{contrato['id']}.pdf"]


# -- 2. Lo que entra es un PDF de verdad -----------------------------------

def test_rechaza_lo_que_no_es_pdf_aunque_se_llame_pdf(client, contrato):
    """El caso real: alguien escanea a JPG y le cambia la extensión."""
    r = _subir(client, contrato["id"], b"\xff\xd8\xff\xe0" + b"0" * 100)
    assert r.status_code == 422, r.text
    assert "PDF" in r.json()["detail"]


def test_rechaza_por_extension(client, contrato):
    r = _subir(client, contrato["id"], _pdf(), nombre="firmado.jpg")
    assert r.status_code == 422, r.text


def test_rechaza_el_vacio(client, contrato):
    r = _subir(client, contrato["id"], b"")
    assert r.status_code == 422, r.text


def test_el_tope_es_de_20_mb(client, contrato):
    """El número, aparte del mecanismo. El test de abajo lo baja para no mover
    20 MB por la suite; sin este, bajarlo de verdad en el código pasaría
    inadvertido."""
    assert archivos.MAX_BYTES == 20 * 1024 * 1024


# -- 3. Un upload que falla no se lleva puesto al que ya estaba ------------

def test_el_que_pasa_el_tope_no_pisa_al_anterior(client, contrato, data_dir, monkeypatch):
    bueno = _pdf(100)
    assert _subir(client, contrato["id"], bueno).status_code == 200

    monkeypatch.setattr(archivos, "MAX_BYTES", 1024)
    r = _subir(client, contrato["id"], _pdf(4096))
    assert r.status_code == 413, r.text

    # 🔴 Lo que este test defiende de verdad: el contrato firmado que ya estaba
    # sigue entero. Escribir directo sobre el destino lo habría dejado truncado.
    assert client.get(f"/api/contratos/{contrato['id']}/archivo").content == bueno
    # Y no queda basura en el volumen.
    assert os.listdir(data_dir / "contratos") == [f"contrato_{contrato['id']}.pdf"]


# -- 4. Borrar, y las fichas sin archivo -----------------------------------

def test_borrar_lo_saca_del_disco_y_de_la_fila(client, contrato, data_dir):
    _subir(client, contrato["id"], _pdf())
    r = client.delete(f"/api/contratos/{contrato['id']}/archivo")
    assert r.status_code == 204, r.text

    assert os.listdir(data_dir / "contratos") == []
    assert client.get(f"/api/contratos/{contrato['id']}").json()["archivo_pdf"] is None
    assert client.get(f"/api/contratos/{contrato['id']}/archivo").status_code == 404


def test_sin_archivo_cargado_da_404(client, contrato):
    assert client.get(f"/api/contratos/{contrato['id']}/archivo").status_code == 404


def test_la_fila_apunta_a_un_archivo_que_no_esta(client, contrato, data_dir):
    """Un restore de un backup viejo, un volumen que no se montó o un borrado a
    mano dejan la columna apuntando a la nada. Sin el chequeo de disco esto es
    un 500 que no le dice nada a nadie."""
    _subir(client, contrato["id"], _pdf())
    os.remove(data_dir / "contratos" / f"contrato_{contrato['id']}.pdf")

    r = client.get(f"/api/contratos/{contrato['id']}/archivo")
    assert r.status_code == 404, r.text


def test_contrato_inexistente(client):
    assert _subir(client, 99999, _pdf()).status_code == 404
    assert client.get("/api/contratos/99999/archivo").status_code == 404
    assert client.delete("/api/contratos/99999/archivo").status_code == 404


# -- 5. 🔴 El firmado entra en el backup -----------------------------------

def test_el_firmado_entra_en_el_backup(client, contrato):
    """Vive sólo en el volumen. Si `Instancia.directorios` no lo nombra, el ZIP
    sale igual y sin los contratos del cliente — el mismo modo de fallar que
    tuvo la base en PostgreSQL hasta el 2026-08-09."""
    contenido = _pdf(500)
    assert _subir(client, contrato["id"], contenido).status_code == 200

    r = client.get("/api/config/backup-ahora")
    assert r.status_code == 200, r.text

    entrada = f"datos/contratos/contrato_{contrato['id']}.pdf"
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        assert entrada in z.namelist(), z.namelist()
        # Y con el contenido, no una entrada vacía.
        assert z.read(entrada) == contenido
