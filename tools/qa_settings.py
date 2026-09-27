"""Real-tile settings matrix, readability warnings and a searchable visual gallery.

Default: every theme x representative zoom x glyph mode x geometry mode.
--full adds the Cartesian product of palette, threshold, shading and colour.
Continuous tone controls are sampled at their defaults, not claimed exhaustive.
"""
# ruff: noqa: E402
import argparse
import html
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from prompt_toolkit.output import ColorDepth

from cartotui.rendering.libcarto_backend import rasterise_view_libcarto
from cartotui.rendering.packed import DEFAULT, PackedFrame, _style
from cartotui.rendering.renderer import Renderer, default_palettes
from cartotui.snapshot import frame_to_png
from cartotui.themes import available_themes, theme_vector_style
from cartotui.ui.direct_paint import paint_rows
from cartotui.ui.map_overlay import apply_vector_overlay
from cartotui.ui.solid_geometry import (
    blank_frame,
    draw_solid_geometry,
    improve_braille_readability,
    luminance,
)
from cartotui.vector_source import VectorTileSource


def pack(rows, width, height):
    if isinstance(rows, PackedFrame):
        return rows
    glyph = np.zeros((height, width), np.uint32)
    fg = np.full_like(glyph, DEFAULT)
    bg = np.full_like(glyph, DEFAULT)
    for y, row in enumerate(rows):
        x = 0
        for style, text in row:
            f, b = _style(style)
            glyph[y, x:x+len(text)] = [ord(c) for c in text]
            if f is not None:
                fg[y, x:x+len(text)] = f
            if b is not None:
                bg[y, x:x+len(text)] = b
            x += len(text)
        assert x == width
    return PackedFrame(glyph, fg, bg, width, height)


def metrics(rows, bg):
    glyph = rows.glyph
    visible = (glyph != 32) & (glyph != 0x2800)
    ink_fraction = float(visible.mean())
    visible &= rows.fg != 0xFFFFFFFF
    fg = rows.fg[visible]
    rgb = np.stack((fg >> 16, fg >> 8 & 255, fg & 255), axis=-1)
    backgrounds = rows.bg[visible]
    bg_rgb = np.stack((backgrounds >> 16 & 255, backgrounds >> 8 & 255, backgrounds & 255), axis=-1)
    bg_rgb[backgrounds == 0xFFFFFFFF] = bg
    lum, background = luminance(rgb), luminance(bg_rgb)
    ratio = (np.maximum(lum, background) + .05) / (np.minimum(lum, background) + .05)
    return {"ink_fraction": round(ink_fraction, 4),
            "low_contrast_fraction": round(float((ratio < 3).mean()), 4) if len(ratio) else 0,
            "distinct_glyphs": len(np.unique(glyph)),
            "contrast_p10": round(float(np.percentile(ratio, 10)), 2) if len(ratio) else None}


