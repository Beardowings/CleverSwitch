import dataclasses
import threading

from ...registry.logi_device_registry import LogiDeviceRegistry
from ...settings.settings_service import SettingsService
from ...topic.topics import Topics
from ..config.config import Config


@dataclasses.dataclass(frozen=True)
class AppContext:
    device_registry: LogiDeviceRegistry
    topics: Topics
    config: Config
    shutdown: threading.Event
    settings: SettingsService | None = None  # None only in tests that build a context by hand
