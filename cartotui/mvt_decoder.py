
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

__all__ = ["decode"]

_WT_VARINT = 0
_WT_64BIT = 1
_WT_LENGTH = 2
_WT_32BIT = 5

_GEOM_UNKNOWN = 0
_GEOM_POINT = 1
_GEOM_LINESTRING = 2
_GEOM_POLYGON = 3

def decode(data: bytes, y_coord_down: bool = True) -> Dict[str, dict]:
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
        if field == 15 and wire == _WT_VARINT:
            version, pos = _read_varint(buf, pos)
        elif field == 1 and wire == _WT_LENGTH:
            length, pos = _read_varint(buf, pos)
            name = buf[pos:pos + length].decode("utf-8", "replace")
            pos += length
        elif field == 2 and wire == _WT_LENGTH:
            length, pos = _read_varint(buf, pos)
            feature_blobs.append(buf[pos:pos + length])
            pos += length
        elif field == 3 and wire == _WT_LENGTH:
            length, pos = _read_varint(buf, pos)
            keys.append(buf[pos:pos + length].decode("utf-8", "replace"))
            pos += length
        elif field == 4 and wire == _WT_LENGTH:
            length, pos = _read_varint(buf, pos)
            values.append(_decode_value(buf[pos:pos + length]))
            pos += length
        elif field == 5 and wire == _WT_VARINT:
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
        if field == 1 and wire == _WT_VARINT:
            fid, pos = _read_varint(buf, pos)
        elif field == 2 and wire == _WT_LENGTH:
            length, pos = _read_varint(buf, pos)
            tags = list(_read_packed_varints(buf, pos, length))
            pos += length
        elif field == 3 and wire == _WT_VARINT:
            geom_type, pos = _read_varint(buf, pos)
        elif field == 4 and wire == _WT_LENGTH:
            length, pos = _read_varint(buf, pos)
            geom_cmds = list(_read_packed_varints(buf, pos, length))
            pos += length
        else:
            pos = _skip(buf, pos, wire)

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

def _decode_geometry(
    cmds: List[int],
    geom_type: int,
    extent: int,
    y_coord_down: bool,
) -> List[List[Tuple[int, int]]]:
    paths: List[List[Tuple[int, int]]] = []
    cur: List[Tuple[int, int]] = []
    x, y = 0, 0
    i = 0
    n = len(cmds)
    while i < n:
        cmd_int = cmds[i]
        cmd, count = cmd_int & 0x7, cmd_int >> 3
        i += 1
        if cmd == 1:
            for _ in range(count):
                if i + 1 >= n:
                    break
                dx, dy = _zigzag(cmds[i]), _zigzag(cmds[i + 1])
                i += 2
                x += dx
                y += dy
                if geom_type in (_GEOM_LINESTRING, _GEOM_POLYGON):
                    if cur:
                        paths.append(cur)
                    cur = [(x, _flip_y(y, extent, y_coord_down))]
                else:
                    cur.append((x, _flip_y(y, extent, y_coord_down)))
        elif cmd == 2:
            for _ in range(count):
                if i + 1 >= n:
                    break
                dx, dy = _zigzag(cmds[i]), _zigzag(cmds[i + 1])
                i += 2
                x += dx
                y += dy
                cur.append((x, _flip_y(y, extent, y_coord_down)))
        elif cmd == 7:
            if cur:
                cur.append(cur[0])
        else:
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
    if geom_type == _GEOM_POINT:
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
        polygons: List[List[List[Tuple[int, int]]]] = []
        for ring in paths:
            if len(ring) < 4:
                continue
            area = _signed_area(ring)
            if area > 0:
                polygons.append([ring])
            else:
                if polygons:
                    polygons[-1].append(ring)
                else:
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
    n = len(ring)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = ring[i]
        x1, y1 = ring[(i + 1) % n]
        s += (x0 * y1) - (x1 * y0)
    return s / 2.0

def _decode_value(buf: bytes) -> Any:
    pos = 0
    end = len(buf)
    while pos < end:
        tag, pos = _read_varint(buf, pos)
        field, wire = tag >> 3, tag & 0x7
        if field == 1 and wire == _WT_LENGTH:
            length, pos = _read_varint(buf, pos)
            return buf[pos:pos + length].decode("utf-8", "replace")
        if field == 2 and wire == _WT_32BIT:
            import struct
            v = struct.unpack_from("<f", buf, pos)[0]
            return v
        if field == 3 and wire == _WT_64BIT:
            import struct
            v = struct.unpack_from("<d", buf, pos)[0]
            return v
        if field == 4 and wire == _WT_VARINT:
            v, pos = _read_varint(buf, pos)
            return v
        if field == 5 and wire == _WT_VARINT:
            v, pos = _read_varint(buf, pos)
            return v
        if field == 6 and wire == _WT_VARINT:
            v, pos = _read_varint(buf, pos)
            return _zigzag(v)
        if field == 7 and wire == _WT_VARINT:
            v, pos = _read_varint(buf, pos)
            return bool(v)
        pos = _skip(buf, pos, wire)
    return None

def _read_varint(buf: bytes, pos: int) -> Tuple[int, int]:
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
            return result, pos

def _read_packed_varints(buf: bytes, pos: int, length: int):
    end = pos + length
    while pos < end:
        v, pos = _read_varint(buf, pos)
        yield v

def _skip(buf: bytes, pos: int, wire: int) -> int:
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
    return len(buf)

def _zigzag(n: int) -> int:
    return (n >> 1) ^ -(n & 1)
