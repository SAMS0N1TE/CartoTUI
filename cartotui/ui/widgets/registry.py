from __future__ import annotations

from typing import Dict, List, Optional, Type

from cartotui.ui.widgets.base import Widget, WidgetContext

_REGISTRY: Dict[str, Type[Widget]] = {}


def register_widget(cls: Type[Widget]) -> Type[Widget]:
    name = getattr(cls, "name", None)
    if not name:
        raise ValueError("widget class needs a 'name'")
    _REGISTRY[name] = cls
    return cls


def widget_names() -> List[str]:
    return list(_REGISTRY.keys())


def widget_class(name: str) -> Optional[Type[Widget]]:
    return _REGISTRY.get(name)


def create_widget(name: str, ctx: WidgetContext) -> Optional[Widget]:
    cls = _REGISTRY.get(name)
    if cls is None:
        return None
    return cls(ctx)
