
from __future__ import annotations

import logging
import os
import platform
from logging.handlers import RotatingFileHandler

from cartotui.config import Config

__all__ = ["setup_logging"]

_LOGGER = logging.getLogger("cartotui")

def _default_log_dir() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(base, "CartoTUI", "Logs")
    if platform.system() == "Darwin":
        return os.path.join(os.path.expanduser("~/Library/Logs"), "CartoTUI")
    return os.path.join(
        os.environ.get("XDG_STATE_HOME", os.path.expanduser("~/.local/state")),
        "cartotui",
    )

def setup_logging(cfg: Config) -> logging.Logger:
    level_name = cfg["logging"].get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    for h in list(root.handlers):
        root.removeHandler(h)

    log_file_cfg = cfg["logging"].get("file")

    if log_file_cfg == "":
        root.addHandler(logging.NullHandler())
    else:
        if log_file_cfg is None:
            log_dir = _default_log_dir()
            log_path = os.path.join(log_dir, "cartotui.log")
        else:
            log_path = os.path.expanduser(log_file_cfg)

        try:
            os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
            fh = RotatingFileHandler(
                log_path,
                maxBytes=int(cfg["logging"].get("rotate_bytes", 5 * 1024 * 1024)),
                backupCount=int(cfg["logging"].get("rotate_keep", 3)),
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except OSError:
            root.addHandler(logging.NullHandler())

    if level > logging.DEBUG:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("PIL").setLevel(logging.WARNING)

    return _LOGGER
