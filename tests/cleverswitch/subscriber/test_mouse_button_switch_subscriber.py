"""Tests for MouseButtonSwitchSubscriber — a mouse button press switches every device to one host."""

from unittest.mock import MagicMock, patch

import pytest

from cleverswitch.event.device_connected_event import DeviceConnectedEvent
from cleverswitch.event.hidpp_error_event import HidppErrorEvent
from cleverswitch.event.hidpp_notification_event import HidppNotificationEvent
from cleverswitch.event.host_change_event import HostChangeEvent, SwitchSource
from cleverswitch.event.info_task_progress_event import InfoTaskProgressEvent
from cleverswitch.event.mouse_button_switch_changed_event import MouseButtonSwitchChangedEvent
from cleverswitch.event.set_report_flag_event import SetReportFlagEvent
from cleverswitch.event.transport_disconnected_event import TransportDisconnectedEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_CHANGE_HOST, FEATURE_REPROG_CONTROLS_V4, SW_ID_DIVERT
from cleverswitch.model.config.mouse_button_switch_config import MouseButtonSwitchConfig
from cleverswitch.model.logi_device import ROLE_KEYBOARD, ROLE_MOUSE, LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.mouse_button_switch_subscriber import MouseButtonSwitchSubscriber
from cleverswitch.subscriber.task.constants import Task
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

SLOT = 2
PID = BOLT_PID
WPID = 0xB034
REPROG_IDX = 11
CID = 0x00C3
TARGET = 1  # 0-based → host 2


def _topics() -> Topics:
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _mouse(*, reprog_idx: int | None = REPROG_IDX, role: str | None = ROLE_MOUSE, connected=True) -> LogiDevice:
    features = {FEATURE_CHANGE_HOST: 10}
    if reprog_idx is not None:
        features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
    device = LogiDevice(
        wpid=WPID, pid=PID, slot=SLOT, role=role, available_features=features, friendly_name="MX Master 3S"
    )
    device.pending_steps = set()
    device.connected = connected
    return device


def _setup(
    device: LogiDevice | None = None,
    *,
    divert=True,
    cached: LogiDevice | None = None,
    stopping=False,
    enabled=True,
    target=TARGET,
):
    registry = LogiDeviceRegistry()
    if device is not None:
        registry.register(device.wpid, device)
    topics = _topics()
    cache = MagicMock()
    cache.find_by_wpid.return_value = cached
    guard = MagicMock()
    config = MouseButtonSwitchConfig(enabled=enabled, cid=CID, target_host=target, divert=divert)
    sub = MouseButtonSwitchSubscriber(config, registry, topics, cache, guard, lambda: stopping)
    return sub, topics, cache, guard


def _press(cids: list[int], *, feature_index=REPROG_IDX, function=0, slot=SLOT) -> HidppNotificationEvent:
    payload = b"".join(c.to_bytes(2, "big") for c in cids).ljust(16, b"\0")
    return HidppNotificationEvent(slot=slot, pid=PID, feature_index=feature_index, function=function, payload=payload)


def _published_host_changes(topics: Topics) -> list[HostChangeEvent]:
    return [c.args[0] for c in topics.hid_event.publish.call_args_list if isinstance(c.args[0], HostChangeEvent)]


# ── Subscriptions ────────────────────────────────────────────────────────────


def test_subscribes_to_hid_event_flags_and_info_progress():
    sub, topics, _, _ = _setup()
    topics.hid_event.subscribe.assert_called_once_with(sub)
    topics.flags.subscribe.assert_called_once_with(sub)
    topics.info_progress.subscribe.assert_called_once_with(sub)


# ── Press handling ───────────────────────────────────────────────────────────


def test_press_publishes_host_change_for_every_device():
    sub, topics, _, guard = _setup(_mouse())
    sub.notify(_press([CID]))
    events = _published_host_changes(topics)
    assert events == [HostChangeEvent(slot=SLOT, pid=PID, target_host=TARGET, source=SwitchSource.BUTTON)]
    guard.record.assert_called_once_with(TARGET)


def test_press_among_other_held_buttons_still_switches():
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(_press([0x0053, 0x0056, CID]))
    assert len(_published_host_changes(topics)) == 1


def test_holding_the_button_switches_once():
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(_press([CID]))
    sub.notify(_press([CID, 0x0053]))  # another button joins while held
    assert len(_published_host_changes(topics)) == 1


def test_release_and_press_again_switches_again():
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(_press([CID]))
    sub.notify(_press([]))
    sub.notify(_press([CID]))
    assert len(_published_host_changes(topics)) == 2


