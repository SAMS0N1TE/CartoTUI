
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from prompt_toolkit.application import Application
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import Float, FloatContainer, HSplit, Layout, VSplit, Window
from prompt_toolkit.styles import DynamicStyle

from cartotui.cache import TileCache
from cartotui.config import Config
from cartotui.rendering.renderer import Renderer, default_palettes
from cartotui.sources import build_source_list
from cartotui.themes import make_style
from cartotui.traffic import AircraftRegistry, build_source as build_traffic_source
from cartotui.ui.compass import Compass
from cartotui.ui.goto import GotoPrompt
from cartotui.ui.helppane import HelpPane
from cartotui.ui.map_control import MapControl
from cartotui.ui.sidebar import Sidebar
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

        self.vector_source = VectorTileSource(
            self.cfg["vector"],
            cache_dir=Path(self.cfg["cache"]["dir"]) / "vector",
            user_agent=ncfg["user_agent"],
        )

        rcfg = self.cfg["render"]
        self.renderer = Renderer(
            default_palettes(),
            subpixel_threshold=str(rcfg.get("subpixel_threshold", "adaptive")),
            subpixel_percentile=float(rcfg.get("subpixel_percentile", 55)),
            shaded_blocks=bool(rcfg.get("shaded_blocks", False)),
        )

        traffic_cfg = self.cfg.data.get("traffic", {}) if hasattr(self.cfg, "data") else {}
        self.aircraft_registry = AircraftRegistry(
            stale_timeout_s=float(traffic_cfg.get("stale_timeout_s", 60.0)),
        )
        self.traffic_source = build_traffic_source(traffic_cfg, self.aircraft_registry)

        self.map_control = MapControl(
            self.cfg, self.state, self.renderer, self.cache,
            vector_source=self.vector_source,
            aircraft_registry=self.aircraft_registry,
            on_select_aircraft=self._on_select_aircraft,
        )

        self.titlebar = TitleBar(self.state, title=self.cfg["app"].get("title", "CartoTUI"))
        self.statusbar = StatusBar(self.state, self.cfg)
        self.compass = Compass(self.state)
        self.help_pane = HelpPane()
        self.goto_prompt = GotoPrompt(on_submit=self._on_goto_submit)

        sidebar_cfg = self.cfg["viewport"]
        self.sidebar = Sidebar(
            self.state, self.cfg,
            get_traffic=lambda: self.traffic_source,
            get_registry=lambda: self.aircraft_registry,
            on_select_aircraft=self._on_select_aircraft,
            on_search_submit=self._on_search_submit,
            width_chars=int(sidebar_cfg.get("sidebar_width", 36)),
        )
        self.sidebar.control.on_perf_changed = (
            lambda: self.map_control.request_render(force=True))

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

        self.map_window = Window(
            content=self.map_control,
            wrap_lines=False,
            dont_extend_width=False,
            dont_extend_height=False,
            style="class:map",
        )
        self.map_control.bind_window(self.map_window)

        vp = self.cfg["viewport"]

        floats = [Float(
            content=self.sidebar.container,
            top=1, right=1, width=self.sidebar.width_chars,
        )]
        map_area = FloatContainer(content=self.map_window, floats=floats)

        rows = []
        if vp.get("show_titlebar", True):
            rows.append(Window(content=self.titlebar, height=1, style="class:titlebar"))

        rows.append(map_area)

        if vp.get("show_toolbar", True):
            rows.append(Window(content=self.toolbar, height=1, style="class:toolbar"))
        if vp.get("show_statusbar", True):
            rows.append(Window(content=self.statusbar, height=1, style="class:statusbar"))

        rows.append(self.help_pane)

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
            refresh_interval=0.5,
        )

    def run(self) -> None:
        try:
            log.info("Starting CartoTUI %s", os.environ.get("USER", ""))
            self.traffic_source.start()
            self.app.run()
        finally:
            try:
                self.traffic_source.stop(timeout_s=2.0)
            except Exception:
                pass
            self.map_control.shutdown()

    def _toggle_help(self) -> None:
        self.help_pane.toggle()
        self.app.invalidate()

    def _show_goto(self) -> None:
        self.goto_prompt.show()

    def _on_goto_submit(self, lat: float, lon: float, z) -> None:
        self.map_control.goto(lat, lon, z)
        self.map_control.focus()

    def _on_select_aircraft(self, icao) -> None:
        self.state.select_aircraft(icao)
        self.map_control.request_render()
        self.app.invalidate()

    def _on_search_submit(self, text: str) -> None:
        from cartotui.ui.goto import _parse
        text = (text or "").strip()
        if not text:
            return
        parsed = _parse(text)
        if parsed is None:
            self.state.set_info(f"Could not resolve: {text}")
            return
        lat, lon, z = parsed
        self.map_control.goto(lat, lon, z)

    def _quit(self) -> None:
        self.app.exit()

    def _initial_source_idx(self) -> int:
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
        self.state.set_info("No other sources available")

    def _reload_theme(self) -> None:
        self.cfg.update({"ui": {"theme": self.state.theme}})
        self._current_style = make_style(self.cfg)
        self.map_control.request_render()
        self.app.invalidate()

    def _build_key_bindings(self) -> KeyBindings:
        kb = KeyBindings()
        step = int(self.cfg["ui"].get("pan_step_cells", 6))

        active = Condition(lambda: not self.goto_prompt.visible)

        from prompt_toolkit.application.current import get_app

        def _map_active() -> bool:
            if self.goto_prompt.visible:
                return False
            try:
                app = get_app()
                if app.layout.current_window is self.sidebar.window:
                    return False
            except Exception:
                pass
            return True
        map_active = Condition(_map_active)

        @kb.add("q", filter=map_active)
        @kb.add("c-c")
        def _(event):
            event.app.exit()

        @kb.add("tab", filter=active)
        def _(event):
            self.state.toggle_sidebar()
            if not self.state.sidebar_visible:
                try:
                    event.app.layout.focus(self.map_window)
                except Exception:
                    pass
            event.app.invalidate()

        @kb.add("f2", filter=active)
        def _(event):
            try:
                if event.app.layout.current_window is self.sidebar.window:
                    event.app.layout.focus(self.map_window)
                else:
                    if self.state.sidebar_visible:
                        event.app.layout.focus(self.sidebar.window)
            except Exception:
                pass

        sidebar_visible_filter = Condition(
            lambda: self.state.sidebar_visible and not self.goto_prompt.visible
        )

        @kb.add("c-right", filter=sidebar_visible_filter)
        @kb.add("escape", "right", filter=sidebar_visible_filter)
        @kb.add("f4", filter=sidebar_visible_filter)
        def _(event):
            self.sidebar.control.cycle_tab(+1)
            event.app.invalidate()

        @kb.add("c-left", filter=sidebar_visible_filter)
        @kb.add("escape", "left", filter=sidebar_visible_filter)
        @kb.add("f3", filter=sidebar_visible_filter)
        def _(event):
            self.sidebar.control.cycle_tab(-1)
            event.app.invalidate()

        for i in range(5):
            @kb.add(f"f{5 + i}", filter=sidebar_visible_filter)
            def _(event, idx=i):
                self.sidebar.control.set_tab(idx)
                event.app.invalidate()

        @kb.add("up", filter=map_active)
        def _(event):
            self.map_control.pan(0, -step)

        @kb.add("down", filter=map_active)
        def _(event):
            self.map_control.pan(0, step)

        @kb.add("left", filter=map_active)
        def _(event):
            self.map_control.pan(-step, 0)

        @kb.add("right", filter=map_active)
        def _(event):
            self.map_control.pan(step, 0)

        @kb.add("s-up", filter=map_active)
        def _(event):
            self.map_control.pan(0, -step * 4)

        @kb.add("s-down", filter=map_active)
        def _(event):
            self.map_control.pan(0, step * 4)

        @kb.add("s-left", filter=map_active)
        def _(event):
            self.map_control.pan(-step * 4, 0)

        @kb.add("s-right", filter=map_active)
        def _(event):
            self.map_control.pan(step * 4, 0)

        @kb.add("+", filter=map_active)
        @kb.add("=", filter=map_active)
        def _(event):
            self.map_control.zoom(+1)

        @kb.add("-", filter=map_active)
        @kb.add("_", filter=map_active)
        def _(event):
            self.map_control.zoom(-1)

        for digit in range(10):
            @kb.add(str(digit), filter=map_active)
            def _(event, d=digit):
                self.map_control.zoom(d - self.state.z)
                self.state.set_zoom(d)
                self.state.set_info(f"Zoom → {d}")
                self.map_control.request_render()

        @kb.add("v", filter=map_active)
        def _(event):
            self.state.toggle_source()
            self.state.set_info(f"Source → {self.state.source}")
            self.map_control.request_render()

        @kb.add("m", filter=map_active)
        def _(event):
            self.state.cycle_render_mode()
            self.state.set_info(f"View → {self.state.render_mode}")
            self.map_control.request_render()

        @kb.add("t", filter=map_active)
        def _(event):
            self.state.cycle_theme()
            self.state.set_info(f"Theme → {self.state.theme}")
            self._reload_theme()

        @kb.add("p", filter=map_active)
        def _(event):
            self.state.cycle_palette(list(default_palettes().keys()))
            self.state.set_info(f"Palette → {self.state.palette}")
            self.map_control.request_render()

        @kb.add("d", filter=map_active)
        def _(event):
            self.state.cycle_dither()
            self.state.set_info(f"Dither → {self.state.dither}")
            self.map_control.request_render()

        @kb.add("s", filter=map_active)
        def _(event):
            self.state.toggle_shaded()
            self.state.set_info(f"Shaded {'on' if self.state.shaded_blocks else 'off'}")
            self.map_control.request_render()

        @kb.add("c", filter=map_active)
        def _(event):
            self.state.toggle_color()
            self.state.set_info(f"Color {'on' if self.state.color else 'off'}")
            self.map_control.request_render()

        @kb.add("k", filter=map_active)
        def _(event):
            self._cycle_source()

        @kb.add("u", filter=map_active)
        def _(event):
            self.state.cycle_threshold()
            self.state.set_info(f"Threshold → {self.state.threshold_mode}")
            self.map_control.request_render()

        @kb.add("[", filter=map_active)
        def _(event):
            self.state.adjust_brightness(-0.1)
            self.state.set_info(f"Brightness → {self.state.brightness:.2f}")
            self.map_control.request_render()

        @kb.add("]", filter=map_active)
        def _(event):
            self.state.adjust_brightness(+0.1)
            self.state.set_info(f"Brightness → {self.state.brightness:.2f}")
            self.map_control.request_render()

        @kb.add("{", filter=map_active)
        def _(event):
            self.state.adjust_contrast(-0.1)
            self.state.set_info(f"Contrast → {self.state.contrast:.2f}")
            self.map_control.request_render()

        @kb.add("}", filter=map_active)
        def _(event):
            self.state.adjust_contrast(+0.1)
            self.state.set_info(f"Contrast → {self.state.contrast:.2f}")
            self.map_control.request_render()

        @kb.add("\\", filter=map_active)
        def _(event):
            self.state.reset_image_adjust()
            self.state.set_info("Image adjust reset")
            self.map_control.request_render()

        @kb.add("h", filter=map_active)
        @kb.add("?", filter=map_active)
        def _(event):
            self._toggle_help()

        @kb.add("g", filter=map_active)
        def _(event):
            self._show_goto()

        @kb.add("r", filter=map_active)
        def _(event):
            self.map_control.goto(
                float(self.cfg["map"]["center_lat"]),
                float(self.cfg["map"]["center_lon"]),
                int(self.cfg["map"]["zoom"]),
            )

        from prompt_toolkit.key_binding import merge_key_bindings

        def _sidebar_focused() -> bool:
            try:
                return get_app().layout.current_window is self.sidebar.window
            except Exception:
                return False
        sidebar_kb_filter = Condition(_sidebar_focused)
        sidebar_kb = self.sidebar.keybindings()
        wrapped = KeyBindings()
        for binding in sidebar_kb.bindings:
            wrapped.add(*binding.keys, filter=sidebar_kb_filter)(binding.handler)

        return merge_key_bindings([kb, wrapped])
