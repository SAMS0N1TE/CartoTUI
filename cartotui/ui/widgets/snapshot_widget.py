from __future__ import annotations

import os

from cartotui.ui.widgets.base import Widget
from cartotui.ui.widgets.registry import register_widget

_QUAL = [(1024, "small"), (1600, "medium"), (2560, "large"), (4096, "max")]
_MODES = ["map", "ascii"]

_MODE_BLURB = {
    "map": "clean re-render, full detail",
    "ascii": "the terminal view, glyphs and all",
}


@register_widget
class SnapshotWidget(Widget):
    name = "snapshot"
    title = "Snapshot"
    default_width = 34
    default_top = 15
    default_left = 34
    default_visible = False

    def build(self, width: int) -> None:
        sn = self.ctx.cfg["snapshot"]
        mode = str(sn.get("png_mode", "map"))
        ls = int(sn.get("png_long_side", 1600))
        qname = next((n for v, n in _QUAL if v == ls), f"{ls}px")

        self.add_section("PNG", width)
        self.add_kv("Style", mode, width, action=self._cycle_mode)
        self.add_dim(_MODE_BLURB.get(mode, ""), width)
        self.add_kv("Size", f"{qname} ({ls}px)", width, action=self._cycle_quality)

        if mode == "map":
            self.add_kv("City labels", _on(sn.get("png_labels", False)), width,
                        action=lambda: self._toggle("png_labels"))
            self.add_kv("Aircraft", _on(sn.get("png_aircraft", False)), width,
                        action=lambda: self._toggle("png_aircraft"))
            self.add_kv("Radar", _on(sn.get("png_radar", True)), width,
                        action=lambda: self._toggle("png_radar", default=True))
            if sn.get("png_labels") or sn.get("png_aircraft"):
                engine = self.ctx.cfg["render"].get("vector_engine", "libcarto")
                if engine == "libcarto":
                    self.add_dim("uses python renderer (slower)", width)
        else:
            self.add_dim("includes labels + aircraft", width)

        self.add_section("Output", width)
        self.add_kv("Open after", _on(sn.get("open_after", True)), width,
                    action=lambda: self._toggle("open_after", default=True))
        self.add_button("Save PNG", width, lambda: self._snap("png"))
        self.add_button("Save HTML", width, lambda: self._snap("html"))
        self.add_button("Open folder", width, lambda: self._snap("open"))
        last = getattr(self.ctx.state, "last_snapshot", "")
        if last:
            self.add_dim("last: " + os.path.basename(last), width)

    def _snap(self, kind: str) -> None:
        if self.ctx.snapshot is not None:
            self.ctx.snapshot(kind)

    def _cycle_mode(self) -> None:
        cur = str(self.ctx.cfg["snapshot"].get("png_mode", "map"))
        i = _MODES.index(cur) if cur in _MODES else 0
        self._apply({"png_mode": _MODES[(i + 1) % len(_MODES)]})

    def _cycle_quality(self) -> None:
        sizes = [v for v, _ in _QUAL]
        cur = int(self.ctx.cfg["snapshot"].get("png_long_side", 1600))
        i = sizes.index(cur) if cur in sizes else 1
        self._apply({"png_long_side": sizes[(i + 1) % len(sizes)]})

    def _toggle(self, key: str, default: bool = False) -> None:
        cur = bool(self.ctx.cfg["snapshot"].get(key, default))
        self._apply({key: not cur})

    def _apply(self, patch: dict) -> None:
        self.ctx.cfg.update({"snapshot": patch})
        try:
            self.ctx.cfg.save()
        except Exception:
            pass
        self.ctx.refresh()


def _on(v) -> str:
    return "on" if v else "off"
