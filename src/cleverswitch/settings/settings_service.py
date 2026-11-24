"""Runtime-editable settings: the single place the tray changes, persists and announces them."""

from __future__ import annotations

import dataclasses
import logging
import threading
from typing import Any

from ..config.config_file import ConfigFileWriter
from ..event.easy_switch_mode_changed_event import EasySwitchModeChangedEvent
from ..event.mouse_button_switch_changed_event import MouseButtonSwitchChangedEvent
from ..hidpp.constants import HOST_SWITCH_CIDS, MOUSE_BUTTON_CIDS
from ..model.config.config import Config
from ..model.config.mouse_button_switch_config import MouseButtonSwitchConfig
from ..topic.topics import Topics

log = logging.getLogger(__name__)

HOST_COUNT = len(HOST_SWITCH_CIDS)
_BUTTON_NAMES = {cid: name for name, cid in MOUSE_BUTTON_CIDS.items()}


class SettingsService:
    """Holds the live mouse button switch settings and the host labels.

    Every change is written to the config file (when there is one) and, for the mouse button switch,
    announced as MouseButtonSwitchChangedEvent on the ``flags`` topic, so MouseButtonSwitchSubscriber
    re-arms the mouse without a restart.
    """

    def __init__(self, config: Config, topics: Topics, writer: ConfigFileWriter | None) -> None:
        self._topics = topics
        self._writer = writer
        self._lock = threading.Lock()
        self._mouse_button_switch = config.mouse_button_switch
        self._host_names = dict(config.host_names)
        self._easy_switch_divert = config.easy_switch_divert

    @property
    def mouse_button_switch(self) -> MouseButtonSwitchConfig:
        with self._lock:
            return self._mouse_button_switch

    @property
    def host_names(self) -> dict[int, str]:
        with self._lock:
            return dict(self._host_names)

    @property
    def easy_switch_divert(self) -> bool:
        with self._lock:
            return self._easy_switch_divert

    def set_easy_switch_divert(self, divert: bool) -> None:
        with self._lock:
            if self._easy_switch_divert == divert:
                return
            self._easy_switch_divert = divert
        log.info(f"Keyboard Easy-Switch keys: {'divert' if divert else 'analytics where supported'}")
        self._persist(lambda raw: _store_easy_switch(raw, divert))
        self._topics.flags.publish(EasySwitchModeChangedEvent(slot=0, pid=0, divert=divert))

    @property
    def config_path(self):
        return self._writer.path if self._writer is not None else None

    # ── Mouse button switch ─────────────────────────────────────────────

    def set_enabled(self, enabled: bool) -> None:
        self._change_mouse_button_switch(enabled=enabled)

    def set_target_host(self, host: int) -> None:
        if host not in range(HOST_COUNT):
            raise ValueError(f"host {host} out of range")
        self._change_mouse_button_switch(target_host=host)

    def set_button(self, cid: int) -> None:
        self._change_mouse_button_switch(cid=cid)

    def set_divert(self, divert: bool) -> None:
        self._change_mouse_button_switch(divert=divert)

    def _change_mouse_button_switch(self, **changes: Any) -> None:
        with self._lock:
            old = self._mouse_button_switch
            new = dataclasses.replace(old, **changes)
            if new == old:
                return
            self._mouse_button_switch = new
        log.info(f"Mouse button switch settings changed: {_describe(new)}")
        self._persist(lambda raw: _store_mouse_button_switch(raw, new))
        self._topics.flags.publish(MouseButtonSwitchChangedEvent(slot=0, pid=0, old=old, new=new))

    # ── Host labels ─────────────────────────────────────────────────────

    def set_host_name(self, host: int, name: str | None) -> None:
        if host not in range(HOST_COUNT):
            raise ValueError(f"host {host} out of range")
        name = (name or "").strip() or None
        with self._lock:
            if self._host_names.get(host) == name:
                return
            if name is None:
                self._host_names.pop(host, None)
            else:
                self._host_names[host] = name
            names = dict(self._host_names)
        self._persist(lambda raw: _store_host_names(raw, names))

    def _persist(self, mutate) -> None:
        if self._writer is not None:
            self._writer.update(mutate)


def _describe(config: MouseButtonSwitchConfig) -> str:
    host = "none" if config.target_host is None else str(config.target_host + 1)
    return (
        f"enabled={config.enabled}, button CID 0x{config.cid:04X}, host {host}, "
        f"{'divert' if config.divert else 'listen only'}"
    )


def _store_mouse_button_switch(raw: dict[str, Any], config: MouseButtonSwitchConfig) -> None:
    section = raw.get("mouse_button_switch")
    if not isinstance(section, dict):
        section = {}
        raw["mouse_button_switch"] = section
    section["enabled"] = config.enabled
    section["button"] = _BUTTON_NAMES.get(config.cid, f"0x{config.cid:04X}")
    if config.target_host is None:
        section.pop("host", None)
    else:
        section["host"] = config.target_host + 1
    section["divert"] = config.divert


def _store_easy_switch(raw: dict[str, Any], divert: bool) -> None:
    section = raw.get("easy_switch")
    if not isinstance(section, dict):
        section = {}
        raw["easy_switch"] = section
    section["divert"] = divert


def _store_host_names(raw: dict[str, Any], names: dict[int, str]) -> None:
    if names:
        raw["host_names"] = {host + 1: names[host] for host in sorted(names)}
    else:
        raw.pop("host_names", None)
