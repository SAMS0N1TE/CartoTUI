#!/usr/bin/env bash
# Convenience wrapper around "python -m cartotui.configure".
#     ./configure.sh set ui.theme dark
#
# ADS-B live traffic:
#     ./configure.sh adsb                                    # interactive wizard
#     ./configure.sh adsb --test                             # probe the saved source
#     ./configure.sh adsb --list-ports                       # show serial ports
#     ./configure.sh adsb --source sbs1 --host 192.168.1.50  # dump1090 over TCP
#     ./configure.sh adsb --source api --provider adsb.lol   # online feed
#     ./configure.sh adsb --disable
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -x "$ROOT/venv/bin/python" ]; then
    PY="$ROOT/venv/bin/python"
else
    PY="python3"
fi
exec "$PY" -m cartotui.configure "$@"
