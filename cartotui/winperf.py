"""Windows frame-pacing and input tuning.

Every entry point here is a no-op on other platforms, so callers do not need to
branch on the OS themselves.
"""

from __future__ import annotations

import logging
import os
import types

log = logging.getLogger("cartotui.winperf")

IS_WINDOWS = os.name == "nt"

_TIMERR_NOERROR = 0
_timer_period: int | None = None


def begin_high_resolution_timer(period_ms: int = 1) -> bool:
    """Raise this process's timer resolution.

    Since Windows 10 2004 the timer period is per-process: a process that never
    asks for a finer one runs on the 15.6 ms default however high another
    process has pushed the global value. asyncio's `call_later` then rounds a
    33 ms redraw interval up to roughly 47 ms, so a 30 fps cap really delivers
    about 21 before any work happens.

    Returns True if the period was raised, in which case the caller owns a
    matching `end_high_resolution_timer`.
    """
    global _timer_period
    if not IS_WINDOWS or _timer_period is not None:
        return False
    try:
        import ctypes

        period = max(1, int(period_ms))
        if ctypes.windll.winmm.timeBeginPeriod(period) == _TIMERR_NOERROR:
            _timer_period = period
            log.debug("timer resolution raised to %d ms", period)
            return True
        log.debug("timeBeginPeriod(%d) refused", period)
    except Exception as e:  # pragma: no cover - depends on the host
        log.debug("timeBeginPeriod unavailable: %s", e)
    return False


def end_high_resolution_timer() -> None:
    """Drop the timer period raised by `begin_high_resolution_timer`."""
    global _timer_period
    if _timer_period is None:
        return
    try:
        import ctypes

        ctypes.windll.winmm.timeEndPeriod(_timer_period)
    except Exception as e:  # pragma: no cover - depends on the host
        log.debug("timeEndPeriod failed: %s", e)
    finally:
        _timer_period = None


# 1000 = button press/release, 1002 = motion *while a button is held*,
# 1015/1006 = the two extended coordinate encodings prompt_toolkit parses.
_MOUSE_ON = ("\x1b[?1000h", "\x1b[?1002h", "\x1b[?1015h", "\x1b[?1006h")
_MOUSE_OFF = ("\x1b[?1006l", "\x1b[?1015l", "\x1b[?1002l", "\x1b[?1000l")


def use_button_only_mouse(output) -> bool:
    """Ask the terminal for 1002 rather than prompt_toolkit's 1003.

    1003 reports every pointer movement across the window, and prompt_toolkit
    redraws after each input event, so merely resting the mouse over a full
    screen map costs a redraw per motion report. The only things here that read
    MOUSE_MOVE are the map drag-pan and widget dragging, both of which happen
    with a button held -- which 1002 still reports.

    Best effort: returns False if the output does not take the override.
    """
    if output is None:
        return False
    try:
        def enable_mouse_support(self) -> None:
            for seq in _MOUSE_ON:
                self.write_raw(seq)

        def disable_mouse_support(self) -> None:
            for seq in _MOUSE_OFF:
                self.write_raw(seq)

        output.enable_mouse_support = types.MethodType(enable_mouse_support, output)
        output.disable_mouse_support = types.MethodType(disable_mouse_support, output)
        return True
    except Exception as e:
        log.debug("could not switch mouse tracking to 1002: %s", e)
        return False
