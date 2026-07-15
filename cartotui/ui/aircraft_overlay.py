
from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from cartotui.aircraft_colors import LEGEND_BANDS, altitude_color
from cartotui.geodesy import latlon_to_tile_xy
from cartotui.traffic.aircraft import project_forward
from cartotui.traffic.interest import classify

StyleRun = Tuple[str, str]
LineFrag = List[StyleRun]
FrameFrag = List[LineFrag]

_HEADING_GLYPHS = (
    "▲",
    "▲",
    "◥",
    "▶",
    "▶",
    "▶",
    "◢",
    "▼",
    "▼",
    "▼",
    "◣",
    "◀",
    "◀",
    "◀",
    "◤",
    "▲",
)

def _glyph_for_track(track_deg: Optional[float]) -> str:
    if track_deg is None:
        return "●"
    idx = int(round(track_deg / 22.5)) % 16
    return _HEADING_GLYPHS[idx]

_DOT_GLYPHS = {"small": "·", "normal": "•", "large": "●"}

def _marker_glyph(track_deg: Optional[float], marker_style: str) -> str:
    if marker_style == "dot":
        return "•"
    if marker_style == "large":
        return "●"
    if marker_style == "plane":
        return "✈"
    if marker_style == "square":
        return "■"
    return _glyph_for_track(track_deg)

def select_visible(
    aircraft: List,
    center_lat: float,
    center_lon: float,
    *,
    max_shown: int = 0,
    hide_ground: bool = False,
    min_altitude: float = 0.0,
    max_altitude: float = 0.0,
    keep_icao: Optional[str] = None,
    highlight_interesting: bool = True,
) -> List:
    keep_icao = keep_icao.upper() if keep_icao else None

    def passes(ac) -> bool:
        if hide_ground and ac.on_ground:
            return False
        alt = ac.altitude_ft
        if min_altitude > 0 and (alt is None or alt < min_altitude):
            return False
        if max_altitude > 0 and (alt is None or alt > max_altitude):
            return False
        return True

    forced, normal = [], []
    for ac in aircraft:
        is_kept = keep_icao is not None and ac.icao.upper() == keep_icao
        is_alert = highlight_interesting and classify(ac).is_alert
        if is_kept or is_alert:
            forced.append(ac)
        elif passes(ac):
            normal.append(ac)

    if max_shown and max_shown > 0:
        slots = max(0, max_shown - len(forced))
        if len(normal) > slots:
            normal.sort(key=lambda a: ((a.lat - center_lat) ** 2
                                       + (a.lon - center_lon) ** 2))
            normal = normal[:slots]
    return forced + normal

def _project_lat_lon_to_cell(
    ac_lat: float,
    ac_lon: float,
    center_lat: float,
    center_lon: float,
    z: int,
    term_w: int,
    term_h: int,
    canvas_px_w: int,
    canvas_px_h: int,
) -> Tuple[float, float]:
    ac_tx, ac_ty = latlon_to_tile_xy(ac_lat, ac_lon, z)
    cn_tx, cn_ty = latlon_to_tile_xy(center_lat, center_lon, z)
    cells_per_tile_x = 256.0 * term_w / max(1, canvas_px_w)
    cells_per_tile_y = 256.0 * term_h / max(1, canvas_px_h)
    cx = term_w / 2.0 + (ac_tx - cn_tx) * cells_per_tile_x
    cy = term_h / 2.0 + (ac_ty - cn_ty) * cells_per_tile_y
    return cx, cy

def _row_to_chars(line: LineFrag, width: int) -> Tuple[List[str], List[str]]:
    styles: List[str] = []
    chars: List[str] = []
    for style, text in line:
        for ch in text:
            styles.append(style)
            chars.append(ch)
    while len(chars) < width:
        styles.append(styles[-1] if styles else "")
        chars.append(" ")
    if len(chars) > width:
        styles = styles[:width]
        chars = chars[:width]
    return styles, chars

def _chars_to_row(styles: Sequence[str], chars: Sequence[str]) -> LineFrag:
    if not chars:
        return [("", "")]
    out: LineFrag = []
    cur_style = styles[0]
    buf: List[str] = [chars[0]]
    for st, ch in zip(styles[1:], chars[1:]):
        if st == cur_style:
            buf.append(ch)
        else:
            out.append((cur_style, "".join(buf)))
            cur_style = st
            buf = [ch]
    out.append((cur_style, "".join(buf)))
    return out

def _bg_of(style: str) -> str:
    if not style:
        return ""
    for tok in style.split():
        if tok.startswith("bg:#"):
            return tok
    return ""

def _with_bg(fg_style: str, under_style: str) -> str:
    if "bg:" in fg_style:
        return fg_style
    bg = _bg_of(under_style)
    return f"{fg_style} {bg}" if bg else fg_style