def test_disconnect_clears_held_state():
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(_press([CID]))
    sub.notify(DeviceConnectedEvent(slot=SLOT, pid=PID, link_established=False, wpid=WPID))
    sub.notify(_press([CID]))
    assert len(_published_host_changes(topics)) == 2


def test_transport_disconnect_clears_held_state():
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(_press([CID]))
    sub.notify(TransportDisconnectedEvent(slot=0xFF, pid=PID))
    sub.notify(_press([CID]))
    assert len(_published_host_changes(topics)) == 2


@pytest.mark.parametrize(
    "event",
    [
        _press([0x0053]),  # another button
        _press([CID], function=1),  # rawXY, not a button event
        _press([CID], feature_index=REPROG_IDX + 1),  # another feature's notification
        _press([CID], slot=SLOT + 1),  # unknown device
    ],
)
def test_ignores_unrelated_notifications(event):
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(event)
    assert _published_host_changes(topics) == []


def test_ignores_keyboard_notification():
    sub, topics, _, _ = _setup(_mouse(role=ROLE_KEYBOARD))
    sub.notify(_press([CID]))
    assert _published_host_changes(topics) == []


def test_no_switch_while_stopping():
    sub, topics, _, guard = _setup(_mouse(), stopping=True)
    sub.notify(_press([CID]))
    assert _published_host_changes(topics) == []
    guard.record.assert_not_called()


def test_short_payload_is_tolerated():
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(HidppNotificationEvent(slot=SLOT, pid=PID, feature_index=REPROG_IDX, function=0, payload=b"\x00"))
    assert _published_host_changes(topics) == []


# ── Arming ───────────────────────────────────────────────────────────────────


def _written(topics: Topics) -> list[bytes]:
    return [c.args[0].hid_message for c in topics.write.publish.call_args_list if isinstance(c.args[0], WriteEvent)]


def test_flags_event_diverts_button():
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(SetReportFlagEvent(slot=SLOT, pid=PID, wpid=WPID))
    (msg,) = _written(topics)
    assert msg[:9] == bytes([0x11, SLOT, REPROG_IDX, 0x30 | SW_ID_DIVERT, 0x00, 0xC3, 0x03, 0x00, 0x00])
    assert len(msg) == 20


def test_disable_flags_event_undiverts_button():
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(SetReportFlagEvent(slot=SLOT, pid=PID, wpid=WPID, enable=False))
    (msg,) = _written(topics)
    assert msg[4:7] == bytes([0x00, 0xC3, 0x02])


def test_disable_flags_event_clears_held_state():
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(_press([CID]))
    sub.notify(SetReportFlagEvent(slot=SLOT, pid=PID, wpid=WPID, enable=False))
    sub.notify(_press([CID]))
    assert len(_published_host_changes(topics)) == 2


def test_listen_only_never_writes():
    sub, topics, _, _ = _setup(_mouse(), divert=False)
    sub.notify(SetReportFlagEvent(slot=SLOT, pid=PID, wpid=WPID))
    topics.write.publish.assert_not_called()
    sub.notify(_press([CID]))
    assert len(_published_host_changes(topics)) == 1


@pytest.mark.parametrize(
    "device",
    [_mouse(role=ROLE_KEYBOARD), _mouse(reprog_idx=None), None],
    ids=["keyboard", "no-reprog", "unknown"],
)
def test_flags_event_ignored_for_non_armable_devices(device):
    sub, topics, _, _ = _setup(device)
    sub.notify(SetReportFlagEvent(slot=SLOT, pid=PID, wpid=WPID))
    topics.write.publish.assert_not_called()


def test_divert_error_is_logged(caplog):
    sub, _, _, _ = _setup(_mouse())
    sub.notify(
        HidppErrorEvent(slot=SLOT, pid=PID, feature_index=REPROG_IDX, function=3, sw_id=SW_ID_DIVERT, error_code=2)
    )
    assert "refused to divert" in caplog.text


@pytest.mark.parametrize(
    "event",
    [
        HidppErrorEvent(slot=SLOT, pid=PID, feature_index=REPROG_IDX, function=1, sw_id=SW_ID_DIVERT, error_code=2),
        HidppErrorEvent(slot=SLOT, pid=PID, feature_index=REPROG_IDX, function=3, sw_id=0x09, error_code=2),
        HidppErrorEvent(slot=SLOT, pid=PID, feature_index=REPROG_IDX + 1, function=3, sw_id=SW_ID_DIVERT, error_code=2),
        HidppErrorEvent(slot=SLOT + 1, pid=PID, feature_index=REPROG_IDX, function=3, sw_id=SW_ID_DIVERT, error_code=2),
    ],
)
def test_unrelated_errors_are_not_logged(event, caplog):
    sub, _, _, _ = _setup(_mouse())
    sub.notify(event)
    assert "refused to divert" not in caplog.text


