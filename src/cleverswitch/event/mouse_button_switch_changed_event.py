import dataclasses

from ..event.event import Event
from ..model.config.mouse_button_switch_config import MouseButtonSwitchConfig


@dataclasses.dataclass
class MouseButtonSwitchChangedEvent(Event):
    """The mouse button switch settings changed at runtime (tray menu). Published on ``flags``."""

    old: MouseButtonSwitchConfig
    new: MouseButtonSwitchConfig