def _stamp_cell(
    rows: FrameFrag,
    width: int,
    cell_x: int,
    cell_y: int,
    glyph: str,
    style: str,
) -> bool:
    if cell_y < 0 or cell_y >= len(rows):
        return False
    if cell_x < 0 or cell_x >= width:
        return False
    styles, chars = _row_to_chars(rows[cell_y], width)
    styles[cell_x] = _with_bg(style, styles[cell_x])
    chars[cell_x] = glyph
    rows[cell_y] = _chars_to_row(styles, chars)
    return True

def _stamp_cells_batch(
    rows: FrameFrag,
    width: int,
    cells: Sequence[Tuple[int, int, str, str]],
) -> None:
    if not cells:
        return
    by_row: Dict[int, List[Tuple[int, str, str]]] = {}
    for cx, cy, glyph, style in cells:
        if cy < 0 or cy >= len(rows):
            continue
        if cx < 0 or cx >= width:
            continue
        by_row.setdefault(cy, []).append((cx, glyph, style))

    for y, mods in by_row.items():
        styles, chars = _row_to_chars(rows[y], width)
        for cx, glyph, style in mods:
            styles[cx] = _with_bg(style, styles[cx])
            chars[cx] = glyph
        rows[y] = _chars_to_row(styles, chars)

def _stamp_label(
    rows: FrameFrag,
    width: int,
    cell_x: int,
    cell_y: int,
    label: str,
    style: str,
) -> None:
    if cell_y < 0 or cell_y >= len(rows):
        return
    styles, chars = _row_to_chars(rows[cell_y], width)
    for i, ch in enumerate(label):
        cx = cell_x + i
        if cx >= width:
            break
        if cx < 0:
            continue
        styles[cx] = _with_bg(style, styles[cx])
        chars[cx] = ch
    rows[cell_y] = _chars_to_row(styles, chars)

def _rgb_to_style(rgb: Tuple[int, int, int], bold: bool = False) -> str:
    r, g, b = rgb
    bold_str = " bold" if bold else ""
    return f"fg:#{r:02x}{g:02x}{b:02x}{bold_str}"

