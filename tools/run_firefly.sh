#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
: "${CONDA_PREFIX:?Activate the dedicated conda environment first}"
cd "$ROOT"
unset PYTHONPATH
export STOCKFISH_PATH="${STOCKFISH_PATH:-$CONDA_PREFIX/bin/stockfish}"
export EDGECHESS_PROFILE="${EDGECHESS_PROFILE:-$(python -c 'import json; print(json.load(open("PACKAGE.json"))["profiles"][0])')}"
export EDGECHESS_3D_MODEL="${EDGECHESS_3D_MODEL:-$(python -c 'import json; print(json.load(open("PACKAGE.json"))["default_3d_model"])')}"
export EDGECHESS_BACKEND="${EDGECHESS_BACKEND:-$(python -c 'import json; print(json.load(open("PACKAGE.json"))["backends"][0])')}"
export EDGECHESS_STOCKFISH_SECONDS="${EDGECHESS_STOCKFISH_SECONDS:-1}"
export EDGECHESS_STOCKFISH_THREADS="${EDGECHESS_STOCKFISH_THREADS:-1}"
export EDGECHESS_STOCKFISH_HASH_MB="${EDGECHESS_STOCKFISH_HASH_MB:-64}"
export PYTHONDONTWRITEBYTECODE=1
export TMPDIR="$ROOT/.tmp" XDG_CACHE_HOME="$ROOT/.cache" XDG_CONFIG_HOME="$ROOT/.config"
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$XDG_CONFIG_HOME"
python - <<'PY'
import json, os, sys
from pathlib import Path
assert Path(sys.prefix).resolve() == Path(os.environ['CONDA_PREFIX']).resolve(), 'Python is not from active conda'
assert os.access(os.environ['STOCKFISH_PATH'], os.X_OK), 'Stockfish executable missing'
package = json.loads(Path('PACKAGE.json').read_text())
root = Path(os.getenv('EDGECHESS_ARTIFACTS', 'convert/artifacts'))
for key in package['models']:
    assert (root / key / 'model.json').is_file(), f'Missing metadata: {key}'
    for backend in package['backends']:
        relative = 'model.onnx' if backend == 'onnx' else f'{backend}/model.rknn'
        assert (root / key / relative).is_file(), f'Missing YOLO artifact: {key}/{relative}'
PY
exec python -m uvicorn web.backend.app:app --host "${EDGECHESS_BIND_HOST:-127.0.0.1}" --port "${EDGECHESS_PORT:-8000}" --loop asyncio --ws websockets --ws-max-size 2097152 --ws-max-queue 1
