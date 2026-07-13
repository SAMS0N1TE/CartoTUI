from __future__ import annotations

import html
import os
import platform
import time
from typing import List, Tuple

Run = Tuple[str, str]


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


def save_html(rows: List[List[Run]], theme_name: str, path: str, title: str = "CartoTUI") -> str:
    doc = frame_to_html(rows, theme_name, title)
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)
    return path
