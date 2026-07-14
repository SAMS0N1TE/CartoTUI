from cartotui.ui.widgets import adsb_widget as _adsb
from cartotui.ui.widgets import compass_widget as _compass
from cartotui.ui.widgets import launcher_widget as _launcher
from cartotui.ui.widgets import location_widget as _location
from cartotui.ui.widgets import looks_widget as _looks
from cartotui.ui.widgets import radar_widget as _radar
from cartotui.ui.widgets import render_widget as _render
from cartotui.ui.widgets import snapshot_widget as _snapshot
from cartotui.ui.widgets import stats_widget as _stats
from cartotui.ui.widgets import theme_widget as _theme
from cartotui.ui.widgets import weather_widget as _weather
from cartotui.ui.widgets.base import Widget, WidgetContext
from cartotui.ui.widgets.manager import WidgetManager
from cartotui.ui.widgets.registry import create_widget, register_widget, widget_names

DEFAULT_WIDGET_ORDER = ["widgets", "looks", "render", "location", "compass",
                        "adsb", "stats", "weather", "radar", "snapshot", "theme"]

__all__ = [
    "Widget", "WidgetContext",
    "register_widget", "create_widget", "widget_names",
    "WidgetManager", "DEFAULT_WIDGET_ORDER",
]
