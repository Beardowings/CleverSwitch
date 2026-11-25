import dataclasses
from enum import StrEnum

from ..event.event import Event


class SwitchSource(StrEnum):
    DEVICE = "device"
    EDGE = "edge"
    BUTTON = "button"
    FOLLOW = "follow"  # the keyboard left by its own Easy-Switch key; the mouse is sent after it


@dataclasses.dataclass
class HostChangeEvent(Event):
    target_host: int
    source: SwitchSource = SwitchSource.DEVICE
