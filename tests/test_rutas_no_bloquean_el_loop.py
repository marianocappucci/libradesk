"""Las rutas de LibraDesk que tocan algo sincrónico no frenan el loop de uvicorn.

🔴 El producto corre uvicorn con **un solo proceso**. Una ruta `async def` que
llama sincrónico a la base —un repositorio sobre la `Session` de SQLAlchemy— o
al disco frena el loop entero mientras dura: ningún otro request avanza,
`/health` incluido. En un test común no se ve, porque la ruta contesta bien: lo
que hace mal es retener a los demás. Acá se mide eso y nada más.

Cómo: una llamada de la ruta se reemplaza por una que duerme con `time.sleep`
—bloquea el hilo donde corre, como la consulta real— y, mientras duerme, se
pide `/health` por el **mismo loop**. Si la ruta corre fuera del loop, `/health`
termina antes de que la llamada lenta se despierte; si lo bloquea, `/health` no
puede ni empezar hasta entonces. Se compara contra el instante en que la
llamada lenta **se despertó**, no contra un umbral de tiempo, así que el
resultado no depende de lo rápida que sea la máquina.

La subida del contrato firmado se mide dos veces, con lo lento en dos lugares:

- `base`: la lectura del contrato, en la ruta misma.
- `disco`: el `os.replace` del final de `guardar_pdf`. 🔑 Es el que atrapa el
  arreglo a medias —la ruta `def` pero `guardar_pdf` corriendo todavía en el
  loop—, que con sólo el caso `base` pasaría en verde.

Es la misma medición que `tests/test_rutas_no_bloquean_el_loop.py` de
LibraCore, Contalibra y Restolibra. Cada caso se probó volviendo la ruta a como
estaba en `origin/develop`: se ponen rojos.
"""
import asyncio
import os
import threading
import time
from datetime import date

import httpx
import pytest

from app.services import archivos

#: Lo que duerme la llamada reemplazada. Alcanza con que sea mucho más que lo
#: que tarda un `/health` sin carga.
LENTO = 0.5


class _Lento:
    """Una llamada sincrónica que tarda.

    `time.sleep` y no `asyncio.sleep` es el punto entero: una consulta a la
    base o una escritura a disco no le ceden el control a nadie.
    """

    def __init__(self):
        self.entro = threading.Event()
        self.desperto_en: float | None = None

    def dormir(self):
        self.entro.set()
        time.sleep(LENTO)
        if self.desperto_en is None:
            self.desperto_en = time.monotonic()


def _mientras_duerme(app, cookies, lento: _Lento, pedir):
    """Corre `pedir(cliente)` y, con la llamada lenta ya adentro, un `/health`
    por el MISMO loop. Devuelve la respuesta del pedido, la de `/health` y el
    instante en que `/health` terminó.

    `https` por la cookie de sesión, que sale con `secure=True`: sobre http el
    cliente la descarta y el pedido vuelve 401 (ver `conftest.client`)."""

    async def _correr():
        transporte = httpx.ASGITransport(app=app)
        async with (
            httpx.AsyncClient(transport=transporte, base_url="https://testserver",
                              cookies=cookies) as quien_pide,
            httpx.AsyncClient(transport=transporte, base_url="https://testserver") as otro,
        ):
            tarea = asyncio.create_task(pedir(quien_pide))
            # La espera va a un hilo para no ocupar el loop con la espera misma.
            assert await asyncio.to_thread(lento.entro.wait, 10), (
                "la llamada lenta nunca empezó: el parche no intercepta la ruta")
            health = await otro.get("/health")
            health_termino = time.monotonic()
            respuesta = await asyncio.wait_for(tarea, 30)
        return respuesta, health, health_termino

    return asyncio.run(_correr())


def _no_bloqueo(lento: _Lento, health, health_termino: float):
    assert health.status_code == 200, health.text
    # Sin esto el test pasaría si el parche no interceptara nada: sin llamada
    # lenta, no hay nada que bloquee.
    assert lento.desperto_en is not None, "la parte lenta no llegó a correr"
    assert health_termino < lento.desperto_en, (
        f"/health terminó {health_termino - lento.desperto_en:.2f}s DESPUÉS de "
        "que se despertara la llamada lenta: la ruta bloqueó el loop mientras dormía"
    )


@pytest.fixture
def instancia(armar_cliente):
    """La app real, logueada como admin y con un contrato cargado."""
    app, cliente = armar_cliente()
    r = cliente.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    titular = cliente.post("/api/clientes", json={
        "nombre": "Estudio Sur", "cuit": "30-71234567-9",
    }).json()
    r = cliente.post("/api/contratos", json={
        "tipo_contrato": "alquiler", "cliente_id": titular["id"],
        "fecha_inicio": date(2026, 8, 1).isoformat(), "estado": "activo",
        "importe": 45000, "dia_vencimiento": 10,
    })
    assert r.status_code == 201, r.text
    return app, cliente, r.json()


# ── contratos: subir el firmado ──────────────────────────────────────────


@pytest.mark.parametrize("donde", ["base", "disco"])
def test_subir_el_contrato_firmado_no_frena_el_loop(instancia, monkeypatch, data_dir, donde):
    app, cliente, contrato = instancia
    lento = _Lento()
    if donde == "base":
        real = app.state.contratos.get

        def leer_lento(contrato_id):
            lento.dormir()
            return real(contrato_id)

        monkeypatch.setattr(app.state.contratos, "get", leer_lento)
    else:
        real = os.replace

        def renombrar_lento(origen, destino):
            lento.dormir()
            return real(origen, destino)

        monkeypatch.setattr(archivos.os, "replace", renombrar_lento)

    contenido = b"%PDF-1.4\n" + b"0" * 200 + b"\n%%EOF\n"
    respuesta, health, fin = _mientras_duerme(
        app, cliente.cookies, lento,
        lambda c: c.post(f"/api/contratos/{contrato['id']}/archivo",
                         files={"archivo": ("firmado.pdf", contenido, "application/pdf")}))
    assert respuesta.status_code == 200, respuesta.text
    assert respuesta.json()["bytes"] == len(contenido)
    # Y el archivo llegó entero: pasar la lectura a `archivo.file` no puede
    # costar ni un byte.
    with open(data_dir / "contratos" / f"contrato_{contrato['id']}.pdf", "rb") as f:
        assert f.read() == contenido
    _no_bloqueo(lento, health, fin)
