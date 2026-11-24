import dataclasses

from ..event.event import Event


@dataclasses.dataclass
class EasySwitchModeChangedEvent(Event):
    """``easy_switch.divert`` changed at runtime (tray menu). Published on ``flags``."""

    divert: bool
