
from __future__ import annotations

from typing import Callable, Optional, Tuple

from prompt_toolkit.application.current import get_app_or_none
from prompt_toolkit.filters import Condition
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import ConditionalContainer, HSplit
from prompt_toolkit.widgets import Frame, TextArea


def _parse(s: str) -> Optional[Tuple[float, float, Optional[int]]]:
    parts = [p.strip() for p in s.replace(";", ",").split(",")]
    if len(parts) < 2:
        return None
    try:
        lat = float(parts[0])
        lon = float(parts[1])
    except ValueError:
        return None
    z: Optional[int] = None
    if len(parts) >= 3 and parts[2]:
        try:
            z = int(float(parts[2]))
        except ValueError:
            z = None
    if not (-85.05 <= lat <= 85.05 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon, z

class GotoPrompt:
    def __init__(
        self,
        on_submit: Callable[[float, float, Optional[int]], None],
    ) -> None:
        self.visible = False
        self.on_submit = on_submit
        self._error = ""

        self.text_area = TextArea(
            multiline=False,
            prompt="goto: ",
            style="class:dialog.body",
            focus_on_click=True,
            height=1,
        )
        self.frame = Frame(
            self.text_area,
            title="Go to (lat, lon[, zoom])",
            style="class:dialog",
        )
        self._kb = KeyBindings()

        @self._kb.add("enter", filter=Condition(lambda: self.visible))
        def _(event):
            text = self.text_area.text.strip()
            parsed = _parse(text)
            if parsed is None:
                self._error = "Bad format — try `42.36, -71.06, 12`"
                return
            lat, lon, z = parsed
            self.on_submit(lat, lon, z)
            self.text_area.text = ""
            self._error = ""
            self.hide()

        @self._kb.add("escape", filter=Condition(lambda: self.visible))
        @self._kb.add("c-g", filter=Condition(lambda: self.visible))
        def _(event):
            self.text_area.text = ""
            self._error = ""
            self.hide()

        self.text_area.control.key_bindings = self._kb
        self.container = ConditionalContainer(
            content=HSplit([self.frame]),
            filter=Condition(lambda: self.visible),
        )

    def __pt_container__(self):
        return self.container

    def show(self) -> None:
        self.visible = True
        app = get_app_or_none()
        if app:
            try:
                app.layout.focus(self.text_area)
            except Exception:
                pass
            app.invalidate()

    def hide(self) -> None:
        self.visible = False
        app = get_app_or_none()
        if app:
            app.invalidate()
