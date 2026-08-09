"""El dashboard operativo — pedido del 2026-08-05.

> *"Mejorar el dashboard de LibraDesk, está muy incompleto, podría tener mucha
> más información y de mejor manera."*

Se decidió con el humano que el dashboard es **operativo**: contesta *qué hay
que hacer hoy*, no *cómo viene el mes*. Lo que había eran cuatro tarjetas con
seis totales absolutos que no cambiaban de un día para el otro.

Lo que fijan estos tests, en orden de lo que se rompe sin que se note:

1. 🔴 **Que el horizonte se aplique a los TRES vencimientos.** El defecto de la
   pantalla vieja era exactamente ése: el filtro movía un solo número de seis y
   nada lo decía. Si el horizonte volviera a tocar uno solo, la pantalla se
   vería igual de rota y el usuario tampoco tendría cómo enterarse.
2. 🔴 **Que lo ya vencido siga apareciendo.** Un contrato vigente cuya fecha de
   fin pasó es lo más urgente que hay; si el filtro fuera `entre hoy y el
   límite` desaparecería justo lo que hay que atender.
3. 🔴 **Que el `total` de cada bloque sea el real y no el de los ítems
   mostrados.** El bloque lista 5 como mucho: si el total se calculara sobre la
   lista recortada, «5 contratos por vencer» sería mentira cuando hay 40.
4. Que el backlog cuente por antigüedad y no por estado.
5. Que lo cerrado y lo dado de baja no ensucien ningún bloque.
"""
from datetime import date, datetime, timedelta

import pytest


@pytest.fixture
def client(client):
    """El `client` de conftest.py, ya logueado."""
    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    return client


HOY = date.today()


def _cliente(client, nombre="Compulibra"):
    r = client.post("/api/clientes", json={"nombre": nombre})
    assert r.status_code == 201, r.text
    return r.json()


def _equipo(client, cliente_id, garantia=None, estado=None):
    """Crea un equipo. `estado="baja"` lo da de baja **cambiándole el estado**,
    que es lo que hace la pantalla.

    ⚠️ No con `DELETE /api/equipos/{id}`: eso borra la fila, y entonces el
    equipo no aparece en ningún lado por no existir, no por estar de baja. La
    primera versión de este helper usaba el DELETE y hacía que el test del
    filtro pasara con el filtro sacado. Lo delató el arnés.
    """
    datos = {"cliente_id": cliente_id, "tipo": "Notebook", "marca": "Dell"}
    if garantia:
        datos["garantia_vence"] = garantia.isoformat()
    r = client.post("/api/equipos", json=datos)
    assert r.status_code == 201, r.text
    equipo = r.json()
    if estado:
        r = client.put(f"/api/equipos/{equipo['id']}", json={**equipo, "estado": estado})
        assert r.status_code == 200, r.text
        equipo = r.json()
    return equipo


