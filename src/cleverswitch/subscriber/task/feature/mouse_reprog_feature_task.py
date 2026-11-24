from ....event.set_report_flag_event import SetReportFlagEvent
from ....hidpp.constants import FEATURE_REPROG_CONTROLS_V4
from ....model.logi_device import LogiDevice
from ....topic.topics import Topics
from ..constants import FEATURE_REPROG_CONTROLS_V4_SW_ID, Task
from .resolve_feature_task import FeatureTask


class MouseReprogFeatureTask(FeatureTask):
    """Resolves x1B04 on a mouse, which keyboard-only discovery skips, so mouse_button_switch can use it.

    Once resolved, a SetReportFlagEvent asks MouseButtonSwitchSubscriber to arm the configured button;
    reconnections then re-arm through the usual DeviceConnectionSubscriber path.
    """

    def __init__(self, device: LogiDevice, topics: Topics) -> None:
        super().__init__(
            Task.Feature.Name.MOUSE_REPROG,
            device,
            topics,
            FEATURE_REPROG_CONTROLS_V4,
            FEATURE_REPROG_CONTROLS_V4_SW_ID,
        )

    def _fire_dependent_steps(self):
        if FEATURE_REPROG_CONTROLS_V4 not in self._device.available_features:
            return
        self._topics.flags.publish(
            SetReportFlagEvent(slot=self._device.slot, pid=self._device.pid, wpid=self._device.wpid)
        )
