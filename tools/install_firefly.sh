#!/usr/bin/env bash
# Run inside an activated, dedicated conda environment on the Firefly.
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
: "${CONDA_PREFIX:?Activate the dedicated conda environment first}"
[[ "$(uname -m)" == aarch64 ]] || { echo 'This package requires Linux aarch64' >&2; exit 1; }
cd "$ROOT"
unset PYTHONPATH
python - <<'PY'
import hashlib, json, os, sys
from pathlib import Path
assert (3, 10) <= sys.version_info[:2] < (3, 13), 'Python 3.10–3.12 required'
assert Path(sys.prefix).resolve() == Path(os.environ['CONDA_PREFIX']).resolve(), 'Python is not from active conda'
manifest = json.loads(Path('stockfish/manifest.json').read_text())
assert manifest['architecture'] == 'aarch64'
libc = os.confstr('CS_GNU_LIBC_VERSION')
assert tuple(map(int, libc.split()[-1].split('.'))) >= (2, 35), 'Official Stockfish 19 requires glibc >= 2.35; rebuild from supplied sources for older OS'
for name, key in [('stockfish', 'binary_sha256'), ('upstream.tar.gz', 'archive_sha256')]:
    assert hashlib.sha256(Path('stockfish', name).read_bytes()).hexdigest() == manifest[key], name
PY
mkdir -p "$ROOT/.cache/pip" "$ROOT/.tmp"
export TMPDIR="$ROOT/.tmp" PIP_CACHE_DIR="$ROOT/.cache/pip"
# Keep engine, original source distribution and license notices inside conda.
mkdir -p "$CONDA_PREFIX/bin" "$CONDA_PREFIX/share/edgechess-stockfish"
if [[ -e "$CONDA_PREFIX/bin/stockfish" ]] && ! cmp -s stockfish/stockfish "$CONDA_PREFIX/bin/stockfish"; then
  echo 'A different Stockfish already exists in this conda environment; use a new dedicated environment.' >&2
  exit 1
fi
python -m pip install -r web/requirements-firefly.txt
install -m 755 stockfish/stockfish "$CONDA_PREFIX/bin/stockfish"
cp stockfish/manifest.json stockfish/upstream.tar.gz "$CONDA_PREFIX/share/edgechess-stockfish/"
python - <<'PY'
import os
import chess
import chess.engine
path = os.path.join(os.environ['CONDA_PREFIX'], 'bin', 'stockfish')
with chess.engine.SimpleEngine.popen_uci(path, timeout=15) as engine:
    engine.configure({'Threads': 1, 'Hash': 64})
    board = chess.Board()
    move = engine.play(board, chess.engine.Limit(time=0.1)).move
    assert move in board.legal_moves
    print(engine.id.get('name'), 'UCI smoke OK:', move.uci())
PY
echo 'Installed in conda. Run: bash tools/run_firefly.sh'
