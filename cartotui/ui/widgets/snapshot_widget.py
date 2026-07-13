from __future__ import annotations

import os

from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget

_QUAL = [(1024, "small"), (1600, "medium"), (2560, "large"), (4096, "max")]


@register_widget
class SnapshotWidget(Widget):
    name = "snapshot"
    title = "Snapshot"
    default_width = 30
    default_top = 15
    default_left = 34
    default_visible = False

    def build(self, width: int) -> None:
        sn = self.ctx.cfg["snapshot"]
        ls = int(sn.get("png_long_side", 1600))
        qname = next((n for v, n in _QUAL if v == ls), f"{ls}px")
        self.add_kv("PNG size", f"{qname} ({ls}px)", width, action=self._cycle_quality)
        self.add_kv("Open after", "on" if sn.get("open_after", True) else "off",
                    width, action=self._toggle_open)
        self.add_button("Save PNG", width, lambda: self._snap("png"))
        self.add_button("Save HTML", width, lambda: self._snap("html"))
        self.add_button("Open folder", width, lambda: self._snap("open"))
        last = getattr(self.ctx.state, "last_snapshot", "")
        if last:
            self.add_dim("last: " + os.path.basename(last), width)

    def _snap(self, kind: str) -> None:
        if self.ctx.snapshot is not None:
            self.ctx.snapshot(kind)

    def _cycle_quality(self) -> None:
        sizes = [v for v, _ in _QUAL]
        cur = int(self.ctx.cfg["snapshot"].get("png_long_side", 1600))
        i = sizes.index(cur) if cur in sizes else 1
        self._apply({"png_long_side": sizes[(i + 1) % len(sizes)]})

    def _toggle_open(self) -> None:
        cur = bool(self.ctx.cfg["snapshot"].get("open_after", True))
        self._apply({"open_after": not cur})

    def _apply(self, patch: dict) -> None:
        self.ctx.cfg.update({"snapshot": patch})
        try:
            self.ctx.cfg.save()
        except Exception:
            pass
        self.ctx.refresh()
