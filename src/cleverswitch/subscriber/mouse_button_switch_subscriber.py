import logging
import struct
import threading
from collections.abc import Callable

from ..cache.device_cache import DeviceCache
from ..event.device_connected_event import DeviceConnectedEvent
from ..event.hidpp_error_event import HidppErrorEvent
from ..event.hidpp_notification_event import HidppNotificationEvent
from ..event.host_change_event import HostChangeEvent, SwitchSource
from ..event.info_task_progress_event import InfoTaskProgressEvent
from ..event.set_report_flag_event import SetReportFlagEvent
from ..event.transport_disconnected_event import TransportDisconnectedEvent
from ..event.write_event import WriteEvent
from ..hidpp.constants import FEATURE_REPROG_CONTROLS_V4, MAP_FLAG_DIVERTED, SW_ID_DIVERT
from ..hidpp.protocol import build_msg
from ..model.config.mouse_button_switch_config import MouseButtonSwitchConfig
from ..model.logi_device import ROLE_MOUSE, LogiDevice
from ..model.switch_echo_guard import SwitchEchoGuard
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics
from .task.constants import Task
from .task.feature.mouse_reprog_feature_task import MouseReprogFeatureTask

log = logging.getLogger(__name__)

_DIVERTED_BUTTONS = 0  # x1B04 divertedButtonsEvent: up to four pressed CIDs, 2 bytes each
_SET_CID_REPORTING = 3
_MAX_PRESSED_CIDS = 4


