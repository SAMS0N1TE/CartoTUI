"""Drive the render worker for real.

Everything else tests the pieces. Nothing ran the function that puts them
together, so a name left behind by a refactor got all the way to a traceback on
startup with a full green suite behind it.

The vector source is stubbed rather than mocked away: the worker must walk its
whole body -- sizing, styling, rasterising, cells, overlays -- and the only way
to be sure it does is to let it, and then look at what came out.
"""
import os
import tempfile
import threading
import time

import pytest
from prompt_toolkit.application.current import create_app_session
from prompt_toolkit.input import DummyInput
from prompt_toolkit.output import DummyOutput

from cartotui.config import Config
from cartotui.ui.app import CartoTUIApp

MODES = ("half", "quadrant", "braille", "ascii")


@pytest.mark.parametrize("panning, expected", [(True, (120, 72, 128)), (False, (240, 144, 256))])
def test_dynamic_pan_reduces_pixels_without_changing_extent(monkeypatch, panning, expected):
    from PIL import Image

    from cartotui.rendering import libcarto_backend

    calls = []
    def raster(source, lat, lon, z, width, height, **kwargs):
        calls.append((width, height, kwargs["tile_px"]))
        return Image.new("RGB", (width, height), (20, 30, 40))

    monkeypatch.setattr(libcarto_backend, "rasterise_view_libcarto", raster)
    app = _app(vector_render_mode="half", vector_scale=3, vector_engine="libcarto")
    app.map_control._panning = lambda: panning
    try:
        assert _drain(app) is not None
        assert calls and all(c == expected for c in calls)
        width, height, tile_px = calls[0]
        assert width / tile_px == 240 / 256
        assert height / tile_px == 144 / 256
    finally:
        app.map_control.shutdown()


def _app(**render):
    cfg = Config()
    # Its own config file: building the app saves a panel layout, and the next
    # test should not inherit this one's.
    cfg.path = os.path.join(tempfile.mkdtemp(prefix="cartotui_worker_"),
                            "config.json")
    cfg.data["traffic"]["enabled"] = False
    cfg.data["traffic"]["source"] = "disabled"
    cfg.data["vector"]["source"] = "mvt_url"
    cfg.data["vector"]["mvt_url"] = ""          # no network: tiles come back None
    cfg.data["render"].update(render)
    with create_app_session(input=DummyInput(), output=DummyOutput()):
        return CartoTUIApp(cfg)


def _drain(app, w=80, h=24, timeout=20.0):
    """Ask for a frame and wait for the worker to hand one back."""
    app.map_control.create_content(w, h)
    app.map_control.request_render(force=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.map_control.create_content(w, h)
        if app.map_control._last_frame is not None:
            return app.map_control._last_frame
        time.sleep(0.05)
    return None


@pytest.mark.parametrize("mode", MODES)
def test_the_worker_produces_a_frame_in_every_mode(mode):
    app = _app(vector_render_mode=mode)
    try:
        frame = _drain(app)
        assert frame is not None, "no frame in %s" % mode
        assert len(frame.rows) == 24
        for row in frame.rows:
            assert sum(len(text) for _style, text in row) >= 1
    finally:
        app.map_control.shutdown()


@pytest.mark.parametrize("mode", MODES)
def test_the_worker_survives_a_raster_source(mode):
    app = _app(raster_render_mode=mode)
    try:
        app.state.set_source("raster")
        assert _drain(app) is not None
    finally:
        app.map_control.shutdown()


def test_the_worker_reports_nothing_to_stderr():
    """A thread that dies takes the map with it and says so only in a trace."""
    seen = []
    real = threading.excepthook

    def hook(args):
        seen.append(args)
        real(args)

    threading.excepthook = hook
    try:
        app = _app()
        try:
            _drain(app)
            for scale in (2, 8):
                app.cfg.data["render"]["vector_scale"] = scale
                app.state.cycle_render_mode()
                _drain(app)
        finally:
            app.map_control.shutdown()
    finally:
        threading.excepthook = real
    assert not seen, "the render thread raised: %r" % (seen,)


@pytest.mark.parametrize("scale", (2, 3, 6, 8))
def test_every_supersample_renders(scale):
    app = _app(vector_scale=scale)
    try:
        assert _drain(app) is not None
    finally:
        app.map_control.shutdown()


def test_a_tiny_terminal_still_renders():
    app = _app()
    try:
        assert _drain(app, w=8, h=3) is not None
    finally:
        app.map_control.shutdown()


def test_the_snapshot_path_runs(tmp_path):
    app = _app()
    try:
        _drain(app)
        out = app.map_control.snapshot_png(str(tmp_path / "s.png"), long_side=512)
        assert out and (tmp_path / "s.png").exists()
    finally:
        app.map_control.shutdown()
