import logging
import struct
from collections.abc import Callable

from ..event.easy_switch_mode_changed_event import EasySwitchModeChangedEvent
from ..event.set_report_flag_event import SetReportFlagEvent
from ..event.write_event import WriteEvent
from ..hidpp.constants import (
    ANALYTICS_BYTE9,
    FEATURE_REPROG_CONTROLS_V4,
    HOST_SWITCH_CIDS,
    KEY_FLAG_ANALYTICS,
    KEY_FLAG_DIVERTABLE,
    KEY_FLAG_PERSISTENTLY_DIVERTABLE,
    MAP_FLAG_DIVERTED,
    MAP_FLAG_PERSISTENTLY_DIVERTED,
    SW_ID_DIVERT,
)
from ..hidpp.protocol import build_msg
from ..model.logi_device import ROLE_MOUSE, LogiDevice
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)


_ANALYTICS_OFF_BYTE9 = 0x02  # avalid set, analyticsKeyEvt cleared


class SetReportFlagSubscriber(Subscriber):
    """Arms the Easy-Switch keys: analytics (the keyboard still switches itself and reports the press)
    when the keyboard supports it, otherwise a divert (the keyboard only reports, CleverSwitch switches).

    ``prefer_divert`` (``easy_switch.divert``, tray menu) forces the divert on a keyboard that offers
    both. That matters when a peer app re-arms the keys after us: an analytics press is then reported
    to the peer only, the keyboard leaves, and the mouse stays behind; a divert keeps the keyboard
    here until CleverSwitch has sent every device. It is always temporary, so a crash or a power
    cycle gives the keys back.
    """

    def __init__(
        self, device_registry: LogiDeviceRegistry, topics: Topics, prefer_divert: Callable[[], bool] = lambda: False
    ):
        self._device_registry = device_registry
        self._topics = topics
        self._prefer_divert = prefer_divert
        topics.flags.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, EasySwitchModeChangedEvent):
            self._on_mode_changed(event)
            return
        if not isinstance(event, SetReportFlagEvent):
            return

        device = self._device_registry.get_by_wpid(event.wpid)
        if device is None:
            log.warning(f"device wpid=0x{event.wpid:04X} not found")
            return

        reprog_idx = device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        if reprog_idx is None:
            log.warning(f"wpid=0x{event.wpid:04X} has no REPROG_CONTROLS_V4")
            return

        if not device.supported_flags & {KEY_FLAG_ANALYTICS, KEY_FLAG_DIVERTABLE}:
            # A mouse has x1B04 only for mouse_button_switch, which arms its own button; it has no ES keys.
            if device.role == ROLE_MOUSE:
                return
            log.warning(f"wpid=0x{event.wpid:04X} has no reprog flags")
            return

        if self._forced_divert(device):
            for cid in event.cids:
                self._write(event.slot, event.pid, device, cid, _divert_params(cid, event.enable))
                log.debug(
                    f"{'Setting' if event.enable else 'Unsetting'} divert CID 0x{cid:04X} on wpid=0x{event.wpid:04X}"
                )
            return

        for cid in event.cids:
            if KEY_FLAG_ANALYTICS in device.supported_flags:
                params = struct.pack("!HBHB", cid, 0x00, 0x0000, ANALYTICS_BYTE9)
            else:
                # Temporary divert: valid + action
                if event.enable:
                    bfield = MAP_FLAG_DIVERTED << 1 | MAP_FLAG_DIVERTED
                else:
                    bfield = MAP_FLAG_DIVERTED << 1
                # Persistent divert if the CID supports it
                if KEY_FLAG_PERSISTENTLY_DIVERTABLE in device.supported_flags:
                    bfield |= MAP_FLAG_PERSISTENTLY_DIVERTED << 1
                    if event.enable:
                        bfield |= MAP_FLAG_PERSISTENTLY_DIVERTED
                params = struct.pack("!HBH", cid, bfield, 0)

            request_id = (reprog_idx << 8) | 0x30 | SW_ID_DIVERT
            msg = build_msg(event.slot, request_id, params)
            self._topics.write.publish(WriteEvent(slot=event.slot, pid=event.pid, hid_message=msg))
            action = (
                "Enabling analytics for"
                if KEY_FLAG_ANALYTICS in device.supported_flags
                else ("Setting divert" if event.enable else "Unsetting divert")
            )
            log.debug(f"{action} CID 0x{cid:04X} on wpid=0x{event.wpid:04X}")

    def _forced_divert(self, device: LogiDevice) -> bool:
        return (
            self._prefer_divert()
            and KEY_FLAG_ANALYTICS in device.supported_flags
            and KEY_FLAG_DIVERTABLE in device.supported_flags
        )

    def _on_mode_changed(self, event: EasySwitchModeChangedEvent) -> None:
        """Moves connected keyboards that offer both modes from one to the other."""
        for device in self._device_registry.all_entries():
            if not device.connected or device.role == ROLE_MOUSE:
                continue
            if FEATURE_REPROG_CONTROLS_V4 not in device.available_features:
                continue
            if not {KEY_FLAG_ANALYTICS, KEY_FLAG_DIVERTABLE} <= device.supported_flags:
                if event.divert:
                    log.warning(f"'{device.display_name}' cannot divert its Easy-Switch keys; keeping analytics")
                continue
            for cid in HOST_SWITCH_CIDS:
                if event.divert:
                    self._write(device.slot, device.pid, device, cid, _analytics_params(cid, False))
                    self._write(device.slot, device.pid, device, cid, _divert_params(cid, True))
                else:
                    self._write(device.slot, device.pid, device, cid, _divert_params(cid, False))
                    self._write(device.slot, device.pid, device, cid, _analytics_params(cid, True))
            mode = "divert" if event.divert else "analytics"
            log.info(f"Easy-Switch keys on '{device.display_name}' now use {mode}")

    def _write(self, slot: int, pid: int, device: LogiDevice, cid: int, params: bytes) -> None:
        reprog_idx = device.available_features[FEATURE_REPROG_CONTROLS_V4]
        request_id = (reprog_idx << 8) | 0x30 | SW_ID_DIVERT
        self._topics.write.publish(WriteEvent(slot=slot, pid=pid, hid_message=build_msg(slot, request_id, params)))


def _divert_params(cid: int, enable: bool) -> bytes:
    bfield = MAP_FLAG_DIVERTED << 1 | (MAP_FLAG_DIVERTED if enable else 0)
    return struct.pack("!HBH", cid, bfield, 0)


def _analytics_params(cid: int, enable: bool) -> bytes:
    return struct.pack("!HBHB", cid, 0x00, 0x0000, ANALYTICS_BYTE9 if enable else _ANALYTICS_OFF_BYTE9)
