#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${PYTHON:-python}

"$PYTHON" "$ROOT/tadpole_swimming_tracking.py" \
  --config "$ROOT/examples/configs/tadpole_recording_001.json" \
  --cache-only \
  "$@"

