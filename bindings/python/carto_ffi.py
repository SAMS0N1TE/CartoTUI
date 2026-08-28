import ctypes
import math
import os
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from ctypes import (
    POINTER,
    c_float,
    Structure,
    byref,
    c_bool,
    c_char,
    c_double,
    c_int,
    c_int32,
    c_size_t,
    c_ubyte,
    c_uint8,
    c_uint32,
    c_void_p,
    cast,
)

_HERE = os.path.dirname(os.path.abspath(__file__))
_BUILD_DIR = os.path.normpath(os.path.join(_HERE, "..", "..", "libcarto", "build"))

if sys.platform == "win32":
    _LIB_NAMES = ("carto.dll", "libcarto.dll")
elif sys.platform == "darwin":
    _LIB_NAMES = ("libcarto.dylib", "carto.dylib")
else:
    _LIB_NAMES = ("libcarto.so", "carto.so")

def _search_dirs():
    yield _BUILD_DIR
    # Frozen builds (PyInstaller) unpack to a temp dir that is not laid out
    # relative to this file.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        yield os.path.join(meipass, "libcarto", "build")
        yield meipass


def _find_default_lib():
    override = os.environ.get("CARTOTUI_LIBCARTO")
    if override:
        return override
    for d in _search_dirs():
        for name in _LIB_NAMES:
            cand = os.path.join(d, name)
            if os.path.exists(cand):
                return cand
    return os.path.join(_BUILD_DIR, _LIB_NAMES[0])

_DEFAULT_DLL = _find_default_lib()

CARTO_FMT_RGB565 = 2
_ROAD_PRIO_MAX = 10

class CartoRGB(Structure):
    _pack_ = 1
    _fields_ = [("r", c_uint8), ("g", c_uint8), ("b", c_uint8)]

class CartoStyle(Structure):
    _pack_ = 1
    _fields_ = [
        ("bg", CartoRGB), ("water", CartoRGB), ("park", CartoRGB), ("building", CartoRGB),
        ("road_color", CartoRGB),
        ("road_width", c_uint8 * (_ROAD_PRIO_MAX + 1)),
        ("road_color_by_prio", CartoRGB * (_ROAD_PRIO_MAX + 1)),
        ("label_color", CartoRGB), ("halo_color", CartoRGB),
        ("aircraft_color", CartoRGB), ("aircraft_selected_color", CartoRGB),
        ("aircraft_emergency_color", CartoRGB), ("aircraft_label_color", CartoRGB),
        ("aircraft_halo_color", CartoRGB),
        ("draw_labels", c_bool),
    ]

class CartoArena(Structure):
    _fields_ = [("base", c_void_p), ("size", c_size_t), ("used", c_size_t), ("peak", c_size_t)]

class CartoFB(Structure):
    _fields_ = [("width", c_int), ("height", c_int), ("format", c_int), ("stride", c_int),
                ("pixels", c_void_p), ("cell_color", c_void_p), ("cell_cols", c_int), ("cell_rows", c_int)]

CARTO_CELL_ASCII, CARTO_CELL_QUADRANT, CARTO_CELL_BRAILLE, CARTO_CELL_HALF = 0, 1, 2, 3
CARTO_THRESH_ADAPTIVE, CARTO_THRESH_GLOBAL, CARTO_THRESH_FIXED = 0, 1, 2
CARTO_ORIENT_DARK, CARTO_ORIENT_BRIGHT, CARTO_ORIENT_GUESS = 0, 1, 2

class CartoCellOpts(Structure):
    _fields_ = [
        ("mode", c_int32), ("cols", c_int32), ("rows", c_int32),
        ("mono", c_int32), ("want_color", c_int32), ("orientation", c_int32),
        ("threshold_mode", c_int32),
        ("black_pct", c_float), ("white_pct", c_float),
        ("tile_grid", c_int32),
        ("signal_floor", c_float), ("signal_gamma", c_float),
        ("shaded", c_int32), ("palette_len", c_int32),
        ("palette", POINTER(c_uint32)),
    ]

class CartoViewport(Structure):
    _fields_ = [("lat", c_double), ("lon", c_double), ("zoom", c_int), ("fb_w", c_int), ("fb_h", c_int),
                ("tile_px", c_int), ("scale", c_int32), ("origin_x", c_int32), ("origin_y", c_int32)]

def tile_center(x, y, z):
    n = 2.0 ** z
    lon = (x + 0.5) / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + 0.5) / n))))
    return lat, lon

