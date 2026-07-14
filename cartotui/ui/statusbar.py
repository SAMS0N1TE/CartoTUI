
from __future__ import annotations

from prompt_toolkit.formatted_text import to_formatted_text
from prompt_toolkit.layout.controls import UIContent, UIControl

from cartotui.config import Config
from cartotui.ui.state import MapState


class StatusBar(UIControl):
    def __init__(self, state: MapState, cfg: Config) -> None:
        self.state = state
        self.cfg = cfg

    def is_focusable(self) -> bool:
        return False

    def create_content(self, width: int, height: int) -> UIContent:
        color = "color" if self.state.color else "mono"
        latency = self.state.last_render_ms
        show_latency = self.cfg["ui"].get("show_latency", True)

        left = (
            f" ▌ {self.state.source.upper():<6} "
            f"VIEW {self.state.render_mode.upper():<8} "
            f"PAL {self.state.palette:<12} "
            f"DITH {self.state.dither.upper():<8} "
            f"{color.upper()} "
        )
        right_parts = []
        if show_latency:
            warn = latency > 250
            right_parts.append(("class:statusbar.warn" if warn else "class:statusbar",
                                f"  {latency:5.1f} ms render "))

        info = self.state.current_info()
        info_seg = f"⟨ {info} ⟩ " if info else ""

        runs = [("class:statusbar", left)]
        runs.append(("class:statusbar.dim", " " * 1))
        runs.append(("class:statusbar", info_seg))
        rendered_left_mid = sum(len(t) for _s, t in runs)
        right_text = "".join(t for _s, t in right_parts)
        gap = max(0, width - rendered_left_mid - len(right_text))
        runs.append(("class:statusbar.dim", " " * gap))
        runs.extend(right_parts)

        rendered = "".join(t for _s, t in runs)
        if len(rendered) > width:
            runs = [("class:statusbar", rendered[:width])]
        elif len(rendered) < width:
            runs.append(("class:statusbar.dim", " " * (width - len(rendered))))

        formatted = to_formatted_text(runs)
        return UIContent(
            get_line=lambda i: formatted if i == 0 else [("class:statusbar", " " * width)],
            line_count=1,
        )
