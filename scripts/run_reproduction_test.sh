#!/usr/bin/env sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
PYTHON=${PYTHON:-python}

"$PYTHON" "$ROOT/tests/run_reproduction_test.py" "$@"
