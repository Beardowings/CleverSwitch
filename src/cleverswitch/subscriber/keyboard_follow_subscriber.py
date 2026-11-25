import logging
import threading
import time
from collections.abc import Callable

from ..event.device_connected_event import DeviceConnectedEvent
from ..event.host_change_event import HostChangeEvent, SwitchSource
from ..hidpp.constants import FEATURE_CHANGE_HOST
from ..model.config.mouse_button_switch_config import MouseButtonSwitchConfig
from ..model.logi_device import ROLE_KEYBOARD, ROLE_MOUSE
from ..model.switch_echo_guard import SwitchEchoGuard
from ..registry.logi_device_registry import LogiDeviceRegistry
from ..subscriber.subscriber import Subscriber
from ..topic.topics import Topics

log = logging.getLogger(__name__)

FOLLOW_DELAY_S = 1.5  # a link that drops and returns within this is a glitch, not a switch
OWN_SWITCH_WINDOW_S = 5.0  # a keyboard leaving this soon after we sent a switch left because of it


class KeyboardFollowSubscriber(Subscriber):
    """Sends the mouse to ``target_host`` when the keyboard leaves this computer and the mouse stays.

    Some keyboards (MX Keys for Business, hardware-tested on Bolt and Bluetooth) accept analytics
    reporting for their Easy-Switch keys but never report the press: the keyboard switches and the
    departing computer only sees it disconnect. That disconnect carries no target host, so the mouse
    is sent to the configured one, which is exact with two computers.

    Guards against a false follow: the keyboard must stay away for FOLLOW_DELAY_S; a mouse must still be
    connected here (a sleeping computer or an unplugged receiver drops both); and no switch may have been
    sent in the last OWN_SWITCH_WINDOW_S (the keyboard then left because we told it to). A keyboard
    switched off by hand while the mouse stays is indistinguishable and does take the mouse along.
    """

    def __init__(
        self,
        device_registry: LogiDeviceRegistry,
        topics: Topics,
        settings: Callable[[], MouseButtonSwitchConfig],
        echo_guard: SwitchEchoGuard,
        stopping: Callable[[], bool] = lambda: False,
        clock: Callable[[], float] = time.monotonic,
        timer_factory=threading.Timer,
    ):
        self._device_registry = device_registry
        self._topics = topics
        self._settings = settings
        self._echo_guard = echo_guard
        self._stopping = stopping
        self._clock = clock
        self._timer_factory = timer_factory
        self._lock = threading.Lock()
        self._timers: dict[int, threading.Timer] = {}
        self._last_switch: float | None = None
        topics.hid_event.subscribe(self)

    def notify(self, event) -> None:
        if isinstance(event, HostChangeEvent):
            with self._lock:
                self._last_switch = self._clock()
        elif isinstance(event, DeviceConnectedEvent):
            self._on_connection(event)

    def _on_connection(self, event: DeviceConnectedEvent) -> None:
        device = self._device_registry.get_by_wpid(event.wpid)
        if device is None or device.role != ROLE_KEYBOARD:
            return
        with self._lock:
            pending = self._timers.pop(event.wpid, None)
        if pending is not None:
            pending.cancel()
        if event.link_established or not self._wanted():
            return
        timer = self._timer_factory(FOLLOW_DELAY_S, self._follow, args=(event.wpid,))
        timer.daemon = True
        with self._lock:
            self._timers[event.wpid] = timer
        timer.start()

    def _wanted(self) -> bool:
        config = self._settings()
        if not config.follow_keyboard or config.target_host is None or self._stopping():
            return False
        with self._lock:
            last = self._last_switch
        return last is None or self._clock() - last > OWN_SWITCH_WINDOW_S

    def _follow(self, wpid: int) -> None:
        with self._lock:
            self._timers.pop(wpid, None)
        keyboard = self._device_registry.get_by_wpid(wpid)
        if keyboard is None or keyboard.connected or not self._wanted():
            return
        mice = [
            d
            for d in self._device_registry.all_entries()
            if d.role == ROLE_MOUSE and d.connected and FEATURE_CHANGE_HOST in d.available_features
        ]
        if not mice:
            return
        target = self._settings().target_host
        log.info(f"'{keyboard.display_name}' left this computer; sending the mouse after it → host {target + 1}")
        self._echo_guard.record(target)
        mouse = mice[0]
        self._topics.hid_event.publish(
            HostChangeEvent(slot=mouse.slot, pid=mouse.pid, target_host=target, source=SwitchSource.FOLLOW)
        )
