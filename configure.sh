#!/usr/bin/env bash
# Convenience wrapper around "python -m cartotui.configure".
#     ./configure.sh set ui.theme dark
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$ROOT/venv/bin/python" ]; then
    PY="$ROOT/venv/bin/python"
else
    PY="python3"
fi
exec "$PY" -m cartotui.configure "$@"
