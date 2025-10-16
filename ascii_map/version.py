#!/usr/bin/env python3
# ascii_map/version.py
"""
Version and build metadata for ASCII Map TUI.
"""

__version__ = "5.0.0"
__build__ = "2025-10-16"
__author__ = "Long Range LLC / Samuel"
__license__ = "MIT"

def version_info() -> str:
    """Return human-readable version string."""
    return f"ASCII Map TUI v{__version__} (build {__build__})"
