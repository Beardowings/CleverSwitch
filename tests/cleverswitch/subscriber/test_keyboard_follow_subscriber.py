"""Tests for KeyboardFollowSubscriber — the mouse follows a keyboard that leaves by its own Easy-Switch key."""

from unittest.mock import MagicMock

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.host_change_event import HostChangeEvent, SwitchSource
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST
from cleverswitch.model.config.mouse_button_switch_config import MouseButtonSwitchConfig
from cleverswitch.model.logi_device import ROLE_KEYBOARD, ROLE_MOUSE, LogiDevice
from cleverswitch.model.switch_echo_guard import SwitchEchoGuard
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.keyboard_follow_subscriber import (
    FOLLOW_DELAY_S,
    OWN_SWITCH_WINDOW_S,
    KeyboardFollowSubscriber,
)
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

KEYBOARD_WPID = 0xB380
MOUSE_WPID = 0xB034
TARGET = 1


class FakeTimer:
    def __init__(self, delay, fn, args=()):
        self.delay = delay
        self.fn = fn
        self.args = args
        self.daemon = False
        self.started = False
        self.cancelled = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.fn(*self.args)


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def _device(wpid, slot, role, *, connected=True, features=None) -> LogiDevice:
    device = LogiDevice(
        wpid=wpid,
        pid=BOLT_PID,
        slot=slot,
        role=role,
        available_features={FEATURE_CHANGE_HOST: 10} if features is None else features,
        friendly_name="MX Keys" if role == ROLE_KEYBOARD else "MX Master 3S",
    )
    device.pending_steps = set()
    device.connected = connected
    return device


def _setup(*, follow=True, target=TARGET, mouse=True, stopping=False):
    registry = LogiDeviceRegistry()
    keyboard = _device(KEYBOARD_WPID, 1, ROLE_KEYBOARD)
    registry.register(KEYBOARD_WPID, keyboard)
    mouse_device = None
    if mouse:
        mouse_device = _device(MOUSE_WPID, 2, ROLE_MOUSE)
        registry.register(MOUSE_WPID, mouse_device)
    topics = Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )
    config = {"value": MouseButtonSwitchConfig(enabled=True, target_host=target, follow_keyboard=follow)}
    timers: list[FakeTimer] = []

    def timer_factory(delay, fn, args=()):
        timer = FakeTimer(delay, fn, args)
        timers.append(timer)
        return timer

    clock = Clock()
    guard = SwitchEchoGuard()
    subscriber = KeyboardFollowSubscriber(
        registry,
        topics,
        lambda: config["value"],
        guard,
        stopping=lambda: stopping,
        clock=clock,
        timer_factory=timer_factory,
    )
    return subscriber, topics, keyboard, mouse_device, timers, clock, config, guard


def _leave(subscriber, keyboard):
    keyboard.connected = False
    subscriber.notify(
        DeviceConnectedEvent(slot=keyboard.slot, pid=BOLT_PID, link_established=False, wpid=keyboard.wpid)
    )


def test_subscribes_to_hid_event():
    subscriber, topics, *_ = _setup()
    topics.hid_event.subscribe.assert_called_once_with(subscriber)


def test_keyboard_leaving_sends_the_mouse_to_the_target_host():
    subscriber, topics, keyboard, mouse, timers, *_ = _setup()

    _leave(subscriber, keyboard)
    assert len(timers) == 1 and timers[0].started and timers[0].daemon
    assert timers[0].delay == FOLLOW_DELAY_S
    topics.hid_event.publish.assert_not_called()

    timers[0].fire()

    event = topics.hid_event.publish.call_args.args[0]
    assert event == HostChangeEvent(slot=mouse.slot, pid=mouse.pid, target_host=TARGET, source=SwitchSource.FOLLOW)


def test_follow_records_the_target_in_the_echo_guard():
    subscriber, _, keyboard, _, timers, _, _, guard = _setup()
    guard.record = MagicMock()

    _leave(subscriber, keyboard)
    timers[0].fire()

    guard.record.assert_called_once_with(TARGET)


def test_keyboard_back_within_the_delay_cancels_the_follow():
    subscriber, topics, keyboard, _, timers, *_ = _setup()

    _leave(subscriber, keyboard)
    keyboard.connected = True
    subscriber.notify(DeviceConnectedEvent(slot=1, pid=BOLT_PID, link_established=True, wpid=KEYBOARD_WPID))

    assert timers[0].cancelled
    assert len(timers) == 1


