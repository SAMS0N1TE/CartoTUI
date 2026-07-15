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


def _print_server_status() -> int:
    from cartotui import adsb_server

    facts = adsb_server.host_facts()
    st = adsb_server.server_status()
    print(f"host      : {facts.system} {facts.arch}"
          + (f" ({facts.distro_id} {facts.codename})" if facts.distro_id else ""))
    print(f"installed : {', '.join(st['installed']) or '(none)'}")
    print(f"service   : {st['service'] or '(none)'}"
          + ("  active" if st["active"] else ""))
    print(f"sdr       : {', '.join(st['sdr']) or '(none detected)'}")
    print(f"port {adsb_server.SBS_PORT} : {'listening' if st['feeding'] else 'not listening'}")
    if not st["feeding"]:
        print("\nNo local feed. Options:")
        print("  cartotui-config adsb --source api      # no hardware needed")
        print("  cartotui-config adsb --install-server  # set up a receiver here")
    return 0 if st["feeding"] else 1


def _install_server(cfg, args) -> int:
    from cartotui import adsb_server

    facts = adsb_server.host_facts()
    backends = adsb_server.plan_backends(facts)
    if not backends:
        print(f"No known ADS-B server backend for {facts.system} {facts.arch}.")
        print("Use --source api for a no-hardware feed instead.")
        return 1

    sdr = adsb_server.detect_sdr()
    if not sdr:
        print("Note: no SDR dongle detected. A local server needs one to hear anything.")
        print("      (--source api needs no hardware.)\n")

    chosen = None
    if args.backend:
        for b in backends:
            if b.key == args.backend:
                chosen = b
                break
        if chosen is None:
            print(f"No backend {args.backend!r} available here. Available: "
                  + ", ".join(b.key for b in backends))
            return 1
    else:
        chosen = backends[0]
        if len(backends) > 1:
            print("Available backends: " + ", ".join(b.key for b in backends))
            print(f"Using {chosen.key} (override with --backend).\n")

    print(adsb_server.describe_plan(chosen))
    print()

    if chosen.manual_steps or not chosen.automatable:
        return 0

    if not args.yes:
        print("Re-run with --yes to execute, or follow the commands yourself.")
        return 0

    rc = adsb_server.run_plan(chosen)
    if rc != 0:
        return rc

    if adsb_server.port_open():
        cfg.update({"traffic": {"enabled": True, "source": "sbs1",
                                "sbs1": {"host": "localhost",
                                         "port": adsb_server.SBS_PORT}}})
        cfg.save()
        print(f"\nFeed is live. CartoTUI pointed at localhost:{adsb_server.SBS_PORT}")
        print(f"saved to {cfg.path}")
    else:
        print(f"\nInstalled, but nothing is listening on {adsb_server.SBS_PORT} yet.")
        print("Check the service and your antenna, then: cartotui-config adsb --test")
    return 0


def cmd_adsb(args) -> int:
    from cartotui import adsb_setup

    cfg = Config.load(args.config)

    if args.server_status:
        return _print_server_status()

    if args.install_server:
        return _install_server(cfg, args)

    if args.list_ports:
        ports = adsb_setup.list_serial_ports()
        if not ports:
            print("No serial ports detected.")
            return 1
        for dev, desc in ports:
            print(f"{dev:<12} {desc}")
        return 0

    if args.disable:
        cfg.update({"traffic": {"enabled": False, "source": "disabled"}})
        cfg.save()
        print(f"ADS-B disabled. Saved to {cfg.path}")
        return 0

    if args.source:
        patch: dict = {"enabled": True, "source": args.source}
        if args.source == "sbs1":
            sbs1 = {}
            if args.host:
                sbs1["host"] = args.host
            if args.port:
                sbs1["port"] = args.port
            patch["sbs1"] = sbs1
        elif args.source == "api":
            api = {}
            if args.provider:
                api["provider"] = args.provider
            if args.radius is not None:
                api["radius_nm"] = args.radius
            if args.interval is not None:
                api["interval_s"] = args.interval
            if args.lat is not None:
                api["lat"] = args.lat
            if args.lon is not None:
                api["lon"] = args.lon
            if args.no_follow_map:
                api["follow_map"] = False
            patch["api"] = api
        elif args.source in ("lakeshark", "lakeshark_tui"):
            ls = {}
            if args.serial_port:
                ls["port"] = args.serial_port
            if args.baud is not None:
                ls["baudrate"] = args.baud
            patch["lakeshark"] = ls
        elif args.source == "replay":
            rp = {}
            if args.path:
                rp["path"] = args.path
            patch["replay"] = rp
        elif args.source == "disabled":
            patch["enabled"] = False

        cfg.update({"traffic": patch})
        cfg.save()
        print(f"traffic.source = {args.source}")
        print(f"saved to {cfg.path}")
        if not args.test:
            return 0

    if args.test:
        ok, detail = adsb_setup.probe_config(cfg)
        print(("OK: " if ok else "Failed: ") + detail)
        return 0 if ok else 1

    return adsb_setup.run_wizard(cfg)


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

    ad = sub.add_parser(
        "adsb",
        help="Set up the ADS-B traffic connection (interactive by default).",
        description="Configure and test the live aircraft feed. With no flags, "
                    "runs an interactive wizard.",
    )
    ad.add_argument("--source", choices=("sbs1", "api", "lakeshark", "lakeshark_tui",
                                         "replay", "disabled"),
                    help="Set the source non-interactively.")
    ad.add_argument("--test", action="store_true", help="Probe the configured source and report.")
    ad.add_argument("--disable", action="store_true", help="Turn ADS-B traffic off.")
    ad.add_argument("--list-ports", action="store_true", help="List serial ports and exit.")
    ad.add_argument("--host", help="sbs1: feed host (e.g. 192.168.1.50).")
    ad.add_argument("--port", type=int, help="sbs1: feed port (default 30003).")
    ad.add_argument("--provider", choices=("airplanes.live", "adsb.lol", "adsb.fi"),
                    help="api: aggregator to poll.")
    ad.add_argument("--radius", type=float, help="api: radius in nautical miles (max 250).")
    ad.add_argument("--interval", type=float, help="api: poll interval in seconds.")
    ad.add_argument("--lat", type=float, help="api: fixed latitude.")
    ad.add_argument("--lon", type=float, help="api: fixed longitude.")
    ad.add_argument("--no-follow-map", action="store_true",
                    help="api: poll a fixed point instead of the map centre.")
    ad.add_argument("--serial-port", help="lakeshark: serial device (e.g. COM3, /dev/ttyUSB0).")
    ad.add_argument("--baud", type=int, help="lakeshark: baud rate (default 115200).")
    ad.add_argument("--path", help="replay: path to a recorded .jsonl capture.")
    ad.add_argument("--install-server", action="store_true",
                    help="Set up a local ADS-B server (dump1090/readsb) on this machine.")
    ad.add_argument("--backend", help="install-server: which backend (see --server-status).")
    ad.add_argument("--server-status", action="store_true",
                    help="Report the local ADS-B server and SDR, and whether 30003 is live.")
    ad.add_argument("--yes", action="store_true",
                    help="install-server: actually run the commands (default: just show them).")
    ad.set_defaults(func=cmd_adsb)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
