#!/usr/bin/env bash
# Run ASCII Map TUI (Unix/Linux/Mac)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${SCRIPT_DIR}/.."

export PYTHONPATH="${ROOT_DIR}:${PYTHONPATH}"

echo "Launching ASCII Map..."
python3 -m ascii_map.cli "$@"