def _incidencia(client, cliente_id, titulo="Falla", **extra):
    r = client.post("/api/incidencias", json={
        "cliente_id": cliente_id, "titulo": titulo, **extra,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _cerrar(client, incidencia, **extra):
    """El PUT de incidencias es un reemplazo completo, no un patch: mandar sólo
    `{"estado": "cerrado"}` da 422 por los campos obligatorios que faltan."""
    datos = {**incidencia, "estado": "cerrado", **extra}
    r = client.put(f"/api/incidencias/{incidencia['id']}", json=datos)
    assert r.status_code == 200, r.text
    return r.json()


def _operativo(client, dias=30):
    r = client.get(f"/api/dashboard/operativo?dias={dias}")
    assert r.status_code == 200, r.text
    return r.json()


def _envejecer(client, incidencia_id, dias):
    """Retrasa `fecha_creacion` en la base.

    No hay forma de crear una incidencia con fecha pasada por la API —y está
    bien que no la haya—, así que el envejecimiento se hace en la tabla. Es lo
    único que estos tests tocan por fuera del contrato HTTP.

    Va por el engine de la app y no por `sqlite3.connect(ruta)`: la suite
    también corre contra PostgreSQL (ver `tests/conftest.py`), donde no hay
    archivo que abrir. Con `sqlite3` directo, estos tres tests fallaban con
    *"no such table: incidencias"* — el archivo existía en el DATA_DIR pero
    vacío, porque los datos estaban en PostgreSQL.
    """
    from sqlalchemy import text

    from app import database

    with database.get_engine().begin() as conn:
        conn.execute(
            text("UPDATE incidencias SET fecha_creacion = :fecha WHERE id = :id"),
            {
                "fecha": (datetime.now() - timedelta(days=dias)).isoformat(sep=" "),
                "id": incidencia_id,
            },
        )


# ── El horizonte ──────────────────────────────────────────────────────────

def test_una_instancia_vacia_devuelve_todos_los_bloques_en_cero(client):
    """Los bloques **no** desaparecen cuando no hay nada: una tarjeta ausente
    deja sin saber si es que no hay vencimientos o si se rompió."""
    d = _operativo(client)

    assert d["vencimientos"]["contratos"]["total"] == 0
    assert d["vencimientos"]["garantias"]["total"] == 0
    assert d["vencimientos"]["agenda"]["total"] == 0
    assert d["taller"]["total"] == 0
    assert d["backlog"]["total_abiertas"] == 0
    assert d["sin_asignar"] == 0


def test_el_horizonte_recorta_las_garantias(client):
    c = _cliente(client)
    _equipo(client, c["id"], garantia=HOY + timedelta(days=10))
    _equipo(client, c["id"], garantia=HOY + timedelta(days=60))

    assert _operativo(client, dias=30)["vencimientos"]["garantias"]["total"] == 1
    assert _operativo(client, dias=90)["vencimientos"]["garantias"]["total"] == 2


def test_el_horizonte_recorta_los_turnos_agendados(client):
    """🔴 El mismo horizonte tiene que aplicar a los tres bloques. El defecto de
    la pantalla vieja era que el filtro movía un solo número."""
    c = _cliente(client)
    _incidencia(client, c["id"], "Cerca",
                fecha_programada=(datetime.now() + timedelta(days=5)).isoformat())
    _incidencia(client, c["id"], "Lejos",
                fecha_programada=(datetime.now() + timedelta(days=60)).isoformat())

    assert _operativo(client, dias=30)["vencimientos"]["agenda"]["total"] == 1
    assert _operativo(client, dias=90)["vencimientos"]["agenda"]["total"] == 2


def test_una_garantia_ya_vencida_sigue_apareciendo(client):
    """🔴 Es lo más urgente que hay. Con un filtro `entre hoy y el límite`
    desaparecería justo lo que hay que atender."""
    c = _cliente(client)
    _equipo(client, c["id"], garantia=HOY - timedelta(days=15))

    bloque = _operativo(client)["vencimientos"]["garantias"]
    assert bloque["total"] == 1
    assert bloque["items"][0]["dias_restantes"] == -15


def test_una_garantia_vencida_hace_mucho_no_entierra_a_las_proximas(client):
    """🔴 Encontrado con los datos reales de dev, no por los tests: el bloque
    traía 22 garantías y **16 habían vencido hace meses** (hasta 283 días),
    dejando fuera de los 5 visibles a las 3 que estaban por vencer — las únicas
    sobre las que se puede hacer algo.

    Una garantía vencida no es una anomalía: el equipo ya no está cubierto y no
    hay nada que hacer. La ventana hacia atrás es del tamaño del horizonte,
    porque una vencida **hace poco** sí importa — el cliente puede llegar
    creyendo que sigue cubierto.
    """
    c = _cliente(client)
    _equipo(client, c["id"], garantia=HOY - timedelta(days=200))
    _equipo(client, c["id"], garantia=HOY - timedelta(days=10))
    _equipo(client, c["id"], garantia=HOY + timedelta(days=10))

    bloque = _operativo(client, dias=30)["vencimientos"]["garantias"]
    assert bloque["total"] == 2
    assert [g["dias_restantes"] for g in bloque["items"]] == [-10, 10]


def test_un_contrato_vencido_hace_mucho_SI_aparece(client):
    """La contracara: un contrato **vigente** con la fecha de fin pasada es una
    anomalía, y da igual cuánto hace. No lleva piso."""
    c = _cliente(client)
    _contrato(client, c["id"], HOY - timedelta(days=200))

    bloque = _operativo(client, dias=30)["vencimientos"]["contratos"]
    assert bloque["total"] == 1
    assert bloque["items"][0]["dias_restantes"] == -200


def test_el_horizonte_tiene_tope(client):
    """Sin tope, un `dias` grande lista todo el sistema y el bloque deja de ser
    "lo que se vence" para volverse el listado completo."""
    assert client.get("/api/dashboard/operativo?dias=100000").status_code == 422
    assert client.get("/api/dashboard/operativo?dias=0").status_code == 422


# ── Lo que no tiene que aparecer ──────────────────────────────────────────

def test_la_garantia_de_un_equipo_dado_de_baja_no_cuenta(client):
    """Mismo criterio que la ficha del cliente: a nadie le importa la garantía
    de un equipo que ya no está.

    El equipo se da de baja **cambiándole el estado**, no borrándolo: si se
    borrara, no aparecería por no existir y el test pasaría con el filtro
    sacado."""
    c = _cliente(client)
    _equipo(client, c["id"], garantia=HOY + timedelta(days=5), estado="baja")
    # Uno vigente, para que el bloque tenga algo que devolver si el filtro
    # dejara de aplicar y la diferencia no sea "cero contra cero".
    _equipo(client, c["id"], garantia=HOY + timedelta(days=6))

    bloque = _operativo(client)["vencimientos"]["garantias"]
    assert bloque["total"] == 1
    assert bloque["items"][0]["dias_restantes"] == 6


def test_un_turno_de_una_incidencia_cerrada_no_cuenta(client):
    c = _cliente(client)
    i = _incidencia(client, c["id"], "Ya resuelta",
                    fecha_programada=(datetime.now() + timedelta(days=3)).isoformat())
    _cerrar(client, i)

    assert _operativo(client)["vencimientos"]["agenda"]["total"] == 0


# ── Contratos y taller ────────────────────────────────────────────────────
#
# Los dos bloques que no se ejercitan con la instancia vacía: sin estos casos,
# las consultas de contratos e ingresos nunca corren con datos y un error en
# ellas se vería sólo en producción.

def _contrato(client, cliente_id, fecha_fin, estado="activo"):
    r = client.post("/api/contratos", json={
        "tipo_contrato": "alquiler",
        "cliente_id": cliente_id,
        "fecha_inicio": (HOY - timedelta(days=365)).isoformat(),
        "fecha_fin": fecha_fin.isoformat(),
        "estado": estado,
        "importe": 100000,
    })
    assert r.status_code == 201, r.text
    return r.json()


def _ingreso(client, cliente_id, equipo_tipo="Notebook"):
    r = client.post("/api/ingresos-reparacion", json={
        "cliente_id": cliente_id, "equipo_tipo": equipo_tipo,
        "equipo_marca": "Dell", "falla_declarada": "No enciende",
    })
    assert r.status_code == 201, r.text
    return r.json()


def test_un_contrato_por_vencer_aparece_con_sus_dias(client):
    c = _cliente(client)
    _contrato(client, c["id"], HOY + timedelta(days=12))

    bloque = _operativo(client)["vencimientos"]["contratos"]
    assert bloque["total"] == 1
    assert bloque["items"][0]["dias_restantes"] == 12
    assert bloque["items"][0]["cliente"] == "Compulibra"


def test_un_contrato_en_borrador_no_cuenta_como_por_vencer(client):
    """Sólo los vigentes: un borrador todavía no rige, y listarlo entre lo que
    hay que atender es ruido."""
    c = _cliente(client)
    _contrato(client, c["id"], HOY + timedelta(days=5), estado="borrador")

    assert _operativo(client)["vencimientos"]["contratos"]["total"] == 0


def test_un_contrato_finalizado_no_cuenta(client):
    """Ya terminó: listarlo como "por vencer" sería ruido permanente."""
    c = _cliente(client)
    _contrato(client, c["id"], HOY + timedelta(days=5), estado="finalizado")

    assert _operativo(client)["vencimientos"]["contratos"]["total"] == 0


def test_un_contrato_sin_fecha_de_fin_no_cuenta(client):
    """`fecha_fin` es nullable: un contrato sin vencimiento no vence."""
    c = _cliente(client)
    r = client.post("/api/contratos", json={
        "tipo_contrato": "alquiler", "cliente_id": c["id"],
        "fecha_inicio": HOY.isoformat(), "estado": "activo", "importe": 1000,
    })
    assert r.status_code == 201, r.text

    assert _operativo(client)["vencimientos"]["contratos"]["total"] == 0


def test_el_horizonte_recorta_los_contratos(client):
    c = _cliente(client)
    _contrato(client, c["id"], HOY + timedelta(days=10))
    _contrato(client, c["id"], HOY + timedelta(days=60))

    assert _operativo(client, dias=30)["vencimientos"]["contratos"]["total"] == 1
    assert _operativo(client, dias=90)["vencimientos"]["contratos"]["total"] == 2


def test_un_equipo_recibido_y_no_entregado_esta_en_el_taller(client):
    c = _cliente(client)
    _ingreso(client, c["id"])

    bloque = _operativo(client)["taller"]
    assert bloque["total"] == 1
    assert "Notebook" in bloque["items"][0]["equipo"]
    assert bloque["items"][0]["dias"] == 0


def test_un_equipo_ya_entregado_sale_del_taller(client):
    """🔴 Es lo único que distingue "está en el taller" de "pasó por el taller".
    Sin el filtro por `fecha_entrega`, el bloque crecería para siempre."""
    c = _cliente(client)
    g = _ingreso(client, c["id"])
    r = client.post(f"/api/ingresos-reparacion/{g['id']}/entregar", json={
        "retirado_por": "El cliente", "trabajo_realizado": "Cambio de fuente",
    })
    assert r.status_code == 200, r.text

    assert _operativo(client)["taller"]["total"] == 0


# ── El backlog ────────────────────────────────────────────────────────────

def test_el_backlog_cuenta_por_antiguedad_y_no_por_estado(client):
    """🔴 Es la pregunta que un sistema de tickets tiene que contestar, y la que
    el desglose por estado no contestaba: cuántas están esperando hace un mes."""
    c = _cliente(client)
    reciente = _incidencia(client, c["id"], "De esta semana")
    media = _incidencia(client, c["id"], "De hace tres semanas")
    vieja = _incidencia(client, c["id"], "De hace dos meses")
    _envejecer(client, media["id"], 20)
    _envejecer(client, vieja["id"], 60)

    backlog = _operativo(client)["backlog"]
    assert backlog["total_abiertas"] == 3
    assert backlog["por_antiguedad"] == {
        "hasta_7_dias": 1, "de_8_a_30_dias": 1, "mas_de_30_dias": 1,
    }
    assert reciente["id"] in {i["id"] for i in backlog["mas_viejas"]}


def test_las_mas_viejas_vienen_primero(client):
    c = _cliente(client)
    nueva = _incidencia(client, c["id"], "Nueva")
    vieja = _incidencia(client, c["id"], "Vieja")
    _envejecer(client, vieja["id"], 45)

    mas_viejas = _operativo(client)["backlog"]["mas_viejas"]
    assert [i["id"] for i in mas_viejas] == [vieja["id"], nueva["id"]]
    assert mas_viejas[0]["dias"] == 45


def test_una_incidencia_cerrada_sale_del_backlog(client):
    c = _cliente(client)
    i = _incidencia(client, c["id"])
    assert _operativo(client)["backlog"]["total_abiertas"] == 1

    _cerrar(client, i)
    assert _operativo(client)["backlog"]["total_abiertas"] == 0


def test_cuenta_las_abiertas_sin_tecnico(client):
    """🔴 Con una sola incidencia el test no distingue nada: el total de
    abiertas también sería 1. Hace falta **una asignada** para que el número
    pueda estar mal."""
    c = _cliente(client)
    r = client.post("/api/tecnicos", json={"nombre": "Ana"})
    assert r.status_code == 201, r.text
    tecnico = r.json()

    _incidencia(client, c["id"], "Sin nadie")
    _incidencia(client, c["id"], "Con Ana", tecnico_id=tecnico["id"])

    d = _operativo(client)
    assert d["backlog"]["total_abiertas"] == 2
    assert d["sin_asignar"] == 1


# ── El tope de la lista ───────────────────────────────────────────────────

def test_el_total_es_el_real_y_no_el_de_los_items_mostrados(client):
    """🔴 El bloque lista 5 como mucho. Si el total se calculara sobre la lista
    recortada, «5 garantías por vencer» sería mentira cuando hay 8 — y el
    usuario no tendría por qué desconfiar del número."""
    c = _cliente(client)
    for n in range(8):
        _equipo(client, c["id"], garantia=HOY + timedelta(days=n + 1))

    bloque = _operativo(client)["vencimientos"]["garantias"]
    assert bloque["total"] == 8
    assert len(bloque["items"]) == 5


def test_los_items_mostrados_son_los_mas_proximos(client):
    """Recortar sin ordenar mostraría cinco cualesquiera."""
    c = _cliente(client)
    for n in (30, 1, 25, 2, 20, 3, 15):
        _equipo(client, c["id"], garantia=HOY + timedelta(days=n))

    items = _operativo(client)["vencimientos"]["garantias"]["items"]
    assert [i["dias_restantes"] for i in items] == [1, 2, 3, 15, 20]


# ── Los defectos de `summary()` que este pedido arregla ───────────────────

def test_el_resumen_declara_que_numeros_responden_al_rango(client):
    """🔴 Antes el filtro movía un solo número de seis y la pantalla no lo
    decía: el usuario cambiaba las fechas, veía que casi nada se movía y no
    tenía cómo saber cuáles lo miraban. Se lee peor que no tener filtro."""
    r = client.get("/api/dashboard")
    assert r.status_code == 200, r.text
    d = r.json()

    assert set(d["responden_al_rango"]) == {"incidencias_en_rango", "horas_en_rango"}
    for clave in d["responden_al_rango"]:
        assert clave in d


def test_las_horas_del_rango_son_del_rango_y_no_de_siempre(client):
    """Antes `horas_totales_invertidas` era el histórico y colgaba del subtítulo
    de «Equipos», que no tiene nada que ver con las horas."""
    c = _cliente(client)
    i = _incidencia(client, c["id"])
    r = client.put(f"/api/incidencias/{i['id']}", json={**i, "horas_invertidas": 4})
    assert r.status_code == 200, r.text
    _envejecer(client, i["id"], 200)

    d = client.get(
        f"/api/dashboard?date_from={HOY.isoformat()}&date_to={HOY.isoformat()}"
    ).json()
    assert d["horas_en_rango"] == 0.0
    assert d["horas_totales_invertidas"] == 4.0
