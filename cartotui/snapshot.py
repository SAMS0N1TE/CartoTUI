from __future__ import annotations

import html
import os
import platform
import subprocess
import time
from typing import Dict, List, Optional, Tuple

Run = Tuple[str, str]

_FONT_CANDIDATES = (
    r"C:\Windows\Fonts\consola.ttf",
    r"C:\Windows\Fonts\DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Menlo.ttc",
)

_font_path_cache: Optional[str] = None
_font_cache: Dict[int, object] = {}


def find_mono_font() -> Optional[str]:
    """Locate a monospace TTF, or None if the box genuinely has none.

    The fixed list only covers Windows, Debian and macOS layouts, so fontconfig
    is asked before giving up -- otherwise distros that shelve fonts elsewhere
    (Fedora, Arch) can't render a PNG at all.
    """
    global _font_path_cache
    if _font_path_cache is not None:
        return _font_path_cache or None

    found = ""
    for c in _FONT_CANDIDATES:
        if os.path.exists(c):
            found = c
            break
    if not found:
        try:
            for query in ("DejaVu Sans Mono", "monospace"):
                got = subprocess.run(["fc-match", "-f", "%{file}", query],
                                     capture_output=True, text=True,
                                     timeout=5).stdout.strip()
                if got and os.path.exists(got):
                    found = got
                    break
        except Exception:
            pass
    if not found:
        for root, _dirs, files in os.walk("/usr/share/fonts"):
            hit = next((f for f in sorted(files)
                        if "mono" in f.lower() and f.lower().endswith((".ttf", ".otf"))),
                       None)
            if hit:
                found = os.path.join(root, hit)
                break

    _font_path_cache = found
    return found or None


def load_mono_font(px: int):
    """A cached monospace font at `px`, or None if none could be found."""
    px = max(4, int(px))
    hit = _font_cache.get(px)
    if hit is not None:
        return hit
    path = find_mono_font()
    if not path:
        return None
    try:
        from PIL import ImageFont
        font = ImageFont.truetype(path, px)
    except Exception:
        return None
    if len(_font_cache) < 64:
        _font_cache[px] = font
    return font


def _config_home() -> str:
    if platform.system() == "Windows":
        base = os.environ.get("APPDATA") or os.path.expanduser("~\\AppData\\Roaming")
        return os.path.join(base, "CartoTUI")
    if platform.system() == "Darwin":
        return os.path.join(os.path.expanduser("~/Library/Application Support"), "CartoTUI")
    return os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")), "cartotui")


def snapshot_dir() -> str:
    d = os.path.join(_config_home(), "snapshots")
    os.makedirs(d, exist_ok=True)
    return d


def new_path(ext: str) -> str:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    return os.path.join(snapshot_dir(), f"cartotui_{stamp}.{ext}")


def _parse_style(style: str, chrome: dict, default_fg: str, default_bg: str) -> Tuple[str, str]:
    fg, bg = default_fg, default_bg
    s = style or ""
    if s.startswith("class:"):
        cls = s.split()[0][len("class:"):]
        resolved = chrome.get(cls)
        if resolved:
            s = resolved
    reverse = False
    for tok in s.split():
        if tok.startswith("bg:#"):
            bg = tok[3:]
        elif tok.startswith("fg:#"):
            fg = tok[3:]
        elif tok.startswith("#"):
            fg = tok
        elif tok == "reverse":
            reverse = True
    if reverse:
        fg, bg = bg, fg
    return fg, bg


