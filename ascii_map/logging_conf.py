#!/usr/bin/env python3
# ascii_map/logging_conf.py
"""
Central logging setup for ASCII Map.
Supports console and optional rotating file logs.
"""

import logging
from logging.handlers import RotatingFileHandler
from typing import Optional
from ascii_map.config import Config


def setup_logging(cfg: Config) -> None:
    level_name = cfg["logging"].get("level", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(level=level, format="%(asctime)s [%(levelname)s] %(message)s")

    log_file = cfg["logging"].get("file")
    if log_file:
        handler = RotatingFileHandler(
            log_file,
            maxBytes=int(cfg["logging"].get("rotate_bytes", 5 * 1024 * 1024)),
            backupCount=int(cfg["logging"].get("rotate_keep", 3)),
            encoding="utf-8",
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logging.getLogger().addHandler(handler)

    if cfg["logging"].get("http_debug"):
        logging.getLogger("urllib3").setLevel(logging.DEBUG)
        logging.getLogger("requests").setLevel(logging.DEBUG)
