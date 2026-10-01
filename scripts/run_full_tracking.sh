#!/usr/bin/env sh
set -eu

if [ "$#" -lt 2 ]; then
  printf 'Usage: %s CONFIG.json VIDEO.mp4 [additional options]\n' "$0" >&2
  exit 2
fi

CONFIG=$1
VIDEO=$2
shift 2
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${PYTHON:-python}

"$PYTHON" "$ROOT/tadpole_swimming_tracking.py" \
  --config "$CONFIG" \
  --video "$VIDEO" \
  --force-retrack \
  "$@"
