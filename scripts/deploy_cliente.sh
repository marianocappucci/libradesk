#!/usr/bin/env bash
# ==============================================================================
# deploy_cliente.sh — despliega una instancia de cliente de LibraDesk
#
#   ./scripts/deploy_cliente.sh <slug> [version] [--ref <git-ref>] [--dry-run]
#   ./scripts/deploy_cliente.sh compulibra --dry-run
#   ./scripts/deploy_cliente.sh compulibra --ref develop      # consciente
#   ./scripts/deploy_cliente.sh compulibra --from-checkout     # legacy
#
# Construye una version nueva de la imagen, repinea el compose de ESA instancia
# y la levanta. Equivale a `panel_admin.py actualizar` del resto de la familia,
# que aca no aplica: LibraDesk no depende de libracore y por lo tanto no tiene
# `libracore.provisioning`.
#
# El punto de todo esto: la instancia corre una imagen fija y solo se mueve
# cuando se la nombra. Un `git pull` o un rebuild de dev ya no la tocan.
#
# ------------------------------------------------------------------------------
# DE QUE CODIGO SE CONSTRUYE (cambiado 2026-08-03)
# ------------------------------------------------------------------------------
# Hasta hoy el contexto de build era el checkout (`REPO_ROOT`) con el `HEAD`
# que tuviera puesto en ese momento. Eso ataba el deploy del cliente a una
# variable global compartida: el mismo checkout alimenta el build de
# `libradesk-dev` (`context: .` en docker-compose.yml), asi que la rama que
# necesita dev decidia, de rebote, que codigo se le desplegaba al cliente. El
# 2026-08-03 el checkout del VPS paso a `develop` para poder desplegar
# service/RMA a dev, y con eso un `deploy_cliente.sh compulibra` habria
# construido `develop` y se lo habria puesto al cliente real. El script
# imprimia el commit, pero no fallaba ni preguntaba.
#
# Ahora el ref se pide por nombre y **por defecto es `main`**, y el build sale
# de un `git worktree` temporal de ese ref. El checkout no se mueve, con lo
# cual desplegarle al cliente ya no interfiere con lo que dev tenga puesto, y
# al reves. La etiqueta `org.libra.commit` pasa a ser verdadera por
# construccion: es el commit del que efectivamente se construyo.
#
# Efecto lateral buscado: el contexto es un arbol limpio, sin los restos
# ignorados que viven en el host (ver los tres incidentes documentados en
# .dockerignore) y sin `clientes/`, que hoy se horneaba en la imagen porque no
# esta en .dockerignore.
# ==============================================================================
set -euo pipefail

SLUG="${1:-}"
if [ -z "$SLUG" ] || [ "$SLUG" = "--help" ]; then
  cat <<'USO'
Uso: deploy_cliente.sh <slug> [version] [--ref <git-ref>] [--from-checkout] [--dry-run]

  --ref <git-ref>   Ref de git del que construir. Por defecto: main.
                    Si existe origin/<ref> se usa ese (lo promovido en GitHub).
                    Acepta rama, tag o SHA.
  --from-checkout   Construir del working tree tal cual, como antes de
                    2026-08-03. Incluye cambios sin commitear. Explicito a
                    proposito: no es el camino normal para una instancia de
                    cliente.
  --dry-run         Resuelve el ref y materializa el worktree para probar que
                    se puede, informa, y no construye ni despliega nada.
USO
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLIENT_DIR="$REPO_ROOT/clientes/$SLUG"
COMPOSE_FILE="$CLIENT_DIR/docker-compose.yml"

DRY_RUN=false
FROM_CHECKOUT=false
REF="main"
VERSION=""

args=("${@:2}")
i=0
while [ "$i" -lt "${#args[@]}" ]; do
  arg="${args[$i]}"
  case "$arg" in
    --dry-run)      DRY_RUN=true ;;
    --from-checkout) FROM_CHECKOUT=true ;;
    --ref)
      i=$((i + 1))
      if [ "$i" -ge "${#args[@]}" ]; then
        echo "[ERROR] --ref necesita un valor (ej: --ref main)" >&2
        exit 1
      fi
      REF="${args[$i]}"
      ;;
    --ref=*)        REF="${arg#--ref=}" ;;
    --*)
      echo "[ERROR] Opcion desconocida: $arg" >&2
      exit 1
      ;;
    *)              VERSION="$arg" ;;
  esac
  i=$((i + 1))
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
HEAD_REF="$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD 2>/dev/null || echo desconocido)"

# ------------------------------------------------------------------------------
# Resolucion del origen del build
# ------------------------------------------------------------------------------
WORKTREE=""
TMPPARENT=""

