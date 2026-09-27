"""Packed cells through composition; fragments are a lazy compatibility view.

No terminal dependency or ISA assumption: old native libraries and unsupported
terminal depths use the existing fragment output path.
"""

import ctypes as ct
from functools import lru_cache

import numpy as np

DEFAULT = 0xFFFFFFFF


@lru_cache(maxsize=4096)
def _style(style):
    fg = bg = None
    for token in style.split():
        if token.startswith("fg:#"):
            fg = int(token[4:10], 16)
        elif token.startswith("bg:#"):
            bg = int(token[4:10], 16)
    return fg, bg


class PackedFrame:
    def __init__(self, glyph, fg, bg, width, height):
        self.width, self.height = width, height
        self.glyph = np.ascontiguousarray(glyph, dtype=np.uint32).reshape(height, width)
        self.fg = (
            np.full((height, width), DEFAULT, np.uint32)
            if fg is None
            else np.ascontiguousarray(fg, dtype=np.uint32).reshape(height, width)
        )
        self.bg = (
            np.full((height, width), DEFAULT, np.uint32)
            if bg is None
            else np.ascontiguousarray(bg, dtype=np.uint32).reshape(height, width)
        )
        self._rows = {}

    def __len__(self):
        return self.height

    def copy(self):
        other = PackedFrame(
            self.glyph.copy(), self.fg.copy(), self.bg.copy(), self.width, self.height
        )
        other._rows = {k: list(v) for k, v in self._rows.items()}
        return other

    def __getitem__(self, y):
        if isinstance(y, slice):
            return [self[i] for i in range(*y.indices(self.height))]
        if not 0 <= y < self.height:
            raise IndexError(y)
        if y not in self._rows:
            out = []
            for glyph, fg, bg in zip(self.glyph[y], self.fg[y], self.bg[y]):
                style = f"fg:#{fg:06x}" if fg != DEFAULT else ""
                if bg != DEFAULT:
                    style += f" bg:#{bg:06x}"
                ch = chr(glyph)
                if out and out[-1][0] == style:
                    out[-1] = (style, out[-1][1] + ch)
                else:
                    out.append((style, ch))
            self._rows[y] = out
        return self._rows[y]

    def __setitem__(self, y, runs):
        self._rows[y] = list(runs)
        x = 0
        for style, text in runs:
            n = min(len(text), self.width - x)
            if n <= 0:
                break
            fg, bg = _style(style)
            self.glyph[y, x : x + n] = [ord(ch) for ch in text[:n]]
            self.fg[y, x : x + n] = DEFAULT if fg is None else fg
            self.bg[y, x : x + n] = DEFAULT if bg is None else bg
            x += n

    def stamp(self, x, y, text, style):
        if not 0 <= y < self.height:
            return
        left, right = max(0, x), min(self.width, x + len(text))
        if right <= left:
            return
        fg, bg = _style(style)
        self.glyph[y, left:right] = [ord(ch) for ch in text[left - x : right - x]]
        self.fg[y, left:right] = DEFAULT if fg is None else fg
        if bg is not None:
            self.bg[y, left:right] = bg
        self._rows.pop(y, None)

    def apply_stamps(self, plan):
        indices, glyph, fg, bg_indices, bg = plan
        self.glyph.reshape(-1)[indices] = glyph
        self.fg.reshape(-1)[indices] = fg
        self.bg.reshape(-1)[bg_indices] = bg
        self._rows.clear()


def compile_stamps(stamps, width, height):
    """Retain final writes per cell, independently retaining explicit backgrounds."""
    cells, backgrounds = {}, {}
    for x, y, text, style in stamps:
        if not 0 <= y < height:
            continue
        fg, bg = _style(style)
        for i, ch in enumerate(text):
            if 0 <= x + i < width:
                index = y * width + x + i
                cells[index] = (ord(ch), DEFAULT if fg is None else fg)
                if bg is not None:
                    backgrounds[index] = bg
    values = np.array(list(cells.values()), np.uint32).reshape(-1, 2)
    return (
        np.array(list(cells), np.intp),
        values[:, 0],
        values[:, 1],
        np.array(list(backgrounds), np.intp),
        np.array(list(backgrounds.values()), np.uint32),
    )


class TerminalEncoder:
    def __init__(self, lib):
        self.prepare = lib.carto_prepare_terminal
        self.prepare.argtypes = [ct.c_void_p] * 4 + [ct.c_size_t, ct.c_uint]
        self.prepare.restype = None
        self.encode = lib.carto_encode_terminal
        self.encode.argtypes = (
            [ct.c_void_p] * 3 + [ct.c_uint] * 4 + [ct.c_void_p, ct.c_size_t, ct.c_uint]
        )
        self.encode.restype = ct.c_size_t
        self.buffer = None
        self.capacity = 0

    def paint(self, frame, x, y, blocked, fg=None, bg=None, depth=8, previous=None):
        n = frame.width * frame.height
        cells = np.empty((n, 3), np.uint32)

        def resolved(array, base):
            return np.where(
                array == DEFAULT, DEFAULT if base is None else int(base, 16), array
            ).astype(np.uint32)

        colors = resolved(frame.fg, fg), resolved(frame.bg, bg)
        self.prepare(
            frame.glyph.ctypes.data,
            colors[0].ctypes.data,
            colors[1].ctypes.data,
            cells.ctypes.data,
            n,
            depth,
        )
        visible = np.ones((frame.height, frame.width), np.uint8)
        for x0, y0, x1, y1 in blocked:
            visible[
                max(0, y0 - y) : min(frame.height, y1 - y),
                max(0, x0 - x) : min(frame.width, x1 - x),
            ] = 0
        capacity = n * 64 + 64
        if self.capacity < capacity:
            self.buffer = ct.create_string_buffer(capacity)
            self.capacity = capacity
        used = self.encode(
            cells.ctypes.data,
            previous.ctypes.data if previous is not None else None,
            visible.ctypes.data,
            frame.width,
            frame.height,
            x,
            y,
            self.buffer,
            self.capacity,
            depth,
        )
        if used == ct.c_size_t(-1).value:
            raise ValueError("Native terminal output exceeded capacity")
        blob = ct.string_at(self.buffer, used)
        if previous is not None and used > n * 2:
            # Dense damage can cost more CUP/color bytes than repainting. Measure
            # both streams only for large updates; sparse/idle updates stay cheap.
            full = self.encode(
                cells.ctypes.data,
                None,
                visible.ctypes.data,
                frame.width,
                frame.height,
                x,
                y,
                self.buffer,
                self.capacity,
                depth,
            )
            if full < used:
                blob = ct.string_at(self.buffer, full)
        return blob.decode("utf8"), cells


def encoder():
    try:
        from cartotui.rendering.libcarto_backend import _get_renderer

        return TerminalEncoder(_get_renderer().lib)
    except (AttributeError, OSError, RuntimeError):
        return None