# ── x1B04 resolution on mice ─────────────────────────────────────────────────

_TASK = "cleverswitch.subscriber.mouse_button_switch_subscriber.MouseReprogFeatureTask"


def _progress(device: LogiDevice, step: str = Task.Name.GET_DEVICE_TYPE, success=True) -> InfoTaskProgressEvent:
    return InfoTaskProgressEvent(slot=SLOT, pid=PID, step_name=step, success=success, device=device)


def test_progress_on_mouse_without_reprog_starts_resolution():
    device = _mouse(reprog_idx=None)
    sub, topics, _, _ = _setup(device)
    with patch(_TASK) as task_cls:
        sub.notify(_progress(device))
    task_cls.assert_called_once_with(device, topics)
    task_cls.return_value.start.assert_called_once()
    assert Task.Feature.Name.MOUSE_REPROG in device.pending_steps


def test_resolution_starts_only_once_while_running():
    device = _mouse(reprog_idx=None)
    sub, _, _, _ = _setup(device)
    with patch(_TASK) as task_cls:
        sub.notify(_progress(device))
        sub.notify(_progress(device, Task.Name.GET_DEVICE_NAME))
    task_cls.assert_called_once()


def test_resolution_can_restart_after_its_task_finished():
    device = _mouse(reprog_idx=None)
    sub, _, _, _ = _setup(device)
    with patch(_TASK) as task_cls:
        sub.notify(_progress(device))
        sub.notify(_progress(device, Task.Feature.Name.MOUSE_REPROG, success=False))
        sub.notify(DeviceConnectedEvent(slot=SLOT, pid=PID, link_established=True, wpid=WPID))
    assert task_cls.call_count == 2


@pytest.mark.parametrize(
    "device",
    [_mouse(), _mouse(reprog_idx=None, role=ROLE_KEYBOARD), _mouse(reprog_idx=None, connected=False)],
    ids=["already-resolved", "keyboard", "disconnected"],
)
def test_progress_does_not_start_resolution(device):
    sub, _, _, _ = _setup(device)
    with patch(_TASK) as task_cls:
        sub.notify(_progress(device))
    task_cls.assert_not_called()


def test_failed_progress_does_not_start_resolution():
    device = _mouse(reprog_idx=None)
    sub, _, _, _ = _setup(device)
    with patch(_TASK) as task_cls:
        sub.notify(_progress(device, success=False))
    task_cls.assert_not_called()


def test_resolution_success_saves_cache():
    device = _mouse()
    sub, _, cache, _ = _setup(device)
    sub.notify(_progress(device, Task.Feature.Name.MOUSE_REPROG))
    cache.save.assert_called_once_with(device)


def test_resolution_failure_does_not_save_cache():
    device = _mouse(reprog_idx=None)
    sub, _, cache, _ = _setup(device)
    sub.notify(_progress(device, Task.Feature.Name.MOUSE_REPROG, success=False))
    cache.save.assert_not_called()


def test_connect_of_cached_mouse_without_reprog_starts_resolution():
    cached = _mouse(reprog_idx=None, connected=False)  # cache-hit: not registered yet, stale connected flag
    sub, topics, _, _ = _setup(cached=cached)
    with patch(_TASK) as task_cls:
        sub.notify(DeviceConnectedEvent(slot=SLOT, pid=PID, link_established=True, wpid=WPID))
    task_cls.assert_called_once_with(cached, topics)


def test_connect_of_unknown_device_does_nothing():
    sub, _, _, _ = _setup()
    with patch(_TASK) as task_cls:
        sub.notify(DeviceConnectedEvent(slot=SLOT, pid=PID, link_established=True, wpid=WPID))
    task_cls.assert_not_called()


def test_logs_its_settings_at_startup(caplog):
    import logging

    with caplog.at_level(logging.INFO):
        _setup()
    assert "Mouse button switch on: button CID 0x00C3 → host 2 (divert)" in caplog.text


def test_logs_when_off_and_when_no_host_is_chosen(caplog):
    import logging

    with caplog.at_level(logging.INFO):
        _setup(enabled=False)
        _setup(target=None)
    assert "Mouse button switch off" in caplog.text
    assert "→ no host chosen yet (divert)" in caplog.text


# ── Runtime changes (tray menu) ─────────────────────────────────────────────

_ON = MouseButtonSwitchConfig(enabled=True, cid=CID, target_host=TARGET, divert=True)