cleanup() {
  if [ -n "$WORKTREE" ] && [ -d "$WORKTREE" ]; then
    git -C "$REPO_ROOT" worktree remove --force "$WORKTREE" >/dev/null 2>&1 || true
  fi
  [ -n "$TMPPARENT" ] && rm -rf "$TMPPARENT"
  git -C "$REPO_ROOT" worktree prune >/dev/null 2>&1 || true
}
trap cleanup EXIT

if [ "$FROM_CHECKOUT" = true ]; then
  BUILD_CONTEXT="$REPO_ROOT"
  COMMIT="$(git -C "$REPO_ROOT" rev-parse --short HEAD 2>/dev/null || echo desconocido)"
  SUCIO="$(git -C "$REPO_ROOT" status --porcelain=v1 2>/dev/null | wc -l | tr -d ' ')"
  ORIGEN="checkout $REPO_ROOT (HEAD=$HEAD_REF, $SUCIO archivo/s sin commitear)"
  echo "[AVISO] --from-checkout: se construye el working tree tal cual esta,"
  echo "        no un ref promovido. HEAD=$HEAD_REF"
else
  if ! git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
    echo "[ERROR] $REPO_ROOT no es un repo git; no se puede resolver --ref $REF." >&2
    echo "        Usa --from-checkout si realmente queres construir el directorio." >&2
    exit 1
  fi

  # Best-effort: si no hay red o falla la deploy key seguimos con lo que haya
  # local, pero avisando — no queremos que un fetch caido bloquee un deploy.
  if ! git -C "$REPO_ROOT" fetch --quiet origin 2>/dev/null; then
    echo "[AVISO] 'git fetch origin' fallo. Se resuelve '$REF' con las refs locales,"
    echo "        que pueden estar viejas."
  fi

  # "main" quiere decir "lo que esta promovido en GitHub", no la rama local que
  # puede haber quedado atras. Si existe el remote-tracking, gana.
  RESOLVED="$REF"
  if git -C "$REPO_ROOT" rev-parse --verify --quiet "refs/remotes/origin/$REF^{commit}" >/dev/null 2>&1; then
    RESOLVED="origin/$REF"
  fi

  if ! COMMIT_FULL="$(git -C "$REPO_ROOT" rev-parse --verify --quiet "${RESOLVED}^{commit}")"; then
    echo "[ERROR] El ref '$REF' no existe en $REPO_ROOT (ni como origin/$REF)." >&2
    echo "        Refs disponibles:" >&2
    git -C "$REPO_ROOT" for-each-ref --format='          %(refname:short)' \
      refs/heads refs/remotes/origin refs/tags 2>/dev/null | head -20 >&2
    exit 1
  fi
  COMMIT="$(git -C "$REPO_ROOT" rev-parse --short "$COMMIT_FULL")"

  TMPPARENT="$(mktemp -d "${TMPDIR:-/tmp}/libradesk-build-XXXXXX")"
  WORKTREE="$TMPPARENT/src"
  git -C "$REPO_ROOT" worktree add --detach --quiet "$WORKTREE" "$COMMIT_FULL"
  BUILD_CONTEXT="$WORKTREE"
  ORIGEN="$REF -> $RESOLVED (worktree limpio; el checkout sigue en $HEAD_REF)"

  if [ "$REF" != "main" ]; then
    echo "[AVISO] Se va a construir '$REF', que no es main, para la instancia"
    echo "        de cliente '$SLUG'. Es explicito, asi que se asume querido."
  fi
fi

echo "  instancia : $SLUG"
echo "  version   : $IMAGE_REF   (commit $COMMIT)"
echo "  origen    : $ORIGEN"
echo "  contexto  : $BUILD_CONTEXT"
echo "  actual    : ${ANTERIOR:-ninguna}"
if [ "$DRY_RUN" = true ]; then
  if [ -n "$WORKTREE" ]; then
    echo "[DRY-RUN] Worktree materializado OK ($(git -C "$WORKTREE" ls-files | wc -l | tr -d ' ') archivos). Se limpia al salir."
  fi
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
  --label "org.libra.ref=$ORIGEN" \
  --label "org.libra.built-at=$(date -Is)" \
  -t "$IMAGE_REF" \
  "$BUILD_CONTEXT"

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

echo "[OK] '$SLUG' corriendo en $IMAGE_REF (commit $COMMIT)"
echo "     Rollback: editar image: en $COMPOSE_FILE y 'docker compose up -d'"
echo "     Versiones disponibles:"
docker images libradesk --format '       {{.Tag}}' | grep -v '<none>' | head -8
