#!/usr/bin/env bash
# Tests de `servicios_de_la_app()` de scripts/deploy_cliente.sh.
#
# El defecto que fijan (2026-08-13): la seleccion descartaba el sidecar de
# PostgreSQL por el sufijo `-db` del nombre del servicio. Esa es la convencion
# de las instancias hechas a mano (`demo`, `compulibra`), pero NO la del
# generador del backoffice: `lagrace` nombro su sidecar
# `libradesk-lagrace-postgres`. Con eso pasaban los DOS servicios, se tomaba el
# primero, y el repin apuntaba a la BASE. Lo freno la guarda posterior --que
# exige que la linea diga `libradesk:`--, pero una guarda que salta en el uso
# normal es un criterio de seleccion equivocado, no una guarda que ande bien.
#
# 🔴 El caso que importa es el TERCERO: sidecar llamado `-postgres`. Los otros
# dos pasaban tambien con el criterio viejo, asi que solos no probarian nada.
#
# Mismo patron que test_poda_tags_deploy.sh: el script no se puede sourcear
# entero (corre el deploy al importarse), asi que se extrae la funcion.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$DIR/scripts/deploy_cliente.sh"
FUENTE="$(mktemp)"
sed -n '/^servicios_de_la_app() {$/,/^}$/p' "$SCRIPT" > "$FUENTE"
[ -s "$FUENTE" ] || { echo "FALLO: no se pudo extraer servicios_de_la_app()"; exit 1; }

fallos=0
ok()    { echo "  ok    $1"; }
falla() { echo "  FALLA $1"; echo "        $2"; fallos=$((fallos + 1)); }

# ── doble de docker ───────────────────────────────────────────────────────────
# Contesta las DOS formas de preguntar por los servicios, las dos derivadas del
# mismo $JSON:
#
#   config --format json  -> el JSON tal cual (lo que usa el criterio vigente)
#   config --services     -> un nombre por linea (lo que usaba el criterio viejo)
#
# La segunda no la necesita el codigo de hoy: esta para que el control en rojo
# sea JUSTO. Si el doble sólo supiera contestar JSON, instalar el criterio viejo
# lo haria fallar por no entender la respuesta, y el rojo no diria nada sobre el
# sufijo '-db' --que es lo unico que este archivo tiene que probar.
docker() {
  if [ "${1:-}" = "compose" ]; then
    case "$*" in
      *"--format json"*)
        printf '%s' "$JSON" ;;
      *"--services"*)
        printf '%s' "$JSON" | python3 -c '
import json, sys
try:
    print("\n".join(json.load(sys.stdin).get("services", {})))
except ValueError:
    sys.exit(1)
' ;;
      *) echo "docker compose inesperado: $*" >&2; return 1 ;;
    esac
    return 0
  fi
  echo "docker inesperado: $*" >&2
  return 1
}
export -f docker 2>/dev/null || true

# shellcheck source=/dev/null
. "$FUENTE"

probar() {  # nombre, json, esperado (nombres separados por espacio)
  local nombre="$1" esperado="$3"
  JSON="$2"
  local obtenido
  obtenido="$(servicios_de_la_app /compose/irrelevante.yml | tr '\n' ' ' | sed 's/ *$//')"
  if [ "$obtenido" = "$esperado" ]; then
    ok "$nombre"
  else
    falla "$nombre" "esperado [$esperado], obtenido [$obtenido]"
  fi
}

# 1. Convencion hecha a mano: el sidecar termina en `-db`.
probar "sidecar '-db' (demo, compulibra)" '{"services":{
  "libradesk-demo-db":{"image":"postgres:16-alpine"},
  "libradesk-demo":{"image":"libradesk:v2026.08.13-1925"}}}' \
  "libradesk-demo"

# 2. El sidecar declarado PRIMERO, que es lo que rompio el criterio anterior a
#    este (tomar la primera linea `image:` del archivo).
probar "sidecar declarado primero" '{"services":{
  "libradesk-x-db":{"image":"postgres:16-alpine"},
  "libradesk-x":{"image":"libradesk:v1"}}}' \
  "libradesk-x"

# 3. 🔴 EL CASO NUEVO: el generador del backoffice lo llama `-postgres`.
#    Con el `grep -v -- '-db$'` este caso devolvia los dos servicios.
probar "sidecar '-postgres' (lagrace, generado)" '{"services":{
  "libradesk-lagrace-postgres":{"image":"postgres:16-alpine"},
  "libradesk-lagrace":{"image":"libradesk:v2026.08.13-1258"}}}' \
  "libradesk-lagrace"

# 4. Control negativo: sin imagen de la app no se inventa ninguna. Sin esto,
#    una funcion que devolviera "el ultimo servicio" pasaria los tres de arriba.
probar "compose sin imagen libradesk" '{"services":{
  "solo-base":{"image":"postgres:16-alpine"}}}' \
  ""

# 5. Ambiguo: dos imagenes de la app. Tiene que devolver LAS DOS para que el
#    llamador corte, no elegir una a dedo.
probar "dos servicios de la app" '{"services":{
  "app-a":{"image":"libradesk:v1"},
  "app-b":{"image":"libradesk:v2"}}}' \
  "app-a app-b"

# 6. Un servicio con `build:` y sin `image:` (el compose de dev) no rompe.
probar "servicio sin image:" '{"services":{
  "libradesk-dev":{"build":{"context":"."}},
  "libradesk-dev-db":{"image":"postgres:16-alpine"}}}' \
  ""

# 7. `docker compose config` que falla y no imprime JSON: 0, no un crash.
probar "config sin salida" '' ""

rm -f "$FUENTE"
if [ "$fallos" -eq 0 ]; then
  echo "TODO OK (7 casos)"
else
  echo "$fallos caso(s) fallaron"
  exit 1
fi
