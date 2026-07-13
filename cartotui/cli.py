
from __future__ import annotations

import argparse
import os
import sys

from cartotui import __version__
from cartotui.config import Config, default_config_path
from cartotui.logging_conf import setup_logging


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="cartotui",
        description="Interactive ASCII map viewer for the terminal.",
    )
    p.add_argument("--version", action="version", version=f"cartotui {__version__}")
    p.add_argument(
        "--config",
        metavar="PATH",
        help=f"Path to config JSON (default: {default_config_path()}).",
    )
    p.add_argument("--lat", type=float, help="Override starting latitude.")
    p.add_argument("--lon", type=float, help="Override starting longitude.")
    p.add_argument("--zoom", "-z", type=int, help="Override starting zoom (0..19).")
    p.add_argument(
        "--mode",
        choices=("vector", "ascii", "quadrant", "braille", "half"),
        help="Override render mode (vector = vector tiles; rest = raster).",
    )
    p.add_argument(
        "--palette",
        help="Override palette name (see resources/palettes.json).",
    )
    p.add_argument(
        "--no-color",
        action="store_true",
        help="Disable colour output.",
    )
    p.add_argument(
        "--theme",
        metavar="NAME",
        help="Override UI theme (built-in or a custom theme from the themes folder).",
    )
    p.add_argument(
        "--protomaps-key",
        metavar="KEY",
        help="Protomaps API key. Sets vector.source=protomaps_api implicitly.",
    )
    p.add_argument(
        "--pmtiles-url",
        metavar="URL",
        help="HTTP-accessible .pmtiles archive URL. Sets vector.source=pmtiles_url.",
    )
    p.add_argument(
        "--mvt-url",
        metavar="URL",
        help="Raw MVT tile URL template like https://example/{z}/{x}/{y}.mvt. "
             "Sets vector.source=mvt_url.",
    )
    p.add_argument(
        "--print-config",
        action="store_true",
        help="Print resolved config and exit.",
    )
    return p

def _apply_overrides(cfg: Config, args: argparse.Namespace) -> None:
    overrides = {}
    if args.lat is not None or args.lon is not None or args.zoom is not None \
       or args.mode is not None or args.palette is not None:
        overrides["map"] = {}
        if args.lat is not None:
            overrides["map"]["center_lat"] = args.lat
        if args.lon is not None:
            overrides["map"]["center_lon"] = args.lon
        if args.zoom is not None:
            overrides["map"]["zoom"] = args.zoom
        if args.mode is not None:
            overrides["map"]["mode"] = args.mode
        if args.palette is not None:
            overrides["map"]["palette"] = args.palette
    if args.no_color:
        overrides.setdefault("render", {})["color"] = False
    if args.theme is not None:
        overrides.setdefault("ui", {})["theme"] = args.theme

    if args.protomaps_key is not None:
        overrides.setdefault("vector", {})["source"] = "protomaps_api"
        overrides["vector"]["protomaps_api_key"] = args.protomaps_key
    if args.pmtiles_url is not None:
        overrides.setdefault("vector", {})["source"] = "pmtiles_url"
        overrides["vector"]["pmtiles_url"] = args.pmtiles_url
    if args.mvt_url is not None:
        overrides.setdefault("vector", {})["source"] = "mvt_url"
        overrides["vector"]["mvt_url"] = args.mvt_url

    if overrides:
        cfg.update(overrides)

def main(argv=None) -> int:
    args = _parser().parse_args(argv)

    cfg = Config.load(args.config)
    _apply_overrides(cfg, args)
    setup_logging(cfg)

    if args.print_config:
        import json
        json.dump(cfg.data, sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    if os.name == "nt" and not sys.stdout.isatty():
        sys.stderr.write(
            "No Windows console detected. Run from cmd, PowerShell, or Windows Terminal.\n"
        )
        return 1
    if not sys.stdout.isatty():
        sys.stderr.write("Standard output is not a TTY; cartotui needs an interactive terminal.\n")
        return 1

    from cartotui.ui.app import CartoTUIApp

    try:
        app = CartoTUIApp(cfg)
        app.run()
    except Exception as e:
        import traceback
        sys.stderr.write("\n")
        sys.stderr.write("CartoTUI crashed:\n")
        sys.stderr.write(f"  {e.__class__.__name__}: {e}\n\n")
        sys.stderr.write("Traceback:\n")
        traceback.print_exc(file=sys.stderr)
        sys.stderr.write(
            "\nIf this looks like a bug, please file an issue at\n"
            "  https://github.com/SAMS0N1TE/CartoTUI/issues\n"
        )
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
