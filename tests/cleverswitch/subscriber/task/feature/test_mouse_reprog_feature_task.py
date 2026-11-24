"""Tests for MouseReprogFeatureTask — resolves x1B04 on a mouse for mouse_button_switch."""

from unittest.mock import MagicMock

from cleverswitch.event.hidpp_response_event import HidppResponseEvent
from cleverswitch.event.set_report_flag_event import SetReportFlagEvent
from cleverswitch.hidpp.constants import BOLT_PID, FEATURE_REPROG_CONTROLS_V4
from cleverswitch.model.logi_device import ROLE_MOUSE, LogiDevice
from cleverswitch.subscriber.task.constants import FEATURE_REPROG_CONTROLS_V4_SW_ID, Task
from cleverswitch.subscriber.task.feature.mouse_reprog_feature_task import MouseReprogFeatureTask
from cleverswitch.topic.topic import Topic
from cleverswitch.topic.topics import Topics
from tests.task_helpers import deliver_on_request

SLOT = 2
WPID = 0xB034


def _topics() -> Topics:
    return Topics(
        hid_event=MagicMock(spec=Topic),
        write=MagicMock(spec=Topic),
        device_info=MagicMock(spec=Topic),
        flags=MagicMock(spec=Topic),
        info_progress=MagicMock(spec=Topic),
    )


def _mouse() -> LogiDevice:
    device = LogiDevice(wpid=WPID, pid=BOLT_PID, slot=SLOT, role=ROLE_MOUSE, available_features={})
    device.pending_steps = {Task.Feature.Name.MOUSE_REPROG}
    return device


def _reply(feature_index: int) -> HidppResponseEvent:
    return HidppResponseEvent(
        slot=SLOT,
        pid=BOLT_PID,
        feature_index=0,
        function=0,
        sw_id=FEATURE_REPROG_CONTROLS_V4_SW_ID,
        payload=bytes([feature_index]) + b"\0" * 15,
    )


def test_resolves_index_and_requests_arming():
    device, topics = _mouse(), _topics()
    task = MouseReprogFeatureTask(device, topics)
    deliver_on_request(task, topics, [_reply(11)])
    task.run()
    assert device.available_features[FEATURE_REPROG_CONTROLS_V4] == 11
    assert Task.Feature.Name.MOUSE_REPROG not in device.pending_steps
    topics.flags.publish.assert_called_once_with(SetReportFlagEvent(slot=SLOT, pid=BOLT_PID, wpid=WPID))


def test_unsupported_feature_completes_without_arming():
    device, topics = _mouse(), _topics()
    task = MouseReprogFeatureTask(device, topics)
    deliver_on_request(task, topics, [_reply(0)])
    task.run()
    assert FEATURE_REPROG_CONTROLS_V4 not in device.available_features
    assert Task.Feature.Name.MOUSE_REPROG not in device.pending_steps
    topics.flags.publish.assert_not_called()
