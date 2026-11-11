#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
unset PYTHONHOME
export PYTHONDONTWRITEBYTECODE=1 PYTHONNOUSERSITE=1
export PYTHONPATH="$ROOT/.runtime/site-packages"
export TMPDIR="$ROOT/.tmp" XDG_CACHE_HOME="$ROOT/.cache" XDG_CONFIG_HOME="$ROOT/.config"
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME"
if [[ $# -eq 0 ]]; then set -- run; fi
exec "$ROOT/.runtime/python/bin/python3.10" -s -B tools/firefly_standalone.py "$@"
