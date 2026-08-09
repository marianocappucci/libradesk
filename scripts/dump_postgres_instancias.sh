#!/usr/bin/env bash
# Dump de las instancias que corren sobre PostgreSQL, en su propio DATA_DIR.
#
# ## Por que existe
#
# `panel_admin.py backup-all` arma un `tar.gz` del directorio `data/` de cada
# cliente y ademas una copia WAL-safe del `.db`. Con la instancia en PostgreSQL
# eso **no falla y no sirve**: el `.db` que empaqueta es el congelado en el
# momento del corte, y los datos de verdad estan en el sidecar. El cliente
# tendria un backup diario, de tamaño normal, sin una sola fila nueva. Es la
# misma forma de fallar que el ZIP de la pantalla de Backup antes de v1.17.0.
#
# El arreglo de fondo es F8 de la migracion: que `panel_admin` sepa de
# PostgreSQL. Mientras tanto, esto: se corre ANTES que `backup-all` y deja un
# `.dump` dentro de `data/`, con lo cual el `tar.gz` que arma el paso siguiente
# ya lo incluye sin tocarle una linea.
#
# Cron sugerido (antes del backup-all de las 03:45):
#   40 3 * * * /root/libradesk/scripts/dump_postgres_instancias.sh >> /var/log/libradesk_pgdump.log 2>&1
set -euo pipefail

RETENCION_DIAS=7
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "=== dump de instancias PostgreSQL ==="
encontradas=0

for dir in /root/libradesk/clientes/*/; do
    slug=$(basename "$dir")
    cont="libradesk-${slug}"
    docker ps --format '{{.Names}}' | grep -qx "$cont" || continue

    url=$(docker exec "$cont" sh -c 'echo "${DATABASE_URL:-}"' 2>/dev/null || echo "")
    if [ -z "$url" ]; then
        log "${slug}: SQLite, lo cubre backup-all"
        continue
    fi

    encontradas=$((encontradas + 1))
    destino="/app/data/postgres-$(date +%Y%m%d_%H%M%S).dump"

    # `pg_dump` corre DENTRO del contenedor de la app: ahi estan el cliente y
    # la URL, y la clave nunca pasa por la linea de comandos del host.
    if docker exec "$cont" sh -c "pg_dump --format=custom --no-owner --no-privileges --file '${destino}' \"\$DATABASE_URL\""; then
        tam=$(docker exec "$cont" sh -c "stat -c %s '${destino}'")
        # Un dump vacio pesa ~1 KB y tiene la misma pinta que uno bueno. Se
        # exige un piso: mas vale un cron en rojo que un backup que miente.
        if [ "$tam" -lt 2000 ]; then
            log "${slug}: 🔴 el dump pesa ${tam} bytes — sospechoso, se conserva pero REVISAR"
        else
            log "${slug}: dump OK (${tam} bytes)"
        fi
    else
        log "${slug}: 🔴 FALLO el pg_dump"
        exit 1
    fi

    # Purga: los dumps viejos se acumulan dentro de data/ y entran a cada tar.
    docker exec "$cont" sh -c \
        "find /app/data -name 'postgres-*.dump' -mtime +${RETENCION_DIAS} -delete"
done

log "=== listo: ${encontradas} instancia(s) sobre PostgreSQL ==="
