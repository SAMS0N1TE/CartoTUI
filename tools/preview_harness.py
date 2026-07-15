"""Headless QA tool: render setting combinations to labelled PNG contact sheets."""
from __future__ import annotations

import argparse
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cartotui import theme_loader  # noqa: E402
from cartotui.composite import apply_image_adjustments as _real_adjust  # noqa: E402
from cartotui.rendering.renderer import Renderer, default_palettes  # noqa: E402


def _find_mono_font() -> str:
    candidates = [
        r"C:\Windows\Fonts\DejaVuSansMono.ttf",
        r"C:\Windows\Fonts\consola.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/Library/Fonts/Menlo.ttc",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c

    try:
        import subprocess
        for query in ("DejaVu Sans Mono", "monospace"):
            got = subprocess.run(["fc-match", "-f", "%{file}", query],
                                 capture_output=True, text=True, timeout=5).stdout.strip()
            if got and os.path.exists(got):
                return got
    except Exception:
        pass

    for root, _dirs, files in os.walk("/usr/share/fonts"):
        for f in sorted(files):
            if "mono" in f.lower() and f.lower().endswith((".ttf", ".otf")):
                return os.path.join(root, f)
    return candidates[0]


MONO_FONT = _find_mono_font()


def _theme_map_rgb(theme: str) -> Dict[str, Tuple[int, int, int]]:
    """Pull the resolved vector-map colours for a theme."""
    kw = theme_loader.vector_style_kwargs(theme)
    return {
        "bg": kw["bg"],
        "water": kw["water"],
        "park": kw["park"],
        "building": kw["building"],
        "road": kw["road_color"],
        "label": kw["label_color"],
        "road_colors": kw["road_colors"],
    }


def synthetic_vector_map(theme: str, w: int, h: int) -> Image.Image:
    """
    A deterministic, city-like scene rendered with a theme's vector colours.
    Contains: water body, park, a block grid of buildings, a road hierarchy
    (motorway / primary / residential), and a couple of label dots -- enough
    tonal + edge variety to expose how render settings behave.
    """
    c = _theme_map_rgb(theme)
    img = Image.new("RGB", (w, h), c["bg"])
    d = ImageDraw.Draw(img)

    river = [
        (0, int(h * 0.62)), (int(w * 0.20), int(h * 0.68)),
        (int(w * 0.42), int(h * 0.60)), (int(w * 0.55), int(h * 0.72)),
        (int(w * 0.55), h), (0, h),
    ]
    d.polygon(river, fill=c["water"])

    d.rectangle([int(w * 0.62), int(h * 0.08), int(w * 0.92), int(h * 0.34)],
                fill=c["park"])

    rng = np.random.RandomState(7)
    for gy in range(6):
        for gx in range(9):
            bx = int(w * (0.06 + gx * 0.085))
            by = int(h * (0.10 + gy * 0.075))
            if bx > w * 0.60 and by < h * 0.36:
                continue
            bw = int(w * 0.05 * (0.6 + rng.rand() * 0.6))
            bh = int(h * 0.04 * (0.6 + rng.rand() * 0.7))
            d.rectangle([bx, by, bx + bw, by + bh], fill=c["building"])

    rc = c["road_colors"]

    def road(pts, pri, width):
        d.line(pts, fill=rc.get(pri, c["road"]), width=width, joint="curve")

    for i in range(1, 8):
        x = int(w * i / 8.0)
        road([(x, int(h * 0.05)), (x, int(h * 0.58))], 4, max(1, int(w * 0.004)))
    for j in range(1, 6):
        y = int(h * j / 8.0)
        road([(int(w * 0.03), y), (int(w * 0.60), y)], 4, max(1, int(w * 0.004)))

    road([(int(w * 0.05), int(h * 0.20)), (w, int(h * 0.30))], 8, max(2, int(w * 0.010)))
    road([(int(w * 0.30), 0), (int(w * 0.38), h)], 8, max(2, int(w * 0.010)))

    road([(0, int(h * 0.90)), (int(w * 0.5), int(h * 0.55)),
          (w, int(h * 0.42))], 10, max(3, int(w * 0.016)))

    for (lx, ly) in [(0.72, 0.20), (0.34, 0.42), (0.15, 0.30)]:
        px, py = int(w * lx), int(h * ly)
        r = max(2, int(w * 0.006))
        d.ellipse([px - r, py - r, px + r, py + r], fill=c["label"])

    return img


def synthetic_raster_photo(w: int, h: int) -> Image.Image:
    """
    A satellite-ish scene with smooth tonal gradients, a coastline and fine
    speckle -- representative of raster tiles (photographic, full tonal range).
    """
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    nx, ny = xx / w, yy / h

    land_g = 90 + 70 * np.sin(nx * 4) * np.cos(ny * 3)
    land = np.stack([
        70 + 40 * np.cos(nx * 5 + ny * 2),
        land_g,
        55 + 30 * np.sin(ny * 4),
    ], axis=-1)

    water = np.stack([
        np.full((h, w), 30.0),
        60 + 20 * np.sin(nx * 8),
        110 + 30 * np.cos(nx * 6),
    ], axis=-1)

    coast = ny + 0.15 * np.sin(nx * 7)
    mask = (coast > 0.55)[..., None]
    arr = np.where(mask, water, land)

    rng = np.random.RandomState(3)
    arr += rng.rand(h, w, 1) * 22 - 11
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


@dataclass
class Look:
    """A full visual-settings combination."""
    source: str = "vector"
    mode: str = "ascii"
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
    sharpen_percent: int = 150
    edge_boost: bool = False
    invert: bool = False
    theme: str = "amber"
    label: str = ""


def apply_image_adjustments(
    img: Image.Image, look: Look, *, full: bool
) -> Image.Image:
    """Run the app's real adjustment pipeline.

    Calls into ``cartotui.composite`` rather than restating it: a QA tool that
    reimplements what it is meant to inspect stops matching the app the moment
    either side moves, and then quietly previews a renderer that doesn't exist.

    ``full`` mirrors the raster path, which additionally sharpens/inverts.
    """
    return _real_adjust(
        img,
        brightness=look.brightness,
        contrast=look.contrast,
        gamma=look.gamma,
        saturation=look.saturation,
        black_point=look.black_point,
        white_point=look.white_point,
        sharpen_percent=look.sharpen_percent if full else 0,
        edge_boost=look.edge_boost if full else False,
        invert=look.invert if full else False,
    )


def render_look(look: Look, term_w: int, term_h: int) -> List[List[Tuple[str, str]]]:
    if look.source == "vector":
        src = synthetic_vector_map(look.theme, term_w * 8, term_h * 16)
        src = apply_image_adjustments(src, look, full=False)
    else:
        src = synthetic_raster_photo(term_w * 8, term_h * 16)
        src = apply_image_adjustments(src, look, full=True)

    r = Renderer(default_palettes(),
                 subpixel_threshold=look.threshold,
                 subpixel_percentile=55.0,
                 shaded_blocks=look.shaded)
    orientation = None
    if look.source == "vector":
        br, bg_, bb = _theme_map_rgb(look.theme)["bg"]
        orientation = ("dark" if (0.299 * br + 0.587 * bg_ + 0.114 * bb) / 255.0 < 0.4
                       else "bright")
    return r.render(src, term_w, term_h, look.color, mode=look.mode,
                    palette_name=look.palette, dither=look.dither,
                    source_kind=look.source, orientation=orientation)


def _parse_style(style: str, chrome: dict, default_fg, default_bg):
    fg, bg = default_fg, default_bg
    s = style or ""
    if s.startswith("class:"):
        cls = s.split()[0][len("class:"):]
        resolved = chrome.get(cls)
        if resolved:
            s = resolved
    reverse = False
    for tok in s.split():
        if tok.startswith("bg:#"):
            bg = tok[3:]
        elif tok.startswith("fg:#"):
            fg = tok[3:]
        elif tok.startswith("#"):
            fg = tok
        elif tok == "reverse":
            reverse = True
    if reverse:
        fg, bg = bg, fg
    return fg, bg


def _hex(s) -> Tuple[int, int, int]:
    if isinstance(s, tuple):
        return s
    return theme_loader._hex_to_rgb(s)


_FONT_CACHE: Dict[int, ImageFont.FreeTypeFont] = {}


def _font(px: int) -> ImageFont.FreeTypeFont:
    f = _FONT_CACHE.get(px)
    if f is None:
        f = ImageFont.truetype(MONO_FONT, px)
        _FONT_CACHE[px] = f
    return f


def frame_to_png(
    rows: List[List[Tuple[str, str]]],
    theme: str,
    cell_px: int = 10,
    base_class: str = "map",
) -> Image.Image:
    """Rasterise a terminal frame to an image using a monospace font.

    ``base_class`` is the chrome class the app wraps this frame in (the map
    Window uses ``class:map``). Cells inherit their background from it, which
    matters because the renderer emits fg-only styles: a flat region of map
    background is a space, and what shows is this class's bg.
    """
    chrome = theme_loader.chrome_style_map(theme)
    ui = theme_loader.resolve_theme(theme)["ui"]
    base_fg, base_bg = _parse_style(chrome.get(base_class, ""), chrome,
                                    ui.get("fg", "#c8c8c8"), ui.get("bg", "#101014"))
    page_bg = _hex(base_bg)
    default_fg = base_fg
    default_bg = base_bg

    n_rows = len(rows)
    n_cols = max((sum(len(t) for _, t in row) for row in rows), default=1)

    fh = cell_px
    fw = max(1, int(round(cell_px * 0.6)))
    font = _font(fh)

    W = n_cols * fw
    H = n_rows * fh
    img = Image.new("RGB", (max(1, W), max(1, H)), page_bg)
    d = ImageDraw.Draw(img)

    for y, row in enumerate(rows):
        x = 0
        for style, text in row:
            if not text:
                continue
            fg, bg = _parse_style(style, chrome, default_fg, default_bg)
            fg_rgb, bg_rgb = _hex(fg), _hex(bg)
            for ch in text:
                px = x * fw
                py = y * fh
                if bg_rgb != page_bg:
                    d.rectangle([px, py, px + fw, py + fh], fill=bg_rgb)
                if ch != " ":
                    d.text((px, py), ch, font=font, fill=fg_rgb)
                x += 1
    return img


def contact_sheet(
    looks: List[Look],
    term_w: int = 60,
    term_h: int = 26,
    cols: int = 3,
    cell_px: int = 9,
    title: str = "CartoTUI preview",
) -> Image.Image:
    pad = 14
    label_h = 26
    tiles: List[Tuple[Look, Image.Image]] = []
    for lk in looks:
        rows = render_look(lk, term_w, term_h)
        tiles.append((lk, frame_to_png(rows, lk.theme, cell_px=cell_px)))

    tw = max(t.width for _, t in tiles)
    th = max(t.height for _, t in tiles)
    rows_n = math.ceil(len(tiles) / cols)

    sheet_w = cols * tw + (cols + 1) * pad
    sheet_h = rows_n * (th + label_h) + (rows_n + 1) * pad + 40
    sheet = Image.new("RGB", (sheet_w, sheet_h), (18, 18, 22))
    d = ImageDraw.Draw(sheet)
    d.text((pad, 12), title, font=_font(20), fill=(235, 235, 235))

    for i, (lk, tile) in enumerate(tiles):
        r, cc = divmod(i, cols)
        x = pad + cc * (tw + pad)
        y = 40 + pad + r * (th + label_h + pad)
        sheet.paste(tile, (x, y))
        d.rectangle([x - 1, y - 1, x + tw, y + th], outline=(70, 70, 78))
        lbl = lk.label or f"{lk.mode}/{lk.palette}"
        lf = _font(13)
        max_chars = max(4, int(tw / 7.8))
        if len(lbl) > max_chars:
            lbl = lbl[:max_chars - 1] + "…"
        d.text((x, y + th + 5), lbl, font=lf, fill=(205, 205, 210))
    return sheet


def _cmd_sheet(args):
    """Matrix: every mode x a spread of palettes, color on, one theme."""
    modes = ["ascii", "quadrant", "braille", "half"]
    palettes = ["shades", "blocks", "dots", "binary", "dos"]
    looks = []
    for m in modes:
        for p in palettes:
            if m == "half":
                looks.append(Look(mode=m, palette="shades", theme=args.theme,
                                  color=True, label="half  color"))
                break
            looks.append(Look(mode=m, palette=p, theme=args.theme, color=True,
                              label=f"{m} / {p}"))
    sheet = contact_sheet(looks, cols=5, term_w=48, term_h=22,
                          title=f"Modes x palettes (color, theme={args.theme})")
    sheet.save(args.out)
    print("wrote", args.out, sheet.size)


def _cmd_mono(args):
    """Monochrome: modes x palettes with color OFF."""
    modes = ["ascii", "quadrant", "braille"]
    palettes = ["shades", "blocks", "dots", "binary", "dos"]
    looks = []
    for m in modes:
        for p in palettes:
            looks.append(Look(mode=m, palette=p, theme=args.theme, color=False,
                              label=f"{m} / {p}  (mono)"))
    sheet = contact_sheet(looks, cols=5, term_w=48, term_h=22,
                          title=f"Modes x palettes (MONO, theme={args.theme})")
    sheet.save(args.out)
    print("wrote", args.out, sheet.size)


def _cmd_dither(args):
    """Dither modes, color on vs off, ascii + quadrant."""
    looks = []
    for color in (True, False):
        for m in ("ascii", "quadrant"):
            for dth in ("none", "bayer", "atkinson", "floyd"):
                looks.append(Look(mode=m, palette="shades", dither=dth,
                                  color=color, theme=args.theme,
                                  label=f"{m} {dth} {'color' if color else 'mono'}"))
    sheet = contact_sheet(looks, cols=4, term_w=44, term_h=20,
                          title=f"Dither (theme={args.theme})")
    sheet.save(args.out)
    print("wrote", args.out, sheet.size)


def _cmd_threshold(args):
    """Threshold modes across ascii/quadrant, color + mono."""
    looks = []
    for m in ("ascii", "quadrant"):
        for color in (True, False):
            for th in ("adaptive", "percentile", "edge", "fixed"):
                looks.append(Look(mode=m, palette="shades", threshold=th,
                                  color=color, theme=args.theme,
                                  label=f"{m} {th} {'clr' if color else 'mono'}"))
    sheet = contact_sheet(looks, cols=4, term_w=44, term_h=20,
                          title=f"Threshold modes (theme={args.theme})")
    sheet.save(args.out)
    print("wrote", args.out, sheet.size)


def _cmd_invert(args):
    """Invert + themes (raster path so invert applies) + shaded."""
    looks = [
        Look(source="raster", mode="quadrant", color=True, invert=False,
             theme="amber", label="raster quad amber"),
        Look(source="raster", mode="quadrant", color=True, invert=True,
             theme="amber", label="raster quad amber INVERT"),
        Look(source="raster", mode="ascii", color=False, invert=False,
             theme="paper", label="raster ascii paper mono"),
        Look(source="raster", mode="ascii", color=False, invert=True,
             theme="paper", label="raster ascii paper mono INVERT"),
        Look(source="vector", mode="quadrant", color=True, theme="paper",
             label="vector quad paper"),
        Look(source="vector", mode="quadrant", color=True, theme="light",
             label="vector quad light"),
        Look(source="vector", mode="ascii", color=False, theme="paper",
             label="vector ascii paper mono"),
        Look(source="vector", mode="ascii", color=False, theme="light",
             label="vector ascii light mono"),
    ]
    sheet = contact_sheet(looks, cols=4, term_w=44, term_h=20,
                          title="Invert + light themes")
    sheet.save(args.out)
    print("wrote", args.out, sheet.size)


def _cmd_extremes(args):
    """Brightness / contrast / gamma extremes (raster)."""
    looks = [
        Look(source="raster", mode="quadrant", brightness=b, contrast=c, gamma=g,
             theme=args.theme, label=lbl)
        for (b, c, g, lbl) in [
            (1.0, 1.05, 1.0, "default"),
            (0.4, 1.05, 1.0, "brightness 0.4"),
            (2.0, 1.05, 1.0, "brightness 2.0"),
            (1.0, 0.3, 1.0, "contrast 0.3"),
            (1.0, 2.5, 1.0, "contrast 2.5"),
            (1.0, 1.05, 0.4, "gamma 0.4"),
            (1.0, 1.05, 2.5, "gamma 2.5"),
            (0.4, 2.5, 1.0, "dark+high contrast"),
        ]
    ]
    sheet = contact_sheet(looks, cols=4, term_w=44, term_h=20,
                          title=f"Image adjust extremes (theme={args.theme})")
    sheet.save(args.out)
    print("wrote", args.out, sheet.size)


def _cmd_tone(args):
    """The tone knobs: levels and saturation against brightness/contrast."""
    looks = [
        Look(source="raster" if args.raster else "vector", mode="quadrant",
             theme=args.theme, brightness=b, contrast=c, saturation=sa,
             black_point=bp, white_point=wp, label=lbl)
        for (b, c, sa, bp, wp, lbl) in [
            (1.0, 1.05, 1.0, 0.00, 1.00, "default"),
            (1.6, 1.05, 1.0, 0.00, 1.00, "brightness 1.6"),
            (1.0, 1.05, 1.0, 0.20, 1.00, "black pt 0.20 (lift darks)"),
            (1.0, 1.05, 1.0, 0.35, 1.00, "black pt 0.35"),
            (1.0, 1.05, 1.0, 0.00, 0.70, "white pt 0.70 (tame brights)"),
            (1.0, 1.05, 1.0, 0.00, 0.50, "white pt 0.50"),
            (1.0, 1.05, 1.0, 0.15, 0.75, "levels 0.15-0.75"),
            (1.0, 0.50, 1.0, 0.00, 1.00, "contrast 0.5"),
            (1.0, 2.00, 1.0, 0.00, 1.00, "contrast 2.0"),
            (1.0, 1.05, 0.0, 0.00, 1.00, "saturation 0"),
            (1.0, 1.05, 1.8, 0.00, 1.00, "saturation 1.8"),
            (1.3, 1.20, 1.2, 0.12, 0.85, "combined"),
        ]
    ]
    sheet = contact_sheet(looks, cols=4, term_w=44, term_h=20,
                          title=f"Tone controls (theme={args.theme})")
    sheet.save(args.out)
    print("wrote", args.out, sheet.size)


def _from_curated(cl, *, source="vector") -> Look:
    """Convert a cartotui.looks.Look into a harness Look."""
    return Look(
        source=source, mode=cl.render_mode, palette=cl.palette, color=cl.color,
        dither=cl.dither, threshold=cl.threshold, shaded=cl.shaded,
        brightness=cl.brightness, contrast=cl.contrast, gamma=cl.gamma,
        saturation=cl.saturation, black_point=cl.black_point,
        white_point=cl.white_point,
        theme=cl.theme or "amber",
        label=f"{cl.name}  —  {cl.summary()}",
    )


def _cmd_looks(args):
    """Render the curated Looks from cartotui.looks (the shipping set)."""
    from cartotui import looks as L
    src = "raster" if args.raster else "vector"
    looks = [_from_curated(cl, source=src) for cl in L.LOOKS]
    sheet = contact_sheet(looks, cols=3, term_w=52, term_h=24, cell_px=9,
                          title=f"CartoTUI curated Looks ({src} source)")
    sheet.save(args.out)
    print("wrote", args.out, sheet.size)


def _cmd_themes(args):
    """One safe look across all themes."""
    looks = [
        Look(mode="quadrant", palette="shades", color=True, theme=t,
             label=t)
        for t in theme_loader.available_theme_names()
    ]
    sheet = contact_sheet(looks, cols=5, term_w=40, term_h=18,
                          title="quadrant/shades/color across all themes")
    sheet.save(args.out)
    print("wrote", args.out, sheet.size)


def main(argv=None):
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    for name, fn in [("sheet", _cmd_sheet), ("mono", _cmd_mono),
                     ("dither", _cmd_dither), ("threshold", _cmd_threshold),
                     ("invert", _cmd_invert), ("extremes", _cmd_extremes),
                     ("tone", _cmd_tone),
                     ("themes", _cmd_themes), ("looks", _cmd_looks)]:
        s = sub.add_parser(name)
        s.add_argument("--out", default=f"preview_{name}.png")
        s.add_argument("--theme", default="amber")
        s.add_argument("--raster", action="store_true",
                       help="use the raster/satellite source image")
        s.set_defaults(func=fn)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
