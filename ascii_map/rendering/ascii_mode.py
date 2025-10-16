#!/usr/bin/env python3
# ascii_map/rendering/ascii_mode.py
"""
Dedicated ASCII renderer backend.
Keeps same algorithm as baseline in renderer.py but separated for modular registration.
"""

from __future__ import annotations
from typing import List, Tuple
import numpy as np
from PIL import Image

StyleRun = Tuple[str, str]
LineFrag = List[StyleRun]
FrameFrag = List[LineFrag]

class AsciiRenderer:
    name = "ascii"

    def _resize(self, img: Image.Image, w: int, h: int) -> Image.Image:
        if img.width == w and img.height == h:
            return img
        return img.resize((w, h), Image.LANCZOS)

    @staticmethod
    def _rgb_to_style(r: int, g: int, b: int) -> str:
        return f"fg:#{r:02x}{g:02x}{b:02x}"

    def render(
        self,
        img: Image.Image,
        w: int,
        h: int,
        use_color: bool,
        palette: str,
    ) -> FrameFrag:
        if w <= 0 or h <= 0:
            return [[("", "")]]

        if img.mode != "RGB":
            img = img.convert("RGB")

        img = self._resize(img, w, h)
        arr = np.asarray(img, dtype=np.uint8)
        lum = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]) / 255.0
        glyphs = np.array(list(palette)) if palette else np.array(list(" ."))
        idx = np.clip((lum * (len(glyphs) - 1)).astype(int), 0, len(glyphs) - 1)

        frame: FrameFrag = []
        if use_color:
            for y in range(h):
                line: LineFrag = []
                last_style = ""
                buf = []
                for x in range(w):
                    r, g, b = arr[y, x]
                    style = self._rgb_to_style(r, g, b)
                    ch = glyphs[idx[y, x]]
                    if style != last_style and buf:
                        line.append((last_style, "".join(buf)))
                        buf = []
                    buf.append(ch)
                    last_style = style
                if buf:
                    line.append((last_style, "".join(buf)))
                frame.append(line)
        else:
            for y in range(h):
                frame.append([("", "".join(glyphs[idx[y, :]].tolist()))])
        return frame
