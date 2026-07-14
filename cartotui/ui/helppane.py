
from __future__ import annotations

from prompt_toolkit.filters import Condition
from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.layout import ConditionalContainer, Window
from prompt_toolkit.layout.controls import UIContent, UIControl

_HELP_LINES = [
    ("title", " ┏━━ HELP ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓ "),
    ("text",  " ┃                                                          ┃ "),
    ("text",  " ┃   LOOKS  (start here — one-press visual styles)          ┃ "),
    ("kv",    " ┃   l           cycle to next Look                         ┃ "),
    ("kv",    " ┃   L           open the Looks gallery (click to apply)    ┃ "),
    ("text",  " ┃                                                          ┃ "),
    ("text",  " ┃   NAVIGATION                                             ┃ "),
    ("kv",    " ┃   ↑ ↓ ← →    pan map                                     ┃ "),
    ("kv",    " ┃   Shift+arrow pan ×4                                     ┃ "),
    ("kv",    " ┃   Mouse drag  pan smoothly                               ┃ "),
    ("kv",    " ┃   Click       recentre / select aircraft                 ┃ "),
    ("kv",    " ┃   Wheel       zoom in / out                              ┃ "),
    ("text",  " ┃                                                          ┃ "),
    ("text",  " ┃   ZOOM                                                   ┃ "),
    ("kv",    " ┃   + / -       zoom in / out                              ┃ "),
    ("kv",    " ┃   0..9        jump to zoom level                         ┃ "),
    ("text",  " ┃                                                          ┃ "),
    ("text",  " ┃   SOURCE                                                 ┃ "),
    ("kv",    " ┃   k           cycle map style (OSM / Topo / CARTO ...)   ┃ "),
    ("kv",    " ┃   v           toggle source kind (vector / raster)       ┃ "),
    ("text",  " ┃                                                          ┃ "),
    ("text",  " ┃   DISPLAY                                                ┃ "),
    ("kv",    " ┃   m            view: ascii/quad/braille/pixel            ┃ "),
    ("kv",    " ┃   t           cycle theme (amber/green/paper/dark/...)   ┃ "),
    ("kv",    " ┃   p           cycle palette                              ┃ "),
    ("kv",    " ┃   d           cycle dither (ascii view only)             ┃ "),
    ("kv",    " ┃   s           toggle shaded blocks (quad/braille only)   ┃ "),
    ("kv",    " ┃   c           toggle colour                              ┃ "),
    ("kv",    " ┃   u           cycle threshold (percentile/edge/fixed)    ┃ "),
    ("text",  " ┃                                                          ┃ "),
    ("text",  " ┃   IMAGE ADJUST                                           ┃ "),
    ("kv",    " ┃   [ / ]       brightness  -/+                            ┃ "),
    ("kv",    " ┃   { / }       contrast    -/+                            ┃ "),
    ("kv",    " ┃   \\           reset brightness/contrast                  ┃ "),
    ("text",  " ┃                                                          ┃ "),
    ("text",  " ┃   PLACES                                                 ┃ "),
    ("kv",    " ┃   g           goto lat,lon                               ┃ "),
    ("kv",    " ┃   r           reset to home                              ┃ "),
    ("text",  " ┃                                                          ┃ "),
    ("text",  " ┃   SIDEBAR                                                ┃ "),
    ("kv",    " ┃   Tab         show/hide right sidebar                    ┃ "),
    ("kv",    " ┃   F2          focus map ↔ sidebar                        ┃ "),
    ("kv",    " ┃   F3 / F4     prev / next tab  (works anywhere)          ┃ "),
    ("kv",    " ┃   F5..F8      jump to tab 1..4                           ┃ "),
    ("kv",    " ┃   ^← / ^→     prev / next tab  (terminal-dependent)      ┃ "),
    ("kv",    " ┃   Esc ← / →   prev / next tab  (Alt+arrow alias)         ┃ "),
    ("kv",    " ┃   1..4        jump to tab (when sidebar focused)         ┃ "),
    ("text",  " ┃                                                          ┃ "),
    ("text",  " ┃   APP                                                    ┃ "),
    ("kv",    " ┃   w            widgets launcher (drag / minimise)        ┃ "),
    ("kv",    " ┃   x            save PNG snapshot (titlebar: PNG / HTML)  ┃ "),
    ("kv",    " ┃   Ctrl-S       save profile (loads on next start)        ┃ "),
    ("kv",    " ┃   h / ?       toggle this help                           ┃ "),
    ("kv",    " ┃   q / Ctrl-C  quit                                       ┃ "),
    ("text",  " ┃                                                          ┃ "),
    ("title", " ┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┛ "),
]

class HelpControl(UIControl):
    def is_focusable(self) -> bool:
        return False

    def create_content(self, width: int, height: int) -> UIContent:
        rows = []
        for kind, line in _HELP_LINES:
            line = line.ljust(width)[:width]
            if kind == "title":
                rows.append(to_formatted_text([("class:help.title", line)]))
            elif kind == "kv":
                rows.append(to_formatted_text([("class:help.key", line[:18]),
                                                ("class:help.text", line[18:])]))
            else:
                rows.append(to_formatted_text([("class:help.text", line)]))

        def get_line(i: int):
            if 0 <= i < len(rows):
                return rows[i]
            return to_formatted_text([("class:help.text", " " * width)])

        return UIContent(get_line=get_line, line_count=max(1, len(rows)))

class HelpPane:
    def __init__(self) -> None:
        self.visible = False
        control = HelpControl()
        cond = Condition(lambda: self.visible)
        self.container = ConditionalContainer(
            content=Window(content=control, height=len(_HELP_LINES), style="class:help"),
            filter=cond,
        )

    def __pt_container__(self):
        return self.container

    def toggle(self) -> None:
        self.visible = not self.visible
