"""Logging setup for CartoTUI.

The TUI runs full-screen so console handlers attach to stderr only when there's
no log file configured (which means they only show up after the app exits, on
crash). With a log file configured, all logs go there via a rotating handler.
"""

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from cartotui.config import Config

__all__ = ["setup_logging"]

_LOGGER = logging.getLogger("cartotui")


def setup_logging(cfg: Config) -> logging.Logger:
    level_name = cfg["logging"].get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    # Clear any pre-existing handlers so re-init in tests is safe.
    for h in list(root.handlers):
        root.removeHandler(h)

    log_file = cfg["logging"].get("file")
    if log_file:
        log_path = os.path.expanduser(log_file)
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        fh = RotatingFileHandler(
            log_path,
            maxBytes=int(cfg["logging"].get("rotate_bytes", 5 * 1024 * 1024)),
            backupCount=int(cfg["logging"].get("rotate_keep", 3)),
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        root.addHandler(fh)
    else:
        # Defer console output to stderr; harmless in full-screen mode because
        # the alt screen restores at exit and any error logs become visible.
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    # Quiet noisy libraries unless we're in DEBUG.
    if level > logging.DEBUG:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("PIL").setLevel(logging.WARNING)

    return _LOGGER
