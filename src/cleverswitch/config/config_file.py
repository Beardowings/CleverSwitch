"""Creating and updating the YAML config file on the user's behalf (first start, tray menu)."""

from __future__ import annotations

import logging
import os
import tempfile
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

_HEADER = (
    "# CleverSwitch configuration.\n"
    "# The tray / menu bar icon updates this file; it rewrites it without comments.\n"
    "# Every option is described in config.example.yaml.\n"
)

DEFAULT_CONFIG: dict[str, Any] = {
    "mouse_button_switch": {
        "enabled": True,
        "button": "gesture",
        "divert": True,
    },
}


def ensure_config_file(path: Path) -> bool:
    """Write the default config to ``path`` when no file exists there. Returns True if one was written.

    Never raises: a config that cannot be written leaves the daemon on built-in defaults.
    """
    if path.exists():
        return False
    try:
        _write(path, DEFAULT_CONFIG)
    except OSError as e:
        log.warning(f"Could not create the default config at {path}: {e}")
        return False
    log.info(f"Created default config at {path}")
    return True


class ConfigFileWriter:
    """Read-modify-write of the config file, one change at a time, written atomically."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    @property
    def path(self) -> Path:
        return self._path

    def update(self, mutate: Callable[[dict[str, Any]], None]) -> bool:
        """Apply ``mutate`` to the file's top-level mapping and write it back. Returns False on failure.

        A file that does not parse is left alone: overwriting it would throw away the user's settings.
        """
        with self._lock:
            try:
                raw = self._read()
            except (OSError, yaml.YAMLError, TypeError) as e:
                log.error(f"Not saving settings: cannot read {self._path}: {e}")
                return False
            mutate(raw)
            try:
                _write(self._path, raw)
            except OSError as e:
                log.error(f"Could not save settings to {self._path}: {e}")
                return False
            return True

    def _read(self) -> dict[str, Any]:
        if not self._path.exists():
            return {}
        with open(self._path, encoding="utf-8") as f:
            raw = yaml.safe_load(f) or {}
        if not isinstance(raw, dict):
            raise TypeError("top level must be a mapping")
        return raw


def _write(path: Path, raw: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = _HEADER + yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False)
    fd, tmp = tempfile.mkstemp(prefix=".config-", suffix=".yaml", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
