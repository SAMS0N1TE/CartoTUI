#!/usr/bin/env python3
# ascii_map/config.py
"""
Config loader/saver and defaults for the ASCII Map TUI.

Goals:
- Single JSON file per user.
- Safe atomic writes.
- Deep-merge of user config over defaults.
- Basic validation with sane fallbacks.
- No external deps.

Usage:
    from ascii_map.config import Config, DEFAULT_CONFIG
    cfg = Config.load()                 # ~/.ascii_map_tui.json or OS-specific
    tile_url = cfg["network"]["tile_url"]
    cfg["ui"]["theme"] = "dark"
    cfg.save()
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

# ----------------------------
# Defaults
# ----------------------------

DEFAULT_CONFIG: Dict[str, Any] = {
    "app": {
        "title": "ASCII Map",
        "fps_limit": 60,                 # render throttle
        "shutdown_timeout_s": 3.0,
    },
    "viewport": {
        "width_chars": 120,              # used as initial hint; UI will measure terminal
        "height_chars": 36,
        "crosshair": True,
        "show_compass": True,
        "statusbar": True,
        "toolbar": True,
        "help_panel": False,
        "padding": 0,
    },
    "map": {
        "center_lat": 42.3601,           # Boston as neutral starting point
        "center_lon": -71.0589,
        "zoom": 4,                        # 0..19 typical web mercator range
        "min_zoom": 0,
        "max_zoom": 19,
        "mode": "ascii",                  # ascii | quadrant | braille
        "palette": "classic",             # see resources/palettes.json for extras
        "overzoom": 1,                    # allow integer upscale when missing tiles
        "label_overlay": False,           # future: city names, streets
    },
    "network": {
        # Web mercator XYZ tile template. {z}/{x}/{y}
        "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "user_agent": "ascii-map-tui/1.0 (+https://example.invalid)",
        "connect_timeout_s": 5.0,
        "read_timeout_s": 15.0,
        "retries": 3,
        "retry_backoff_s": [0.2, 0.5, 1.0],
        "parallel_downloads": 8,
        "http_cache": True,
    },
    "cache": {
        "dir": None,                      # auto if None: OS cache dir
        "max_bytes": 256 * 1024 * 1024,   # 256 MiB
        "prune_watermark": 0.85,          # prune down to 85% when exceeding
    },
    "render": {
        "dither": "none",                 # none | atkinson | bayer
        "gamma": 1.0,
        "contrast": 1.0,
        "brightness": 1.0,
        "color": True,
        "transparent_water": False,
        "grid": False,
        "grid_step_deg": 1.0,
    },
    "prefetch": {
        "ring_radius": 1,                 # tiles around view to prefetch
        "enable": True,
        "max_queue": 128,
    },
    "ui": {
        "theme": "auto",                  # auto | light | dark
        "mouse": True,
        "key_repeat_ms": 35,
        "show_latency_ms": True,
        "border_style": "ascii",          # ascii | heavy | rounded
    },
    "logging": {
        "level": "INFO",
        "http_debug": False,
        "file": None,                     # path or None
        "rotate_bytes": 5 * 1024 * 1024,
        "rotate_keep": 3,
    },
}

# ----------------------------
# Helpers
# ----------------------------

def _os_config_home() -> str:
    """Return per-OS config base directory."""
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return os.path.join(base, "AsciiMap")
    # macOS: ~/Library/Application Support/AsciiMap
    if platform.system() == "Darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), "AsciiMap")
    # Linux and others: ~/.config/ascii_map
    return os.path.join(os.path.expanduser("~/.config"), "ascii_map")

def _os_cache_home() -> str:
    """Return per-OS cache base directory."""
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(base, "AsciiMap", "Cache")
    if platform.system() == "Darwin":
        return os.path.join(os.path.expanduser("~/Library/Caches"), "AsciiMap")
    return os.path.join(os.path.expanduser("~/.cache"), "ascii_map")

def _default_config_path() -> str:
    """Resolve default config path, honoring ASCII_MAP_CONFIG env override."""
    env = os.environ.get("ASCII_MAP_CONFIG")
    if env:
        return os.path.expanduser(env)
    return os.path.join(_os_config_home(), "ascii_map_tui.json")

def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Return deep-merged copy of dicts: values in b override a."""
    out = dict(a)
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out

