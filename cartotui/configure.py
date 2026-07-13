from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from typing import Any

from cartotui.config import DEFAULT_CONFIG, Config, default_config_path


def _split(path: str):
    return [p for p in path.split(".") if p]


def _get(data: dict, path: str) -> Any:
    cur: Any = data
    for part in _split(path):
        if not isinstance(cur, dict) or part not in cur:
            raise KeyError(path)
        cur = cur[part]
    return cur


def _nest(path: str, value: Any) -> dict:
    parts = _split(path)
    out: dict = {}
    cur = out
    for part in parts[:-1]:
        cur[part] = {}
        cur = cur[part]
    cur[parts[-1]] = value
    return out


def _parse_value(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return raw


def _flatten(data: dict, prefix: str = ""):
    for k, v in data.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            yield from _flatten(v, key)
        else:
            yield key, v


def cmd_path(args) -> int:
    print(args.config or default_config_path())
    return 0


def cmd_get(args) -> int:
    cfg = Config.load(args.config)
    try:
        val = _get(cfg.data, args.key)
    except KeyError:
        sys.stderr.write(f"No such key: {args.key}\n")
        return 1
    print(json.dumps(val, indent=2) if isinstance(val, (dict, list)) else val)
    return 0


def cmd_set(args) -> int:
    cfg = Config.load(args.config)
    value = _parse_value(args.value)
    try:
        _get(DEFAULT_CONFIG, args.key)
        known = True
    except KeyError:
        known = False
    cfg.update(_nest(args.key, value))
    cfg.save()
    try:
        saved = _get(cfg.data, args.key)
    except KeyError:
        saved = value
    note = "" if known else "  (note: not a standard key)"
    print(f"{args.key} = {json.dumps(saved) if isinstance(saved,(dict,list)) else saved}{note}")
    print(f"saved to {cfg.path}")
    return 0


def cmd_list(args) -> int:
    cfg = Config.load(args.config)
    if args.flat:
        for k, v in _flatten(cfg.data):
            print(f"{k} = {json.dumps(v) if isinstance(v,(list,dict)) else v}")
    else:
        json.dump(cfg.data, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
    return 0


def cmd_themes(args) -> int:
    from cartotui import theme_loader
    cur = Config.load(args.config).data["ui"].get("theme")
    for name in theme_loader.available_theme_names():
        t = theme_loader.resolve_theme(name)
        tag = "builtin" if t.get("builtin") else "custom "
        mark = "*" if name == cur else " "
        print(f" {mark} [{tag}] {name}")
    print(f"\nuser theme folder: {theme_loader.user_theme_dir()}")
    return 0


def cmd_reset(args) -> int:
    path = args.config or default_config_path()
    if os.path.exists(path):
        backup = path + ".bak"
        try:
            shutil.copyfile(path, backup)
            print(f"backed up existing config to {backup}")
        except OSError:
            pass
    cfg = Config(dict(DEFAULT_CONFIG), path)
    cfg.save()
    print(f"reset config written to {path}")
    return 0


def cmd_edit(args) -> int:
    path = args.config or default_config_path()
    if not os.path.exists(path):
        Config.load(path)
    editor = os.environ.get("EDITOR")
    try:
        if editor:
            subprocess.call([editor, path])
        elif os.name == "nt":
            os.startfile(path)  # type: ignore[attr-defined]
        else:
            subprocess.call(["xdg-open", path])
    except Exception as e:
        sys.stderr.write(f"Could not open editor: {e}\nEdit manually: {path}\n")
        return 1
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cartotui-config",
        description="Read and edit the CartoTUI config.json.",
    )
    p.add_argument("--config", metavar="PATH", help="Config file (default: standard location).")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("path", help="Print the config file path.").set_defaults(func=cmd_path)

    g = sub.add_parser("get", help="Print one value, e.g. get ui.theme")
    g.add_argument("key")
    g.set_defaults(func=cmd_get)

    s = sub.add_parser("set", help="Set a value, e.g. set ui.theme dark")
    s.add_argument("key")
    s.add_argument("value")
    s.set_defaults(func=cmd_set)

    ls = sub.add_parser("list", help="Print the whole config.")
    ls.add_argument("--flat", action="store_true", help="One dotted key per line.")
    ls.set_defaults(func=cmd_list)

    sub.add_parser("themes", help="List available themes.").set_defaults(func=cmd_themes)
    sub.add_parser("reset", help="Reset config to defaults (backs up first).").set_defaults(func=cmd_reset)
    sub.add_parser("edit", help="Open the config in your editor.").set_defaults(func=cmd_edit)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
