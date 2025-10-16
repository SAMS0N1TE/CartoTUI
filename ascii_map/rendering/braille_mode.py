#!/usr/bin/env python3
# ascii_map/rendering/braille_mode.py
"""
Braille (2x4) renderer.
Encodes eight subpixels per terminal cell using Unicode Braille patterns.
Higher density than quadrant mode. Good for fine map detail in small terminals.
"""

from __future__ import annotations
from typing import List, Tuple
import numpy as np
from PIL import Image

StyleRun = Tuple[str, str]
LineFrag = List[StyleRun]
FrameFrag = List[LineFrag]

# Braille bit positions:
#  dots: 1 4
#        2 5
#        3 6
#        7 8
# Unicode = 0x2800 | bits
DOT_BITS = (
    (0x01, 0x08),  # row 0: col 0 -> dot1, col 1 -> dot4
    (0x02, 0x10),  # row 1: col 0 -> dot2, col 1 -> dot5
    (0x04, 0x20),  # row 2: col 0 -> dot3, col 1 -> dot6
    (0x40, 0x80),  # row 3: col 0 -> dot7, col 1 -> dot8
)

class BrailleRenderer:
    name = "braille"

    @staticmethod
    def _rgb_to_style(r: int, g: int, b: int) -> str:
        return f"fg:#{r:02x}{g:02x}{b:02x}"

    @staticmethod
    def _to_braille_char(block: np.ndarray, threshold: float = 0.5) -> str:
        """
        block: (4,2) grayscale in [0,1], 0=black.
        threshold compares darkness; darker than threshold sets the dot.
        """
        bits = 0
        for ry in range(4):
            for cx in range(2):
                if block[ry, cx] < threshold:
                    bits |= DOT_BITS[ry][cx]
        return chr(0x2800 | bits)

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

        # Each terminal cell -> 2x4 pixels
        w = term_w * 2
        h = term_h * 4

        img = img.convert("RGB").resize((w, h), Image.LANCZOS)
        arr = np.asarray(img, dtype=np.uint8)
        gray = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]).astype(np.float32) / 255.0

        frame: FrameFrag = []
        for cy in range(0, h, 4):
            line: LineFrag = []
            last_style = ""
            buf = []
            for cx in range(0, w, 2):
                block_g = gray[cy:cy+4, cx:cx+2]
                if block_g.shape != (4, 2):
                    ch = " "
                    style = last_style
                else:
                    ch = self._to_braille_char(block_g, threshold=0.5)
                    if use_color:
                        r, g, b = arr[cy:cy+4, cx:cx+2].mean(axis=(0, 1)).astype(int)
                        style = self._rgb_to_style(r, g, b)
                    else:
                        style = ""
                if style != last_style and buf:
                    line.append((last_style, "".join(buf)))
                    buf = []
                buf.append(ch)
                last_style = style
            if buf:
                line.append((last_style, "".join(buf)))
            frame.append(line if line else [("", "")])
        return frame
