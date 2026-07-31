#!/usr/bin/env bash
# ==============================================================================
# deploy_cliente.sh — despliega una instancia de cliente de LibraDesk
#
#   ./scripts/deploy_cliente.sh <slug> [version]
#   ./scripts/deploy_cliente.sh compulibra --dry-run
#
# Construye una version nueva de la imagen, repinea el compose de ESA instancia
# y la levanta. Equivale a `panel_admin.py actualizar` del resto de la familia,
# que aca no aplica: LibraDesk no depende de libracore y por lo tanto no tiene
# `libracore.provisioning`.
#
# El punto de todo esto: la instancia corre una imagen fija y solo se mueve
# cuando se la nombra. Un `git pull` o un rebuild de dev ya no la tocan.
# ==============================================================================
set -euo pipefail

SLUG="${1:-}"
if [ -z "$SLUG" ] || [ "$SLUG" = "--help" ]; then
  echo "Uso: $0 <slug> [version] [--dry-run]"
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT_DIR="$REPO_ROOT/clientes/$SLUG"
COMPOSE_FILE="$CLIENT_DIR/docker-compose.yml"

DRY_RUN=false
VERSION=""
for arg in "${@:2}"; do
  case "$arg" in
    --dry-run) DRY_RUN=true ;;
    *)         VERSION="$arg" ;;
  esac
done
# Mismo esquema que el resto del ecosistema (ver deploy.sh de Farmacia y
# libracore.provisioning.deploy_version).
VERSION="${VERSION:-v$(date '+%Y.%m.%d-%H%M')}"

if [ ! -f "$COMPOSE_FILE" ]; then
  echo "[ERROR] No existe $COMPOSE_FILE"
  echo "        Crealo a partir de clientes.example.yml"
  exit 1
fi

IMAGE_REF="libradesk:$VERSION"
ANTERIOR="$(grep -m1 -oE 'image:[[:space:]]*\S+' "$COMPOSE_FILE" | awk '{print $2}')"
COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo desconocido)"

echo "  instancia : $SLUG"
echo "  version   : $IMAGE_REF   (commit $COMMIT)"
echo "  actual    : ${ANTERIOR:-ninguna}"
if [ "$DRY_RUN" = true ]; then
  echo "[DRY-RUN] No se construye ni se despliega nada."
  exit 0
fi

echo "[*] Construyendo $IMAGE_REF ..."
DOCKER_BUILDKIT=1 docker build \
  --ssh "default=${LIBRAAUTH_SSH_KEY:-$HOME/.ssh/id_ed25519_libraauth}" \
  --ssh "libraauth=${LIBRAAUTH_SSH_KEY:-$HOME/.ssh/id_ed25519_libraauth}" \
  --ssh "libracore=${LIBRACORE_SSH_KEY:-$HOME/.ssh/id_ed25519_libracore}" \
  --ssh "libra-ui=${LIBRA_UI_SSH_KEY:-$HOME/.ssh/id_ed25519_libra_ui}" \
  --label "org.libra.version=$VERSION" \
  --label "org.libra.commit=$COMMIT" \
  --label "org.libra.built-at=$(date -Is)" \
  -t "$IMAGE_REF" \
  "$REPO_ROOT"

# `latest` NO se mueve a proposito: nadie deberia apuntarle, y moverlo seria
# reintroducir el tag mutable que este esquema vino a sacar.

echo "[*] Repineando $COMPOSE_FILE -> $IMAGE_REF"
sed -i -E "0,/^([[:space:]]*image:[[:space:]]*).*/s//\\1$IMAGE_REF/" "$COMPOSE_FILE"

echo "[*] Levantando $SLUG ..."
if ! (cd "$CLIENT_DIR" && docker compose up -d); then
  echo "[ERROR] Fallo el arranque. Repineando a ${ANTERIOR:-la version anterior}."
  if [ -n "$ANTERIOR" ]; then
    sed -i -E "0,/^([[:space:]]*image:[[:space:]]*).*/s//\\1$ANTERIOR/" "$COMPOSE_FILE"
  fi
  exit 1
fi

echo "[OK] '$SLUG' corriendo en $IMAGE_REF"
echo "     Rollback: editar image: en $COMPOSE_FILE y 'docker compose up -d'"
echo "     Versiones disponibles:"
docker images libradesk --format '       {{.Tag}}' | grep -v '<none>' | head -8
