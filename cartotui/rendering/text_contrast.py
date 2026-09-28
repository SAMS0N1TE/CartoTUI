"""Keep sparse DOS characters readable without changing their density."""
from functools import lru_cache
import re

import numpy as np

from cartotui.rendering.packed import PackedFrame, DEFAULT

_FG = re.compile(r"(?<!\S)fg:#([0-9a-fA-F]{6})(?![0-9a-fA-F])")


@lru_cache(maxsize=128)
def _colors(colors, background):
    from cartotui.ui.solid_geometry import readable_color
    values = np.asarray(colors, dtype=np.uint32)
    rgb = np.stack(((values >> 16) & 255, (values >> 8) & 255, values & 255), axis=-1)
    # A dot covers little cell area; give its ink text-level contrast.
    adjusted = readable_color(rgb, background, 4.5).astype(np.uint32)
    return (adjusted[:, 0] << 16) | (adjusted[:, 1] << 8) | adjusted[:, 2]


def balance_dos_ink(frame, background):
    """Adjust explicit foreground ink only; preserve cells and backgrounds."""
    background = tuple(background)
    if isinstance(frame, PackedFrame):
        colors, inverse = np.unique(frame.fg, return_inverse=True)
        valid = colors != DEFAULT
        mapped = colors.copy()
        if valid.any():
            mapped[valid] = _colors(tuple(int(c) for c in colors[valid]), background)
        frame.fg = mapped[inverse].reshape(frame.fg.shape)
        frame._rows.clear()
        return frame
    colors = sorted({int(m.group(1), 16) for row in frame for style, _ in row
                     for m in [_FG.search(style)] if m})
    if not colors:
        return frame
    mapped = dict(zip(colors, _colors(tuple(colors), background)))
    return [[(_FG.sub(lambda m: f"fg:#{mapped[int(m.group(1), 16)]:06x}", style), text)
             for style, text in row] for row in frame]