def _atomic_write_json(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_cfg_", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, sort_keys=True)
            f.write("\n")
        # replace
        if platform.system() == "Windows":
            # On Windows replace is not atomic across devices; assume same dir
            if os.path.exists(path):
                os.remove(path)
        os.replace(tmp, path)
    except Exception:
        # Clean temp on error
        try:
            os.remove(tmp)
        except Exception:
            pass
        raise

def _coerce_num(v: Any, default: float, minmax: Optional[Tuple[float, float]] = None) -> float:
    try:
        x = float(v)
        if minmax:
            lo, hi = minmax
            if x < lo: x = lo
            if x > hi: x = hi
        return x
    except Exception:
        return float(default)

def _coerce_int(v: Any, default: int, minmax: Optional[Tuple[int, int]] = None) -> int:
    try:
        x = int(v)
        if minmax:
            lo, hi = minmax
            if x < lo: x = lo
            if x > hi: x = hi
        return x
    except Exception:
        return int(default)

def _coerce_bool(v: Any, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "on"): return True
        if s in ("0", "false", "no", "off"): return False
    return default

# ----------------------------
# Validation
# ----------------------------

def _validate(cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Return validated copy with fallbacks applied."""
    c = _deep_merge(DEFAULT_CONFIG, cfg or {})

    # app
    c["app"]["fps_limit"] = _coerce_int(c["app"].get("fps_limit"), DEFAULT_CONFIG["app"]["fps_limit"], (1, 240))
    c["app"]["shutdown_timeout_s"] = _coerce_num(c["app"].get("shutdown_timeout_s"), 3.0, (0.5, 30.0))

    # viewport
    vp = c["viewport"]
    vp["width_chars"]  = _coerce_int(vp.get("width_chars"), 120, (20, 1000))
    vp["height_chars"] = _coerce_int(vp.get("height_chars"), 36, (10, 500))
    for key in ("crosshair", "show_compass", "statusbar", "toolbar", "help_panel"):
        vp[key] = _coerce_bool(vp.get(key), DEFAULT_CONFIG["viewport"][key])
    vp["padding"] = _coerce_int(vp.get("padding"), 0, (0, 5))

    # map
    m = c["map"]
    m["center_lat"] = _coerce_num(m.get("center_lat"), DEFAULT_CONFIG["map"]["center_lat"], (-85.0511, 85.0511))
    m["center_lon"] = _coerce_num(m.get("center_lon"), DEFAULT_CONFIG["map"]["center_lon"], (-180.0, 180.0))
    m["min_zoom"]   = _coerce_int(m.get("min_zoom"), 0, (0, 22))
    m["max_zoom"]   = _coerce_int(m.get("max_zoom"), 19, (0, 22))
    m["zoom"]       = _coerce_int(m.get("zoom"), 4, (m["min_zoom"], m["max_zoom"]))
    m["overzoom"]   = _coerce_int(m.get("overzoom"), 1, (0, 8))
    if m.get("mode") not in ("ascii", "quadrant", "braille"):
        m["mode"] = DEFAULT_CONFIG["map"]["mode"]
    m["label_overlay"] = _coerce_bool(m.get("label_overlay"), DEFAULT_CONFIG["map"]["label_overlay"])

    # network
    n = c["network"]
    n["tile_url"] = str(n.get("tile_url") or DEFAULT_CONFIG["network"]["tile_url"])
    n["user_agent"] = str(n.get("user_agent") or DEFAULT_CONFIG["network"]["user_agent"])
    n["connect_timeout_s"] = _coerce_num(n.get("connect_timeout_s"), 5.0, (0.2, 60.0))
    n["read_timeout_s"]    = _coerce_num(n.get("read_timeout_s"), 15.0, (0.5, 120.0))
    n["retries"]           = _coerce_int(n.get("retries"), 3, (0, 10))
    backoff = n.get("retry_backoff_s")
    if not isinstance(backoff, list) or not backoff:
        n["retry_backoff_s"] = DEFAULT_CONFIG["network"]["retry_backoff_s"][:]
    else:
        n["retry_backoff_s"] = [max(0.0, float(x)) for x in backoff]
    n["parallel_downloads"] = _coerce_int(n.get("parallel_downloads"), 8, (1, 64))
    n["http_cache"] = _coerce_bool(n.get("http_cache"), DEFAULT_CONFIG["network"]["http_cache"])

    # cache
    cc = c["cache"]
    cc["dir"] = cc.get("dir") or os.path.join(_os_cache_home(), "tiles")
    cc["max_bytes"] = int(max(8 * 1024 * 1024, int(cc.get("max_bytes") or DEFAULT_CONFIG["cache"]["max_bytes"])))
    pw = cc.get("prune_watermark")
    try:
        pw = float(pw)
    except Exception:
        pw = DEFAULT_CONFIG["cache"]["prune_watermark"]
    cc["prune_watermark"] = min(0.99, max(0.50, pw))

    # render
    r = c["render"]
    if r.get("dither") not in ("none", "atkinson", "bayer"):
        r["dither"] = DEFAULT_CONFIG["render"]["dither"]
    r["gamma"]     = _coerce_num(r.get("gamma"), 1.0, (0.2, 3.0))
    r["contrast"]  = _coerce_num(r.get("contrast"), 1.0, (0.1, 3.0))
    r["brightness"]= _coerce_num(r.get("brightness"), 1.0, (0.1, 3.0))
    r["color"]     = _coerce_bool(r.get("color"), DEFAULT_CONFIG["render"]["color"])
    r["transparent_water"] = _coerce_bool(r.get("transparent_water"), DEFAULT_CONFIG["render"]["transparent_water"])
    r["grid"]      = _coerce_bool(r.get("grid"), DEFAULT_CONFIG["render"]["grid"])
    r["grid_step_deg"] = _coerce_num(r.get("grid_step_deg"), 1.0, (0.05, 30.0))

    # ui
    ui = c["ui"]
    if ui.get("theme") not in ("auto", "light", "dark"):
        ui["theme"] = DEFAULT_CONFIG["ui"]["theme"]
    ui["mouse"] = _coerce_bool(ui.get("mouse"), DEFAULT_CONFIG["ui"]["mouse"])
    ui["key_repeat_ms"] = _coerce_int(ui.get("key_repeat_ms"), 35, (10, 200))
    ui["show_latency_ms"] = _coerce_bool(ui.get("show_latency_ms"), DEFAULT_CONFIG["ui"]["show_latency_ms"])
    if ui.get("border_style") not in ("ascii", "heavy", "rounded"):
        ui["border_style"] = DEFAULT_CONFIG["ui"]["border_style"]

    # logging
    lg = c["logging"]
    if lg.get("level") not in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"):
        lg["level"] = DEFAULT_CONFIG["logging"]["level"]
    lg["http_debug"] = _coerce_bool(lg.get("http_debug"), DEFAULT_CONFIG["logging"]["http_debug"])
    lf = lg.get("file")
    lg["file"] = str(lf) if lf else None
    lg["rotate_bytes"] = _coerce_int(lg.get("rotate_bytes"), DEFAULT_CONFIG["logging"]["rotate_bytes"], (256 * 1024, 50 * 1024 * 1024))
    lg["rotate_keep"]  = _coerce_int(lg.get("rotate_keep"), DEFAULT_CONFIG["logging"]["rotate_keep"], (0, 50))

    return c

# ----------------------------
# Public API
# ----------------------------

@dataclass
class Config:
    """Thin wrapper around a nested dict with load/save/merge."""
    data: Dict[str, Any] = field(default_factory=lambda: json.loads(json.dumps(DEFAULT_CONFIG)))
    path: str = field(default_factory=_default_config_path)

    # --- Mapping-style access
    def __getitem__(self, k: str) -> Any:
        return self.data[k]

    def __setitem__(self, k: str, v: Any) -> None:
        self.data[k] = v

    def get(self, k: str, default: Any = None) -> Any:
        return self.data.get(k, default)

    # --- Ops
    @classmethod
    def load(cls, path: Optional[str] = None, create_if_missing: bool = True) -> "Config":
        cfg_path = os.path.expanduser(path) if path else _default_config_path()
        if not os.path.exists(cfg_path):
            cfg = _validate(DEFAULT_CONFIG)
            if create_if_missing:
                _atomic_write_json(cfg_path, cfg)
            return cls(cfg, cfg_path)

        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                user_cfg = json.load(f)
        except Exception:
            # Corrupt file. Backup and regenerate.
            backup = cfg_path + ".corrupt.bak"
            try:
                shutil.copyfile(cfg_path, backup)
            except Exception:
                pass
            user_cfg = {}

        merged = _deep_merge(DEFAULT_CONFIG, user_cfg)
        validated = _validate(merged)

        # Ensure cache dir exists
        try:
            os.makedirs(validated["cache"]["dir"], exist_ok=True)
        except Exception:
            # fallback to OS cache home
            validated["cache"]["dir"] = os.path.join(_os_cache_home(), "tiles")
            os.makedirs(validated["cache"]["dir"], exist_ok=True)

        return cls(validated, cfg_path)

    def save(self) -> None:
        """Persist to JSON atomically."""
        # Only serialize keys that differ from defaults to keep file tidy
        diff = _diff(DEFAULT_CONFIG, self.data)
        # But include top-level sections even if empty to help discoverability
        for section in DEFAULT_CONFIG.keys():
            diff.setdefault(section, {})
            if not diff[section]:
                del diff[section]
        # Write validated data (defaults + diff) so file is complete and readable
        full = _validate(_deep_merge(DEFAULT_CONFIG, diff))
        _atomic_write_json(self.path, full)
        self.data = full  # sync in-memory with normalized values

    def update(self, partial: Dict[str, Any]) -> None:
        """Deep-merge a partial config then validate."""
        merged = _deep_merge(self.data, partial)
        self.data = _validate(merged)

    # Convenience getters
    @property
    def cache_dir(self) -> str:
        return self.data["cache"]["dir"]

    @property
    def tile_url(self) -> str:
        return self.data["network"]["tile_url"]


def _diff(base: Dict[str, Any], cur: Dict[str, Any]) -> Dict[str, Any]:
    """Return nested dictionary of keys where cur differs from base."""
    out: Dict[str, Any] = {}
    for k in cur.keys() | base.keys():
        if k not in base:
            out[k] = cur[k]
            continue
        if k not in cur:
            continue
        vb = base[k]
        vc = cur[k]
        if isinstance(vb, dict) and isinstance(vc, dict):
            d = _diff(vb, vc)
            if d:
                out[k] = d
        elif vb != vc:
            out[k] = vc
    return out

__all__ = [
    "Config",
    "DEFAULT_CONFIG",
    "_default_config_path",
]