def frame_to_html(rows: List[List[Run]], theme_name: str, title: str = "CartoTUI") -> str:
    from cartotui import theme_loader
    chrome = theme_loader.chrome_style_map(theme_name)
    ui = theme_loader.resolve_theme(theme_name)["ui"]
    page_bg = ui.get("bg", "#101014")
    default_fg = ui.get("fg", "#c8c8c8")
    default_bg = page_bg

    out: List[str] = []
    for row in rows:
        parts: List[str] = []
        for style, text in row:
            if not text:
                continue
            fg, bg = _parse_style(style, chrome, default_fg, default_bg)
            parts.append(
                f'<span style="color:{fg};background:{bg}">{html.escape(text)}</span>'
            )
        out.append("".join(parts) if parts else "&nbsp;")
    body = "\n".join(out)
    return (
        "<!doctype html>\n<html><head><meta charset=\"utf-8\">\n"
        f"<title>{html.escape(title)}</title>\n<style>\n"
        f"  body{{margin:0;background:{page_bg};}}\n"
        "  pre{margin:0;padding:12px;line-height:1.0;"
        "font-family:'Cascadia Mono','Consolas','DejaVu Sans Mono',monospace;"
        "font-size:12px;white-space:pre;}\n"
        "</style></head>\n<body><pre>"
        + body +
        "</pre></body></html>\n"
    )


def _hex_to_rgb(s) -> Tuple[int, int, int]:
    if isinstance(s, tuple):
        return s
    from cartotui import theme_loader
    return theme_loader._hex_to_rgb(s)


def frame_to_png(
    rows: List[List[Run]],
    theme_name: str,
    cell_px: int = 16,
    base_class: str = "map",
):
    """Rasterise a terminal frame to an image with a monospace font.

    This is the "what's on screen" export: the frame already carries the glyph
    rendering, the place labels and the aircraft, so it needs no overlay work of
    its own -- only a font and the theme's colours.

    `base_class` is the chrome class the app wraps the frame in. Cells inherit
    their background from it, which matters because the renderer emits fg-only
    styles: a flat patch of map background is a space, and what shows through is
    this class's bg.
    """
    from PIL import Image, ImageDraw

    from cartotui import theme_loader

    chrome = theme_loader.chrome_style_map(theme_name)
    ui = theme_loader.resolve_theme(theme_name)["ui"]
    base_fg, base_bg = _parse_style(chrome.get(base_class, ""), chrome,
                                    ui.get("fg", "#c8c8c8"), ui.get("bg", "#101014"))
    page_bg = _hex_to_rgb(base_bg)

    n_rows = len(rows)
    n_cols = max((sum(len(t) for _s, t in row) for row in rows), default=1)

    fh = max(4, int(cell_px))
    fw = max(1, int(round(fh * 0.6)))
    font = load_mono_font(fh)

    img = Image.new("RGB", (max(1, n_cols * fw), max(1, n_rows * fh)), page_bg)
    d = ImageDraw.Draw(img)

    for y, row in enumerate(rows):
        x = 0
        for style, text in row:
            if not text:
                continue
            fg, bg = _parse_style(style, chrome, base_fg, base_bg)
            fg_rgb, bg_rgb = _hex_to_rgb(fg), _hex_to_rgb(bg)
            for ch in text:
                px, py = x * fw, y * fh
                if bg_rgb != page_bg:
                    d.rectangle([px, py, px + fw, py + fh], fill=bg_rgb)
                if ch != " " and font is not None:
                    d.text((px, py), ch, font=font, fill=fg_rgb)
                x += 1
    return img


def save_frame_png(
    rows: List[List[Run]],
    theme_name: str,
    path: str,
    long_side: int = 1600,
    base_class: str = "map",
) -> str:
    """Save a terminal frame as a PNG roughly `long_side` on its longer edge.

    The cell size is derived from the target rather than fixed, so the same frame
    can come out as a thumbnail or a poster.
    """
    n_rows = max(1, len(rows))
    n_cols = max(1, max((sum(len(t) for _s, t in row) for row in rows), default=1))
    by_w = long_side / max(1e-6, n_cols * 0.6)
    by_h = long_side / n_rows
    cell = int(max(4, min(96, min(by_w, by_h))))
    img = frame_to_png(rows, theme_name, cell_px=cell, base_class=base_class)
    img.save(path)
    return path


def save_html(rows: List[List[Run]], theme_name: str, path: str, title: str = "CartoTUI") -> str:
    doc = frame_to_html(rows, theme_name, title)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path
