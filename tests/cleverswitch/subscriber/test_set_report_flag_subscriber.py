"""Unit tests for subscriber/set_report_flag_subscriber.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from cleverswitch.event.set_report_flag_event import SetReportFlagEvent
from cleverswitch.event.write_event import WriteEvent
from cleverswitch.hidpp.constants import (
    BOLT_PID,
    FEATURE_CHANGE_HOST,
    FEATURE_REPROG_CONTROLS_V4,
    HOST_SWITCH_CIDS,
    KEY_FLAG_ANALYTICS,
    KEY_FLAG_DIVERTABLE,
    KEY_FLAG_PERSISTENTLY_DIVERTABLE,
)
from cleverswitch.model.logi_device import ROLE_KEYBOARD, LogiDevice
from cleverswitch.registry.logi_device_registry import LogiDeviceRegistry
from cleverswitch.subscriber.set_report_flag_subscriber import SetReportFlagSubscriber
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics

PID = BOLT_PID
WPID = 0x407B
REPROG_IDX = 8


def _make_topics():
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _make_device(reprog_idx=REPROG_IDX, supported_flags=None):
    features = {FEATURE_CHANGE_HOST: 9}
    if reprog_idx is not None:
        features[FEATURE_REPROG_CONTROLS_V4] = reprog_idx
    device = LogiDevice(
        wpid=WPID,
        pid=PID,
        slot=1,
        role=ROLE_KEYBOARD,
        available_features=features,
    )
    if supported_flags is not None:
        device.supported_flags = set(supported_flags)
    return device


def test_analytics_flag_sends_analytics_params_for_all_es_cids():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags={KEY_FLAG_ANALYTICS})
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID)
    sub.notify(event)

    # One write per HOST_SWITCH_CID (3 total)
    assert topics.write.publish.call_count == len(HOST_SWITCH_CIDS)
    for call in topics.write.publish.call_args_list:
        assert isinstance(call[0][0], WriteEvent)


def test_divertable_flag_sends_divert_bfield():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags={KEY_FLAG_DIVERTABLE})
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID)
    sub.notify(event)

    assert topics.write.publish.call_count == len(HOST_SWITCH_CIDS)
    for call in topics.write.publish.call_args_list:
        assert isinstance(call[0][0], WriteEvent)


def test_divertable_and_persistently_divertable_includes_persist_flags():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags={KEY_FLAG_DIVERTABLE, KEY_FLAG_PERSISTENTLY_DIVERTABLE})
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID)
    sub.notify(event)

    assert topics.write.publish.call_count == len(HOST_SWITCH_CIDS)


def test_enable_false_sends_clear_divert_bfield():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags={KEY_FLAG_DIVERTABLE})
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID, enable=False)
    sub.notify(event)

    assert topics.write.publish.call_count == len(HOST_SWITCH_CIDS)


def test_unknown_device_no_write():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=0x9999)
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_no_reprog_controls_v4_feature_no_write():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(reprog_idx=None, supported_flags={KEY_FLAG_DIVERTABLE})
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID)
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_empty_supported_flags_no_write():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags=set())
    registry.register(WPID, device)

    event = SetReportFlagEvent(slot=1, pid=PID, wpid=WPID)
    sub.notify(event)

    topics.write.publish.assert_not_called()


def test_non_set_report_flag_event_is_noop():
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)
    sub.notify("not an event")  # must not raise

    topics.write.publish.assert_not_called()


def test_mouse_without_es_flags_is_skipped_silently(caplog):
    from cleverswitch.model.logi_device import ROLE_MOUSE

    registry = LogiDeviceRegistry()
    topics = _make_topics()
    sub = SetReportFlagSubscriber(registry, topics)

    device = _make_device(supported_flags=set())
    device.role = ROLE_MOUSE
    registry.register(WPID, device)

    sub.notify(SetReportFlagEvent(slot=1, pid=PID, wpid=WPID))

    topics.write.publish.assert_not_called()
    assert "has no reprog flags" not in caplog.text


# ── Forced divert (easy_switch.divert / tray) ────────────────────────────────

from cleverswitch.event.easy_switch_mode_changed_event import EasySwitchModeChangedEvent  # noqa: E402
from cleverswitch.model.logi_device import ROLE_MOUSE  # noqa: E402

_BOTH = {KEY_FLAG_ANALYTICS, KEY_FLAG_DIVERTABLE, KEY_FLAG_PERSISTENTLY_DIVERTABLE}


def _forced(flags=_BOTH, prefer=True):
    registry = LogiDeviceRegistry()
    topics = _make_topics()
    device = _make_device(supported_flags=flags)
    registry.register(WPID, device)
    sub = SetReportFlagSubscriber(registry, topics, lambda: prefer)
    return sub, topics, device


def _params(topics):
    return [c.args[0].hid_message[4:10] for c in topics.write.publish.call_args_list]


def test_forced_divert_uses_temporary_divert_even_with_analytics():
    sub, topics, _ = _forced()
    sub.notify(SetReportFlagEvent(slot=1, pid=PID, wpid=WPID))
    params = _params(topics)
    assert len(params) == 3
    assert all(p[2] == 0x03 for p in params)  # temporary divert only, never persistent


def test_forced_divert_undiverts_on_disable():
    sub, topics, _ = _forced()
    sub.notify(SetReportFlagEvent(slot=1, pid=PID, wpid=WPID, enable=False))
    assert all(p[2] == 0x02 for p in _params(topics))


def test_forced_divert_needs_a_divertable_key():
    sub, topics, _ = _forced(flags={KEY_FLAG_ANALYTICS})
    sub.notify(SetReportFlagEvent(slot=1, pid=PID, wpid=WPID))
    assert all(p[5] == 0x03 and p[2] == 0x00 for p in _params(topics))  # analytics as before


def test_mode_change_to_divert_moves_connected_keyboards():
    sub, topics, _ = _forced()
    sub.notify(EasySwitchModeChangedEvent(slot=0, pid=0, divert=True))
    params = _params(topics)
    assert len(params) == 6
    assert [p[5] for p in params[0::2]] == [0x02] * 3  # analytics off
    assert [p[2] for p in params[1::2]] == [0x03] * 3  # divert on


def test_mode_change_back_to_analytics():
    sub, topics, _ = _forced(prefer=False)
    sub.notify(EasySwitchModeChangedEvent(slot=0, pid=0, divert=False))
    params = _params(topics)
    assert [p[2] for p in params[0::2]] == [0x02] * 3  # divert off
    assert [p[5] for p in params[1::2]] == [0x03] * 3  # analytics on


def test_mode_change_skips_keyboards_that_cannot_divert(caplog):
    sub, topics, _ = _forced(flags={KEY_FLAG_ANALYTICS})
    sub.notify(EasySwitchModeChangedEvent(slot=0, pid=0, divert=True))
    topics.write.publish.assert_not_called()
    assert "cannot divert its Easy-Switch keys" in caplog.text
    sub.notify(EasySwitchModeChangedEvent(slot=0, pid=0, divert=False))
    topics.write.publish.assert_not_called()


def test_mode_change_skips_mice_disconnected_and_unresolved_devices():
    for change in (
        lambda d: setattr(d, "connected", False),
        lambda d: setattr(d, "role", ROLE_MOUSE),
        lambda d: d.available_features.pop(FEATURE_REPROG_CONTROLS_V4),
    ):
        sub, topics, device = _forced()
        change(device)
        sub.notify(EasySwitchModeChangedEvent(slot=0, pid=0, divert=True))
        topics.write.publish.assert_not_called()
