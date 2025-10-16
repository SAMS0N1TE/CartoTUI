#!/usr/bin/env python3
# ascii_map/rendering/quadrant_mode.py
"""
Quadrant (2x2 block) renderer.
Uses Unicode block elements ▖ ▗ ▘ ▙ ▚ ▛ ▜ ▝ ▞ ▟ to encode four subpixels per cell.
Higher density than ASCII; maps small 2x2 pixel regions into a single terminal glyph.
"""

from __future__ import annotations
from typing import List, Tuple
import numpy as np
from PIL import Image

StyleRun = Tuple[str, str]
LineFrag = List[StyleRun]
FrameFrag = List[LineFrag]

# Unicode quadrants (https://en.wikipedia.org/wiki/Block_Elements)
# Bits: TL TR BL BR  (top-left, top-right, bottom-left, bottom-right)
_QUAD_GLYPHS = {
    0b0000: " ",
    0b0001: "▗",
    0b0010: "▖",
    0b0011: "▄",
    0b0100: "▝",
    0b0101: "▐",
    0b0110: "▞",
    0b0111: "▟",
    0b1000: "▘",
    0b1001: "▚",
    0b1010: "▌",
    0b1011: "▙",
    0b1100: "▀",
    0b1101: "▜",
    0b1110: "▛",
    0b1111: "█",
}


class QuadrantRenderer:
    name = "quadrant"

    @staticmethod
    def _rgb_to_style(r: int, g: int, b: int) -> str:
        return f"fg:#{r:02x}{g:02x}{b:02x}"

    def render(
        self,
        img: Image.Image,
        term_w: int,
        term_h: int,
        use_color: bool,
        palette: str = "",
    ) -> FrameFrag:
        if term_w <= 0 or term_h <= 0:
            return [[("", "")]]

        # Convert to RGB and grayscale
        img = img.convert("RGB")
        # Each cell represents 2x2 pixels
        w = term_w * 2
        h = term_h * 2
        img = img.resize((w, h), Image.LANCZOS)
        arr = np.asarray(img, dtype=np.uint8)
        gray = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]).astype(np.float32) / 255.0

        frame: FrameFrag = []
        for cy in range(0, h, 2):
            line: LineFrag = []
            last_style = ""
            buf = []
            for cx in range(0, w, 2):
                sub = gray[cy:cy+2, cx:cx+2]
                if sub.size < 4:
                    ch = " "
                else:
                    bits = 0
                    # Threshold 0.5 luminance for filled pixel
                    if sub[0, 0] < 0.5: bits |= 0b1000
                    if sub[0, 1] < 0.5: bits |= 0b0100
                    if sub[1, 0] < 0.5: bits |= 0b0010
                    if sub[1, 1] < 0.5: bits |= 0b0001
                    ch = _QUAD_GLYPHS.get(bits, " ")
                if use_color:
                    r, g, b = arr[cy:cy+2, cx:cx+2].mean(axis=(0, 1)).astype(int)
                    style = self._rgb_to_style(r, g, b)
                    if style != last_style and buf:
                        line.append((last_style, "".join(buf)))
                        buf = []
                    buf.append(ch)
                    last_style = style
                else:
                    buf.append(ch)
            if buf:
                line.append((last_style, "".join(buf)))
            frame.append(line)
        return frame
