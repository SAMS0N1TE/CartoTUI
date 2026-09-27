"""Paint the map region straight to the terminal, around prompt_toolkit.

prompt_toolkit keeps a `Screen` of `Char` objects and diffs it against the
previous frame. That is the right model for the chrome -- a status bar that
changes one field costs one field. It is the wrong model for a full-screen map,
where a pan changes every cell and the diff pays to discover that: 12 ms a frame
against roughly 3 ms to simply write the bytes.

So the map window reports blank content, prompt_toolkit composites the sidebar
and the widget panels over that blank region as it always did, and this paints
the map underneath them afterwards -- only into the columns no floating window
covers, taken from the write positions prompt_toolkit itself recorded. Painting
after rather than before is what keeps a panel that has just moved from leaving
a hole: prompt_toolkit blanks the vacated cells, then this fills them in the
same frame.

Enabled by default on VT-capable outputs; `render.direct_paint` controls it.
"""

from __future__ import annotations

import logging
import time
from functools import lru_cache
from typing import Dict, List, Optional, Sequence, Tuple

from prompt_toolkit.output import ColorDepth
from prompt_toolkit.output.vt100 import _EscapeCodeCache
from prompt_toolkit.renderer import Renderer as _PTRenderer

log = logging.getLogger("cartotui.direct_paint")

LineFrag = Sequence[Tuple[str, str]]

# DECSC / DECRC. Saves and restores cursor position *and* the SGR attributes,
# which is what keeps prompt_toolkit's own cursor and style tracking valid
# across a write it does not know about.
_SAVE = "\x1b7"
_RESTORE = "\x1b8"
_RESET = "\x1b[0m"

# Distinct from None, which is a legitimate colour meaning "terminal default".
_UNSET = object()

_COLOR_CACHE: Dict[tuple, tuple] = {}
_COLOR_CACHE_MAX = 200000


def colors_for(style: str, base_fg: Optional[str], base_bg: Optional[str]):
    """The (fg, bg) a cell ends up with, as 6-digit hex or None.

    prompt_toolkit merges the *window's* style underneath the cell's, so a map
    cell written as just "fg:#c8a068" still takes its background from
    `class:map`. Painting only what the cell string carries leaves the
    background as whatever escape happened to be in effect -- which is why the
    modes that set no background picked up bands of the chrome's colour, and
    half-block, which always sets one, did not.
    """
    key = (style, base_fg, base_bg)
    hit = _COLOR_CACHE.get(key)
    if hit is not None:
        return hit
    fg = bg = None
    for part in style.split():
        if part.startswith("fg:#") and len(part) >= 10:
            fg = part[4:10]
        elif part.startswith("bg:#") and len(part) >= 10:
            bg = part[4:10]
    out = (fg or base_fg, bg or base_bg)
    if len(_COLOR_CACHE) >= _COLOR_CACHE_MAX:
        _COLOR_CACHE.clear()
    _COLOR_CACHE[key] = out
    return out


# Memoised: these are hit once per fragment, ~9.5k times a frame, and parsing
# three hex bytes and formatting them each time costs more than the rest of the
# paint put together.
_FG_SEQ: Dict[Optional[str], str] = {None: "\x1b[39m"}
_BG_SEQ: Dict[Optional[str], str] = {None: "\x1b[49m"}
_SEQ_CACHE_MAX = 200000


def _fg_seq(h: Optional[str]) -> str:
    seq = _FG_SEQ.get(h)
    if seq is None:
        seq = "\x1b[38;2;%d;%d;%dm" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        if len(_FG_SEQ) >= _SEQ_CACHE_MAX:
            _FG_SEQ.clear()
            _FG_SEQ[None] = "\x1b[39m"
        _FG_SEQ[h] = seq
    return seq


def _bg_seq(h: Optional[str]) -> str:
    seq = _BG_SEQ.get(h)
    if seq is None:
        seq = "\x1b[48;2;%d;%d;%dm" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
        if len(_BG_SEQ) >= _SEQ_CACHE_MAX:
            _BG_SEQ.clear()
            _BG_SEQ[None] = "\x1b[49m"
        _BG_SEQ[h] = seq
    return seq


_CUBE = (0, 95, 135, 175, 215, 255)
_CUBE_NEAREST = tuple(min(range(6), key=lambda i: (v - _CUBE[i]) ** 2)
                      for v in range(256))
_GRAY_NEAREST = tuple(min(range(24), key=lambda i: abs(s - 3 * (8 + 10 * i)))
                      for s in range(766))


