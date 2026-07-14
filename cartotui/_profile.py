from __future__ import annotations

import cProfile
import io
import os
import pstats
import sys
import threading
import time

_DEFAULT_DUMP = "cartotui.prof"
_DEFAULT_TOP = 40


def _print_stats(prof: cProfile.Profile, top: int) -> None:
    s = io.StringIO()
    ps = pstats.Stats(prof, stream=s).sort_stats("cumulative")
    ps.print_stats(top)
    sys.stderr.write("\n=== cProfile (cumulative, top %d) ===\n" % top)
    sys.stderr.write(s.getvalue())

    s2 = io.StringIO()
    ps2 = pstats.Stats(prof, stream=s2).sort_stats("tottime")
    ps2.print_stats(top)
    sys.stderr.write("\n=== cProfile (tottime, top %d) ===\n" % top)
    sys.stderr.write(s2.getvalue())


def _periodic_dump(prof: cProfile.Profile, dump_path: str, every_s: float, stop: threading.Event) -> None:
    while not stop.wait(every_s):
        try:
            prof.dump_stats(dump_path)
        except Exception:
            pass


def main() -> int:
    dump_path = os.environ.get("CARTOTUI_PROF_DUMP", _DEFAULT_DUMP)
    top = int(os.environ.get("CARTOTUI_PROF_TOP", str(_DEFAULT_TOP)))
    interval = float(os.environ.get("CARTOTUI_PROF_INTERVAL", "10"))

    sys.stderr.write(
        "[_profile] starting cartotui under cProfile\n"
        "[_profile] dump:%s top:%d interval:%.1fs\n"
        "[_profile] press Ctrl-C to stop and emit stats\n"
        % (dump_path, top, interval)
    )

    from cartotui.cli import main as cli_main

    prof = cProfile.Profile()
    stop = threading.Event()
    dumper = threading.Thread(
        target=_periodic_dump,
        args=(prof, dump_path, interval, stop),
        daemon=True,
        name="prof-dumper",
    )

    started = time.time()
    rc = 0
    prof.enable()
    dumper.start()
    try:
        rc = cli_main(sys.argv[1:])
    except (KeyboardInterrupt, SystemExit) as e:
        if isinstance(e, SystemExit):
            rc = e.code if isinstance(e.code, int) else 0
    except Exception:
        import traceback
        traceback.print_exc(file=sys.stderr)
        rc = 1
    finally:
        prof.disable()
        stop.set()
        try:
            prof.dump_stats(dump_path)
        except Exception as e:
            sys.stderr.write("[_profile] dump_stats failed: %s\n" % e)

    elapsed = time.time() - started
    sys.stderr.write("[_profile] ran %.1fs, rc=%s\n" % (elapsed, rc))
    sys.stderr.write("[_profile] stats written to %s\n" % dump_path)

    _print_stats(prof, top)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
