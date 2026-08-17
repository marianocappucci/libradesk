"""El abono deja de cobrar sin operar: las visitas de mantenimiento.

Hasta el 2026-08-16 el sistema le cobraba el mantenimiento al cliente todos los
meses y **no sabía que había que ir**. Verificado dos veces: cero coincidencias
de preventivo, próxima visita o recurrencia en todo `app/`.

Lo que fijan estos tests, en orden de lo que duele si se rompe:

1. 🔴 **Que generar dos veces no duplique la visita.** Es lo mismo que se
   sostiene en las cuotas, y acá además lo respalda un único en la base.
2. 🔴 **Que un contrato sin frecuencia no genere nada.** Es la garantía de
   adopción: los contratos que ya existen se comportan exactamente como hoy.
3. 🔴 **Que la visita nazca cubierta por el abono.** Si naciera sin cobertura,
   la conversión a remito la facturaría — y el cliente ya la paga en la cuota.
4. Que la cadencia de visita sea **independiente** de la de facturación.
5. Que fuera de la vigencia del contrato no se visite.
"""

import os
from datetime import date

import pytest

CUANDO = date(2026, 9, 15)


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado como admin."""
    r = client.post("/auth/login", json={
        "username": os.environ.get("LIBRADESK_ADMIN_USERNAME", "admin"),
        "password": os.environ.get("LIBRADESK_ADMIN_PASSWORD", "admin"),
    })
    assert r.status_code == 200, r.text
    return client


def f(d: date) -> str:
    return d.isoformat()


@pytest.fixture
def cliente(client):
    return client.post("/api/clientes", json={
        "nombre": "Medici Neumatec", "empresa": "NEUMYSER SRL",
        "tipo_facturacion": "mensual",
    }).json()


def _contrato(client, cliente, **extra):
    datos = {
        "tipo_contrato": "abono", "cliente_id": cliente["id"],
        "fecha_inicio": f(date(2026, 1, 1)), "estado": "activo", "importe": 45000,
        **extra,
    }
    r = client.post("/api/contratos", json=datos)
    assert r.status_code in (200, 201), r.text
    return r.json()


def _previsualizar(client, ancla=CUANDO, **extra):
    r = client.get("/api/visitas/previsualizar",
                   params={"ancla": f(ancla), **extra})
    assert r.status_code == 200, r.text
    return r.json()


def _generar(client, ancla=CUANDO, **extra):
    r = client.post("/api/visitas/generar", json={"ancla": f(ancla), **extra})
    assert r.status_code == 200, r.text
    return r.json()


# ── 1 y 2. Genera, y sólo cuando corresponde ─────────────────────────────


def test_un_abono_con_frecuencia_genera_su_visita(client, cliente):
    _contrato(client, cliente, frecuencia_visita="mensual")

    previo = _previsualizar(client)
    assert previo["a_generar"] == 1
    assert "septiembre 2026" in previo["visitas"][0]["titulo"]

    salida = _generar(client)
    assert salida["generadas"] == 1

    ticket = client.get(f"/api/incidencias/{salida['visitas'][0]['incidencia_id']}").json()
    assert ticket["estado"] == "abierto"
    assert ticket["fecha_programada"], "una visita se sabe cuándo es desde que nace"


def test_un_contrato_sin_frecuencia_no_genera_nada(client, cliente):
    """La garantía de adopción: lo que ya existe sigue comportándose igual."""
    _contrato(client, cliente)  # sin `frecuencia_visita`

    assert _previsualizar(client)["a_generar"] == 0
    assert _generar(client)["generadas"] == 0


def test_generar_dos_veces_no_duplica(client, cliente):
    _contrato(client, cliente, frecuencia_visita="mensual")

    assert _generar(client)["generadas"] == 1
    assert _generar(client)["generadas"] == 0, (
        "el segundo pase no puede volver a agendar el mismo período"
    )

    previo = _previsualizar(client)
    assert previo["a_generar"] == 0 and previo["ya_generadas"] == 1, (
        "y la ya generada se muestra, no se esconde: que el mes esté agendado "
        "es información"
    )


def test_un_contrato_que_no_esta_activo_no_visita(client, cliente):
    _contrato(client, cliente, frecuencia_visita="mensual", estado="borrador")
    assert _generar(client)["generadas"] == 0


# ── 3. La visita nace cubierta por el abono ──────────────────────────────


def test_la_visita_nace_cubierta_y_por_eso_no_se_factura(client, cliente):
    """🔴 El cliente ya la paga en la cuota. Si naciera sin cobertura, la
    conversión a remito la cobraría de nuevo."""
    _contrato(client, cliente, frecuencia_visita="mensual")
    salida = _generar(client)
    tid = salida["visitas"][0]["incidencia_id"]

    ticket = client.get(f"/api/incidencias/{tid}").json()
    assert ticket["cobertura_abono"] == "total"

    # Y la consecuencia, que es lo que importa: cerrada, no se puede remitar.
    client.put(f"/api/incidencias/{tid}", json={**ticket, "estado": "cerrado"})
    r = client.post("/api/incidencias/convertir-en-remito",
                    json={"incidencia_ids": [tid]})
    assert r.status_code == 409
    assert "abono cubre" in r.json()["detail"]


# ── 4. Visitar y cobrar son cadencias distintas ──────────────────────────


def test_la_cadencia_de_visita_es_independiente_de_la_de_cobro(client, cliente):
    """Cobra mensual y visita trimestral. Si el generador leyera `periodicidad`
    en vez de `frecuencia_visita`, el período sería septiembre y no jul-sep."""
    _contrato(client, cliente, periodicidad="mensual",
              frecuencia_visita="trimestral")

    visita = _previsualizar(client)["visitas"][0]
    assert visita["periodo_desde"] == "2026-07-01"
    assert visita["periodo_hasta"] == "2026-09-30"
    assert "julio a septiembre" in visita["titulo"], (
        "un trimestral titulado por un solo mes se lee como mensual"
    )


def test_un_trimestral_no_genera_de_nuevo_dentro_del_mismo_bloque(client, cliente):
    _contrato(client, cliente, frecuencia_visita="trimestral")

    assert _generar(client, date(2026, 7, 5))["generadas"] == 1
    # Agosto cae en el MISMO bloque jul-sep: no corresponde otra visita.
    assert _generar(client, date(2026, 8, 20))["generadas"] == 0
    # Octubre ya es el bloque siguiente.
    assert _generar(client, date(2026, 10, 2))["generadas"] == 1


# ── 5. Vigencia ──────────────────────────────────────────────────────────


def test_no_se_visita_antes_de_que_arranque_el_contrato(client, cliente):
    _contrato(client, cliente, frecuencia_visita="mensual",
              fecha_inicio=f(date(2026, 11, 1)))
    assert _generar(client, date(2026, 9, 15))["generadas"] == 0


def test_no_se_visita_despues_de_que_termino(client, cliente):
    _contrato(client, cliente, frecuencia_visita="mensual",
              fecha_fin=f(date(2026, 8, 31)))
    assert _generar(client, date(2026, 9, 15))["generadas"] == 0


# ── La validación de la frecuencia ───────────────────────────────────────


def test_una_frecuencia_que_la_aritmetica_no_entiende_se_rechaza(client, cliente):
    """Si entrara, el contrato quedaría sin generar visitas **en silencio**:
    `_proponer()` la saltea para no tumbar la previsualización entera."""
    r = client.post("/api/contratos", json={
        "tipo_contrato": "abono", "cliente_id": cliente["id"],
        "fecha_inicio": f(date(2026, 1, 1)), "estado": "activo",
        "importe": 45000, "frecuencia_visita": "quincenal",
    })
    # 409 y no 422: es el código que este router usa para todo `ValueError` del
    # servicio, y la frecuencia se valida ahí junto con la periodicidad.
    assert r.status_code == 409
    assert "quincenal" in r.text


def test_el_dia_de_la_visita_sale_de_primera_visita_y_no_del_cobro(client, cliente):
    """🔴 **Visitar y cobrar dejaron de estar atados** (revisión `0030`).

    Antes el día salía del `dia_vencimiento`, que es cuándo se **cobra**. Este
    contrato cobra el 10 y visita el 25 — justo lo que no se podía expresar.
    """
    _contrato(client, cliente, frecuencia_visita="mensual",
              dia_vencimiento=10, primera_visita=f(date(2026, 3, 25)))
    # El ancla es el 15-09, y con arranque el 25 el período vigente **empezó el
    # 25 de agosto** (25-08 al 24-09). El día es el 25, que es lo que importa
    # acá; el mes lo decide en qué período cae el ancla.
    assert _previsualizar(client)["visitas"][0]["fecha_programada"] == "2026-08-25"


def test_la_ficha_devuelve_el_ancla_que_se_guardo(client, cliente):
    """🔴 **El campo no está terminado hasta que un test lo lee como lo lee la
    pantalla.** Un `response_model` que no lo declare lo deja entrar a la base y
    no salir nunca — pasó con `IncidenciaOut` en la revisión `0027` y la suite
    entera quedó en verde igual.
    """
    contrato = _contrato(client, cliente, frecuencia_visita="trimestral",
                         primera_visita=f(date(2026, 2, 10)))

    ficha = client.get(f"/api/contratos/{contrato['id']}").json()
    assert ficha["primera_visita"] == "2026-02-10"
    assert ficha["frecuencia_visita"] == "trimestral", (
        "la ficha muestra las DOS cadencias, y la de visita también tiene que salir"
    )


def test_sin_primera_visita_se_ancla_a_la_fecha_de_inicio(client, cliente):
    """El default, y por qué no cae a los bloques de calendario: el contrato
    siempre tiene `fecha_inicio`, y es lo que mejor aproxima el acuerdo."""
    _contrato(client, cliente, frecuencia_visita="mensual",
              fecha_inicio=f(date(2026, 2, 12)))
    assert _previsualizar(client)["visitas"][0]["fecha_programada"] == "2026-09-12"


def test_un_trimestral_cae_en_los_meses_del_acuerdo(client, cliente):
    """🔴 Lo que la aritmética de calendario hacía imposible.

    Arrancando en **febrero**, un trimestral visita feb/may/ago/nov. Antes caía
    siempre ene/abr/jul/oct sin importar lo que se hubiera pactado con el
    cliente.
    """
    _contrato(client, cliente, frecuencia_visita="trimestral",
              primera_visita=f(date(2026, 2, 10)))

    visita = _previsualizar(client, date(2026, 9, 15))["visitas"][0]
    assert visita["periodo_desde"] == "2026-08-10", "ago-nov, no jul-sep"
    assert visita["fecha_programada"] == "2026-08-10"


def test_un_dia_31_no_revienta_en_un_mes_de_30(client, cliente):
    """Recorta al último del mes, misma regla que la aritmética de períodos.

    El ancla es **octubre** a propósito: así el período vigente arranca en
    septiembre, que tiene 30 días. Con el ancla en un mes de 31 el recorte no se
    ejercita y el test pasaría igual sin él.
    """
    _contrato(client, cliente, frecuencia_visita="mensual",
              primera_visita=f(date(2026, 1, 31)))
    visita = _previsualizar(client, date(2026, 10, 15))["visitas"][0]
    assert visita["fecha_programada"] == "2026-09-30"