def _xterm256(r, g, b):
    """Exact nearest fixed palette entry, without searching all 240 colours.

    The cube separates into independent channels; the nearest gray depends
    only on their sum. Ties use the earlier palette index, like prompt_toolkit.
    Entries 0-15 are terminal-customisable and deliberately excluded.
    """
    ri, gi, bi = _CUBE_NEAREST[r], _CUBE_NEAREST[g], _CUBE_NEAREST[b]
    gray = _GRAY_NEAREST[r + g + b]
    gv = 8 + 10 * gray
    cube_distance = (r - _CUBE[ri]) ** 2 + (g - _CUBE[gi]) ** 2 + (b - _CUBE[bi]) ** 2
    gray_distance = (r - gv) ** 2 + (g - gv) ** 2 + (b - gv) ** 2
    return 16 + 36 * ri + 6 * gi + bi if cube_distance <= gray_distance else 232 + gray


@lru_cache(maxsize=65536)
def _color_seq(h, background, depth):
    if depth == ColorDepth.DEPTH_24_BIT:
        return _bg_seq(h) if background else _fg_seq(h)
    if h is None:
        return "\x1b[49m" if background else "\x1b[39m"
    if depth == ColorDepth.DEPTH_8_BIT:
        rgb = int(h, 16)
        index = _xterm256(rgb >> 16, (rgb >> 8) & 255, rgb & 255)
        return f"\x1b[{48 if background else 38};5;{index}m"
    # Quantise the two pixel colours independently. Text contrast correction
    # (forcing similar fg/bg apart at 16 colours) corrupts half-block images.
    cache = _EscapeCodeCache(depth)
    codes = list(cache._colors_to_code("" if background else h,
                                      h if background else ""))
    return "\x1b[" + ";".join(codes) + "m" if codes else ""


@lru_cache(maxsize=65536)
def _style_sequences(style, base_fg, base_bg, depth):
    fg, bg = colors_for(style, base_fg, base_bg)
    return _color_seq(fg, False, depth), _color_seq(bg, True, depth)


