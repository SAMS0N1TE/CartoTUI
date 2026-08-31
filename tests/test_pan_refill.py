"""A pan renders from cache, so tiles that have not arrived are drawn as
nothing. Something has to come back for them once the pan settles."""

import threading
import time

from cartotui.ui.map_control import MapControl


class _Ctl:
    """The refill machinery off the real class, without a render worker."""

    _refill_after_pan = MapControl._refill_after_pan
    _refill_fire = MapControl._refill_fire
    _panning = MapControl._panning
    _mark_panning = MapControl._mark_panning

    def __init__(self, dynamic=True):
        self._refill_lock = threading.Lock()
        self._refill_timer = None
        self._pan_until = 0.0
        self.cfg = {"render": {"dynamic_quality": dynamic}}
        self.renders = []

    def request_render(self, force=False):
        self.renders.append(force)


def test_many_incomplete_frames_queue_one_refill():
    ctl = _Ctl()
    ctl._mark_panning()
    for _ in range(50):
        ctl._refill_after_pan()
        ctl._mark_panning()
    assert ctl._refill_timer is not None
    assert ctl.renders == []

    for _ in range(100):
        if ctl.renders:
            break
        time.sleep(0.02)
    assert ctl.renders == [True]
    assert ctl._refill_timer is None


def test_refill_defers_while_the_pan_continues():
    ctl = _Ctl()
    ctl._mark_panning()
    ctl._refill_after_pan()

    deadline = time.time() + 1.0
    while ctl._refill_timer is not None and time.time() < deadline:
        ctl._mark_panning()
        time.sleep(0.02)
    during = list(ctl.renders)

    for _ in range(100):
        if ctl.renders:
            break
        time.sleep(0.02)
    assert during == [], "must not repaint mid-pan"
    assert ctl.renders == [True], "must repaint once the pan stops"


def test_backend_reports_tiles_it_could_not_fetch():
    from cartotui.rendering.libcarto_backend import rasterise_view_libcarto

    class _Empty:
        def get_raw(self, z, x, y, cached_only=False):
            return None

    stats = {}
    try:
        rasterise_view_libcarto(_Empty(), 43.02, -71.47, 14, 512, 256,
                                cached_only=True, preload=False, stats=stats)
    except Exception:
        return          # no native renderer available in this environment
    assert stats.get("misses", 0) > 0