class MouseButtonSwitchSubscriber(Subscriber):
    """Switches every device to the configured host when the configured mouse button is pressed.

    The button is armed (diverted) over x1B04 setCidReporting, so the mouse reports presses as
    divertedButtonsEvent notifications instead of acting on them. With ``divert: false`` nothing is
    armed: presses are only seen while a peer app (Logi Options+) diverts the button itself, because
    every open HID handle receives the device's notifications.

    Discovery resolves x1B04 for keyboards only, so this subscriber resolves it on mice itself
    (MouseReprogFeatureTask). Arming then rides on SetReportFlagEvent, which the reconnection path,
    the GATT re-arm and the shutdown un-divert already publish for every device that has x1B04.
    """

    def __init__(
        self,
        config: MouseButtonSwitchConfig,
        device_registry: LogiDeviceRegistry,
        topics: Topics,
        cache: DeviceCache,
        echo_guard: SwitchEchoGuard,
        stopping: Callable[[], bool] = lambda: False,
    ):
        self._config = config
        self._device_registry = device_registry
        self._topics = topics
        self._cache = cache
        self._echo_guard = echo_guard
        self._stopping = stopping
        self._lock = threading.Lock()
        self._pressed: dict[int, bool] = {}  # wpid → configured button currently held
        self._resolving: set[int] = set()  # wpids with a MouseReprogFeatureTask started by us
        topics.hid_event.subscribe(self)
        topics.flags.subscribe(self)
        topics.info_progress.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, HidppNotificationEvent):
            self._on_notification(event)
        elif isinstance(event, SetReportFlagEvent):
            self._on_flags(event)
        elif isinstance(event, InfoTaskProgressEvent):
            self._on_progress(event)
        elif isinstance(event, DeviceConnectedEvent):
            self._on_connection(event)
        elif isinstance(event, TransportDisconnectedEvent):
            self._clear_pressed(pid=event.pid)
        elif isinstance(event, HidppErrorEvent):
            self._on_error(event)

    # ── x1B04 resolution ────────────────────────────────────────────────────

    def _on_progress(self, event: InfoTaskProgressEvent) -> None:
        device = event.device
        if event.step_name == Task.Feature.Name.MOUSE_REPROG:
            with self._lock:
                self._resolving.discard(device.wpid)  # a failure is retried by the orchestrator
            if event.success:
                # The orchestrator caches a device only once, usually before this step was added.
                self._cache.save(device)
            return
        if event.success:
            self._resolve_if_needed(device)

    def _on_connection(self, event: DeviceConnectedEvent) -> None:
        if not event.link_established:
            self._clear_pressed(wpid=event.wpid)
            return
        # A device cached before this feature existed has no x1B04 and runs no discovery step on reconnect.
        device = self._device_registry.get_by_wpid(event.wpid) or self._cache.find_by_wpid(event.wpid)
        if device is not None:
            # The event itself says the link is up; the device's own flag may not be updated yet.
            self._resolve_if_needed(device, link_up=True)

    def _resolve_if_needed(self, device: LogiDevice, link_up: bool = False) -> None:
        if device.role != ROLE_MOUSE or not (link_up or device.connected):
            return
        if FEATURE_REPROG_CONTROLS_V4 in device.available_features:
            return
        with self._lock:
            if device.wpid in self._resolving:
                return
            self._resolving.add(device.wpid)
            device.pending_steps.add(Task.Feature.Name.MOUSE_REPROG)
        log.debug(f"wpid=0x{device.wpid:04X}: resolving 0x{FEATURE_REPROG_CONTROLS_V4:04X} for mouse button switch")
        MouseReprogFeatureTask(device, self._topics).start()

    # ── Arming ──────────────────────────────────────────────────────────────

    def _on_flags(self, event: SetReportFlagEvent) -> None:
        device = self._device_registry.get_by_wpid(event.wpid)
        if device is None or device.role != ROLE_MOUSE:
            return
        reprog_idx = device.available_features.get(FEATURE_REPROG_CONTROLS_V4)
        if reprog_idx is None:
            return
        if not event.enable:
            self._clear_pressed(wpid=device.wpid)
        if not self._config.divert:
            return
        # Temporary divert only: the mouse forgets it on reset, so a crash never leaves the button dead for good.
        bfield = MAP_FLAG_DIVERTED << 1 | (MAP_FLAG_DIVERTED if event.enable else 0)
        params = struct.pack("!HBH", self._config.cid, bfield, 0)
        request_id = (reprog_idx << 8) | (_SET_CID_REPORTING << 4) | SW_ID_DIVERT
        msg = build_msg(event.slot, request_id, params)
        self._topics.write.publish(WriteEvent(slot=event.slot, pid=event.pid, hid_message=msg))
        action = "Diverting" if event.enable else "Un-diverting"
        log.info(f"{action} button CID 0x{self._config.cid:04X} on '{device.display_name}' for host switching")

    def _on_error(self, event: HidppErrorEvent) -> None:
        if event.sw_id != SW_ID_DIVERT or event.function != _SET_CID_REPORTING:
            return
        device = self._find_device(event.slot, event.pid)
        if device is None or device.role != ROLE_MOUSE:
            return
        if device.available_features.get(FEATURE_REPROG_CONTROLS_V4) != event.feature_index:
            return
        log.warning(
            f"'{device.display_name}' refused to divert button CID 0x{self._config.cid:04X} "
            f"(error 0x{event.error_code:02X}); pick another 'button' in mouse_button_switch"
        )

    # ── Press handling ──────────────────────────────────────────────────────

    def _on_notification(self, event: HidppNotificationEvent) -> None:
        if event.function != _DIVERTED_BUTTONS:
            return
        device = self._find_device(event.slot, event.pid)
        if device is None or device.role != ROLE_MOUSE:
            return
        if device.available_features.get(FEATURE_REPROG_CONTROLS_V4) != event.feature_index:
            return

        pressed_cids = {
            (event.payload[i] << 8) | event.payload[i + 1]
            for i in range(0, min(len(event.payload), 2 * _MAX_PRESSED_CIDS) - 1, 2)
        }
        held = self._config.cid in pressed_cids
        with self._lock:
            was_held = self._pressed.get(device.wpid, False)
            self._pressed[device.wpid] = held
        if not held or was_held or self._stopping():
            return

        target = self._config.target_host
        log.info(f"Button CID 0x{self._config.cid:04X} pressed on '{device.display_name}' → host {target + 1}")
        self._echo_guard.record(target)
        self._topics.hid_event.publish(
            HostChangeEvent(slot=device.slot, pid=device.pid, target_host=target, source=SwitchSource.BUTTON)
        )

    def _clear_pressed(self, wpid: int | None = None, pid: int | None = None) -> None:
        with self._lock:
            if wpid is not None:
                self._pressed.pop(wpid, None)
            if pid is not None:
                for device in self._device_registry.all_entries():
                    if device.pid == pid:
                        self._pressed.pop(device.wpid, None)

    def _find_device(self, slot: int, pid: int) -> LogiDevice | None:
        for entry in self._device_registry.all_entries():
            if entry.pid == pid and entry.slot == slot:
                return entry
        return None
