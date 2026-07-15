"""Curated one-press visual presets ("Looks") and guardrail helpers."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

__all__ = [
    "Look", "LOOKS", "look_keys", "look_names", "get_look", "default_look_key",
    "apply_look", "current_look_key", "next_look_key",
    "dither_affects", "palette_affects", "shading_affects",
]

_MODES = ("ascii", "quadrant", "braille", "half")
_DITHERS = ("none", "bayer", "atkinson", "floyd")
_THRESHOLDS = ("adaptive", "percentile", "edge", "fixed")


@dataclass(frozen=True)
class Look:
    """A complete, coherent visual-settings combination."""

    key: str
    name: str
    desc: str
    render_mode: str = "quadrant"
    palette: str = "shades"
    color: bool = True
    dither: str = "none"
    threshold: str = "adaptive"
    shaded: bool = False
    brightness: float = 1.0
    contrast: float = 1.05
    gamma: float = 1.0
    saturation: float = 1.0
    black_point: float = 0.0
    white_point: float = 1.0
    theme: Optional[str] = None
    tags: Tuple[str, ...] = ()

    def summary(self) -> str:
        bits = [self.render_mode]
        if self.render_mode == "ascii":
            bits.append(self.palette)
        bits.append("colour" if self.color else "mono")
        if self.render_mode == "ascii" and self.dither != "none":
            bits.append(self.dither)
        if self.threshold != "adaptive":
            bits.append(self.threshold)
        if self.theme:
            bits.append(f"@{self.theme}")
        return " · ".join(bits)


LOOKS: Tuple[Look, ...] = (
    Look(
        key="terminal", name="Terminal",
        desc="Balanced colour map. Safe default.",
        render_mode="quadrant", palette="shades", color=True,
        threshold="adaptive", tags=("colour", "everyday"),
    ),
    Look(
        key="photo", name="Hi-Fi Photo",
        desc="Half-block colour. Maximum detail.",
        render_mode="half", palette="shades", color=True,
        tags=("colour", "detail"),
    ),
    Look(
        key="bold", name="Bold Blocks",
        desc="Chunky shaded colour blocks.",
        render_mode="quadrant", palette="blocks", color=True, shaded=True,
        tags=("colour",),
    ),
    Look(
        key="classic", name="Classic ASCII",
        desc="Clean grey-scale character map.",
        render_mode="ascii", palette="shades", color=False,
        threshold="adaptive", tags=("mono", "text"),
    ),
    Look(
        key="newsprint", name="Newsprint",
        desc="Dithered halftone, like newsprint.",
        render_mode="ascii", palette="shades", color=False,
        dither="atkinson", tags=("mono", "art"),
    ),
    Look(
        key="blueprint", name="Blueprint",
        desc="Edge-only line drawing.",
        render_mode="ascii", palette="shades", color=False,
        threshold="edge", tags=("mono", "art"),
    ),
    Look(
        key="braille", name="Fine Braille",
        desc="High-res braille line art.",
        render_mode="braille", palette="shades", color=False,
        threshold="adaptive", tags=("mono", "detail"),
    ),
    Look(
        key="amber_crt", name="Amber CRT",
        desc="Warm amber phosphor glow.",
        render_mode="quadrant", palette="shades", color=True,
        theme="amber", tags=("colour", "retro"),
    ),
    Look(
        key="matrix", name="Matrix",
        desc="Green-on-black character map.",
        render_mode="ascii", palette="shades", color=True,
        theme="green", tags=("retro", "art"),
    ),
    Look(
        key="paper", name="Paper Map",
        desc="Light printed-atlas look.",
        render_mode="quadrant", palette="shades", color=True,
        theme="paper", tags=("colour", "light"),
    ),
    Look(
        key="night", name="Night Ops",
        desc="Muted dark palette for night.",
        render_mode="quadrant", palette="shades", color=True,
        theme="night", tags=("colour", "dark"),
    ),
    Look(
        key="hicon", name="High Contrast",
        desc="Max-legibility neon on black.",
        render_mode="quadrant", palette="blocks", color=True,
        contrast=1.25, theme="hicon", tags=("colour", "a11y"),
    ),
)

_BY_KEY: Dict[str, Look] = {lk.key: lk for lk in LOOKS}


def look_keys() -> Tuple[str, ...]:
    return tuple(lk.key for lk in LOOKS)


def look_names() -> Tuple[str, ...]:
    return tuple(lk.name for lk in LOOKS)


def get_look(key: str) -> Optional[Look]:
    return _BY_KEY.get(str(key))


def default_look_key() -> str:
    return LOOKS[0].key


def dither_affects(mode: str) -> bool:
    """Dither is only honoured by the ASCII backend."""
    return mode == "ascii"


def palette_affects(mode: str) -> bool:
    """The glyph ramp only meaningfully drives the ASCII backend."""
    return mode == "ascii"


def shading_affects(mode: str) -> bool:
    """`shaded_blocks` only applies to the subpixel block backends."""
    return mode in ("quadrant", "braille")


def apply_look(state, cfg, look: Look) -> bool:
    """Apply a Look to state + config. Returns True if the theme changed."""
    theme_changed = False

    state.set_render_mode(look.render_mode)
    state.palette = look.palette
    state.color = bool(look.color)
    state.dither = look.dither if look.dither in _DITHERS else "none"
    state.threshold_mode = (look.threshold if look.threshold in _THRESHOLDS
                            else "adaptive")
    state.shaded_blocks = bool(look.shaded)
    state.brightness = float(look.brightness)
    state.contrast = float(look.contrast)
    state.gamma = float(look.gamma)
    state.saturation = float(look.saturation)
    state.black_point = float(look.black_point)
    state.white_point = float(look.white_point)
    state.current_look = look.key

    if look.theme and look.theme != state.theme:
        state.theme = look.theme
        theme_changed = True

    render_patch = {
        "color": bool(look.color),
        "dither": state.dither,
        "brightness": round(float(look.brightness), 3),
        "contrast": round(float(look.contrast), 3),
        "gamma": round(float(look.gamma), 3),
        "saturation": round(float(look.saturation), 3),
        "black_point": round(float(look.black_point), 3),
        "white_point": round(float(look.white_point), 3),
        "subpixel_threshold": state.threshold_mode,
        "shaded_blocks": bool(look.shaded),
        "invert": False,
    }
    mode_key = ("raster_render_mode"
                if getattr(state, "source", "vector") == "raster"
                else "vector_render_mode")
    render_patch[mode_key] = look.render_mode
    patch: Dict = {
        "map": {"palette": look.palette},
        "render": render_patch,
    }
    if look.theme:
        patch["ui"] = {"theme": look.theme}
    try:
        cfg.update(patch)
    except Exception:
        pass
    return theme_changed


def _current_tuple(state, cfg=None) -> tuple:
    return (
        state.render_mode,
        state.palette,
        bool(state.color),
        state.dither,
        state.threshold_mode,
        bool(state.shaded_blocks),
        round(float(state.brightness), 2),
        round(float(state.contrast), 2),
        round(float(getattr(state, "gamma", 1.0)), 2),
        round(float(getattr(state, "saturation", 1.0)), 2),
        round(float(getattr(state, "black_point", 0.0)), 2),
        round(float(getattr(state, "white_point", 1.0)), 2),
    )


def _look_tuple(look: Look) -> tuple:
    return (
        look.render_mode,
        look.palette,
        bool(look.color),
        look.dither,
        look.threshold,
        bool(look.shaded),
        round(float(look.brightness), 2),
        round(float(look.contrast), 2),
        round(float(look.gamma), 2),
        round(float(look.saturation), 2),
        round(float(look.black_point), 2),
        round(float(look.white_point), 2),
    )


def current_look_key(state, cfg=None) -> Optional[str]:
    """Key of the Look matching the live settings, or None. Theme-bound wins."""
    cur = _current_tuple(state, cfg)
    theme = getattr(state, "theme", None)

    for lk in LOOKS:
        if lk.theme and lk.theme == theme and _look_tuple(lk) == cur:
            return lk.key
    for lk in LOOKS:
        if not lk.theme and _look_tuple(lk) == cur:
            return lk.key
    return None


def next_look_key(current: Optional[str], step: int = 1) -> str:
    keys = look_keys()
    if current in keys:
        i = keys.index(current)
        return keys[(i + step) % len(keys)]
    return keys[0]