def apply_aircraft_overlay(
    rows: FrameFrag,
    aircraft_iter: Iterable,
    *,
    center_lat: float,
    center_lon: float,
    z: int,
    term_w: int,
    term_h: int,
    canvas_px_w: int,
    canvas_px_h: int,
    style,
    selected_icao: Optional[str] = None,
    show_labels: bool = True,
    label_mode: str = "smart",
    show_trails: bool = True,
    trail_duration_s: float = 60.0,
    altitude_colors: bool = True,
    show_legend: bool = True,
    dead_reckoning: bool = True,
    predict_track: bool = True,
    predict_seconds: float = 60.0,
    highlight_interesting: bool = True,
    show_banner: bool = True,
    marker_style: str = "arrow",
    now: Optional[float] = None,
) -> List[Tuple[str, int, int, int, int]]:
    import time as _time
    if now is None:
        now = _time.time()

    hitboxes: List[Tuple[str, int, int, int, int]] = []

    items: List[Tuple] = []
    alert_items: List[Tuple] = []
    sel_item: Optional[Tuple] = None
    for ac in aircraft_iter:
        if not ac.has_position():
            continue
        if dead_reckoning:
            proj = ac.projected_position(now=now)
            ac_lat, ac_lon = proj if proj is not None else (ac.lat, ac.lon)
        else:
            ac_lat, ac_lon = ac.lat, ac.lon
        cx_f, cy_f = _project_lat_lon_to_cell(
            ac_lat, ac_lon, center_lat, center_lon, z,
            term_w, term_h, canvas_px_w, canvas_px_h,
        )
        cx, cy = int(round(cx_f)), int(round(cy_f))
        if cx < -1 or cy < -1 or cx > term_w or cy > term_h:
            if not show_trails:
                continue
            try:
                if not getattr(ac, "history", None):
                    continue
            except Exception:
                continue

        is_sel = (selected_icao is not None
                  and ac.icao.upper() == selected_icao.upper())

        interest = classify(ac) if highlight_interesting else None
        is_alert = bool(interest) and interest.is_alert

        if is_alert or ac.emergency:
            color = style.aircraft_emergency_color
        elif is_sel:
            color = style.aircraft_selected_color
        elif altitude_colors:
            color = altitude_color(ac.altitude_ft, bool(ac.on_ground))
        else:
            color = style.aircraft_color

        if is_sel:
            glyph = "✈"
        elif is_alert:
            glyph = "⚠"
        else:
            glyph = _marker_glyph(ac.track_deg, marker_style)
        marker_cell_style = _rgb_to_style(color, bold=True)

        if label_mode == "all":
            want_label = True
        elif label_mode == "selected":
            want_label = is_sel or is_alert
        elif label_mode == "none":
            want_label = is_alert
        else:
            want_label = is_sel or bool(interest)

        label = ""
        if want_label:
            try:
                base = ac.display_label() or ""
            except Exception:
                base = ac.icao or ""
            if interest and interest.label:
                base = f"{interest.label} {base}".strip()
            if base:
                label = " " + base

        label_style = _rgb_to_style(color, bold=is_sel or is_alert)

        entry = (ac, cx, cy, glyph, marker_cell_style, label, label_style,
                 is_sel, color, is_alert)
        if is_sel:
            sel_item = entry
        elif is_alert:
            alert_items.append(entry)
        else:
            items.append(entry)

    items.extend(alert_items)
    if sel_item is not None:
        items.append(sel_item)

    if show_trails:
        for ac, cx, cy, _g, _ms, _lbl, _ls, _is_sel, color, _ia in items:
            _stamp_trail(
                rows, ac, color,
                center_lat=center_lat, center_lon=center_lon, z=z,
                term_w=term_w, term_h=term_h,
                canvas_px_w=canvas_px_w, canvas_px_h=canvas_px_h,
                trail_duration_s=trail_duration_s,
                now=now,
            )

    if predict_track and sel_item is not None and predict_seconds > 0:
        _stamp_predicted_track(
            rows, sel_item[0], sel_item[8],
            center_lat=center_lat, center_lon=center_lon, z=z,
            term_w=term_w, term_h=term_h,
            canvas_px_w=canvas_px_w, canvas_px_h=canvas_px_h,
            predict_seconds=predict_seconds,
            dead_reckoning=dead_reckoning, now=now,
        )

    occupied_labels: set = set()
    for ac, cx, cy, glyph, m_style, label, l_style, is_sel, _c, is_alert in items:
        _stamp_cell(rows, term_w, cx, cy, glyph, m_style)

        drew_label = False
        if label:
            protected = is_sel or is_alert
            span = range(cx + 1, cx + 1 + len(label))
            collides = any((x, cy) in occupied_labels for x in span)
            if protected or not collides:
                _stamp_label(rows, term_w, cx + 1, cy, label, l_style)
                for x in span:
                    occupied_labels.add((x, cy))
                drew_label = True

        x0 = max(0, cx)
        y0 = max(0, cy)
        x1 = min(term_w - 1, cx + (len(label) if drew_label else 0))
        y1 = min(term_h - 1, cy)
        if x1 >= x0 and y1 >= y0:
            hitboxes.append((ac.icao, x0, y0, x1, y1))

    if show_legend and altitude_colors and items:
        _stamp_altitude_legend(rows, term_w, term_h)

    if show_banner and highlight_interesting and alert_items:
        _stamp_alert_banner(rows, term_w, alert_items, style)

    return hitboxes

def _stamp_alert_banner(rows: FrameFrag, term_w: int,
                        alert_items: List[Tuple], style) -> None:
    if not rows or term_w < 20:
        return
    n = len(alert_items)
    parts: List[str] = []
    for ac, *_rest in alert_items[:3]:
        cs = ""
        try:
            cs = ac.display_label()
        except Exception:
            cs = ac.icao
        sq = f" sq{ac.squawk}" if ac.squawk else ""
        parts.append(f"{cs}{sq}")
    more = f" +{n - 3} more" if n > 3 else ""
    text = f" ⚠ ALERT x{n}: " + "  ".join(parts) + more + " "
    if len(text) > term_w:
        text = text[:term_w]
    st = _rgb_to_style(style.aircraft_emergency_color, bold=True)
    cells = [(x, 0, ch, st) for x, ch in enumerate(text)]
    _stamp_cells_batch(rows, term_w, cells)

def _stamp_altitude_legend(rows: FrameFrag, term_w: int, term_h: int) -> None:
    if term_h < 2 or term_w < 20:
        return
    y = term_h - 1
    cells: List[Tuple[int, int, str, str]] = []
    x = 1
    for label, rgb in LEGEND_BANDS:
        st = _rgb_to_style(rgb, bold=True)
        cells.append((x, y, "█", st))
        x += 1
        for ch in label:
            if x >= term_w - 1:
                break
            cells.append((x, y, ch, st))
            x += 1
        x += 1
        if x >= term_w - 1:
            break
    _stamp_cells_batch(rows, term_w, cells)

