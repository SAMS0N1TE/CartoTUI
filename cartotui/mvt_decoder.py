"""Pure-Python MVT (Mapbox Vector Tile) decoder.

The official ``mapbox-vector-tile`` package on PyPI requires ``shapely`` and
``pyclipper`` as runtime deps, both of which need C extensions (GEOS, Cython
build) and are notoriously fragile to install on Windows / Python 3.13. We
don't actually need their geometry processing — just raw coordinates.

This module implements just enough of the MVT 2.1 spec
(https://github.com/mapbox/vector-tile-spec/tree/master/2.1) to decode tiles
into the same shape that the rest of CartoTUI consumed from
``mapbox_vector_tile.decode``::

    {
      "<layer_name>": {
        "extent": 4096,
        "version": 2,
        "features": [
          {
            "geometry": {"type": "LineString", "coordinates": [[x, y], ...]},
            "properties": {"name": "...", "kind": "...", ...},
            "type": 2,
            "id": 12345,
          },
          ...
        ],
      },
      ...
    }

The geometry types follow GeoJSON conventions (Point / MultiPoint /
LineString / MultiLineString / Polygon / MultiPolygon).

Coordinates are returned in tile-local pixel space (0..extent on each axis),
with y *increasing downward* (screen-space) so the rasteriser doesn't need
to flip them. This matches what the rest of the code expects.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

__all__ = ["decode"]


# Wire types
_WT_VARINT = 0
_WT_64BIT = 1
_WT_LENGTH = 2
_WT_32BIT = 5

# MVT geometry feature types
_GEOM_UNKNOWN = 0
_GEOM_POINT = 1
_GEOM_LINESTRING = 2
_GEOM_POLYGON = 3


def decode(data: bytes, y_coord_down: bool = True) -> Dict[str, dict]:
    """Decode a single MVT tile blob into a dict of layers.

    Args:
        data: raw MVT bytes (already gunzipped if applicable).
        y_coord_down: keep y in screen-space (top=0, increases downward) when
            True. When False, flip to GeoJSON convention (north-up). Defaults
            to True so the rasteriser can use coordinates directly.

    Returns:
        Dict mapping layer name to ``{extent, version, features}``.
    """
    layers: Dict[str, dict] = {}
    pos = 0
    end = len(data)
    while pos < end:
        tag, pos = _read_varint(data, pos)
        field, wire = tag >> 3, tag & 0x7
        if field == 3 and wire == _WT_LENGTH:
            length, pos = _read_varint(data, pos)
            layer_blob = data[pos:pos + length]
            pos += length
            layer = _decode_layer(layer_blob, y_coord_down=y_coord_down)
            if layer is not None:
                name, body = layer
                layers[name] = body
        else:
            pos = _skip(data, pos, wire)
    return layers


# ---------------------------------------------------------------------------
# Layer
# ---------------------------------------------------------------------------


def _decode_layer(buf: bytes, y_coord_down: bool) -> Optional[Tuple[str, dict]]:
    name: Optional[str] = None
    extent = 4096
    version = 1
    keys: List[str] = []
    values: List[Any] = []
    feature_blobs: List[bytes] = []

    pos = 0
    end = len(buf)
    while pos < end:
        tag, pos = _read_varint(buf, pos)
        field, wire = tag >> 3, tag & 0x7
        if field == 15 and wire == _WT_VARINT:        # version
            version, pos = _read_varint(buf, pos)
        elif field == 1 and wire == _WT_LENGTH:        # name
            length, pos = _read_varint(buf, pos)
            name = buf[pos:pos + length].decode("utf-8", "replace")
            pos += length
        elif field == 2 and wire == _WT_LENGTH:        # features
            length, pos = _read_varint(buf, pos)
            feature_blobs.append(buf[pos:pos + length])
            pos += length
        elif field == 3 and wire == _WT_LENGTH:        # keys
            length, pos = _read_varint(buf, pos)
            keys.append(buf[pos:pos + length].decode("utf-8", "replace"))
            pos += length
        elif field == 4 and wire == _WT_LENGTH:        # values
            length, pos = _read_varint(buf, pos)
            values.append(_decode_value(buf[pos:pos + length]))
            pos += length
        elif field == 5 and wire == _WT_VARINT:        # extent
            extent, pos = _read_varint(buf, pos)
        else:
            pos = _skip(buf, pos, wire)

    if name is None:
        return None

    features = [
        _decode_feature(fb, keys, values, extent, y_coord_down=y_coord_down)
        for fb in feature_blobs
    ]
    features = [f for f in features if f is not None]

    return name, {"extent": extent, "version": version, "features": features}


# ---------------------------------------------------------------------------
# Feature
# ---------------------------------------------------------------------------


def _decode_feature(
    buf: bytes,
    keys: List[str],
    values: List[Any],
    extent: int,
    y_coord_down: bool,
) -> Optional[dict]:
    fid: Optional[int] = None
    tags: List[int] = []
    geom_type = _GEOM_UNKNOWN
    geom_cmds: List[int] = []

    pos = 0
    end = len(buf)
    while pos < end:
        tag, pos = _read_varint(buf, pos)
        field, wire = tag >> 3, tag & 0x7
        if field == 1 and wire == _WT_VARINT:          # id
            fid, pos = _read_varint(buf, pos)
        elif field == 2 and wire == _WT_LENGTH:        # tags (packed)
            length, pos = _read_varint(buf, pos)
            tags = list(_read_packed_varints(buf, pos, length))
            pos += length
        elif field == 3 and wire == _WT_VARINT:        # type
            geom_type, pos = _read_varint(buf, pos)
        elif field == 4 and wire == _WT_LENGTH:        # geometry (packed)
            length, pos = _read_varint(buf, pos)
            geom_cmds = list(_read_packed_varints(buf, pos, length))
            pos += length
        else:
            pos = _skip(buf, pos, wire)

    # Decode geometry commands into (sub)paths.
    paths = _decode_geometry(geom_cmds, geom_type, extent, y_coord_down)
    if not paths:
        return None

    geom = _classify_geometry(paths, geom_type)
    if geom is None:
        return None

    properties: Dict[str, Any] = {}
    if tags:
        for i in range(0, len(tags) - 1, 2):
            ki, vi = tags[i], tags[i + 1]
            if 0 <= ki < len(keys) and 0 <= vi < len(values):
                properties[keys[ki]] = values[vi]

    out: Dict[str, Any] = {
        "type": geom_type,
        "geometry": geom,
        "properties": properties,
    }
    if fid is not None:
        out["id"] = fid
    return out


# ---------------------------------------------------------------------------
# Geometry command decoder
# ---------------------------------------------------------------------------


def _decode_geometry(
    cmds: List[int],
    geom_type: int,
    extent: int,
    y_coord_down: bool,
) -> List[List[Tuple[int, int]]]:
    """Decode the MVT command/parameter integer stream into a list of paths.

    Each path is a list of (x, y) integer coordinates in tile-local space.
    For Point geometry, each "path" is just the run of point coordinates.
    For LineString/Polygon, each MoveTo starts a new path.
    """
    paths: List[List[Tuple[int, int]]] = []
    cur: List[Tuple[int, int]] = []
    x, y = 0, 0
    i = 0
    n = len(cmds)
    while i < n:
        cmd_int = cmds[i]
        cmd, count = cmd_int & 0x7, cmd_int >> 3
        i += 1
        if cmd == 1:  # MoveTo — params are pairs (dx, dy)
            for _ in range(count):
                if i + 1 >= n:
                    break
                dx, dy = _zigzag(cmds[i]), _zigzag(cmds[i + 1])
                i += 2
                x += dx
                y += dy
                # MoveTo starts a new path for line/poly. For points, every
                # MoveTo param is a separate point — the spec is ambiguous
                # about exactly how to slice them; we collect them all into
                # one "path" list and let _classify_geometry split.
                if geom_type in (_GEOM_LINESTRING, _GEOM_POLYGON):
                    if cur:
                        paths.append(cur)
                    cur = [(x, _flip_y(y, extent, y_coord_down))]
                else:
                    cur.append((x, _flip_y(y, extent, y_coord_down)))
        elif cmd == 2:  # LineTo — params are pairs (dx, dy)
            for _ in range(count):
                if i + 1 >= n:
                    break
                dx, dy = _zigzag(cmds[i]), _zigzag(cmds[i + 1])
                i += 2
                x += dx
                y += dy
                cur.append((x, _flip_y(y, extent, y_coord_down)))
        elif cmd == 7:  # ClosePath — no params, repeat first vertex
            if cur:
                cur.append(cur[0])
        else:
            # Unknown command — stop.
            break
    if cur:
        paths.append(cur)
    return paths


def _flip_y(y: int, extent: int, y_coord_down: bool) -> int:
    return y if y_coord_down else extent - y


def _classify_geometry(
    paths: List[List[Tuple[int, int]]],
    geom_type: int,
) -> Optional[dict]:
    """Wrap raw paths in a GeoJSON-style geometry object."""
    if geom_type == _GEOM_POINT:
        # All collected points are in paths[0] (single MoveTo run).
        coords = paths[0] if paths else []
        if not coords:
            return None
        if len(coords) == 1:
            return {"type": "Point", "coordinates": list(coords[0])}
        return {"type": "MultiPoint", "coordinates": [list(p) for p in coords]}

    if geom_type == _GEOM_LINESTRING:
        if not paths:
            return None
        if len(paths) == 1:
            return {"type": "LineString",
                    "coordinates": [list(p) for p in paths[0]]}
        return {"type": "MultiLineString",
                "coordinates": [[list(p) for p in path] for path in paths]}

    if geom_type == _GEOM_POLYGON:
        # Group rings into polygons by orientation: outer rings have positive
        # area (in screen space, y-down — so ring is clockwise), holes have
        # negative area. We use the spec's ring-order rule: each new outer
        # ring starts a new polygon; subsequent inner rings belong to it.
        polygons: List[List[List[Tuple[int, int]]]] = []
        for ring in paths:
            if len(ring) < 4:
                continue
            area = _signed_area(ring)
            # In MVT spec (y-down), outer = positive area (CW),
            # inner = negative area (CCW).
            if area > 0:
                polygons.append([ring])
            else:
                if polygons:
                    polygons[-1].append(ring)
                else:
                    # Stray inner ring before any outer — treat as outer.
                    polygons.append([ring])
        if not polygons:
            return None
        if len(polygons) == 1:
            return {
                "type": "Polygon",
                "coordinates": [[list(p) for p in ring] for ring in polygons[0]],
            }
        return {
            "type": "MultiPolygon",
            "coordinates": [
                [[list(p) for p in ring] for ring in poly]
                for poly in polygons
            ],
        }

    return None


def _signed_area(ring: List[Tuple[int, int]]) -> float:
    """Shoelace signed area of a ring."""
    n = len(ring)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        s += (x0 * y1) - (x1 * y0)
    return s / 2.0


# ---------------------------------------------------------------------------
# Value decoder
# ---------------------------------------------------------------------------


def _decode_value(buf: bytes) -> Any:
    pos = 0
    end = len(buf)
    while pos < end:
        tag, pos = _read_varint(buf, pos)
        field, wire = tag >> 3, tag & 0x7
        if field == 1 and wire == _WT_LENGTH:          # string
            length, pos = _read_varint(buf, pos)
            return buf[pos:pos + length].decode("utf-8", "replace")
        if field == 2 and wire == _WT_32BIT:           # float
            import struct
            v = struct.unpack_from("<f", buf, pos)[0]
            return v
        if field == 3 and wire == _WT_64BIT:           # double
            import struct
            v = struct.unpack_from("<d", buf, pos)[0]
            return v
        if field == 4 and wire == _WT_VARINT:          # int (signed)
            v, pos = _read_varint(buf, pos)
            return v
        if field == 5 and wire == _WT_VARINT:          # uint
            v, pos = _read_varint(buf, pos)
            return v
        if field == 6 and wire == _WT_VARINT:          # sint
            v, pos = _read_varint(buf, pos)
            return _zigzag(v)
        if field == 7 and wire == _WT_VARINT:          # bool
            v, pos = _read_varint(buf, pos)
            return bool(v)
        # Unknown: skip
        pos = _skip(buf, pos, wire)
    return None


# ---------------------------------------------------------------------------
# Wire format primitives
# ---------------------------------------------------------------------------


def _read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
    """Decode a base-128 varint starting at `pos`. Returns (value, new_pos)."""
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            return result, pos
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if (b & 0x80) == 0:
            return result, pos
        shift += 7
        if shift > 63:
            # Malformed; abort.
            return result, pos


def _read_packed_varints(buf: bytes, pos: int, length: int):
    """Yield successive varints from a `length`-byte packed run starting at pos."""
    end = pos + length
    while pos < end:
        v, pos = _read_varint(buf, pos)
        yield v


def _skip(buf: bytes, pos: int, wire: int) -> int:
    """Skip an unrecognised field of given wire type."""
    if wire == _WT_VARINT:
        _, pos = _read_varint(buf, pos)
        return pos
    if wire == _WT_64BIT:
        return pos + 8
    if wire == _WT_LENGTH:
        length, pos = _read_varint(buf, pos)
        return pos + length
    if wire == _WT_32BIT:
        return pos + 4
    # Unknown wire type; abort to end of buffer.
    return len(buf)


def _zigzag(n: int) -> int:
    """Decode zigzag-encoded signed varint."""
    return (n >> 1) ^ -(n & 1)