class Renderer:
    """Handle on the native renderer.

    One scratch arena and one style struct are shared by every caller, and the
    native side carves its context out of that arena while holding a live
    pointer to the style. Two threads rendering at once therefore hand each
    other overlapping memory: the second carto_begin lands on the first one's
    context, and the first then draws through a framebuffer pointer that is no
    longer its own. Once the other thread returns and Python frees its pixel
    buffer, that write goes into freed memory and the process dies inside
    carto_put_px, with no Python traceback to show for it.

    Renders are therefore serialised on `lock`. Pass a style to `render_viewport`
    rather than calling `set_vector_style` separately, so both land under it.
    """

    def __init__(self, dll_path=None):
        self.lib = ctypes.CDLL(dll_path or _DEFAULT_DLL)
        L = self.lib
        L.carto_fb_init.argtypes = [POINTER(CartoFB), c_int, c_int, c_int, c_void_p]
        L.carto_fb_init.restype = c_int
        L.carto_style_default.argtypes = [POINTER(CartoStyle)]
        L.carto_style_default.restype = None
        L.carto_begin.argtypes = [POINTER(CartoArena), POINTER(CartoFB), POINTER(CartoViewport),
                                  POINTER(CartoStyle)]
        L.carto_begin.restype = c_void_p
        L.carto_render_tile.argtypes = [c_void_p, POINTER(c_ubyte), c_size_t, c_int, c_int, c_int]
        L.carto_render_tile.restype = c_int
        L.carto_end.argtypes = [c_void_p]
        L.carto_end.restype = None

        self.has_cells = hasattr(L, "carto_cellify")
        if self.has_cells:
            L.carto_cellify.argtypes = [c_void_p, c_int32, c_int32,
                                        POINTER(CartoCellOpts),
                                        c_void_p, c_void_p, c_void_p]
            L.carto_cellify.restype = c_int
            L.carto_cell_geometry.argtypes = [c_int32, POINTER(c_int32),
                                              POINTER(c_int32)]
            L.carto_cell_geometry.restype = None
        self.has_cells_565 = hasattr(L, "carto_cellify_rgb565")
        if self.has_cells_565:
            L.carto_cellify_rgb565.argtypes = [c_void_p, c_int32, c_int32, c_void_p,
                                               POINTER(CartoCellOpts),
                                               c_void_p, c_void_p, c_void_p]
            L.carto_cellify_rgb565.restype = c_int

        self._arena_buf = (c_char * (8 * 1024 * 1024))()
        self._render_lock = threading.RLock()
        self._style = CartoStyle()
        self._style_lock = self._render_lock
        L.carto_style_default(byref(self._style))

        self._tile_cache = {}
        self._tile_lru = []
        self._tile_cache_max = 512
        self._cache_lock = threading.Lock()

        # Two pools, kept apart on purpose: a viewport render blocks on its
        # own fetches, so it must not queue behind speculative ring prefetches.
        self._pools = {}
        self._pool_lock = threading.Lock()
        self._prefetch_inflight = set()
        self._prefetch_lock = threading.Lock()

    def set_vector_style(self, vs, road_width_scale: float = 1.0) -> None:
        if vs is None:
            return
        with self._style_lock:
            s = self._style

            def put(field, rgb):
                c = getattr(s, field)
                c.r = int(rgb[0]) & 0xFF
                c.g = int(rgb[1]) & 0xFF
                c.b = int(rgb[2]) & 0xFF

            try:
                put("bg", vs.bg)
                put("water", vs.water)
                put("park", vs.park)
                put("building", vs.building)
                put("road_color", vs.road_color)
                put("label_color", vs.label_color)
                put("halo_color", vs.halo_color)
                put("aircraft_color", vs.aircraft_color)
                put("aircraft_selected_color", vs.aircraft_selected_color)
                put("aircraft_emergency_color", vs.aircraft_emergency_color)
                put("aircraft_label_color", vs.aircraft_label_color)
                put("aircraft_halo_color", vs.aircraft_halo_color)
                road_colors = getattr(vs, "road_colors", {}) or {}
                road_widths = getattr(vs, "road_widths", {}) or {}
                for p in range(1, _ROAD_PRIO_MAX + 1):
                    rgb = road_colors.get(p, vs.road_color)
                    cc = s.road_color_by_prio[p]
                    cc.r = int(rgb[0]) & 0xFF
                    cc.g = int(rgb[1]) & 0xFF
                    cc.b = int(rgb[2]) & 0xFF
                    s.road_width[p] = max(1, min(255, int(round(
                        road_widths.get(p, 3) * road_width_scale))))
                s.draw_labels = False
            except Exception:
                pass

    def _store_tile(self, k, raw):
        buf = None
        if raw:
            arr = (c_ubyte * len(raw)).from_buffer_copy(raw)
            buf = (arr, len(raw))
        with self._cache_lock:
            self._tile_cache[k] = buf
            self._tile_lru.append(k)
            if len(self._tile_lru) > self._tile_cache_max:
                old = self._tile_lru.pop(0)
                self._tile_cache.pop(old, None)
        return buf

    def _fetch_pool(self, name, workers):
        """A long-lived pool for tile fetches.

        Built on demand and kept, because these are hit once per rendered frame;
        standing a pool up per call costs more than the work it does.
        """
        pool = self._pools.get(name)
        if pool is None:
            with self._pool_lock:
                pool = self._pools.get(name)
                if pool is None:
                    pool = ThreadPoolExecutor(
                        max_workers=max(1, int(workers)),
                        thread_name_prefix=f"carto-{name}")
                    self._pools[name] = pool
        return pool

    def cell_geometry(self, mode):
        cw, chh = c_int32(0), c_int32(0)
        self.lib.carto_cell_geometry(int(mode), byref(cw), byref(chh))
        return cw.value, chh.value

    def cellify(self, rgb_ptr, w, h, opts, glyph_ptr, fg_ptr=0, bg_ptr=0):
        """Reduce a subcell RGB grid to glyphs and colours.

        Pointers are passed as integers so this stays free of a numpy import;
        the caller owns the buffers and there is no copy. Unlike the render
        entry points this touches no shared arena, so it needs no lock.
        """
        if not self.has_cells:
            raise RuntimeError("libcarto has no carto_cellify (rebuild it)")
        rc = self.lib.carto_cellify(c_void_p(rgb_ptr), int(w), int(h),
                                    byref(opts), c_void_p(glyph_ptr),
                                    c_void_p(fg_ptr or None),
                                    c_void_p(bg_ptr or None))
        if rc != 0:
            raise RuntimeError(f"carto_cellify failed ({rc})")

    def cellify_rgb565(self, src_ptr, sw, sh, lut_ptr, opts,
                       glyph_ptr, fg_ptr=0, bg_ptr=0):
        """Cells straight from the native framebuffer, downsampling on the way.

        Returns False when the shape needs a filter this does not implement, so
        the caller can fall back rather than get a wrong frame.
        """
        if not self.has_cells_565:
            return False
        rc = self.lib.carto_cellify_rgb565(
            c_void_p(src_ptr), int(sw), int(sh), c_void_p(lut_ptr), byref(opts),
            c_void_p(glyph_ptr), c_void_p(fg_ptr or None), c_void_p(bg_ptr or None))
        return rc == 0

    def close(self):
        with self._pool_lock:
            pools, self._pools = self._pools, {}
        for pool in pools.values():
            pool.shutdown(wait=False, cancel_futures=True)

    def prefetch_ring(self, lat, lon, z, w, h, fetch, ring=1, workers=4):
        # Work out what is missing on the caller's thread. This runs on every
        # non-panning frame and is almost always a no-op, so spawning a thread
        # first and deciding afterwards just burns a thread per frame.
        n = 2 ** z
        cx = ((lon + 180.0) / 360.0) * n * 256
        yn = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0
        cy = yn * n * 256
        tx0 = int(math.floor((cx - w / 2.0) / 256)) - ring
        tx1 = int(math.floor((cx + w / 2.0) / 256)) + ring
        ty0 = int(math.floor((cy - h / 2.0) / 256)) - ring
        ty1 = int(math.floor((cy + h / 2.0) / 256)) + ring
        missing = []
        with self._cache_lock:
            for ty in range(ty0, ty1 + 1):
                for tx in range(tx0, tx1 + 1):
                    if (0 <= tx < n and 0 <= ty < n
                            and (z, tx, ty) not in self._tile_cache):
                        missing.append((z, tx, ty))
        if not missing:
            return

        pool = self._fetch_pool("prefetch", workers)
        with self._prefetch_lock:
            missing = [k for k in missing if k not in self._prefetch_inflight]
            if not missing:
                return
            self._prefetch_inflight.update(missing)

        def one(k):
            try:
                self._store_tile(k, fetch(k[0], k[1], k[2]))
            except Exception:
                pass
            finally:
                with self._prefetch_lock:
                    self._prefetch_inflight.discard(k)

        for k in missing:
            try:
                pool.submit(one, k)
            except RuntimeError:
                with self._prefetch_lock:
                    self._prefetch_inflight.discard(k)

    @property
    def lock(self):
        """Guards the shared arena and style. Reentrant: hold it across a
        style-then-render pair to stop another thread restyling mid-render."""
        return self._render_lock

    def render_tile(self, tile: bytes, z: int, x: int, y: int, w: int, h: int) -> bytes:
        L = self.lib
        mvt = (c_ubyte * len(tile)).from_buffer_copy(tile)
        with self._render_lock:
            arena = CartoArena(cast(self._arena_buf, c_void_p), len(self._arena_buf), 0, 0)
            pixels = (c_uint8 * (w * h * 2))()
            fb = CartoFB()
            L.carto_fb_init(byref(fb), w, h, CARTO_FMT_RGB565, cast(pixels, c_void_p))

            lat, lon = tile_center(x, y, z)
            vp = CartoViewport(lat, lon, z, w, h, w, 0, 0, 0)
            ctx = L.carto_begin(byref(arena), byref(fb), byref(vp), byref(self._style))
            if not ctx:
                raise RuntimeError("carto_begin failed (arena too small?)")
            L.carto_render_tile(ctx, mvt, len(tile), x, y, z)
            L.carto_end(ctx)
            return bytes(pixels)

    def render_viewport(self, lat, lon, z, w, h, fetch, tile_px=256,
                        style=None, road_width_scale=1.0, fetch_z=None):
        """Render a viewport. Pass `style` here rather than calling
        `set_vector_style` separately: the native context keeps a live pointer to
        the one style struct, so applying it under the same lock as the render is
        what stops another thread restyling this frame mid-flight."""
        L = self.lib
        # Overzoom. carto_render_tile places a tile at tile_x * tile_px and
        # ignores the tile's own z, so rendering the world at the fetch zoom
        # with tile_px doubled per level covers exactly the deeper viewport --
        # the parent tiles scaled up, instead of a blank frame.
        if fetch_z is not None and 0 <= fetch_z < z:
            tile_px = int(tile_px) << (int(z) - int(fetch_z))
            z = int(fetch_z)
        n = 2 ** z
        cx = ((lon + 180.0) / 360.0) * n * tile_px
        yn = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0
        cy = yn * n * tile_px
        tx0 = int(math.floor((cx - w / 2.0) / tile_px))
        tx1 = int(math.floor((cx + w / 2.0) / tile_px))
        ty0 = int(math.floor((cy - h / 2.0) / tile_px))
        ty1 = int(math.floor((cy + h / 2.0) / tile_px))

        tiles = []
        for ty in range(ty0, ty1 + 1):
            for tx in range(tx0, tx1 + 1):
                if 0 <= tx < n and 0 <= ty < n:
                    tiles.append((tx, ty))

        missing = [(z, tx, ty) for (tx, ty) in tiles if (z, tx, ty) not in self._tile_cache]
        if len(missing) > 1:
            ex = self._fetch_pool("viewport", 8)
            for k, raw in ex.map(lambda kk: (kk, fetch(kk[0], kk[1], kk[2])), missing):
                self._store_tile(k, raw)
        elif missing:
            k = missing[0]
            self._store_tile(k, fetch(k[0], k[1], k[2]))

        with self._render_lock:
            if style is not None:
                self.set_vector_style(style, road_width_scale=road_width_scale)
            arena = CartoArena(cast(self._arena_buf, c_void_p), len(self._arena_buf), 0, 0)
            pixels = (c_uint8 * (w * h * 2))()
            fb = CartoFB()
            L.carto_fb_init(byref(fb), w, h, CARTO_FMT_RGB565, cast(pixels, c_void_p))
            vp = CartoViewport(lat, lon, z, w, h, tile_px, 0, 0, 0)
            ctx = L.carto_begin(byref(arena), byref(fb), byref(vp), byref(self._style))
            if not ctx:
                raise RuntimeError("carto_begin failed (arena too small?)")

            drawn = 0
            for (tx, ty) in tiles:
                buf = self._tile_cache.get((z, tx, ty))
                if buf:
                    arr, ln = buf
                    L.carto_render_tile(ctx, arr, ln, tx, ty, z)
                    drawn += 1
            L.carto_end(ctx)
            return bytes(pixels), drawn
