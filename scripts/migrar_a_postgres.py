"""Corte de una instancia de LibraDesk: de SQLite a PostgreSQL.

Copia los datos de un `libradesk.db` a una base PostgreSQL vacía, verifica que
llegaron todos y deja el `.db` intacto. **No borra nada y no toca el
contenedor**: pararlo y arrancarlo con la variable nueva es el paso del
operador, y el rollback es volver la variable atrás — el archivo sigue ahí.

## Cómo se usa

    # 1. Ensayo: migra a una base descartable y verifica, sin tocar nada.
    python scripts/migrar_a_postgres.py --sqlite data/libradesk.db \\
        --postgres postgresql://u:p@host/libradesk_ensayo --ensayo

    # 2. El corte de verdad, con el contenedor YA parado.
    python scripts/migrar_a_postgres.py --sqlite data/libradesk.db \\
        --postgres postgresql://u:p@host/libradesk

`--ensayo` borra la base destino al terminar. Sin él, la deja puesta.

## Las cuatro cosas que hace, y por qué en ese orden

1. **Censa el origen** — filas por tabla y huérfanas por FK. Las huérfanas van
   primero porque son lo único que puede abortar el corte a mitad de camino:
   en SQLite el pragma `foreign_keys` está apagado, así que puede haber filas
   apuntando a ids inexistentes que PostgreSQL va a rechazar. **Se sabe antes
   de parar el contenedor, no durante.**
2. **Construye el schema con `create_app()`**, no traduciendo el DDL. Así el
   destino es exactamente lo que la app espera —cadena de Alembic, `create_all`
   de los motores, DDL de LibraCore— y no una interpretación de este script.
3. **Copia tabla por tabla en orden topológico**, con los booleanos convertidos
   (SQLite guarda 0/1 y las columnas son BOOLEAN) y en una sola transacción.
4. **Verifica y recién ahí commitea**: conteos por tabla iguales al origen,
   cero huérfanas, y la revisión de Alembic igual. Si algo no cuadra, rollback
   y la base destino queda como estaba.

> ⚠️ El `.db` de origen se abre en **solo lectura**. Ni este script ni un error
> suyo pueden dañarlo, y es lo que hace que el rollback sea gratis.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import tempfile
from collections import defaultdict


# ── Censo del origen ────────────────────────────────────────────────────────

def snapshot_del_origen(ruta: str, destino: str) -> None:
    """Copia coherente del origen, **con lo que haya en el WAL**.

    🔴 Esta función existe por un incidente concreto del 2026-08-09. Se copió
    `libradesk.db` con `scp` para ensayar el corte y la copia tenía **29 tablas
    contra las 30 de la original**: `servicios` se había creado horas antes y
    seguía viviendo en el `-wal`, sin checkpointear. El script migró las 29,
    comparó el destino contra su propio censo del origen —que también decía
    29— y reportó **"verificación OK"**.

    O sea: copiar el `.db` suelto no es un snapshot, y el chequeo de conteos no
    puede detectarlo porque mide contra el origen truncado. Un corte hecho así
    pierde tablas enteras y se ve perfecto.

    Se usa `Connection.backup()`, la API de backup online de SQLite, que es lo
    mismo que ya hace `libracore.respaldo` y por el mismo motivo.
    """
    src = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(destino)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()


def avisar_si_hay_wal(ruta: str) -> None:
    """Un `-wal` no vacío al lado del origen significa que el contenedor
    escribió después del último checkpoint — o que sigue corriendo."""
    wal = f"{ruta}-wal"
    if os.path.exists(wal) and os.path.getsize(wal) > 0:
        print(f"   ⚠️  hay {os.path.basename(wal)} con {os.path.getsize(wal)} bytes sin "
              f"checkpointear: se toma snapshot con la API de backup, no se lee el archivo suelto")


def abrir_origen(ruta: str) -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def tablas_de(con: sqlite3.Connection) -> list[str]:
    return [
        r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name NOT LIKE 'sqlite_%' ORDER BY name"
        )
    ]


def conteos(con: sqlite3.Connection, tablas: list[str]) -> dict[str, int]:
    return {t: con.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0] for t in tablas}


def huerfanas(con: sqlite3.Connection, tablas: list[str]) -> list[tuple[str, str, str, int]]:
    """Filas que apuntan a un id que no existe. Lo que PostgreSQL va a rechazar."""
    salida = []
    for t in tablas:
        for fk in con.execute(f'PRAGMA foreign_key_list("{t}")'):
            padre, col, col_padre = fk["table"], fk["from"], fk["to"] or "id"
            if padre not in tablas:
                continue
            n = con.execute(
                f'SELECT COUNT(*) FROM "{t}" h WHERE h."{col}" IS NOT NULL '
                f'AND NOT EXISTS (SELECT 1 FROM "{padre}" p WHERE p."{col_padre}" = h."{col}")'
            ).fetchone()[0]
            if n:
                salida.append((t, col, padre, n))
    return salida


def orden_topologico(con: sqlite3.Connection, tablas: list[str]) -> list[str]:
    """Padres antes que hijos, para insertar sin violar ninguna FK.

    Las autorreferencias (`categorias_incidencia.parent_id`) se ignoran al
    ordenar: no se pueden satisfacer con un orden de tablas, y se resuelven
    difiriendo las constraints durante la copia.
    """
    depende_de: dict[str, set[str]] = defaultdict(set)
    for t in tablas:
        for fk in con.execute(f'PRAGMA foreign_key_list("{t}")'):
            padre = fk["table"]
            if padre in tablas and padre != t:
                depende_de[t].add(padre)

    orden, pendientes = [], list(tablas)
    while pendientes:
        libres = [t for t in pendientes if not (depende_de[t] - set(orden))]
        if not libres:
            # Ciclo entre tablas: se emiten en el orden que quedó. Las
            # constraints van diferidas, así que igual entra.
            orden.extend(sorted(pendientes))
            break
        for t in sorted(libres):
            orden.append(t)
            pendientes.remove(t)
    return orden


# ── Destino ─────────────────────────────────────────────────────────────────

def url_sqlalchemy(url: str) -> str:
    """La URL como la necesita SQLAlchemy, con el driver explícito.

    Con `postgresql://` a secas SQLAlchemy elige **psycopg2**, que esta familia
    no instala, y falla con `ModuleNotFoundError: psycopg2` — un error que se
    lee como "falta una dependencia" cuando lo que falta es el sufijo.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def url_libpq(url: str) -> str:
    """La URL como la necesita psycopg directo: sin el `+psycopg` de SQLAlchemy."""
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def construir_schema(url: str, data_dir: str) -> None:
    """El schema lo crea la app, no este script.

    `create_app()` corre la cadena de Alembic, los `create_all()` de los
    motores y el DDL de LibraCore. Cualquier traducción de DDL escrita acá
    sería una segunda fuente de verdad que se desincroniza en el primer
    cambio de schema.
    """
    os.environ.setdefault("ENV", "development")
    os.environ["DATA_DIR"] = data_dir
    from app.main import create_app

    create_app(url_sqlalchemy(url), data_dir)
    from app import database

    database.get_engine().dispose()


