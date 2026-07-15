
from __future__ import annotations

import json
import os
import platform
import shutil
import tempfile
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

__all__ = ["Config", "DEFAULT_CONFIG", "default_config_path"]

DEFAULT_CONFIG: Dict[str, Any] = {
    "app": {
        "title": "CartoTUI",
        "shutdown_timeout_s": 3.0,
    },
    "viewport": {
        "crosshair": True,
        "crosshair_char": "╋",
        "show_compass": True,
        "show_statusbar": True,
        "show_toolbar": True,
        "show_titlebar": True,
        "help_panel": False,
        "show_sidebar": True,
        "sidebar_width": 36,
    },
    "map": {
        "center_lat": 42.3601,
        "center_lon": -71.0589,
        "zoom": 4,
        "min_zoom": 0,
        "max_zoom": 19,
        "mode": "vector",
        "palette": "shades",
        "overzoom": 2,
        "max_composite_px": 1400,
    },
    "vector": {
        "source": "mvt_url",
        "mvt_url": "https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}",
        "pmtiles_url": "https://protomaps.github.io/PMTiles/protomaps(vector)ODbL_firenze.pmtiles",
        "protomaps_api_key": "",
        "protomaps_api_url": "https://api.protomaps.com/tiles/v4/{z}/{x}/{y}.mvt",
        "style": "auto",
    },
    "network": {
        "tile_url": "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
        "user_agent": "CartoTUI/0.7 (+https://github.com/SAMS0N1TE/CartoTUI)",
        "connect_timeout_s": 5.0,
        "read_timeout_s": 15.0,
        "retries": 3,
        "parallel_downloads": 8,
    },
    "cache": {
        "dir": None,
        "max_bytes": 256 * 1024 * 1024,
        "prune_watermark": 0.85,
    },
    "render": {
        "color": True,
        "dither": "none",
        "contrast": 1.05,
        "brightness": 1.0,
        "gamma": 1.0,
        "saturation": 1.0,
        "black_point": 0.0,
        "white_point": 1.0,
        "sharpen_percent": 150,
        "sharpen_radius": 1.5,
        "sharpen_threshold": 3,
        "edge_boost": False,
        "invert": False,
        "subpixel_threshold": "adaptive",
        "subpixel_percentile": 55,
        "shaded_blocks": False,
        "vector_overlay": True,
        "boundaries": True,
        "vector_engine": "libcarto",
        "vector_scale": 6,
        "vector_render_mode": "quadrant",
        "raster_render_mode": "ascii",
        "boundary_style": "dots",
        "road_thickness": 1.0,
        "road_thickness_by_mode": {
            "ascii": 0.6,
            "half": 1.0,
            "quadrant": 1.0,
            "braille": 1.0,
        },
        "road_highlight": False,
        "raster_tint": "none",
        "dynamic_quality": True,
        "color_depth": "truecolor",
    },
    "prefetch": {
        "enable": True,
        "ring_radius": 1,
        "max_inflight": 4,
    },
    "ui": {
        "theme": "amber",
        "mouse": True,
        "border_style": "heavy",
        "show_latency": True,
        "pan_step_cells": 6,
        "panels": [],
        "max_fps": 30,
    },
    "aircraft": {
        "altitude_colors": True,
        "legend": True,
        "dead_reckoning": True,
        "predict_track": True,
        "predict_seconds": 60.0,
        "highlight_interesting": True,
        "max_shown": 150,
        "label_mode": "smart",
        "marker_style": "arrow",
        "marker_size": "normal",
        "hide_ground": False,
        "min_altitude": 0.0,
        "max_altitude": 0.0,
        "follow_selected": False,
    },
    "aircraft_trails": {
        "enabled": True,
        "duration_s": 60.0,
    },
    "logging": {
        "level": "INFO",
        "file": None,
        "rotate_bytes": 5 * 1024 * 1024,
        "rotate_keep": 3,
    },
    "traffic": {
        "enabled": False,
        "source": "disabled",
        "stale_timeout_s": 60.0,
        "lakeshark": {
            "port": "",
            "baudrate": 115200,
            "format": "auto",
        },
        "sbs1": {
            "host": "localhost",
            "port": 30003,
        },
        "api": {
            "provider": "airplanes.live",
            "radius_nm": 100.0,
            "interval_s": 5.0,
            "follow_map": True,
            "follow_zoom": True,
            "lat": 0.0,
            "lon": 0.0,
        },
        "replay": {
            "path": "",
            "speed": 1.0,
            "loop": True,
        },
        "record": {
            "enabled": False,
            "path": "",
            "interval_s": 1.0,
        },
    },
    "theme": {
        "chrome": {},
        "road_colors": {},
    },
    "overlays": {
        "radar": {
            "enabled": False,
            "opacity": 0.65,
            "color": 4,
            "smooth": 1,
            "snow": 1,
            "frame": "latest",
            "animate": False,
            "frame_interval": 0.6,
            "refresh_interval_s": 120.0,
        },
    },
    "snapshot": {
        "png_long_side": 1600,
        "open_after": True,
        "png_mode": "map",
        "png_labels": False,
        "png_aircraft": False,
        "png_radar": True,
    },
}