def test_keyboard_reconnected_when_the_timer_fires_sends_nothing():
    subscriber, topics, keyboard, _, timers, *_ = _setup()

    _leave(subscriber, keyboard)
    keyboard.connected = True
    timers[0].fire()

    topics.hid_event.publish.assert_not_called()


def test_no_follow_when_the_option_is_off():
    subscriber, topics, keyboard, _, timers, *_ = _setup(follow=False)

    _leave(subscriber, keyboard)

    assert timers == []


def test_no_follow_without_a_target_host():
    subscriber, _, keyboard, _, timers, *_ = _setup(target=None)

    _leave(subscriber, keyboard)

    assert timers == []


def test_no_follow_while_stopping():
    subscriber, _, keyboard, _, timers, *_ = _setup(stopping=True)

    _leave(subscriber, keyboard)

    assert timers == []


def test_option_switched_off_during_the_delay_sends_nothing():
    subscriber, topics, keyboard, _, timers, _, config, _ = _setup()

    _leave(subscriber, keyboard)
    config["value"] = MouseButtonSwitchConfig(enabled=True, target_host=TARGET, follow_keyboard=False)
    timers[0].fire()

    topics.hid_event.publish.assert_not_called()


def test_keyboard_leaving_because_of_our_own_switch_is_not_followed():
    subscriber, _, keyboard, _, timers, clock, *_ = _setup()

    subscriber.notify(HostChangeEvent(slot=2, pid=BOLT_PID, target_host=TARGET, source=SwitchSource.BUTTON))
    clock.now += OWN_SWITCH_WINDOW_S - 1
    _leave(subscriber, keyboard)

    assert timers == []


def test_old_switch_does_not_block_a_later_follow():
    subscriber, topics, keyboard, _, timers, clock, *_ = _setup()

    subscriber.notify(HostChangeEvent(slot=2, pid=BOLT_PID, target_host=TARGET, source=SwitchSource.BUTTON))
    clock.now += OWN_SWITCH_WINDOW_S + 1
    _leave(subscriber, keyboard)
    timers[0].fire()

    topics.hid_event.publish.assert_called_once()


def test_no_follow_when_the_mouse_is_gone_too():
    subscriber, topics, keyboard, mouse, timers, *_ = _setup()

    _leave(subscriber, keyboard)
    mouse.connected = False
    timers[0].fire()

    topics.hid_event.publish.assert_not_called()


def test_no_follow_without_a_mouse():
    subscriber, topics, keyboard, _, timers, *_ = _setup(mouse=False)

    _leave(subscriber, keyboard)
    timers[0].fire()

    topics.hid_event.publish.assert_not_called()


def test_mouse_without_change_host_is_not_sent():
    subscriber, topics, keyboard, mouse, timers, *_ = _setup()
    mouse.available_features = {}

    _leave(subscriber, keyboard)
    timers[0].fire()

    topics.hid_event.publish.assert_not_called()


def test_mouse_leaving_starts_nothing():
    subscriber, _, _, mouse, timers, *_ = _setup()

    mouse.connected = False
    subscriber.notify(DeviceConnectedEvent(slot=2, pid=BOLT_PID, link_established=False, wpid=MOUSE_WPID))

    assert timers == []


def test_unknown_device_is_ignored():
    subscriber, _, _, _, timers, *_ = _setup()

    subscriber.notify(DeviceConnectedEvent(slot=3, pid=BOLT_PID, link_established=False, wpid=0x1234))

    assert timers == []


def test_keyboard_removed_from_registry_before_the_timer_sends_nothing():
    subscriber, topics, keyboard, _, timers, *_ = _setup()
    registry_get = subscriber._device_registry.get_by_wpid

    _leave(subscriber, keyboard)
    subscriber._device_registry.get_by_wpid = lambda wpid: None if wpid == KEYBOARD_WPID else registry_get(wpid)
    timers[0].fire()

    topics.hid_event.publish.assert_not_called()


def test_other_events_are_ignored():
    subscriber, topics, _, _, timers, *_ = _setup()

    subscriber.notify(object())

    assert timers == []
    topics.hid_event.publish.assert_not_called()
