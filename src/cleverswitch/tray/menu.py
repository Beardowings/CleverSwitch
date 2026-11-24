"""The menu as plain data, so it is built and tested without a GUI toolkit."""

from __future__ import annotations

import dataclasses
from collections.abc import Callable


@dataclasses.dataclass(frozen=True)
class MenuEntry:
    text: str = ""
    action: Callable[[], None] | None = None
    checked: bool | None = None  # None: not a checkable entry
    radio: bool = False
    enabled: bool = True
    submenu: tuple[MenuEntry, ...] | None = None
    separator: bool = False


SEPARATOR = MenuEntry(separator=True)
