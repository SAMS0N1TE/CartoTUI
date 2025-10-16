#!/usr/bin/env python3
# ascii_map/rendering/renderer.py
"""
Rendering dispatcher and baseline ASCII backend.

- Common API: Renderer.render(img, term_w, term_h, use_color, mode, palette_name)
- Backends may register via Renderer.register(mode, backend)
- Style format: list[list[tuple[str, str]]] suitable for prompt_toolkit FormattedText
  where style strings use "fg:#RRGGBB", "bold", "reverse" tokens.

This module includes a reliable built-in ASCII backend so the app works
even before optional specialized backends are added (quadrant, braille).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from PIL import Image
import numpy as np

StyleRun = Tuple[str, str]                # (style, text)
LineFrag = List[StyleRun]                 # one terminal row as runs
FrameFrag = List[LineFrag]                # full terminal frame as rows

__all__ = [
    "Renderer",
    "RenderBackend",
    "default_palettes",
    "StyleRun",
    "LineFrag",
    "FrameFrag",
]

# -------------------------
# Palettes
# -------------------------

def default_palettes() -> Dict[str, str]:
    # Matches original monolith defaults.
    return {
        "dot_only": " .",
        "ascii_basic": " .:-=+*#%@",
        "ascii_dense": " .'`^\",:;Il!i~+_-?][}{1)(|\\/*tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$",
        "blocks": " ▏▎▍▌▋▊▉█",
        "shades": " ░▒▓█",
    }

# -------------------------
# Backends
# -------------------------

class RenderBackend:
    """Interface for all renderers."""
    name: str = "base"

    def render(
        self,
        img: Image.Image,
        term_w: int,
        term_h: int,
        use_color: bool,
        palette: str,
    ) -> FrameFrag:
        raise NotImplementedError


class AsciiBackend(RenderBackend):
    """
    Baseline ASCII renderer.
    - Downsamples to (term_w, term_h)
    - Maps luminance to palette index
    - Optionally colors glyphs with average RGB
    """

    name = "ascii"

    @staticmethod
    def _resize_for_grid(img: Image.Image, w: int, h: int) -> Image.Image:
        # Favor quality. ANTIALIAS is LANCZOS in recent Pillow.
        if img.width == w and img.height == h:
            return img
        return img.resize((w, h), Image.LANCZOS)

    @staticmethod
    def _rgb_to_style(r: int, g: int, b: int) -> str:
        # prompt_toolkit accepts "fg:#RRGGBB"
        return f"fg:#{r:02x}{g:02x}{b:02x}"

    def render(
        self,
        img: Image.Image,
        term_w: int,
        term_h: int,
        use_color: bool,
        palette: str,
    ) -> FrameFrag:
        if term_w < 1 or term_h < 1:
            return [[("", "")]]

        # Ensure RGB
        if img.mode != "RGB":
            img = img.convert("RGB")

        # Downsample to cell grid
        small = self._resize_for_grid(img, term_w, term_h)
        arr = np.asarray(small, dtype=np.uint8)  # (H, W, 3)

        # Per-pixel luminance (Rec. 601)
        lum = (0.299 * arr[..., 0] + 0.587 * arr[..., 1] + 0.114 * arr[..., 2]).astype(np.float32)
        # Normalize to [0, 1]
        lum /= 255.0

        # Palette mapping
        glyphs = np.array(list(palette))
        if glyphs.size == 0:
            glyphs = np.array(list(" ."))
        # Index by brightness
        idx = np.clip((lum * (glyphs.size - 1)).round().astype(np.int32), 0, glyphs.size - 1)

        # Build lines with simple run-length merging
        H, W = idx.shape
        frame: FrameFrag = []
        if use_color:
            # Style per cell from RGB
            for y in range(H):
                line: LineFrag = []
                run_style = None
                run_text = []
                for x in range(W):
                    ch = glyphs[idx[y, x]]
                    r, g, b = arr[y, x].tolist()
                    style = self._rgb_to_style(r, g, b)
                    if style != run_style and run_text:
                        line.append((run_style, "".join(run_text)))
                        run_text = []
                    run_style = style
                    run_text.append(ch)
                if run_text:
                    line.append((run_style, "".join(run_text)))
                frame.append(line if line else [("", "")])
        else:
            # Monochrome. Merge entire line when possible.
            for y in range(H):
                text = "".join(glyphs[idx[y, :]].tolist())
                frame.append([("", text)])
        return frame

# -------------------------
# Dispatcher
# -------------------------

@dataclass
class Renderer:
    """
    Rendering strategy holder.
    Use register() to add new modes, e.g., 'quadrant', 'braille'.
    """
    palettes: Dict[str, str]
    default_palette: str = "ascii_dense"

    def __post_init__(self):
        self._backends: Dict[str, RenderBackend] = {}
        # Always provide baseline ASCII
        self.register("ascii", AsciiBackend())

    def register(self, mode: str, backend: RenderBackend) -> None:
        self._backends[mode] = backend

    def get_palette(self, name: Optional[str]) -> str:
        if name and name in self.palettes:
            return self.palettes[name]
        if self.default_palette in self.palettes:
            return self.palettes[self.default_palette]
        # Fallback
        return default_palettes()["ascii_basic"]

    def render(
        self,
        img: Image.Image,
        term_w: int,
        term_h: int,
        use_color: bool,
        mode: str = "ascii",
        palette_name: Optional[str] = None,
    ) -> FrameFrag:
        backend = self._backends.get(mode)
        if backend is None:
            # Fallback to ascii if unknown mode requested
            backend = self._backends["ascii"]
        palette = self.get_palette(palette_name)
        return backend.render(img, term_w, term_h, use_color, palette)
