"""El espejo de `parties` aguanta dos procesos sincronizando a la vez.

Lo vio `libradesk-demo` el 2026-10-21: los dos workers de uvicorn corren
`sincronizar_parties()` en el arranque, los dos ven al mismo cliente sin
`party` (el anti-join no ve lo que el otro todavía no commiteó) y el segundo
muere con `UniqueViolation` en `parties_pkey`. Uvicorn lo relanzaba y el
contenedor quedaba sano, pero el arranque tiraba un traceback por instancia.

La carrera se arma sin depender del reloj: una conexión inserta el `party` y
NO commitea; la sincronización de otro hilo queda bloqueada en el índice
único (se espera a verla en `pg_stat_activity`), y recién ahí se commitea la
primera.
"""
import threading
import time


def test_dos_sincronizaciones_a_la_vez_no_chocan(client):
    from libracore.db.core import get_connection

    from app.services import comercial

    r = client.post("/auth/login", json={"username": "admin", "password": "admin"})
    assert r.status_code == 200, r.text
    cid = client.post("/api/clientes", json={"nombre": "Carrera SA"}).json()["id"]
    # El alta ya deja el espejo; se borra para que vuelva a faltar, como en
    # una instancia con clientes de antes del espejo.
    with get_connection() as conn:
        conn.execute("DELETE FROM parties WHERE id = ?", (cid,))

    errores: list[BaseException] = []

    def sincronizar():
        try:
            comercial.sincronizar_parties()
        except BaseException as e:  # noqa: BLE001 - se reporta en el assert
            errores.append(e)

    otro = threading.Thread(target=sincronizar)
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO parties (id, party_type, display_name, legal_name, tax_id,"
            " email, phone, active) VALUES (?, 'person', 'Carrera SA', 'Carrera SA',"
            " '', '', '', 1)",
            (cid,),
        )
        otro.start()
        limite = time.monotonic() + 10
        while True:
            with get_connection() as mirador:
                bloqueados = mirador.execute(
                    "SELECT count(*) AS n FROM pg_stat_activity"
                    " WHERE datname = current_database() AND wait_event_type = 'Lock'"
                ).fetchone()["n"]
            if bloqueados or not otro.is_alive() or time.monotonic() > limite:
                break
            time.sleep(0.05)
        assert bloqueados, "la sincronización del otro hilo no llegó a esperar el índice"
    otro.join(timeout=10)

    assert not errores, errores
    with get_connection() as conn:
        n = conn.execute("SELECT count(*) AS n FROM parties WHERE id = ?", (cid,)).fetchone()["n"]
    assert n == 1
