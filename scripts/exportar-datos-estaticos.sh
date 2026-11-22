#!/usr/bin/env bash
set -euo pipefail

raiz="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporal="$(mktemp -d "$raiz/web/.exportacion.XXXXXXXX")"
proyecto="aetheris-exportacion-${temporal##*.}"
export COMPOSE_FILE="${COMPOSE_FILE:-$raiz/compose.exportacion.yml}"
compose=(docker compose -p "${proyecto,,}")
destino="$raiz/web/public/datos"

limpiar() {
  "${compose[@]}" down --volumes --remove-orphans --rmi local >/dev/null || true
  rm -rf "$temporal"
}
trap limpiar EXIT

"${compose[@]}" up --build --abort-on-container-exit --exit-code-from exportador
"${compose[@]}" cp exportador:/tmp/datos "$temporal/"
test -s "$temporal/datos/corte.json"
bloqueo="$raiz/web/.exportacion.lock"
if ! mkdir "$bloqueo"; then
  echo "Ya se está instalando otro corte estático." >&2
  exit 1
fi
trap 'rmdir "$bloqueo"; limpiar' EXIT
if [[ -e "$destino" ]]; then mv "$destino" "$temporal/anterior"; fi
if ! mv "$temporal/datos" "$destino"; then
  if [[ -e "$temporal/anterior" ]]; then mv "$temporal/anterior" "$destino"; fi
  exit 1
fi