def _uncovered_spans(x0: int, width: int,
                     covers: Sequence[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """Columns of [x0, x0+width) left over once `covers` are removed."""
    if not covers:
        return [(x0, x0 + width)]
    spans = [(x0, x0 + width)]
    for cx0, cx1 in covers:
        nxt: List[Tuple[int, int]] = []
        for s0, s1 in spans:
            if cx1 <= s0 or cx0 >= s1:
                nxt.append((s0, s1))
                continue
            if cx0 > s0:
                nxt.append((s0, cx0))
            if cx1 < s1:
                nxt.append((cx1, s1))
        spans = nxt
        if not spans:
            break
    return spans


def paint_rows(rows: Sequence[LineFrag], x: int, y: int, width: int, height: int,
               blocked: Sequence[Tuple[int, int, int, int]],
               base_fg: Optional[str] = None,
               base_bg: Optional[str] = None,
               color_depth=ColorDepth.DEPTH_24_BIT,
               previous_rows=None) -> str:
    """The escape stream that draws `rows` at (x, y), skipping blocked rects.

    `blocked` is a sequence of (x0, y0, x1, y1) in screen coordinates.
    `base_fg`/`base_bg` are the window's own colours, used wherever a cell
    does not name its own.

    Foreground and background are tracked separately and emitted only on
    change, so a mode whose cells all share one background pays for it once
    per frame rather than per run. Both start unknown, so the first run always
    states both and nothing is inherited from whatever came before.
    """
    out: List[str] = [_SAVE, _RESET]
    cur_fg = cur_bg = _UNSET
    n = min(height, len(rows))
    for ry in range(n):
        if previous_rows is not None and ry < len(previous_rows) and rows[ry] == previous_rows[ry]:
            continue
        sy = y + ry
        covers = [(bx0, bx1) for bx0, by0, bx1, by1 in blocked if by0 <= sy < by1]
        spans = _uncovered_spans(x, width, covers)
        if not spans:
            continue
        row = rows[ry]
        if not covers:
            # Almost all map rows are completely visible. Avoid constructing
            # and clipping a second list of every fragment on this hot path.
            out.append("\x1b[%d;%dH" % (sy + 1, x + 1))
            remaining = width
            for style, text in row:
                if not text:
                    continue
                fg_seq, bg_seq = _style_sequences(style, base_fg, base_bg, color_depth)
                if fg_seq != cur_fg:
                    out.append(fg_seq)
                    cur_fg = fg_seq
                if bg_seq != cur_bg:
                    out.append(bg_seq)
                    cur_bg = bg_seq
                out.append(text if len(text) <= remaining else text[:remaining])
                remaining -= len(text)
                if remaining <= 0:
                    break
            continue
        # Flatten the row's runs into (column, style, text) so a span can be cut
        # out of the middle of one.
        col = x
        pieces: List[Tuple[int, int, str, str]] = []
        for style, text in row:
            if not text:
                continue
            end = col + len(text)
            pieces.append((col, end, style, text))
            col = end
            if col >= x + width:
                break
        for s0, s1 in spans:
            out.append("\x1b[%d;%dH" % (sy + 1, s0 + 1))
            for p0, p1, style, text in pieces:
                if p1 <= s0 or p0 >= s1:
                    continue
                a = max(p0, s0) - p0
                b = min(p1, s1) - p0
                if b <= a:
                    continue
                fg_seq, bg_seq = _style_sequences(style, base_fg, base_bg, color_depth)
                # Different RGBs often map to the same 256/16-colour entry.
                # Track what is transmitted, rather than the original RGB.
                if fg_seq != cur_fg:
                    out.append(fg_seq)
                    cur_fg = fg_seq
                if bg_seq != cur_bg:
                    out.append(bg_seq)
                    cur_bg = bg_seq
                out.append(text[a:b])
    if len(out) == 2:
        return ""
    out.append(_RESET)
    out.append(_RESTORE)
    return "".join(out)


class DirectPaintRenderer(_PTRenderer):
    """A prompt_toolkit renderer that paints the map itself.

    Everything prompt_toolkit does is left alone; this only adds a second write
    after its own, covering the map window's area minus any floating window on
    top of it.
    """

    map_source = None  # set by the app: an object with .direct_paint_rows()
    map_window = None

    def render(self, app, layout, is_done: bool = False) -> None:
        if self._last_screen is None:
            self._paint_previous = None
            self._packed_previous = None
        self._paint_depth = app.color_depth
        super().render(app, layout, is_done)
        if is_done or self.map_source is None or self.map_window is None:
            return
        try:
            t0 = time.perf_counter()
            blob = self._map_blob()
            self.map_source.state.last_encode_ms = (time.perf_counter() - t0) * 1000
        except Exception as e:  # never let painting break the frame
            log.debug("direct paint failed (%s); leaving the frame as drawn", e)
            return
        if not blob:
            return
        output = app.output
        t0 = time.perf_counter()
        output.write_raw(blob)
        output.flush()
        self.map_source.note_output(time.perf_counter() - t0, len(blob.encode("utf8")))

    def _map_blob(self) -> Optional[str]:
        screen = self._last_screen
        if screen is None:
            return None
        positions = screen.visible_windows_to_write_positions
        wp = positions.get(self.map_window)
        if wp is None or wp.width < 1 or wp.height < 1:
            return None
        rows = self.map_source.direct_paint_rows(wp.width, wp.height)
        if not rows:
            return None
        base_fg, base_bg = self._window_colors()

        mx0, my0 = wp.xpos, wp.ypos
        mx1, my1 = mx0 + wp.width, my0 + wp.height
        blocked = []
        for win, other in positions.items():
            if win is self.map_window:
                continue
            ox0, oy0 = other.xpos, other.ypos
            ox1, oy1 = ox0 + other.width, oy0 + other.height
            if ox1 <= mx0 or ox0 >= mx1 or oy1 <= my0 or oy0 >= my1:
                continue
            blocked.append((ox0, oy0, ox1, oy1))
        depth = getattr(self, "_paint_depth", ColorDepth.DEPTH_24_BIT)
        signature = (mx0, my0, wp.width, wp.height, tuple(blocked), base_fg, base_bg, depth)
        from cartotui.rendering.packed import PackedFrame, encoder
        if isinstance(rows, PackedFrame) and depth in (ColorDepth.DEPTH_8_BIT, ColorDepth.DEPTH_24_BIT):
            if not hasattr(self, "_native_encoder"):
                self._native_encoder = encoder()
            if self._native_encoder is not None:
                previous = getattr(self, "_packed_previous", None)
                old = previous[1] if previous and previous[0] == signature else None
                try:
                    blob, cells = self._native_encoder.paint(
                        rows, mx0, my0, blocked, base_fg, base_bg,
                        8 if depth == ColorDepth.DEPTH_8_BIT else 24, old)
                except Exception as exc:
                    log.warning("native terminal encoder unavailable (%s); using fragments", exc)
                    self._native_encoder = None
                else:
                    self._packed_previous = (signature, cells)
                    self._paint_previous = None
                    return blob
        self._packed_previous = None
        previous = getattr(self, "_paint_previous", None)
        old_rows = previous[1] if previous and previous[0] == signature else None
        blob = paint_rows(rows, mx0, my0, wp.width, wp.height, blocked,
                          base_fg=base_fg, base_bg=base_bg, color_depth=depth,
                          previous_rows=old_rows)
        self._paint_previous = (signature, [list(row) for row in rows])
        return blob

    def _window_colors(self):
        """The map window's own colours, the way prompt_toolkit resolves them.

        Its style sits under every cell's, so painting without it leaves the
        background to whatever escape was last in effect.
        """
        try:
            style = self.map_window.style
            if callable(style):
                style = style()
            attrs = self._attrs_for_style[style or ""]
            return attrs.color or None, attrs.bgcolor or None
        except Exception:
            return None, None
