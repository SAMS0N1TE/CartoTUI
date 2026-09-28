"""Cell-level compatibility with v0.13.0, independent of fragment grouping.

The committed digests were generated with the release Python code and its own
native library. Fixtures exercise palette tones, thin roads, flat fills and radar.
"""
import hashlib
import itertools
import json
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from cartotui.rendering.renderer import Renderer, _native_renderer, default_palettes

FIXTURE = Path(__file__).parent / "fixtures" / "release_cells.json"


def scene(bright):
    image = Image.new("RGB", (96, 64), (235, 231, 220) if bright else (22, 22, 30))
    d = ImageDraw.Draw(image)
    d.rectangle((0, 0, 23, 63), fill=(46, 74, 134))
    d.rectangle((32, 5, 65, 30), fill=(47, 106, 74))
    for x in range(38, 96, 9):
        d.rectangle((x, 37, x+3, 53), fill=(58, 63, 82))
    for width, y in ((1, 14), (2, 28), (4, 56)):
        d.line((0, y, 95, y-8), fill=(50, 50, 50) if bright else (224, 175, 104), width=width)
    return image


def cases():
    for mode, color, shaded, palette, bright, radar, native in itertools.product(
        ("ascii", "quadrant", "braille", "half"), (False, True), (False, True),
        ("shades", "dos5"), (False, True), (False, True), (False, True),
    ):
        # Shading only changes the block/braille reducers.
        if shaded and mode in ("ascii", "half"):
            continue
        yield dict(mode=mode, color=color, shaded=shaded, palette=palette,
                   bright=bright, radar=radar, native=native, dither="none")
    for dither in ("bayer", "atkinson", "floyd"):
        yield dict(mode="ascii", color=True, shaded=False, palette="dos5",
                   bright=False, radar=True, native=True, dither=dither)


def render(case, packed=False):
    r = Renderer(default_palettes(), subpixel_threshold="adaptive",
                 shaded_blocks=case["shaded"], use_native_cells=case["native"])
    img = scene(case["bright"])
    overlay = Image.new("RGBA", img.size, (0, 160, 220, 110)) if case["radar"] else None
    extra = {"packed": True} if packed else {}
    return r.render(img, 24, 16, case["color"], case["mode"],
                    palette_name=case["palette"], dither=case["dither"],
                    orientation="bright" if case["bright"] else "dark",
                    overlay=overlay, **extra)


def digest(rows):
    cells = [(s.strip(), ch) for row in rows for s, text in row for ch in text]
    return hashlib.sha256(json.dumps(cells, ensure_ascii=True).encode()).hexdigest()


@pytest.mark.parametrize("record", [] if __name__ == "__main__" else json.loads(FIXTURE.read_text()))
@pytest.mark.parametrize("packed", [False, True])
def test_release_cells(record, packed):
    if record["case"]["native"] and _native_renderer() is None:
        pytest.skip("native library unavailable")
    assert digest(render(record["case"], packed)) == record["sha256"]


if __name__ == "__main__":
    from cartotui import __version__
    assert __version__ == "0.13.0", "Only the release may generate compatibility fixtures"
    assert _native_renderer() is not None
    FIXTURE.parent.mkdir(exist_ok=True)
    FIXTURE.write_text(json.dumps([dict(case=c, sha256=digest(render(c))) for c in cases()], indent=2))