def _change(sub, old: MouseButtonSwitchConfig, new: MouseButtonSwitchConfig) -> None:
    sub.notify(MouseButtonSwitchChangedEvent(slot=0, pid=0, old=old, new=new))


def test_press_while_disabled_does_nothing():
    sub, topics, _, _ = _setup(_mouse(), enabled=False)
    sub.notify(_press([CID]))
    assert _published_host_changes(topics) == []


def test_press_without_target_host_warns_and_does_nothing(caplog):
    sub, topics, _, guard = _setup(_mouse(), target=None)
    sub.notify(_press([CID]))
    assert _published_host_changes(topics) == []
    guard.record.assert_not_called()
    assert "no target host is set" in caplog.text


def test_flags_event_while_disabled_writes_nothing():
    sub, topics, _, _ = _setup(_mouse(), enabled=False)
    sub.notify(SetReportFlagEvent(slot=SLOT, pid=PID, wpid=WPID))
    assert _written(topics) == []


def test_switching_off_undiverts_the_button():
    sub, topics, _, _ = _setup(_mouse())
    _change(sub, _ON, MouseButtonSwitchConfig(enabled=False, cid=CID, target_host=TARGET))
    (msg,) = _written(topics)
    assert msg[4:7] == bytes([0x00, 0xC3, 0x02])


def test_switching_on_diverts_the_button():
    sub, topics, _, _ = _setup(_mouse(), enabled=False)
    _change(sub, MouseButtonSwitchConfig(enabled=False, cid=CID, target_host=TARGET), _ON)
    (msg,) = _written(topics)
    assert msg[4:7] == bytes([0x00, 0xC3, 0x03])
    sub.notify(_press([CID]))
    assert len(_published_host_changes(topics)) == 1


def test_changing_the_button_moves_the_divert():
    sub, topics, _, _ = _setup(_mouse())
    _change(sub, _ON, MouseButtonSwitchConfig(enabled=True, cid=0x0056, target_host=TARGET))
    released, armed = _written(topics)
    assert released[4:7] == bytes([0x00, 0xC3, 0x02])
    assert armed[4:7] == bytes([0x00, 0x56, 0x03])
    sub.notify(_press([CID]))
    assert _published_host_changes(topics) == []
    sub.notify(_press([0x0056]))
    assert len(_published_host_changes(topics)) == 1


def test_changing_only_the_host_writes_nothing_and_uses_the_new_host():
    sub, topics, _, _ = _setup(_mouse())
    _change(sub, _ON, MouseButtonSwitchConfig(enabled=True, cid=CID, target_host=2))
    assert _written(topics) == []
    sub.notify(_press([CID]))
    (event,) = _published_host_changes(topics)
    assert event.target_host == 2


def test_turning_divert_off_releases_the_button():
    sub, topics, _, _ = _setup(_mouse())
    _change(sub, _ON, MouseButtonSwitchConfig(enabled=True, cid=CID, target_host=TARGET, divert=False))
    (msg,) = _written(topics)
    assert msg[4:7] == bytes([0x00, 0xC3, 0x02])


@pytest.mark.parametrize("device", [_mouse(connected=False), _mouse(role=ROLE_KEYBOARD)])
def test_change_skips_disconnected_mice_and_keyboards(device):
    sub, topics, _, _ = _setup(device)
    _change(sub, _ON, MouseButtonSwitchConfig(enabled=False, cid=CID, target_host=TARGET))
    assert _written(topics) == []


def test_switching_on_resolves_a_mouse_without_reprog():
    device = _mouse(reprog_idx=None)
    sub, topics, _, _ = _setup(device, enabled=False)
    with patch(_TASK) as task_cls:
        _change(sub, MouseButtonSwitchConfig(enabled=False, cid=CID, target_host=TARGET), _ON)
    task_cls.assert_called_once_with(device, topics)
    assert _written(topics) == []


def test_disabled_does_not_resolve():
    device = _mouse(reprog_idx=None)
    sub, _, _, _ = _setup(device, enabled=False)
    with patch(_TASK) as task_cls:
        sub.notify(_progress(device))
    task_cls.assert_not_called()


def test_change_while_stopping_writes_nothing():
    sub, topics, _, _ = _setup(_mouse(), stopping=True)
    _change(sub, _ON, MouseButtonSwitchConfig(enabled=False, cid=CID, target_host=TARGET))
    assert _written(topics) == []


def test_change_clears_held_state():
    sub, topics, _, _ = _setup(_mouse())
    sub.notify(_press([CID]))
    _change(sub, _ON, MouseButtonSwitchConfig(enabled=True, cid=CID, target_host=2))
    sub.notify(_press([CID]))
    assert len(_published_host_changes(topics)) == 2
