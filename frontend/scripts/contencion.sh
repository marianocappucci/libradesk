#!/usr/bin/env bash
#
# Arnés de contención: corre la suite con los núcleos saturados a propósito,
# para que salgan los falsos rojos que sólo aparecen cuando el CI está apretado.
#
# ## Para qué
#
# Los flakes de esta suite no se reproducen en una máquina en reposo. El de
# `configuracion-facturacion` (2026-08-13) dio 0 fallos en 10 corridas del
# archivo y 5 de la suite completa, y aun así se cayó en CI. Con este arnés sale
# a la primera o segunda corrida.
#
# Lo que importa no es la lentitud, es que los workers de vitest se peleen el
# scheduler: ahí React llega a procesar un evento contra un componente que
# todavía no terminó de comitear, y el cambio se pierde. Ver
# `src/test/escribir.ts` para el detalle de lo que se midió.
#
# ## Uso
#
#   frontend/scripts/contencion.sh                    # la suite entera, 3 veces
#   CORRIDAS=6 frontend/scripts/contencion.sh         # más vueltas
#   frontend/scripts/contencion.sh src/test/x.test.tsx   # un archivo
#
# ⚠️ **`taskset` solo NO sirve, hace lo contrario**: vitest dimensiona el pool
# con `availableParallelism()`, así que limitar CPUs achica el pool y los tests
# salen más rápidos. Lo que hace falta es CPU ocupada por OTROS procesos, que es
# lo que hace este script.
set -uo pipefail
cd "$(dirname "$0")/.."

CORRIDAS=${CORRIDAS:-3}
OBJETIVO=${1:-}

pids=()
limpiar() { for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null; done; }
trap limpiar EXIT

for _ in $(seq 1 "$(nproc)"); do
  bash -c 'while :; do :; done' &
  pids+=($!)
done
echo "carga: $(nproc) procesos quemando CPU"

fallos=0
for i in $(seq 1 "$CORRIDAS"); do
  # shellcheck disable=SC2086
  npx vitest run $OBJETIVO > "/tmp/contencion-$i.log" 2>&1
  ec=$?
  [ "$ec" -ne 0 ] && fallos=$((fallos + 1))
  echo "corrida $i: exit=$ec  $(grep -E '^ *Tests ' "/tmp/contencion-$i.log" | tail -1)"
  grep -E '^ FAIL|AssertionError' "/tmp/contencion-$i.log" | head -4
done

echo "=== corridas con fallos: $fallos de $CORRIDAS ==="
echo "logs en /tmp/contencion-*.log"
[ "$fallos" -eq 0 ]
