#!/bin/sh
# Cursor adapter: forward hook stdin to the Trace writer. Fail open.
ROOT="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)"
PY="$ROOT/.venv/bin/python"
if [ -x "$PY" ]; then
  exec "$PY" -m traces.hook
fi
PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
export PYTHONPATH
exec python3 -m traces.hook
