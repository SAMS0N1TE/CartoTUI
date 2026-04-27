"""Logging setup for CartoTUI.

The TUI runs full-screen via prompt_toolkit's alt-screen. Anything written to
stderr while the alt-screen is active will bleed through prompt_toolkit's
renderer and corrupt the visible UI — log lines stack on top of the map,
sidebars get overwritten, and the terminal becomes unreadable.

To avoid that, we never attach a stderr StreamHandler. If the user has
configured a log file, we use a RotatingFileHandler. Otherwise we install
one at a default location under the OS log/cache dir so the logs are still
recoverable after a session.

Tests and `--print-config` paths can opt out by passing a config with
``logging.file`` explicitly set to the empty string ``""`` — in that case
we attach only a NullHandler and emit nothing anywhere.
"""

from __future__ import annotations

import logging
import os
import platform
from logging.handlers import RotatingFileHandler

from cartotui.config import Config

__all__ = ["setup_logging"]

_LOGGER = logging.getLogger("cartotui")


def _default_log_dir() -> str:
    """Pick a reasonable default directory to put session logs in."""
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

    # Always start clean so re-init in tests is safe.
    for h in list(root.handlers):
        root.removeHandler(h)

    log_file_cfg = cfg["logging"].get("file")

    # Distinguish three cases:
    #   None       -> caller didn't configure; auto-pick a default file path
    #   ""         -> caller explicitly suppressed file logging (tests etc)
    #   "<path>"   -> caller wants logs in this specific file
    if log_file_cfg == "":
        # Suppress all log output. NullHandler stops the "no handler" warning
        # from logging without writing anywhere.
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
            # If we can't open the log file (read-only fs, permission denied,
            # weird path on Windows), swallow it silently — emitting *anything*
            # to stderr at this point would be the very corruption we're
            # trying to avoid. Drop logs on the floor instead.
            root.addHandler(logging.NullHandler())

    # Quiet noisy libraries unless we're in DEBUG.
    if level > logging.DEBUG:
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("PIL").setLevel(logging.WARNING)

    return _LOGGER