def _config_home() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return os.path.join(base, "CartoTUI")
    if platform.system() == "Darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), "CartoTUI")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "cartotui")

def _cache_home() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(base, "CartoTUI", "Cache")
    if platform.system() == "Darwin":
        return os.path.join(os.path.expanduser("~/Library/Caches"), "CartoTUI")
    return os.path.join(os.environ.get("XDG_CACHE_HOME", os.path.expanduser("~/.cache")), "cartotui")

def default_config_path() -> str:
    env = os.environ.get("CARTOTUI_CONFIG")
    if env:
        return os.path.expanduser(env)
    return os.path.join(_config_home(), "config.json")

def _deep_merge(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
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
        os.replace(tmp, path)
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise

def _coerce_num(v: Any, default: float, bounds: Optional[Tuple[float, float]] = None) -> float:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return float(default)
    if bounds is not None:
        lo, hi = bounds
        x = max(lo, min(hi, x))
    return x

def _coerce_int(v: Any, default: int, bounds: Optional[Tuple[int, int]] = None) -> int:
    try:
        x = int(v)
    except (TypeError, ValueError):
        return int(default)
    if bounds is not None:
        lo, hi = bounds
        x = max(lo, min(hi, x))
    return x

def _coerce_bool(v: Any, default: bool) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("1", "true", "yes", "on"):
            return True
        if s in ("0", "false", "no", "off"):
            return False
    return default

def _coerce_choice(v: Any, choices: Tuple[str, ...], default: str) -> str:
    if isinstance(v, str) and v in choices:
        return v
    return default

def _coerce_theme(v: Any, default: str) -> str:
    if not isinstance(v, str) or not v.strip():
        return default
    name = v.strip().lower()
    try:
        from cartotui import theme_loader
        avail = theme_loader.available_theme_names()
    except Exception:
        avail = ()
    if not avail or name in avail:
        return name
    return default

def _validate(cfg: Dict[str, Any]) -> Dict[str, Any]:
    c = _deep_merge(DEFAULT_CONFIG, cfg or {})

    a = c["app"]
    a["title"] = str(a.get("title") or DEFAULT_CONFIG["app"]["title"])
    a["shutdown_timeout_s"] = _coerce_num(a.get("shutdown_timeout_s"), 3.0, (0.5, 30.0))

    vp = c["viewport"]
    for key in ("crosshair", "show_compass", "show_statusbar", "show_toolbar",
                "show_titlebar", "help_panel", "show_sidebar"):
        vp[key] = _coerce_bool(vp.get(key), DEFAULT_CONFIG["viewport"][key])
    cross = vp.get("crosshair_char") or "+"
    vp["crosshair_char"] = str(cross)[:1] or "+"
    vp["sidebar_width"] = _coerce_int(vp.get("sidebar_width"), 36, (24, 120))

    m = c["map"]
    m["center_lat"] = _coerce_num(m.get("center_lat"), DEFAULT_CONFIG["map"]["center_lat"], (-85.05, 85.05))
    m["center_lon"] = _coerce_num(m.get("center_lon"), DEFAULT_CONFIG["map"]["center_lon"], (-180.0, 180.0))
    m["min_zoom"]   = _coerce_int(m.get("min_zoom"), 0, (0, 22))
    m["max_zoom"]   = _coerce_int(m.get("max_zoom"), 19, (0, 22))
    if m["max_zoom"] < m["min_zoom"]:
        m["max_zoom"] = m["min_zoom"]
    m["zoom"]       = _coerce_int(m.get("zoom"), 4, (m["min_zoom"], m["max_zoom"]))
    m["overzoom"]   = _coerce_int(m.get("overzoom"), 2, (0, 8))
    m["max_composite_px"] = _coerce_int(m.get("max_composite_px"), 1400, (256, 8192))
    m["mode"] = _coerce_choice(m.get("mode"), ("vector", "ascii", "quadrant", "braille", "half"),
                               DEFAULT_CONFIG["map"]["mode"])
    m["palette"] = str(m.get("palette") or DEFAULT_CONFIG["map"]["palette"])

    v = c["vector"]
    v["source"] = _coerce_choice(v.get("source"), ("protomaps_api", "pmtiles_url", "mvt_url"),
                                  DEFAULT_CONFIG["vector"]["source"])
    v["pmtiles_url"] = str(v.get("pmtiles_url") or DEFAULT_CONFIG["vector"]["pmtiles_url"])
    v["protomaps_api_key"] = str(v.get("protomaps_api_key") or "")
    v["protomaps_api_url"] = str(v.get("protomaps_api_url") or DEFAULT_CONFIG["vector"]["protomaps_api_url"])
    v["mvt_url"] = str(v.get("mvt_url") or DEFAULT_CONFIG["vector"]["mvt_url"])
    v["style"] = _coerce_choice(v.get("style"), ("auto", "nav", "minimal", "full"),
                                 DEFAULT_CONFIG["vector"]["style"])

    n = c["network"]
    n["tile_url"] = str(n.get("tile_url") or DEFAULT_CONFIG["network"]["tile_url"])
    n["user_agent"] = str(n.get("user_agent") or DEFAULT_CONFIG["network"]["user_agent"])
    n["connect_timeout_s"] = _coerce_num(n.get("connect_timeout_s"), 5.0, (0.2, 60.0))
    n["read_timeout_s"]    = _coerce_num(n.get("read_timeout_s"), 15.0, (0.5, 120.0))
    n["retries"]           = _coerce_int(n.get("retries"), 3, (0, 10))
    n["parallel_downloads"] = _coerce_int(n.get("parallel_downloads"), 8, (1, 32))

    cc = c["cache"]
    cc["dir"] = cc.get("dir") or os.path.join(_cache_home(), "tiles")
    cc["max_bytes"] = _coerce_int(cc.get("max_bytes"), DEFAULT_CONFIG["cache"]["max_bytes"],
                                   (8 * 1024 * 1024, 16 * 1024 * 1024 * 1024))
    cc["prune_watermark"] = _coerce_num(cc.get("prune_watermark"), 0.85, (0.5, 0.99))

    r = c["render"]
    r["color"]     = _coerce_bool(r.get("color"), DEFAULT_CONFIG["render"]["color"])
    r["dither"]    = _coerce_choice(r.get("dither"), ("none", "atkinson", "bayer", "floyd"),
                                     DEFAULT_CONFIG["render"]["dither"])
    r["contrast"]  = _coerce_num(r.get("contrast"), 1.05, (0.1, 3.0))
    r["brightness"] = _coerce_num(r.get("brightness"), 1.0, (0.1, 3.0))
    r["gamma"]     = _coerce_num(r.get("gamma"), 1.0, (0.2, 3.0))
    r["saturation"] = _coerce_num(r.get("saturation"), 1.0, (0.0, 3.0))
    r["black_point"] = _coerce_num(r.get("black_point"), 0.0, (0.0, 0.9))
    r["white_point"] = _coerce_num(r.get("white_point"), 1.0, (0.1, 1.0))
    r["sharpen_percent"] = _coerce_int(r.get("sharpen_percent"), 150, (0, 500))
    r["sharpen_radius"]  = _coerce_num(r.get("sharpen_radius"), 1.5, (0.0, 10.0))
    r["sharpen_threshold"] = _coerce_int(r.get("sharpen_threshold"), 3, (0, 50))
    r["edge_boost"] = _coerce_bool(r.get("edge_boost"), DEFAULT_CONFIG["render"]["edge_boost"])
    r["invert"]    = _coerce_bool(r.get("invert"), DEFAULT_CONFIG["render"]["invert"])
    r["subpixel_threshold"] = _coerce_choice(
        r.get("subpixel_threshold"), ("adaptive", "fixed", "percentile", "edge"),
        DEFAULT_CONFIG["render"]["subpixel_threshold"])
    r["subpixel_percentile"] = _coerce_int(r.get("subpixel_percentile"), 55, (5, 95))
    r["shaded_blocks"] = _coerce_bool(r.get("shaded_blocks"), DEFAULT_CONFIG["render"]["shaded_blocks"])
    r["vector_overlay"] = _coerce_bool(r.get("vector_overlay"), DEFAULT_CONFIG["render"]["vector_overlay"])
    r["boundaries"] = _coerce_bool(r.get("boundaries"), DEFAULT_CONFIG["render"]["boundaries"])
    r["vector_engine"] = _coerce_choice(r.get("vector_engine"), ("libcarto", "python"),
                                        DEFAULT_CONFIG["render"]["vector_engine"])
    r["vector_scale"] = _coerce_int(r.get("vector_scale"), 6, (2, 8))
    r["vector_render_mode"] = _coerce_choice(r.get("vector_render_mode"),
                                             ("ascii", "quadrant", "braille", "half"), "quadrant")
    r["raster_render_mode"] = _coerce_choice(r.get("raster_render_mode"),
                                             ("ascii", "quadrant", "braille", "half"), "ascii")
    r["boundary_style"] = _coerce_choice(r.get("boundary_style"),
                                         ("dots", "line", "dashed"), "dots")
    r["road_thickness"] = _coerce_num(r.get("road_thickness"), 1.0, (0.2, 4.0))
    rtm = r.get("road_thickness_by_mode")
    if not isinstance(rtm, dict):
        rtm = dict(DEFAULT_CONFIG["render"]["road_thickness_by_mode"])
        r["road_thickness_by_mode"] = rtm
    for _m, _d in DEFAULT_CONFIG["render"]["road_thickness_by_mode"].items():
        rtm[_m] = _coerce_num(rtm.get(_m), _d, (0.2, 4.0))
    r["road_highlight"] = _coerce_bool(r.get("road_highlight"), False)
    r["raster_tint"] = _coerce_choice(r.get("raster_tint"), ("none", "theme"), "none")
    r["dynamic_quality"] = _coerce_bool(r.get("dynamic_quality"), True)
    r["color_depth"] = _coerce_choice(r.get("color_depth"), ("truecolor", "256", "16"), "truecolor")

    pf = c["prefetch"]
    pf["enable"]       = _coerce_bool(pf.get("enable"), DEFAULT_CONFIG["prefetch"]["enable"])
    pf["ring_radius"]  = _coerce_int(pf.get("ring_radius"), 1, (0, 4))
    pf["max_inflight"] = _coerce_int(pf.get("max_inflight"), 4, (1, 32))

    ui = c["ui"]
    ui["theme"] = _coerce_theme(ui.get("theme"), DEFAULT_CONFIG["ui"]["theme"])
    ui["mouse"] = _coerce_bool(ui.get("mouse"), True)
    ui["border_style"] = _coerce_choice(ui.get("border_style"), ("ascii", "heavy", "rounded"),
                                         DEFAULT_CONFIG["ui"]["border_style"])
    ui["show_latency"] = _coerce_bool(ui.get("show_latency"), True)
    ui["pan_step_cells"] = _coerce_int(ui.get("pan_step_cells"), 6, (1, 64))
    ui["max_fps"] = _coerce_int(ui.get("max_fps"), 30, (5, 120))
    if not isinstance(ui.get("panels"), list):
        ui["panels"] = []

    tr = c["traffic"]
    tr["enabled"] = _coerce_bool(tr.get("enabled"), DEFAULT_CONFIG["traffic"]["enabled"])
    tr["source"] = _coerce_choice(tr.get("source"),
                                   ("disabled", "lakeshark", "lakeshark_tui", "sbs1",
                                    "api", "replay"),
                                   DEFAULT_CONFIG["traffic"]["source"])
    tr["stale_timeout_s"] = _coerce_num(tr.get("stale_timeout_s"), 60.0, (1.0, 3600.0))
    ls = tr.get("lakeshark")
    if not isinstance(ls, dict):
        ls = dict(DEFAULT_CONFIG["traffic"]["lakeshark"])
        tr["lakeshark"] = ls
    ls["port"] = str(ls.get("port") or "")
    ls["baudrate"] = _coerce_int(ls.get("baudrate"), 115200, (1200, 4000000))
    ls["format"] = str(ls.get("format") or "auto")
    sb = tr.get("sbs1")
    if not isinstance(sb, dict):
        sb = dict(DEFAULT_CONFIG["traffic"]["sbs1"])
        tr["sbs1"] = sb
    sb["host"] = str(sb.get("host") or "localhost")
    sb["port"] = _coerce_int(sb.get("port"), 30003, (1, 65535))
    ap = tr.get("api")
    if not isinstance(ap, dict):
        ap = dict(DEFAULT_CONFIG["traffic"]["api"])
        tr["api"] = ap
    ap["provider"] = _coerce_choice(ap.get("provider"),
                                    ("airplanes.live", "adsb.lol", "adsb.fi"),
                                    DEFAULT_CONFIG["traffic"]["api"]["provider"])
    ap["radius_nm"] = _coerce_num(ap.get("radius_nm"), 100.0, (1.0, 250.0))
    ap["interval_s"] = _coerce_num(ap.get("interval_s"), 5.0, (0.5, 3600.0))
    ap["follow_map"] = _coerce_bool(ap.get("follow_map"), True)
    ap["follow_zoom"] = _coerce_bool(ap.get("follow_zoom"), True)
    ap["lat"] = _coerce_num(ap.get("lat"), 0.0, (-90.0, 90.0))
    ap["lon"] = _coerce_num(ap.get("lon"), 0.0, (-180.0, 180.0))
    rp = tr.get("replay")
    if not isinstance(rp, dict):
        rp = dict(DEFAULT_CONFIG["traffic"]["replay"])
        tr["replay"] = rp
    rp["path"] = str(rp.get("path") or "")
    rp["speed"] = _coerce_num(rp.get("speed"), 1.0, (0.1, 60.0))
    rp["loop"] = _coerce_bool(rp.get("loop"), True)
    rc = tr.get("record")
    if not isinstance(rc, dict):
        rc = dict(DEFAULT_CONFIG["traffic"]["record"])
        tr["record"] = rc
    rc["enabled"] = _coerce_bool(rc.get("enabled"), False)
    rc["path"] = str(rc.get("path") or "")
    rc["interval_s"] = _coerce_num(rc.get("interval_s"), 1.0, (0.2, 60.0))

    acf = c.get("aircraft")
    if not isinstance(acf, dict):
        acf = dict(DEFAULT_CONFIG["aircraft"])
        c["aircraft"] = acf
    _ad = DEFAULT_CONFIG["aircraft"]
    acf["label_mode"] = _coerce_choice(acf.get("label_mode"),
                                       ("smart", "all", "selected", "none"),
                                       _ad["label_mode"])
    acf["marker_style"] = _coerce_choice(acf.get("marker_style"),
                                         ("arrow", "dot", "large", "plane", "square"),
                                         _ad["marker_style"])
    acf["marker_size"] = _coerce_choice(acf.get("marker_size"),
                                        ("small", "normal", "large", "huge"),
                                        _ad["marker_size"])
    acf["max_shown"] = _coerce_int(acf.get("max_shown"), _ad["max_shown"], (0, 10000))
    acf["predict_seconds"] = _coerce_num(acf.get("predict_seconds"),
                                         _ad["predict_seconds"], (0.0, 600.0))
    for _k in ("altitude_colors", "legend", "dead_reckoning", "predict_track",
               "highlight_interesting", "hide_ground", "follow_selected"):
        acf[_k] = _coerce_bool(acf.get(_k), _ad[_k])

    at = c.get("aircraft_trails")
    if not isinstance(at, dict):
        at = dict(DEFAULT_CONFIG["aircraft_trails"])
        c["aircraft_trails"] = at
    at["enabled"] = _coerce_bool(at.get("enabled"),
                                 DEFAULT_CONFIG["aircraft_trails"]["enabled"])
    at["duration_s"] = _coerce_num(at.get("duration_s"), 60.0, (5.0, 600.0))

    ov = c["overlays"]
    rd = ov.get("radar")
    if not isinstance(rd, dict):
        rd = dict(DEFAULT_CONFIG["overlays"]["radar"])
        ov["radar"] = rd
    rd["enabled"] = _coerce_bool(rd.get("enabled"), False)
    rd["opacity"] = _coerce_num(rd.get("opacity"), 0.65, (0.1, 1.0))
    rd["color"] = _coerce_int(rd.get("color"), 4, (0, 8))
    rd["smooth"] = _coerce_int(rd.get("smooth"), 1, (0, 1))
    rd["snow"] = _coerce_int(rd.get("snow"), 1, (0, 1))
    rd["frame"] = _coerce_choice(rd.get("frame"), ("latest", "nowcast"), "latest")
    rd["animate"] = _coerce_bool(rd.get("animate"), False)
    rd["frame_interval"] = _coerce_num(rd.get("frame_interval"), 0.6, (0.15, 3.0))
    rd["refresh_interval_s"] = _coerce_num(rd.get("refresh_interval_s"), 120.0, (15.0, 3600.0))

    sn = c["snapshot"]
    sn["png_long_side"] = _coerce_int(sn.get("png_long_side"), 1600, (512, 6144))
    sn["open_after"] = _coerce_bool(sn.get("open_after"), True)
    sn["png_mode"] = _coerce_choice(sn.get("png_mode"), ("map", "ascii"),
                                    DEFAULT_CONFIG["snapshot"]["png_mode"])
    sn["png_labels"] = _coerce_bool(sn.get("png_labels"), False)
    sn["png_aircraft"] = _coerce_bool(sn.get("png_aircraft"), False)
    sn["png_radar"] = _coerce_bool(sn.get("png_radar"), True)

    lg = c["logging"]
    lg["level"] = _coerce_choice(
        lg.get("level"),
        ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET"),
        DEFAULT_CONFIG["logging"]["level"],
    )
    lf = lg.get("file")
    lg["file"] = str(lf) if lf else None
    lg["rotate_bytes"] = _coerce_int(lg.get("rotate_bytes"), DEFAULT_CONFIG["logging"]["rotate_bytes"],
                                      (256 * 1024, 50 * 1024 * 1024))
    lg["rotate_keep"]  = _coerce_int(lg.get("rotate_keep"), DEFAULT_CONFIG["logging"]["rotate_keep"], (0, 50))

    return c

@dataclass
class Config:

    data: Dict[str, Any] = field(default_factory=lambda: _validate({}))
    path: str = field(default_factory=default_config_path)

    def __getitem__(self, k: str) -> Any:
        return self.data[k]

    def __setitem__(self, k: str, v: Any) -> None:
        self.data[k] = v

    def get(self, k: str, default: Any = None) -> Any:
        return self.data.get(k, default)

    @classmethod
    def load(cls, path: Optional[str] = None, create_if_missing: bool = True) -> Config:
        cfg_path = os.path.expanduser(path) if path else default_config_path()
        if not os.path.exists(cfg_path):
            cfg = _validate({})
            if create_if_missing:
                try:
                    _atomic_write_json(cfg_path, cfg)
                except OSError:
                    pass
            return cls(cfg, cfg_path)

        try:
            with open(cfg_path, encoding="utf-8") as f:
                user_cfg = json.load(f)
        except Exception:
            backup = cfg_path + ".corrupt.bak"
            try:
                shutil.copyfile(cfg_path, backup)
            except OSError:
                pass
            user_cfg = {}

        validated = _validate(user_cfg)
        try:
            os.makedirs(validated["cache"]["dir"], exist_ok=True)
        except OSError:
            validated["cache"]["dir"] = os.path.join(_cache_home(), "tiles")
            os.makedirs(validated["cache"]["dir"], exist_ok=True)
        return cls(validated, cfg_path)

    def save(self) -> None:
        _atomic_write_json(self.path, _validate(self.data))

    def update(self, partial: Dict[str, Any]) -> None:
        self.data = _validate(_deep_merge(self.data, partial))
