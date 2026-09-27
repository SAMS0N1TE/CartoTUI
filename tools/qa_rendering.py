"""Real-tile visual QA and warm performance measurements. Requires network on first run."""

# ruff: noqa: E402
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from prompt_toolkit.output import ColorDepth

from cartotui.rendering.libcarto_backend import _get_renderer, rasterise_view_libcarto
from cartotui.rendering.renderer import Renderer, default_palettes
from cartotui.snapshot import frame_to_png
from cartotui.themes import theme_vector_style
from cartotui.ui.direct_paint import paint_rows
from cartotui.vector_source import VectorTileSource


def median_ms(fn, count=9):
    fn()
    values = []
    for _ in range(count):
        t = time.perf_counter()
        fn()
        values.append((time.perf_counter() - t) * 1000)
    return round(statistics.median(values), 3)


def main():
    p = argparse.ArgumentParser(
        description="Real tile zoom sweep and warm renderer/SSH-output measurements"
    )
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--cache", type=Path, required=True)
    p.add_argument("--baseline-lib", type=Path)
    p.add_argument("--lat", type=float, default=44.4798)
    p.add_argument("--lon", type=float, default=-70.7787)
    p.add_argument("--theme", default="night")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    source = VectorTileSource(
        {"source": "mvt_url", "mvt_url": "https://tiles.versatiles.org/tiles/osm/{z}/{x}/{y}"},
        args.cache,
        "CartoTUI renderer QA",
    )
    style = theme_vector_style(args.theme, {})
    orientation = (
        "dark"
        if sum(a * b for a, b in zip(style.bg, (0.299, 0.587, 0.114))) / 255 < 0.4
        else "bright"
    )
    baseline = None
    if args.baseline_lib:
        from carto_ffi import Renderer as Native

        baseline = Native(str(args.baseline_lib.resolve()))
    records = []
    previews = []
    renderer = Renderer(default_palettes(), subpixel_threshold="stable")
    try:
        for z in range(20):
            # The configured Shortbread endpoint supplies z0-14; exercise
            # overzoom from its last source level for all higher view levels.
            img = rasterise_view_libcarto(
                source,
                args.lat,
                args.lon,
                z,
                720,
                480,
                style=style,
                supersample=6,
                max_fetch_zoom=min(z, 14),
                lazy=True,
            )
            if img is None:
                records.append({"zoom": z, "missing": True})
                print("missing", z, flush=True)
                continue
            item = {"zoom": z, "source_zoom": min(z, 14), "modes": {}}
            for mode in ("ascii", "quadrant", "braille", "half"):
                renderer.update_options(subpixel_threshold="stable")
                fn = lambda img=img, mode=mode: renderer.render(
                    img, 120, 40, True, mode, orientation=orientation
                )
                rows = fn()
                assert len(rows) == 40 and all(sum(len(t) for _, t in row) == 120 for row in rows)
                ms = median_ms(fn)
                item["modes"][mode] = {
                    "cell_ms": ms,
                    "bytes_256": len(
                        paint_rows(
                            rows, 0, 0, 120, 40, [], color_depth=ColorDepth.DEPTH_8_BIT
                        ).encode()
                    ),
                    "idle_bytes": len(
                        paint_rows(rows, 0, 0, 120, 40, [], previous_rows=rows).encode()
                    ),
                }
                if z in (0, 4, 8, 12, 16, 19):
                    preview = frame_to_png(rows, args.theme, cell_px=12)
                    previews.append((f"z{z} {mode} stable", preview))
                if mode == "braille":
                    renderer.update_options(subpixel_threshold="adaptive")
                    item["adaptive_braille_ms"] = median_ms(fn)
            fetch = lambda zz, xx, yy: source.get_raw(zz, xx, yy)

            def raster(r, z=z, fetch=fetch):
                return r.render_viewport(
                    args.lat,
                    args.lon,
                    z,
                    720,
                    480,
                    fetch,
                    style=style,
                    road_width_scale=6,
                    fetch_z=min(z, 14),
                )

            current = _get_renderer()
            item["raster_ms"] = median_ms(lambda raster=raster, current=current: raster(current), 5)
            if baseline:
                old, _ = raster(baseline)
                new, _ = raster(current)
                assert old == new, f"raster pixel regression at z{z}"
                item["baseline_raster_ms"] = median_ms(lambda raster=raster: raster(baseline), 5)
            records.append(item)
            print("zoom", z, json.dumps(item), flush=True)
            (args.out / "measurements.json").write_text(
                json.dumps(records, indent=2), encoding="utf8"
            )
        if previews:
            tw, th = previews[0][1].size
            sheet = Image.new("RGB", (4 * tw, 6 * (th + 26)), (18, 18, 22))
            d = ImageDraw.Draw(sheet)
            for i, (label, img) in enumerate(previews):
                x = (i % 4) * tw
                y = (i // 4) * (th + 26)
                d.text((x + 6, y + 5), label, fill="white")
                sheet.paste(img, (x, y + 26))
            sheet.save(args.out / "zoom-review.png")
    finally:
        source.close()
        if baseline:
            baseline.close()


if __name__ == "__main__":
    main()
