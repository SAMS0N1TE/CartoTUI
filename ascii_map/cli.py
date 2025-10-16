#!/usr/bin/env python3
# ascii_map/cli.py
"""
Entry point for ASCII Map TUI.
Loads configuration and runs AsciiMapApp.
"""

import sys, os
from ascii_map.ui.app import AsciiMapApp

def main():
    if os.name == "nt" and not sys.stdout.isatty():
        print("No Windows console detected. Run from cmd, PowerShell, or Windows Terminal.")
        raise SystemExit(1)
    app = AsciiMapApp()
    app.run()

if __name__ == "__main__":
    main()
