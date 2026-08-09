#!/usr/bin/env bash
# Reset diario de la demo publica de Libradesk — item 8 de los pendientes de
# Libra.
#
# Borra la base, deja que el arranque reconstruya el esquema y vuelve a
# sembrar. **El estado limpio es codigo, no un backup guardado a mano**: eso es
# lo que hace que sea reproducible, y que agregar un dato de ejemplo sea un
# commit y no una operacion manual sobre el servidor.
#
# Corre por cron a las 04:45, despues del dump de PostgreSQL de las 03:40 y del
# `backup-all` de las 03:45 — no se pisan, y si un backup tarda de mas el reset
# no lo interrumpe.
#
# 🔴 **Solo toca la instancia demo.** El contenedor esta escrito aca, no
# viene por argumento: un reset apuntado al contenedor equivocado le borra la
# base a un cliente, y no hay confirmacion que valga a las cuatro de la manana.
set -euo pipefail

CONTENEDOR="libradesk-demo"
# El checkout del que sale el seed. Overridable para poder probarlo fuera del
# VPS sin editar el script.
REPO="${LIBRADESK_REPO:-/root/libradesk}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

# --- La guarda ------------------------------------------------------------
# Si el nombre no es el de una demo, no se sigue. Es barato, y es lo unico que
# separa "resetear la demo" de "borrarle la base a un cliente".
case "$CONTENEDOR" in
  *-demo|*-publica) ;;
  *) log "ABORTA: '$CONTENEDOR' no parece una instancia demo."; exit 2 ;;
esac

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTENEDOR"; then
  log "ABORTA: el contenedor $CONTENEDOR no esta corriendo."
  exit 3
fi

# 🔴 La guarda del nombre NO alcanza, y esto no es teorico: hasta el 2026-08-07
# el contenedor llamado `restolibra-demo` era el que servia
# sistema.restolibra.com.ar. El nombre decia demo y no lo era. Por eso se
# verifica una propiedad real de la instancia -- DEMO_MODE, lo unico que
# enciende el auto-login publico -- y no como se llama.
if ! docker exec "$CONTENEDOR" printenv DEMO_MODE 2>/dev/null | grep -qx 1; then
  log "ABORTA: $CONTENEDOR no tiene DEMO_MODE=1. El nombre no alcanza."
  exit 4
fi

log "=== reset de $CONTENEDOR ==="

# --- 0. El seed, ANTES de tocar la base -----------------------------------
# 🔴 El 2026-08-06 este script borro la base y recien despues descubrio que no
# podia sembrar: `scripts/seed_demo.py` vive en `develop` y el checkout del VPS
# estaba en `main`. Cinco demos quedaron vacias, y el cron lo habria repetido
# todas las noches. El orden correcto es conseguir el insumo primero: si no
# esta, no se borra nada.
#
# Sale de `origin/develop` y no del arbol de trabajo, que es de donde sale la
# imagen que corre la demo — y asi da igual en que rama quede el checkout.
SEED_DEMO=/tmp/seed-libradesk-demo.py
SEED_DEV=/tmp/seed-libradesk-dev.py
git -C "$REPO" fetch -q origin || { log "ABORTA: no se pudo hacer fetch de $REPO."; exit 5; }
git -C "$REPO" show origin/develop:scripts/seed_demo.py > "$SEED_DEMO" \
  || { log "ABORTA: no esta scripts/seed_demo.py en origin/develop."; exit 6; }
git -C "$REPO" show origin/develop:scripts/seed_dev.py > "$SEED_DEV" \
  || { log "ABORTA: no esta scripts/seed_dev.py en origin/develop."; exit 7; }
# Un `git show` de un archivo vacio tambien sale con codigo 0.
[ -s "$SEED_DEMO" ] && [ -s "$SEED_DEV" ] \
  || { log "ABORTA: algun seed salio vacio."; exit 8; }
log "seed listo desde origin/develop ($(wc -l < "$SEED_DEMO") lineas)"

# --- 1. Base de cero ------------------------------------------------------
#
# 🔴 Desde el corte a PostgreSQL del 2026-08-09 la demo NO guarda sus datos en
# un archivo. Si esto siguiera haciendo solo `rm *.db`, el reset **no
# resetearia nada** y no fallaria: borraria un archivo que la app ya no lee, el
# seed agregaria ejemplos ENCIMA de los del dia anterior, y la demo iria
# acumulando basura sin que nada avise. Por eso se decide segun el backend real
# de la instancia, leido de su entorno, y no por una constante de este script.
URL_BASE=$(docker exec "$CONTENEDOR" sh -c 'echo "${DATABASE_URL:-}"')

if [ -n "$URL_BASE" ]; then
  log "backend PostgreSQL detectado"
  # Se vacia el SCHEMA, no la base: borrar la base pide desconectar a todos y
  # el contenedor de la app esta conectado. El arranque la reconstruye entera
  # -- `create_app()` corre Alembic y los create_all -- que es exactamente el
  # mismo camino que ya se usaba con SQLite.
  docker exec "$CONTENEDOR" sh -c '
    python3 - <<PY
import os, psycopg
url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1)
with psycopg.connect(url, autocommit=True) as c:
    c.execute("DROP SCHEMA public CASCADE")
    c.execute("CREATE SCHEMA public")
print("schema public recreado")
PY
  '
  log "base PostgreSQL vaciada"
else
  # Se borran tambien los `-wal` y `-shm`: sin eso SQLite puede reconstruir
  # parte de lo borrado desde el journal, y el reset queda a medias.
  docker exec "$CONTENEDOR" sh -c 'rm -f /app/data/*.db /app/data/*.db-wal /app/data/*.db-shm'
  log "base SQLite borrada"
fi

docker restart "$CONTENEDOR" >/dev/null
for _ in $(seq 1 40); do
  estado=$(docker inspect -f '{{.State.Health.Status}}' "$CONTENEDOR" 2>/dev/null || echo starting)
  [ "$estado" = "healthy" ] && break
  sleep 3
done
estado=$(docker inspect -f '{{.State.Health.Status}}' "$CONTENEDOR" 2>/dev/null || echo desconocido)
log "contenedor: $estado"
if [ "$estado" != "healthy" ]; then
  log "ABORTA: no levanto sano; no se siembra sobre una instancia rota."
  exit 9
fi

# --- 2. Sembrar -----------------------------------------------------------
# Por la API y desde adentro del contenedor: la contrasena sale de su propio
# entorno y nunca pasa por la linea de comandos del host, donde quedaria en el
# `ps` y en el log del cron.
# ⚠️ Se copian los DOS archivos, y con su nombre real. `seed_demo.py` importa
# `seed_dev` para no duplicar los datos de ejemplo en dos lugares que se van a
# desincronizar; con un solo archivo adentro del contenedor —y peor, renombrado
# a `seed.py`— la importacion muere con `ModuleNotFoundError`.
docker exec "$CONTENEDOR" mkdir -p /tmp/seed
docker cp "$SEED_DEMO" "$CONTENEDOR:/tmp/seed/seed_demo.py"
docker cp "$SEED_DEV" "$CONTENEDOR:/tmp/seed/seed_dev.py"
docker exec -i "$CONTENEDOR" sh -c '
  python3 /tmp/seed/seed_demo.py \
    --url https://demo.libradesk.com.ar \
    --usuario "${LIBRADESK_ADMIN_USERNAME:-admin}" \
    --password "$LIBRADESK_ADMIN_PASSWORD"
'
docker exec "$CONTENEDOR" rm -rf /tmp/seed

log "=== listo ==="
