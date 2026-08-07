#!/usr/bin/env bash
# Tests de `podar_tags_viejos()` de scripts/deploy_cliente.sh.
#
# El script no se puede sourcear entero (corre el deploy al importarse), asi
# que se extrae la funcion y se la ejercita con un `docker` falso. Corre bajo
# `set -euo pipefail`, igual que el script real: es justamente lo que estos
# tests tienen que atrapar — un `grep` sin coincidencias ahi adentro aborta el
# deploy despues de haber desplegado.
set -uo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="$DIR/scripts/deploy_cliente.sh"
FUENTE="$(mktemp)"
sed -n '/^podar_tags_viejos() {$/,/^}$/p' "$SCRIPT" > "$FUENTE"
[ -s "$FUENTE" ] || { echo "FALLO: no se pudo extraer la funcion"; exit 1; }

fallos=0
ok()    { echo "  ok    $1"; }
falla() { echo "  FALLA $1"; echo "        $2"; fallos=$((fallos + 1)); }

# ── doble de docker ───────────────────────────────────────────────────────────
# TAGS / EN_USO / RMI_FALLA se setean por test. RMI_LOG acumula lo intentado.
docker() {
  case "$1 ${2:-}" in
    "images "*)  printf '%s\n' $TAGS ;;
    "ps -a")     printf '%s\n' $EN_USO ;;
    "image inspect")
        # `docker image inspect -f '{{.Id}}' <ref>`: el ref es $5, no $4.
        local ref="$5"
        printf '%s\n' $TAGS $EN_USO | grep -qxF "${ref#libradesk:}" \
          || printf '%s\n' $EN_USO | grep -qxF "$ref" || return 1
        echo "sha256:${ref}" ;;
    "rmi "*)
        echo "$2" >> "$RMI_LOG"
        printf '%s\n' ${RMI_FALLA:-} | grep -qxF "$2" && return 1
        return 0 ;;
    *) return 0 ;;
  esac
}
export -f docker 2>/dev/null || true

correr() {
  RMI_LOG="$(mktemp)"
  set -euo pipefail
  # shellcheck disable=SC1090
  source "$FUENTE"
  podar_tags_viejos > /tmp/poda_salida.txt 2>&1
  local rc=$?
  set +e
  return $rc
}

REPO_ROOT="$(mktemp -d)"; mkdir -p "$REPO_ROOT/clientes"

echo "== conserva los 3 mas nuevos y borra el resto"
TAGS="v2026.08.07-0900 v2026.08.06-0800 v2026.08.05-0700 v2026.08.04-0600 v2026.08.03-0500"
EN_USO=""; RMI_FALLA=""
correr
borrados="$(sort "$RMI_LOG" | tr '\n' ' ')"
[ "$borrados" = "libradesk:v2026.08.03-0500 libradesk:v2026.08.04-0600 " ] \
  && ok "borra las 2 mas viejas" || falla "borra las 2 mas viejas" "borro: $borrados"

echo "== no toca los tags puestos a mano"
TAGS="v2026.08.07-0900 v2026.08.06-0800 v2026.08.05-0700 v2026.08.04-0600 p7 pre-p8-cutover-rollback pre-recibos-20260805"
EN_USO=""; RMI_FALLA=""
correr
borrados="$(cat "$RMI_LOG")"
echo "$borrados" | grep -qE 'p7|pre-' \
  && falla "no toca hitos" "borro: $borrados" || ok "no toca hitos ni rollbacks"

echo "== no borra lo pineado por un cliente parado"
mkdir -p "$REPO_ROOT/clientes/pausado"
echo "services:
  libradesk:
    image: libradesk:v2026.07.01-0100" > "$REPO_ROOT/clientes/pausado/docker-compose.yml"
TAGS="v2026.08.07-0900 v2026.08.06-0800 v2026.08.05-0700 v2026.08.04-0600 v2026.07.01-0100"
EN_USO=""; RMI_FALLA=""
correr
grep -qF "v2026.07.01-0100" "$RMI_LOG" \
  && falla "respeta el pin" "borro la pineada" || ok "respeta el pin de un cliente parado"
rm -rf "$REPO_ROOT/clientes/pausado"

echo "== no borra la que usa un contenedor"
TAGS="v2026.08.07-0900 v2026.08.06-0800 v2026.08.05-0700 v2026.08.02-0200"
EN_USO="libradesk:v2026.08.02-0200"; RMI_FALLA=""
correr
grep -qF "v2026.08.02-0200" "$RMI_LOG" \
  && falla "respeta contenedor" "borro la que esta en uso" || ok "respeta la imagen de un contenedor"

echo "== sobrevive a que docker rmi se niegue"
TAGS="v2026.08.07-0900 v2026.08.06-0800 v2026.08.05-0700 v2026.08.02-0200 v2026.08.01-0100"
EN_USO=""; RMI_FALLA="libradesk:v2026.08.02-0200"
if correr; then ok "no aborta cuando rmi falla"; else falla "no aborta cuando rmi falla" "salio != 0"; fi
grep -q "1 de 2" /tmp/poda_salida.txt \
  && ok "reporta 1 de 2 borrados" || falla "reporta 1 de 2" "$(cat /tmp/poda_salida.txt)"

echo "== sobrevive a no tener ningun cliente (grep sin coincidencias)"
TAGS="v2026.08.07-0900 v2026.08.01-0100"
EN_USO=""; RMI_FALLA=""
if correr; then ok "no aborta sin clientes" ; else falla "no aborta sin clientes" "salio != 0 (el grep vacio mato el script)"; fi

echo "== sobrevive a no tener ninguna imagen"
TAGS=""; EN_USO=""; RMI_FALLA=""
if correr; then ok "no aborta sin imagenes"; else falla "no aborta sin imagenes" "salio != 0"; fi

echo "== nunca usa -f"
grep -qE 'docker rmi .*(-f|--force)' "$SCRIPT" \
  && falla "sin -f" "el script usa rmi -f" || ok "nunca usa rmi -f"

echo
if [ "$fallos" -eq 0 ]; then echo "TODO OK"; else echo "$fallos FALLA/S"; fi
exit "$fallos"