def _stamp_predicted_track(
    rows: FrameFrag,
    ac,
    color: Tuple[int, int, int],
    *,
    center_lat: float,
    center_lon: float,
    z: int,
    term_w: int,
    term_h: int,
    canvas_px_w: int,
    canvas_px_h: int,
    predict_seconds: float,
    dead_reckoning: bool,
    now: Optional[float],
) -> None:
    if ac.track_deg is None or ac.ground_speed_kt is None or ac.ground_speed_kt <= 0:
        return
    if dead_reckoning:
        start = ac.projected_position(now=now) or (ac.lat, ac.lon)
    else:
        start = (ac.lat, ac.lon)
    end = project_forward(start[0], start[1], ac.track_deg,
                          ac.ground_speed_kt, predict_seconds)

    sx_f, sy_f = _project_lat_lon_to_cell(
        start[0], start[1], center_lat, center_lon, z,
        term_w, term_h, canvas_px_w, canvas_px_h)
    ex_f, ey_f = _project_lat_lon_to_cell(
        end[0], end[1], center_lat, center_lon, z,
        term_w, term_h, canvas_px_w, canvas_px_h)
    sx, sy = int(round(sx_f)), int(round(sy_f))
    ex, ey = int(round(ex_f)), int(round(ey_f))

    dim = _dim_color(color, 0.7)
    style = _rgb_to_style(dim, bold=False)
    pts = _bresenham(sx, sy, ex, ey)
    for i, (lx, ly) in enumerate(pts):
        if (lx, ly) == (sx, sy):
            continue
        if i % 2 == 0:
            continue
        if 0 <= lx < term_w and 0 <= ly < term_h:
            _stamp_cell(rows, term_w, lx, ly, "·", style)

_TRAIL_GLYPHS = (".", "·", "•", "○")

_TRAIL_DIM_BANDS = (0.30, 0.45, 0.60, 0.80)

def _dim_color(rgb: Tuple[int, int, int], factor: float) -> Tuple[int, int, int]:
    return (
        max(0, min(255, int(rgb[0] * factor))),
        max(0, min(255, int(rgb[1] * factor))),
        max(0, min(255, int(rgb[2] * factor))),
    )

def _stamp_trail(
    rows: FrameFrag,
    ac,
    color: Tuple[int, int, int],
    *,
    center_lat: float,
    center_lon: float,
    z: int,
    term_w: int,
    term_h: int,
    canvas_px_w: int,
    canvas_px_h: int,
    trail_duration_s: float,
    now: float,
) -> None:
    try:
        history = getattr(ac, "history", None)
        if not history:
            return
    except Exception:
        return

    cutoff = now - trail_duration_s

    pts: List[Tuple[int, int, float]] = []
    for ts, lat, lon in history:
        if ts < cutoff:
            continue
        age = now - ts
        age_frac = max(0.0, min(1.0, age / trail_duration_s))
        cx_f, cy_f = _project_lat_lon_to_cell(
            lat, lon, center_lat, center_lon, z,
            term_w, term_h, canvas_px_w, canvas_px_h,
        )
        cx, cy = int(round(cx_f)), int(round(cy_f))
        pts.append((cx, cy, age_frac))

    if not pts:
        return

    prev: Optional[Tuple[int, int, float]] = None
    for cx, cy, age_frac in pts:
        if prev is not None:
            for lx, ly in _bresenham(prev[0], prev[1], cx, cy):
                if (lx, ly) == (prev[0], prev[1]) or (lx, ly) == (cx, cy):
                    continue
                _stamp_trail_cell(rows, term_w, term_h, lx, ly, age_frac, color)
        _stamp_trail_cell(rows, term_w, term_h, cx, cy, age_frac, color)
        prev = (cx, cy, age_frac)

def _stamp_trail_cell(
    rows: FrameFrag,
    term_w: int,
    term_h: int,
    cx: int,
    cy: int,
    age_frac: float,
    base_color: Tuple[int, int, int],
) -> None:
    if cx < 0 or cx >= term_w or cy < 0 or cy >= term_h:
        return
    band_idx = max(0, min(3, int((1.0 - age_frac) * 4)))
    glyph = _TRAIL_GLYPHS[band_idx]
    dim = _TRAIL_DIM_BANDS[band_idx]
    color = _dim_color(base_color, dim)
    style = _rgb_to_style(color, bold=False)
    _stamp_cell(rows, term_w, cx, cy, glyph, style)

def _bresenham(x0: int, y0: int, x1: int, y1: int) -> List[Tuple[int, int]]:
    points: List[Tuple[int, int]] = []
    dx = abs(x1 - x0)
    dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    for _ in range(dx - dy + 2):
        points.append((x, y))
        if x == x1 and y == y1:
            break
        e2 = 2 * err
        if e2 >= dy:
            err += dy
            x += sx
        if e2 <= dx:
            err += dx
            y += sy
    return points
