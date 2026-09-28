"""Portable visual presets. No locations, credentials or machine tuning."""
import re
from copy import deepcopy

TONE = ("brightness", "contrast", "gamma", "saturation", "black_point", "white_point")
OPTIONS = ("road_highlight", "raster_tint", "road_thickness", "road_thickness_by_mode",
           "geometry_mode", "detail_labels", "boundaries", "boundary_style", "label_background",
           "crisp_roads", "crisp_boundaries", "crisp_labels")


def preset_name(value):
    name = value.strip().lower().replace(" ", "_")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}", name):
        raise ValueError("Use 1–40 letters, numbers, spaces or - _.")
    if name.split(".")[0] in {"con", "prn", "aux", "nul", *[f"com{i}" for i in range(10)], *[f"lpt{i}" for i in range(10)]}:
        raise ValueError("Choose another name.")
    return name


def capture_settings(state, cfg):
    result = {k: deepcopy(cfg["render"][k]) for k in OPTIONS if k in cfg["render"]}
    result.update({k: getattr(state, k) for k in TONE})
    result.update(preset_version=1, source=state.source, view=state.render_mode,
                  palette=state.palette, color=state.color, dither=state.dither,
                  subpixel_threshold=state.threshold_mode, shaded_blocks=state.shaded_blocks,
                  vector_overlay=state.labels)
    return result


def apply_settings(state, cfg, settings):
    r = deepcopy(settings)
    # Config validation supplies the same bounds/choices as interactive controls.
    from cartotui.config import _validate
    clean = _validate({"render": r})["render"]
    cfg.update({"render": {k: clean[k] for k in (*OPTIONS, *TONE,
        "color", "dither", "subpixel_threshold", "shaded_blocks", "vector_overlay") if k in r}})
    if r.get("source") in ("vector", "raster"):
        state.set_source(r["source"])
    if r.get("view") in ("ascii", "half", "quadrant", "braille"):
        state.set_render_mode(r["view"])
        cfg.update({"render": {f"{state.source}_render_mode": state.render_mode}})
    cfg.update({"map": {"mode": "vector" if state.source == "vector" else state.render_mode}})
    for key in TONE + ("color", "dither", "shaded_blocks"):
        if key in r:
            setattr(state, key, clean[key])
    for key, attr in (("subpixel_threshold", "threshold_mode"), ("vector_overlay", "labels")):
        if key in r:
            setattr(state, attr, clean[key])
    if r.get("palette"):
        state.palette = r["palette"]
        cfg.update({"map": {"palette": state.palette}})
    state.current_look = ""
