import ctypes
import math
import os
from ctypes import (c_int, c_int32, c_uint8, c_ubyte, c_double, c_size_t,
                    c_void_p, c_char, POINTER, byref, cast, Structure)

_HERE = os.path.dirname(os.path.abspath(__file__))
_DEFAULT_DLL = os.path.normpath(os.path.join(_HERE, "..", "..", "libcarto", "build", "carto.dll"))

CARTO_FMT_RGB565 = 2


class CartoArena(Structure):
    _fields_ = [("base", c_void_p), ("size", c_size_t), ("used", c_size_t), ("peak", c_size_t)]


class CartoFB(Structure):
    _fields_ = [("width", c_int), ("height", c_int), ("format", c_int), ("stride", c_int),
                ("pixels", c_void_p), ("cell_color", c_void_p), ("cell_cols", c_int), ("cell_rows", c_int)]


class CartoViewport(Structure):
    _fields_ = [("lat", c_double), ("lon", c_double), ("zoom", c_int), ("fb_w", c_int), ("fb_h", c_int),
                ("tile_px", c_int), ("scale", c_int32), ("origin_x", c_int32), ("origin_y", c_int32)]


def tile_center(x, y, z):
    n = 2.0 ** z
    lon = (x + 0.5) / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + 0.5) / n))))
    return lat, lon


class Renderer:
    def __init__(self, dll_path=None):
        self.lib = ctypes.CDLL(dll_path or _DEFAULT_DLL)
        L = self.lib
        L.carto_fb_init.argtypes = [POINTER(CartoFB), c_int, c_int, c_int, c_void_p]
        L.carto_fb_init.restype = c_int
        L.carto_style_default.argtypes = [c_void_p]
        L.carto_style_default.restype = None
        L.carto_begin.argtypes = [POINTER(CartoArena), POINTER(CartoFB), POINTER(CartoViewport), c_void_p]
        L.carto_begin.restype = c_void_p
        L.carto_render_tile.argtypes = [c_void_p, POINTER(c_ubyte), c_size_t, c_int, c_int, c_int]
        L.carto_render_tile.restype = c_int
        L.carto_end.argtypes = [c_void_p]
        L.carto_end.restype = None

        self._arena_buf = (c_char * (8 * 1024 * 1024))()
        self._style = (c_char * 256)()
        L.carto_style_default(cast(self._style, c_void_p))

        self._tile_cache = {}
        self._tile_lru = []
        self._tile_cache_max = 512

    def _store_tile(self, k, raw):
        buf = None
        if raw:
            arr = (c_ubyte * len(raw)).from_buffer_copy(raw)
            buf = (arr, len(raw))
        self._tile_cache[k] = buf
        self._tile_lru.append(k)
        if len(self._tile_lru) > self._tile_cache_max:
            old = self._tile_lru.pop(0)
            self._tile_cache.pop(old, None)
        return buf

    def render_tile(self, tile: bytes, z: int, x: int, y: int, w: int, h: int) -> bytes:
        L = self.lib
        arena = CartoArena(cast(self._arena_buf, c_void_p), len(self._arena_buf), 0, 0)
        pixels = (c_uint8 * (w * h * 2))()
        fb = CartoFB()
        L.carto_fb_init(byref(fb), w, h, CARTO_FMT_RGB565, cast(pixels, c_void_p))

        lat, lon = tile_center(x, y, z)
        vp = CartoViewport(lat, lon, z, w, h, w, 0, 0, 0)
        ctx = L.carto_begin(byref(arena), byref(fb), byref(vp), cast(self._style, c_void_p))
        if not ctx:
            raise RuntimeError("carto_begin failed (arena too small?)")
        mvt = (c_ubyte * len(tile)).from_buffer_copy(tile)
        L.carto_render_tile(ctx, mvt, len(tile), x, y, z)
        L.carto_end(ctx)
        return bytes(pixels)

    def render_viewport(self, lat, lon, z, w, h, fetch, tile_px=256):
        L = self.lib
        arena = CartoArena(cast(self._arena_buf, c_void_p), len(self._arena_buf), 0, 0)
        pixels = (c_uint8 * (w * h * 2))()
        fb = CartoFB()
        L.carto_fb_init(byref(fb), w, h, CARTO_FMT_RGB565, cast(pixels, c_void_p))
        vp = CartoViewport(lat, lon, z, w, h, tile_px, 0, 0, 0)
        ctx = L.carto_begin(byref(arena), byref(fb), byref(vp), cast(self._style, c_void_p))
        if not ctx:
            raise RuntimeError("carto_begin failed (arena too small?)")

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
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=min(8, len(missing))) as ex:
                for k, raw in ex.map(lambda kk: (kk, fetch(kk[0], kk[1], kk[2])), missing):
                    self._store_tile(k, raw)
        elif missing:
            k = missing[0]
            self._store_tile(k, fetch(k[0], k[1], k[2]))

        drawn = 0
        for (tx, ty) in tiles:
            buf = self._tile_cache.get((z, tx, ty))
            if buf:
                arr, ln = buf
                L.carto_render_tile(ctx, arr, ln, tx, ty, z)
                drawn += 1
        L.carto_end(ctx)
        return bytes(pixels), drawn