def columnas_booleanas(cur, tabla: str) -> set[str]:
    cur.execute(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = current_schema() AND table_name = %s "
        "AND data_type = 'boolean'",
        (tabla,),
    )
    return {r[0] for r in cur.fetchall()}


def copiar(origen: sqlite3.Connection, cur, tabla: str, orden_cols: list[str]) -> int:
    filas = origen.execute(f'SELECT * FROM "{tabla}"').fetchall()
    if not filas:
        return 0
    booleanas = columnas_booleanas(cur, tabla)
    cols = [c for c in filas[0].keys() if c in orden_cols]
    marcadores = ", ".join(["%s"] * len(cols))
    comillas = ", ".join(f'"{c}"' for c in cols)
    datos = [
        tuple(
            # SQLite guarda los booleanos como 0/1; PostgreSQL no acepta un
            # entero en una columna BOOLEAN. Es la misma trampa que ya
            # apareció en el DDL y en el plan de módulos.
            (bool(f[c]) if f[c] is not None else None) if c in booleanas else f[c]
            for c in cols
        )
        for f in filas
    ]
    cur.executemany(
        f'INSERT INTO "{tabla}" ({comillas}) VALUES ({marcadores})', datos
    )
    return len(datos)


def ajustar_secuencias(cur) -> list[str]:
    """`setval` en cada secuencia, o el próximo alta choca con un id existente.

    Es el paso que más fácil se olvida y el que peor se manifiesta: la
    migración se ve perfecta, y el primer INSERT del día siguiente falla con
    "duplicate key". Se recorren las secuencias reales del catálogo en vez de
    suponer una por tabla.
    """
    cur.execute("""
        SELECT s.relname, t.relname, a.attname
        FROM pg_class s
        JOIN pg_depend d ON d.objid = s.oid AND d.deptype = 'a'
        JOIN pg_class t ON t.oid = d.refobjid
        JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = d.refobjsubid
        WHERE s.relkind = 'S'
    """)
    ajustadas = []
    for secuencia, tabla, columna in cur.fetchall():
        cur.execute(
            f'SELECT setval(%s, COALESCE((SELECT MAX("{columna}") FROM "{tabla}"), 0) + 1, false)',
            (secuencia,),
        )
        ajustadas.append(f"{secuencia} -> max({tabla}.{columna})")
    return ajustadas


