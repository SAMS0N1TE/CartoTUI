"""Top-level application composition for CartoTUI."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, VSplit, Window
from prompt_toolkit.styles import DynamicStyle

from cartotui.cache import TileCache
from cartotui.config import Config
from cartotui.rendering.renderer import Renderer, default_palettes
from cartotui.sources import build_source_list
from cartotui.themes import make_style
from cartotui.ui.compass import Compass
from cartotui.ui.goto import GotoPrompt
from cartotui.ui.helppane import HelpPane
from cartotui.ui.map_control import MapControl
from cartotui.ui.state import MapState
from cartotui.ui.statusbar import StatusBar
from cartotui.ui.titlebar import TitleBar
from cartotui.ui.toolbar import Toolbar
from cartotui.vector_source import VectorTileSource

log = logging.getLogger("cartotui.app")


class CartoTUIApp:
    def __init__(self, cfg: Optional[Config] = None) -> None:
        self.cfg = cfg or Config.load()
        self.state = MapState(self.cfg)

        # Build the source registry. The user's configured tile_url / vector
        # source becomes the initial selection; if not in the registry it's
        # added as a custom entry at the end.
        self.sources = build_source_list(self.cfg.data)
        self.state.source_idx = self._initial_source_idx()

        ncfg = self.cfg["network"]
        self.cache = TileCache(
            url_template=ncfg["tile_url"],
            cache_dir=Path(self.cfg["cache"]["dir"]),
            user_agent=ncfg["user_agent"],
            connect_timeout=float(ncfg["connect_timeout_s"]),
            read_timeout=float(ncfg["read_timeout_s"]),
            retries=int(ncfg["retries"]),
            parallel_downloads=int(ncfg["parallel_downloads"]),
        )

        # Vector tile source — reads PMTiles or hits a vector tile URL.
        self.vector_source = VectorTileSource(
            self.cfg["vector"],
            cache_dir=Path(self.cfg["cache"]["dir"]) / "vector",
            user_agent=ncfg["user_agent"],
        )

        rcfg = self.cfg["render"]
        self.renderer = Renderer(
            default_palettes(),
            subpixel_threshold=str(rcfg.get("subpixel_threshold", "percentile")),
            subpixel_percentile=float(rcfg.get("subpixel_percentile", 55)),
            shaded_blocks=bool(rcfg.get("shaded_blocks", False)),
        )
        self.map_control = MapControl(
            self.cfg, self.state, self.renderer, self.cache,
            vector_source=self.vector_source,
        )

        # Widgets
        self.titlebar = TitleBar(self.state, title=self.cfg["app"].get("title", "CartoTUI"))
        self.statusbar = StatusBar(self.state, self.cfg)
        self.compass = Compass(self.state)
        self.help_pane = HelpPane()
        self.goto_prompt = GotoPrompt(on_submit=self._on_goto_submit)

        palettes = list(default_palettes().keys())
        self.toolbar = Toolbar(
            self.state,
            self.map_control,
            on_help=self._toggle_help,
            on_quit=self._quit,
            on_goto=self._show_goto,
            palettes=palettes,
            on_theme_changed=self._reload_theme,
            on_cycle_source=self._cycle_source,
        )

        # Layout
        self.map_window = Window(
            content=self.map_control,
            wrap_lines=False,
            dont_extend_width=False,
            dont_extend_height=False,
            style="class:map",
        )
        self.map_control.bind_window(self.map_window)

        vp = self.cfg["viewport"]
        rows = []
        if vp.get("show_titlebar", True):
            rows.append(Window(content=self.titlebar, height=1, style="class:titlebar"))

        body = VSplit([
            self.map_window,
            Window(width=1, char="│", style="class:border"),
            Window(content=self.compass, width=9, style="class:compass"),
        ])
        rows.append(body)

        if vp.get("show_toolbar", True):
            rows.append(Window(content=self.toolbar, height=1, style="class:toolbar"))
        if vp.get("show_statusbar", True):
            rows.append(Window(content=self.statusbar, height=1, style="class:statusbar"))

        # The help pane is a conditional row so it folds away when hidden.
        rows.append(self.help_pane)

        # Goto prompt sits above status; conditional too.
        rows.insert(-1, self.goto_prompt)

        self.root = HSplit(rows)

        self.kb = self._build_key_bindings()
        self._current_style = make_style(self.cfg)
        self.app = Application(
            layout=Layout(self.root, focused_element=self.map_window),
            key_bindings=self.kb,
            full_screen=True,
            mouse_support=bool(self.cfg["ui"].get("mouse", True)),
            style=DynamicStyle(lambda: self._current_style),
            refresh_interval=0.5,  # keep status timing live
        )

    # ------------------------------------------------------------------
    # Run / lifecycle
    # ------------------------------------------------------------------

    def run(self) -> None:
        try:
            log.info("Starting CartoTUI %s", os.environ.get("USER", ""))
            self.app.run()
        finally:
            self.map_control.shutdown()

    # ------------------------------------------------------------------
    # Action handlers
    # ------------------------------------------------------------------

    def _toggle_help(self) -> None:
        self.help_pane.toggle()
        self.app.invalidate()

    def _show_goto(self) -> None:
        self.goto_prompt.show()

    def _on_goto_submit(self, lat: float, lon: float, z) -> None:
        self.map_control.goto(lat, lon, z)
        self.map_control.focus()

    def _quit(self) -> None:
        self.app.exit()

    def _initial_source_idx(self) -> int:
        """Find which registry entry matches the user's current config."""
        cur_raster = self.cfg["network"].get("tile_url", "")
        v = self.cfg["vector"]
        cur_vector_backend = v.get("source")
        cur_protomaps_url = v.get("protomaps_api_url", "")
        cur_pmtiles = v.get("pmtiles_url", "")
        cur_mvt = v.get("mvt_url", "")
        configured_mode = self.cfg["map"].get("mode", "vector")

        for idx, src in enumerate(self.sources):
            if src.kind == "raster" and src.url_template == cur_raster:
                if configured_mode != "vector":
                    return idx
            if src.kind == "vector" and src.vector_backend == cur_vector_backend:
                if cur_vector_backend == "protomaps_api" and src.url_template == cur_protomaps_url:
                    return idx
                if cur_vector_backend == "pmtiles_url" and (cur_pmtiles == src.pmtiles_url or src.pmtiles_url == ""):
                    return idx
                if cur_vector_backend == "mvt_url" and src.url_template == cur_mvt:
                    return idx
        return 0

    def _cycle_source(self) -> None:
        if not self.sources:
            return
        # Skip sources that need a key we don't have, to avoid silently
        # showing a blank map.
        current = self.state.source_idx
        n = len(self.sources)
        for step in range(1, n + 1):
            idx = (current + step) % n
            src = self.sources[idx]
            if src.needs_key:
                key = self.cfg["vector"].get("protomaps_api_key", "")
                if not key:
                    continue
            self.state.source_idx = idx
            self.map_control.swap_to_source(src)
            self.state.set_info(f"Source → {src.name}")
            return
        # No usable sources found beyond current.
        self.state.set_info("No other sources available")

    def _reload_theme(self) -> None:
        """Rebuild the prompt_toolkit style from the current state.theme."""
        # Sync the cfg snapshot so make_style sees the new theme.
        self.cfg.update({"ui": {"theme": self.state.theme}})
        self._current_style = make_style(self.cfg)
        # Vector renderer reads theme directly from snapshot, so re-render too.
        self.map_control.request_render()
        self.app.invalidate()

    # ------------------------------------------------------------------
    # Key bindings
    # ------------------------------------------------------------------

    def _build_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()
        step = int(self.cfg["ui"].get("pan_step_cells", 6))

        # Disable map keybindings while goto prompt is visible.
        active = Condition(lambda: not self.goto_prompt.visible)

        @kb.add("q", filter=active)
        @kb.add("c-c")
        def _(event):
            event.app.exit()

        @kb.add("up", filter=active)
        def _(event):
            self.map_control.pan(0, -step)

        @kb.add("down", filter=active)
        def _(event):
            self.map_control.pan(0, step)

        @kb.add("left", filter=active)
        def _(event):
            self.map_control.pan(-step, 0)

        @kb.add("right", filter=active)
        def _(event):
            self.map_control.pan(step, 0)

        @kb.add("s-up", filter=active)
        def _(event):
            self.map_control.pan(0, -step * 4)

        @kb.add("s-down", filter=active)
        def _(event):
            self.map_control.pan(0, step * 4)

        @kb.add("s-left", filter=active)
        def _(event):
            self.map_control.pan(-step * 4, 0)

        @kb.add("s-right", filter=active)
        def _(event):
            self.map_control.pan(step * 4, 0)

        @kb.add("+", filter=active)
        @kb.add("=", filter=active)
        def _(event):
            self.map_control.zoom(+1)

        @kb.add("-", filter=active)
        @kb.add("_", filter=active)
        def _(event):
            self.map_control.zoom(-1)

        for digit in range(10):
            @kb.add(str(digit), filter=active)
            def _(event, d=digit):
                self.map_control.zoom(d - self.state.z)
                self.state.set_zoom(d)
                self.state.set_info(f"Zoom → {d}")
                self.map_control.request_render()

        @kb.add("v", filter=active)
        def _(event):
            self.state.toggle_source()
            self.state.set_info(f"Source → {self.state.source}")
            self.map_control.request_render()

        @kb.add("m", filter=active)
        def _(event):
            self.state.cycle_render_mode()
            self.state.set_info(f"View → {self.state.render_mode}")
            self.map_control.request_render()

        @kb.add("t", filter=active)
        def _(event):
            self.state.cycle_theme()
            self.state.set_info(f"Theme → {self.state.theme}")
            self._reload_theme()

        @kb.add("p", filter=active)
        def _(event):
            self.state.cycle_palette(list(default_palettes().keys()))
            self.state.set_info(f"Palette → {self.state.palette}")
            self.map_control.request_render()

        @kb.add("d", filter=active)
        def _(event):
            self.state.cycle_dither()
            self.state.set_info(f"Dither → {self.state.dither}")
            self.map_control.request_render()

        @kb.add("s", filter=active)
        def _(event):
            self.state.toggle_shaded()
            self.state.set_info(f"Shaded {'on' if self.state.shaded_blocks else 'off'}")
            self.map_control.request_render()

        @kb.add("c", filter=active)
        def _(event):
            self.state.toggle_color()
            self.state.set_info(f"Color {'on' if self.state.color else 'off'}")
            self.map_control.request_render()

        @kb.add("k", filter=active)
        def _(event):
            self._cycle_source()

        @kb.add("u", filter=active)
        def _(event):
            self.state.cycle_threshold()
            self.state.set_info(f"Threshold → {self.state.threshold_mode}")
            self.map_control.request_render()

        # Brightness — Shift+= / Shift+-
        @kb.add("[", filter=active)
        def _(event):
            self.state.adjust_brightness(-0.1)
            self.state.set_info(f"Brightness → {self.state.brightness:.2f}")
            self.map_control.request_render()

        @kb.add("]", filter=active)
        def _(event):
            self.state.adjust_brightness(+0.1)
            self.state.set_info(f"Brightness → {self.state.brightness:.2f}")
            self.map_control.request_render()

        # Contrast — { / }
        @kb.add("{", filter=active)
        def _(event):
            self.state.adjust_contrast(-0.1)
            self.state.set_info(f"Contrast → {self.state.contrast:.2f}")
            self.map_control.request_render()

        @kb.add("}", filter=active)
        def _(event):
            self.state.adjust_contrast(+0.1)
            self.state.set_info(f"Contrast → {self.state.contrast:.2f}")
            self.map_control.request_render()

        @kb.add("\\", filter=active)
        def _(event):
            self.state.reset_image_adjust()
            self.state.set_info("Image adjust reset")
            self.map_control.request_render()

        @kb.add("h", filter=active)
        @kb.add("?", filter=active)
        def _(event):
            self._toggle_help()

        @kb.add("g", filter=active)
        def _(event):
            self._show_goto()

        @kb.add("r", filter=active)
        def _(event):
            self.map_control.goto(
                float(self.cfg["map"]["center_lat"]),
                float(self.cfg["map"]["center_lon"]),
                int(self.cfg["map"]["zoom"]),
            )

        return kb
