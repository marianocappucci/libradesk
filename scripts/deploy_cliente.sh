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
# que aca no aplica: LibraDesk usa libracore para PDFs y config, pero no monta
# `libracore.provisioning`, que es lo que aquel panel maneja.
#   (Esta linea decia "LibraDesk no depende de libracore". Es falso —el
#   pyproject lo pinea desde siempre— y la afirmacion circulo tambien por el
#   wiki. Lo que no usa es el modulo de provisioning, no el paquete.)
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

# ------------------------------------------------------------------------------
# Cual de las lineas `image:` es la de la APP
# ------------------------------------------------------------------------------
# 🔴 Esto miraba la PRIMERA aparicion de `image:` del compose, y desde el corte a
# PostgreSQL del 2026-08-09 la primera es la del SIDECAR: cada instancia tiene
# ahora dos servicios y la base se declara arriba. O sea que el repin le habria
# escrito `libradesk:<version>` encima a `postgres:16-alpine`, y el `up -d`
# habria recreado el contenedor de la BASE con la imagen de la app. En `demo`
# eso es una demo caida; en `compulibra`, el cliente real sin base.
#
# Lo delato el `--dry-run`, que reportaba `actual : postgres:16-alpine`.
#
# Ahora la clave del servicio se LEE -- no se supone: en el compose de compulibra
# el servicio y el `container_name` no coinciden -- y se ubica su linea `image:`
# por numero.
CLAVE_APP="$(docker compose -f "$COMPOSE_FILE" config --services | grep -vE -- '-db$')"
CLAVE_APP="${CLAVE_APP%%$'\n'*}"
[ -n "$CLAVE_APP" ] || { echo "[ERROR] No se pudo leer el servicio de la app en $COMPOSE_FILE"; exit 1; }

LINEA_SVC="$(awk -v s="  ${CLAVE_APP}:" '$0 == s { print NR; exit }' "$COMPOSE_FILE")"
[ -n "$LINEA_SVC" ] || { echo "[ERROR] No se encontro el bloque del servicio '$CLAVE_APP'"; exit 1; }
LINEA_IMG="$(awk -v n="$LINEA_SVC" 'NR > n && /^[[:space:]]*image:/ { print NR; exit }' "$COMPOSE_FILE")"
[ -n "$LINEA_IMG" ] || { echo "[ERROR] El servicio '$CLAVE_APP' no declara image:"; exit 1; }

ANTERIOR="$(sed -n "${LINEA_IMG}s/^[[:space:]]*image:[[:space:]]*//p" "$COMPOSE_FILE")"

# Guarda: la linea que se va a reescribir tiene que tener HOY una imagen de este
# producto. Si dijera `postgres:...` es que se apunto al sidecar, y ahi hay que
# parar en vez de pisar la base.
case "$ANTERIOR" in
  libradesk:*) ;;
  *) echo "[ERROR] La linea $LINEA_IMG de $COMPOSE_FILE dice '$ANTERIOR',"
     echo "        que no es una imagen de libradesk. Se aborta para no pisar el"
     echo "        servicio equivocado (el sidecar de PostgreSQL, casi seguro)."
     exit 1 ;;
esac
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
  --ssh "libragenda=${LIBRAGENDA_SSH_KEY:-$HOME/.ssh/id_ed25519_libragenda}" \
  --ssh "libra-ui=${LIBRA_UI_SSH_KEY:-$HOME/.ssh/id_ed25519_libra_ui}" \
  --label "org.libra.version=$VERSION" \
  --label "org.libra.commit=$COMMIT" \
  --label "org.libra.ref=$ORIGEN" \
  --label "org.libra.built-at=$(date -Is)" \
  -t "$IMAGE_REF" \
  "$BUILD_CONTEXT"

# `latest` NO se mueve a proposito: nadie deberia apuntarle, y moverlo seria
# reintroducir el tag mutable que este esquema vino a sacar.

echo "[*] Repineando $COMPOSE_FILE linea $LINEA_IMG ($CLAVE_APP) -> $IMAGE_REF"
sed -i -E "${LINEA_IMG}s|^([[:space:]]*image:[[:space:]]*).*|\\1$IMAGE_REF|" "$COMPOSE_FILE"

# Un `sed` que no matchea sale con codigo 0. Se comprueba que la linea quedo.
grep -q "image: $IMAGE_REF" "$COMPOSE_FILE" || {
  echo "[ERROR] El repin no quedo escrito en $COMPOSE_FILE"; exit 1; }