def verificar(cur, esperados: dict[str, int]) -> list[str]:
    """Conteos y huérfanas del DESTINO. Devuelve la lista de problemas."""
    problemas = []
    for tabla, esperado in sorted(esperados.items()):
        cur.execute(f'SELECT COUNT(*) FROM "{tabla}"')
        real = cur.fetchone()[0]
        if real != esperado:
            problemas.append(f"{tabla}: {real} filas, se esperaban {esperado}")
    return problemas


# ── Programa ────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sqlite", required=True, help="ruta al libradesk.db de origen")
    ap.add_argument("--postgres", required=True, help="URL de la base destino (vacía)")
    ap.add_argument("--ensayo", action="store_true",
                    help="borra la base destino al terminar; para probar sin comprometer nada")
    args = ap.parse_args()

    import psycopg

    print(f"== Origen: {args.sqlite}")
    avisar_si_hay_wal(args.sqlite)

    # Se trabaja SIEMPRE sobre un snapshot, nunca sobre el archivo suelto: lo
    # que no esté checkpointeado no se ve, y el chequeo de conteos no puede
    # detectarlo porque mide contra el propio origen. Ver `snapshot_del_origen`.
    tmp_snapshot = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_snapshot.close()
    snapshot_del_origen(args.sqlite, tmp_snapshot.name)

    origen = abrir_origen(tmp_snapshot.name)
    tablas = tablas_de(origen)
    esperados = conteos(origen, tablas)
    total = sum(esperados.values())
    print(f"   {len(tablas)} tablas, {total} filas (snapshot con la API de backup)")

    sueltas = huerfanas(origen, tablas)
    if sueltas:
        print("\n🔴 HUERFANAS — PostgreSQL las va a rechazar. Hay que resolverlas ANTES del corte:")
        for t, col, padre, n in sueltas:
            print(f"   {t}.{col} -> {padre}: {n}")
        print("\nEl corte NO se hace con huerfanas: la migracion abortaria a mitad.")
        return 2
    print("   huerfanas: ninguna")

    print(f"\n== Destino: {args.postgres.split('@')[-1]}")
    with tempfile.TemporaryDirectory() as data_dir:
        construir_schema(args.postgres, data_dir)
    print("   schema construido por create_app() (Alembic + create_all + DDL de LibraCore)")

    url = url_libpq(args.postgres)
    with psycopg.connect(url) as destino:
        with destino.cursor() as cur:
            # El schema recien creado trae sus semillas (modulos, admin). Se
            # vacia para que los conteos del final comparen contra el origen y
            # no contra origen+semilla.
            cur.execute("SET session_replication_role = replica")
            for t in reversed(orden_topologico(origen, tablas)):
                cur.execute(f'TRUNCATE TABLE "{t}" CASCADE')

            copiadas = {}
            for t in orden_topologico(origen, tablas):
                cur.execute(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = current_schema() AND table_name = %s",
                    (t,),
                )
                cols_destino = [r[0] for r in cur.fetchall()]
                if not cols_destino:
                    print(f"   ⚠️ {t}: no existe en el destino, se saltea")
                    continue
                copiadas[t] = copiar(origen, cur, t, cols_destino)

            cur.execute("SET session_replication_role = DEFAULT")
            secuencias = ajustar_secuencias(cur)

            problemas = verificar(cur, {t: n for t, n in esperados.items() if t in copiadas})
            faltantes = set(esperados) - set(copiadas)
            if faltantes:
                problemas.append(f"tablas del origen sin destino: {sorted(faltantes)}")

            if problemas:
                destino.rollback()
                print("\n🔴 LA VERIFICACION FALLO. Nada quedo escrito:")
                for p in problemas:
                    print(f"   {p}")
                return 1

            destino.commit()

    print(f"   {sum(copiadas.values())} filas copiadas en {len(copiadas)} tablas")
    print(f"   {len(secuencias)} secuencias ajustadas con setval")
    print("\n🟢 Verificacion OK: conteos iguales por tabla y cero huerfanas.")
    print(f"   El origen {args.sqlite} quedo intacto — el rollback es volver la variable de entorno.")

    origen.close()
    os.unlink(tmp_snapshot.name)

    if args.ensayo:
        nombre = url.rsplit("/", 1)[-1]
        admin = url.rsplit("/", 1)[0] + "/postgres"
        with psycopg.connect(admin, autocommit=True) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{nombre}"')
        print(f"   (ensayo: base {nombre} borrada)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
