import dataclasses
from pathlib import Path

from .args_settings import ArgsSettings
from .edge_switch_config import EdgeSwitchConfig
from .hooks_config import HooksConfig
from .logging_config import LoggingConfig
from .mouse_button_switch_config import MouseButtonSwitchConfig


@dataclasses.dataclass(frozen=True)
class Config:
    hooks: HooksConfig
    arguments_settings: ArgsSettings
    cache_path: Path
    logging: LoggingConfig = dataclasses.field(default_factory=LoggingConfig)
    edge_switch: EdgeSwitchConfig = dataclasses.field(default_factory=EdgeSwitchConfig)
    mouse_button_switch: MouseButtonSwitchConfig = dataclasses.field(default_factory=MouseButtonSwitchConfig)
    host_names: dict[int, str] = dataclasses.field(default_factory=dict)  # 0-based host → user label
    config_path: Path | None = None  # the YAML file this config was (or would be) read from
