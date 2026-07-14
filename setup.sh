#!/usr/bin/env bash
# CartoTUI setup for macOS / Linux.
# Creates a virtualenv, installs CartoTUI, and builds the native renderer if a
# C compiler is available.
#
#     ./setup.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

SKIP_DLL=0
RECREATE=0
for arg in "$@"; do
    case "$arg" in
        --skip-dll) SKIP_DLL=1 ;;
        --recreate) RECREATE=1 ;;
    esac
done

PY=""
for cand in python3.12 python3 python; do
    if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
    echo "No Python found. Install Python 3.9+ and re-run." >&2
    exit 1
fi

echo "CartoTUI setup"
echo "root: $ROOT"

VENV="$ROOT/venv"
VENV_PY="$VENV/bin/python"

if [ "$RECREATE" = "1" ] && [ -d "$VENV" ]; then
    echo "Removing existing venv..."
    rm -rf "$VENV"
fi

if [ ! -x "$VENV_PY" ]; then
    echo "Creating venv with $PY"
    "$PY" -m venv "$VENV"
fi

echo "Installing dependencies..."
"$VENV_PY" -m pip install --upgrade pip >/dev/null
"$VENV_PY" -m pip install -r "$ROOT/requirements.txt"
"$VENV_PY" -m pip install -e "$ROOT"

if [ "$SKIP_DLL" = "0" ]; then
    echo "Building native renderer (libcarto)..."
    CC=""
    for name in clang gcc cc; do
        if command -v "$name" >/dev/null 2>&1; then CC="$name"; break; fi
    done
    if [ -n "$CC" ]; then
        LIB="$ROOT/libcarto"
        mkdir -p "$LIB/build"
        case "$(uname -s)" in
            Darwin) EXT="dylib" ;;
            *)      EXT="so" ;;
        esac
        OUT="$LIB/build/libcarto.$EXT"
        "$CC" -shared -fPIC -O2 -I"$LIB/include" \
            "$LIB/src/style.c" "$LIB/src/framebuffer.c" "$LIB/src/raster.c" \
            "$LIB/src/geom.c" "$LIB/src/mvt.c" "$LIB/src/carto.c" \
            -o "$OUT" -lm
        [ -f "$OUT" ] && echo "  built $OUT" || echo "  DLL build failed; the Python renderer will be used."
    else
        echo "No C compiler found. Skipping native renderer; the Python renderer will be used."
    fi
fi

echo ""
echo "Done."
echo "Run CartoTUI:"
echo "    source venv/bin/activate"
echo "    python -m cartotui --mvt-url 'https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}' --lat 43.2081 --lon -71.5376 --zoom 14"
echo ""
echo "Edit settings:"
echo "    ./configure.sh set ui.theme dark"