echo "[*] Levantando $SLUG ..."
if ! (cd "$CLIENT_DIR" && docker compose up -d); then
  echo "[ERROR] Fallo el arranque. Repineando a ${ANTERIOR:-la version anterior}."
  if [ -n "$ANTERIOR" ]; then
    sed -i -E "${LINEA_IMG}s|^([[:space:]]*image:[[:space:]]*).*|\\1$ANTERIOR|" "$COMPOSE_FILE"
  fi
  exit 1
fi

# ------------------------------------------------------------------------------
# PODA DE TAGS VIEJOS (agregado 2026-08-07)
# ------------------------------------------------------------------------------
# Hasta hoy nada borraba los tags: cada deploy acuna `v$(date +%Y.%m.%d-%H%M)`
# y ninguno se retiraba nunca. Medido en el VPS el 2026-08-07, libradesk tenia
# 17 tags de ~570 MB, y entre los seis productos las imagenes y el build cache
# eran 63 de los 75 GB usados, con el disco al 75%.
#
# Espejo de `libracore.provisioning.panel_admin.podar_imagenes_viejas()`, que
# cubre a los otros cinco productos. Corre al final y nunca antes: si el deploy
# falla, la imagen vieja es justo a la que hay que poder volver.
#
# ⚠️ Todo lo de adentro va con `|| true`. Este script corre con
# `set -euo pipefail`, y aca hay tres comandos que devuelven != 0 en su camino
# NORMAL: `grep` sin coincidencias (ningun cliente todavia), `docker image
# inspect` de un tag ausente, y `docker rmi` de una imagen retenida. Sin el
# `|| true` cualquiera de los tres aborta el script — despues de haber
# desplegado, que es el peor momento para cortar.
podar_tags_viejos() {
  local keep="${IMAGE_RETENTION:-3}" recientes=0 tag ref iid r
  local candidatos=() ids_en_uso="" en_uso="" pineados=""

  # Refs que retiene algun contenedor, corriendo O PARADO: un contenedor
  # parado tambien necesita su imagen para poder volver a arrancar.
  en_uso="$(docker ps -a --format '{{.Image}}' 2>/dev/null | sort -u || true)"
  while read -r r; do
    [ -z "$r" ] && continue
    iid="$(docker image inspect -f '{{.Id}}' "$r" 2>/dev/null || true)"
    [ -n "$iid" ] && ids_en_uso+="$iid"$'\n'
  done <<< "$en_uso"

  # Lo pineado en el compose de cualquier cliente, aunque no este corriendo.
  pineados="$(grep -hoE 'image:[[:space:]]*[^[:space:]]+' \
      "$REPO_ROOT"/clientes/*/docker-compose.yml 2>/dev/null \
      | awk '{print $2}' | sort -u || true)"

  while read -r tag; do
    case "$tag" in ""|latest|"<none>") continue ;; esac
    ref="libradesk:$tag"
    # Los tags que no acuno el deploy son hitos y puntos de rollback puestos a
    # mano (p7, pre-p8-cutover-rollback, pre-recibos-*). No se tocan.
    echo "$tag" | grep -qE '^v[0-9]{4}\.[0-9]{2}\.[0-9]{2}-[0-9]{4}$' || continue
    if [ "$recientes" -lt "$keep" ]; then recientes=$((recientes + 1)); continue; fi
    echo "$pineados" | grep -qxF "$ref" && continue
    iid="$(docker image inspect -f '{{.Id}}' "$ref" 2>/dev/null || true)"
    if [ -n "$iid" ] && echo "$ids_en_uso" | grep -qxF "$iid"; then continue; fi
    candidatos+=("$ref")
  done < <(docker images libradesk --format '{{.Tag}}' 2>/dev/null | sort -r || true)

  if [ "${#candidatos[@]}" -eq 0 ]; then
    echo "[OK] Poda: nada que borrar (se conservan los $keep tags mas nuevos)."
    return 0
  fi
  local borrados=0
  for ref in "${candidatos[@]}"; do
    # Sin `-f` a proposito: si algo la retiene, Docker se niega y seguimos.
    if docker rmi "$ref" >/dev/null 2>&1; then borrados=$((borrados + 1)); fi
  done
  echo "[OK] Poda: $borrados de ${#candidatos[@]} tag/s de deploy viejos borrados"
  echo "     (se conservan los $keep mas nuevos, los pineados y los de rollback)."
}
podar_tags_viejos

echo "[OK] '$SLUG' corriendo en $IMAGE_REF (commit $COMMIT)"
echo "     Rollback: editar image: en $COMPOSE_FILE y 'docker compose up -d'"
echo "     Versiones disponibles:"
docker images libradesk --format '       {{.Tag}}' | grep -v '<none>' | head -8