def write_gallery(directory, records):
    cards = []
    for r in records:
        if "image" not in r:
            continue
        label = f'{r["theme"]} z{r["zoom"]} {r["mode"]} {r["geometry"]} {r["palette"]} {r["threshold"]} shade={r["shaded"]} color={r["color"]}'
        warning = str(bool(r["warnings"])).lower()
        cards.append(f'<article data-warning="{warning}" data-key="{html.escape(label)}"><h3>{html.escape(label)}</h3><p>{html.escape(str(r["warnings"]))} · {r["ms"]} ms · ink {r["ink_fraction"]} · contrast p10 {r["contrast_p10"]}</p><img loading="lazy" src="{r["image"]}"></article>')
    (directory/"index.html").write_text('''<!doctype html><meta charset="utf-8"><title>CartoTUI visual QA</title>
<style>body{background:#171a20;color:#eee;font:15px system-ui;margin:24px}input{padding:12px;width:80%;position:sticky;top:8px}article{border:1px solid #667;margin:18px 0;padding:12px}img{max-width:100%;image-rendering:pixelated}p{color:#bbb}</style>
<h1>CartoTUI settings review</h1><p>Metrics flag candidates for human review; sparse ocean and dense cities can be correct. Timing includes composition and excludes initial raster/network. Full coverage details are in results.json.</p><input id="search" placeholder="Filter: paper braille, night solid, z19 …" oninput="filterCases()"><label><input id="warnings" type="checkbox" style="width:auto;position:static" onchange="filterCases()"> Warnings only</label>
<script>function filterCases(){const q=document.getElementById('search').value.toLowerCase().split(/\\s+/);const warnings=document.getElementById('warnings').checked;document.querySelectorAll('article').forEach(a=>a.hidden=!(q.every(t=>a.dataset.key.toLowerCase().includes(t))&&(!warnings||a.dataset.warning==='true')))}</script>''' + "".join(cards),encoding="utf8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cache", type=Path)
    parser.add_argument("--gallery-only", action="store_true", help="Rebuild the gallery from existing results, without rendering")
    parser.add_argument("--themes", default=",".join(available_themes()))
    parser.add_argument("--zooms", default="0,5,8,13,16,19")
    parser.add_argument("--lat", type=float, default=42.36)
    parser.add_argument("--lon", type=float, default=-71.06)
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--dithers", default="none", help="Comma-separated none,bayer,atkinson,floyd; relevant to ASCII")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--width", type=int, default=100)
    parser.add_argument("--height", type=int, default=32)
    args = parser.parse_args()
    if args.gallery_only:
        write_gallery(args.out, json.loads((args.out / "results.json").read_text(encoding="utf8"))["cases"])
        return
    if args.cache is None:
        parser.error("--cache is required for rendering")
    args.out.mkdir(parents=True, exist_ok=True)
    source = VectorTileSource({"source": "mvt_url", "mvt_url": "https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}"}, args.cache, "CartoTUI settings QA")
    renderer = Renderer(default_palettes(), subpixel_threshold="stable")
    records = []
    w, h = args.width, args.height
    variants = list(itertools.product(default_palettes(), ("stable", "adaptive", "edge", "fixed", "percentile"), (False, True), (False, True))) if args.full else [("shades", "stable", False, True)]
    try:
        for theme, zoom in itertools.product(args.themes.split(","), map(int, args.zooms.split(","))):
            style = theme_vector_style(theme, {})
            orientation = "bright" if sum(a*b for a,b in zip(style.bg, (.299,.587,.114))) / 255 >= .4 else "dark"
            img = rasterise_view_libcarto(source, args.lat, args.lon, zoom, w*6, h*12, style=style, supersample=6, max_fetch_zoom=min(zoom,14), lazy=True)
            if img is None:
                raise RuntimeError(f"Missing tiles: {theme} z{zoom}")
            for mode, geometry, variant, dither in itertools.product(("ascii", "quadrant", "braille", "half"), ("standard", "solid", "vector-only"), variants, args.dithers.split(",")):
                palette, threshold, shaded, color = variant
                renderer.update_options(subpixel_threshold=threshold, shaded_blocks=shaded)
                start = time.perf_counter()
                rows = renderer.render(img, w, h, color, mode, palette, dither=dither, orientation=orientation, packed=True)
                if geometry == "vector-only":
                    rows = blank_frame(w, h, style.bg)
                elif mode == "braille":
                    improve_braille_readability(rows, style.bg, zoom)
                common = dict(center_lat=args.lat, center_lon=args.lon, z=zoom, term_w=w, term_h=h,
                              canvas_px_w=w*3, canvas_px_h=h*6, style=style)
                if geometry != "standard":
                    draw_solid_geometry(rows, source, **common, max_fetch_zoom=min(zoom,14), vector_only=geometry == "vector-only")
                labels = apply_vector_overlay(rows, source, **common, pmap_max_zoom=min(zoom,14),
                                              max_labels=max(64,w*h//100), detail_labels=True, draw_boundaries=True)
                rows = pack(rows, w, h)
                assert rows.glyph.shape == (h,w)
                assert np.all(rows.glyph <= 0x10FFFF)
                record = dict(theme=theme, zoom=zoom, mode=mode, geometry=geometry, palette=palette,
                              threshold=threshold, shaded=shaded, color=color, dither=dither, labels=labels,
                              ms=round((time.perf_counter()-start)*1000,2), **metrics(rows,style.bg))
                # Exercise both ordinary SSH colour encodings for every frame.
                record["bytes_256"] = len(paint_rows(rows, 0, 0, w, h, [], color_depth=ColorDepth.DEPTH_8_BIT).encode())
                record["bytes_truecolor"] = len(paint_rows(rows, 0, 0, w, h, [], color_depth=ColorDepth.DEPTH_24_BIT).encode())
                warnings = []
                if record["ink_fraction"] < .005:
                    warnings.append("sparse: may be valid geography")
                if mode == "braille" and color and geometry != "vector-only" and record["low_contrast_fraction"] > .1:
                    warnings.append("low dot contrast")
                record["warnings"] = warnings
                if variant == variants[0]:
                    preview = frame_to_png(rows, theme, cell_px=12)
                    pixels = np.asarray(preview.convert("RGB"))
                    light = luminance(pixels)
                    record["pixel_luma_p05"], record["pixel_luma_p95"] = map(float, np.percentile(light, [5, 95]))
                    if record["pixel_luma_p95"] - record["pixel_luma_p05"] < .025:
                        warnings.append("low tonal range: inspect geography/theme")
                records.append(record)
                # Full matrix gets metrics for every combination; gallery keeps
                # representative cases and warnings, avoiding huge image sets.
                if variant == variants[0] or warnings:
                    name = f"{len(records):06d}.png"
                    (preview if variant == variants[0] else frame_to_png(rows,theme,cell_px=12)).save(args.out/name)
                    record["image"] = name
                if args.limit and len(records) >= args.limit:
                    break
            print(f"{theme} z{zoom}: {len(records)} cases", flush=True)
            if args.limit and len(records) >= args.limit:
                break
    finally:
        source.close()
        (args.out/"results.json").write_text(json.dumps({"coverage": vars(args) | {"out":str(args.out),"cache":str(args.cache)}, "cases":records},indent=2),encoding="utf8")
        write_gallery(args.out, records)
    print(f"Completed {len(records)} cases; gallery: {args.out/'index.html'}")


if __name__ == "__main__":
    main()
