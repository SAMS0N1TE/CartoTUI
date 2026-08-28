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

Off by default; `render.direct_paint` turns it on.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence, Tuple

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
               base_bg: Optional[str] = None) -> str:
    """The escape stream that draws `rows` at (x, y), skipping blocked rects.

    `blocked` is a sequence of (x0, y0, x1, y1) in screen coordinates.
    `base_fg`/`base_bg` are the window's own colours, used wherever a cell
    does not name its own.

    Foreground and background are tracked separately and emitted only on
    change, so a mode whose cells all share one background pays for it once
    per frame rather than per run. Both start unknown, so the first run always
    states both and nothing is inherited from whatever came before.
    """
    out: List[str] = [_SAVE]
    cur_fg = cur_bg = _UNSET
    n = min(height, len(rows))
    for ry in range(n):
        sy = y + ry
        covers = [(bx0, bx1) for bx0, by0, bx1, by1 in blocked if by0 <= sy < by1]
        spans = _uncovered_spans(x, width, covers)
        if not spans:
            continue
        row = rows[ry]
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
                fg, bg = colors_for(style, base_fg, base_bg)
                if fg != cur_fg:
                    out.append(_fg_seq(fg))
                    cur_fg = fg
                if bg != cur_bg:
                    out.append(_bg_seq(bg))
                    cur_bg = bg
                out.append(text[a:b])
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
        super().render(app, layout, is_done)
        if is_done or self.map_source is None or self.map_window is None:
            return
        try:
            blob = self._map_blob()
        except Exception as e:  # never let painting break the frame
            log.debug("direct paint failed (%s); leaving the frame as drawn", e)
            return
        if not blob:
            return
        output = app.output
        output.write_raw(blob)
        output.flush()

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
        return paint_rows(rows, mx0, my0, wp.width, wp.height, blocked,
                          base_fg=base_fg, base_bg=base_bg)

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
