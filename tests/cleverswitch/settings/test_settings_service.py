"""Tests for settings/settings_service.py — runtime settings changed from the tray."""

from unittest.mock import MagicMock

import pytest
import yaml

from cleverswitch.config.config_file import ConfigFileWriter
from cleverswitch.event.mouse_button_switch_changed_event import MouseButtonSwitchChangedEvent
from cleverswitch.model.config.config import Config
from cleverswitch.model.config.mouse_button_switch_config import MouseButtonSwitchConfig
from cleverswitch.settings.settings_service import SettingsService


def _service(tmp_path=None, *, mbs=None, names=None, raw_text=None):
    config = Config(
        hooks=MagicMock(),
        arguments_settings=MagicMock(),
        cache_path=MagicMock(),
        mouse_button_switch=mbs or MouseButtonSwitchConfig(enabled=True, target_host=1),
        host_names=names or {},
    )
    topics = MagicMock()
    writer = None
    if tmp_path is not None:
        path = tmp_path / "config.yaml"
        if raw_text is not None:
            path.write_text(raw_text)
        writer = ConfigFileWriter(path)
    return SettingsService(config, topics, writer), topics, writer


def _saved(writer):
    return yaml.safe_load(writer.path.read_text())


def test_exposes_initial_values():
    service, _, _ = _service(names={0: "Notebook"})
    assert service.mouse_button_switch.target_host == 1
    assert service.host_names == {0: "Notebook"}
    assert service.config_path is None


def test_change_publishes_event_with_old_and_new(tmp_path):
    service, topics, _ = _service(tmp_path)
    old = service.mouse_button_switch
    service.set_target_host(2)
    (event,) = [c.args[0] for c in topics.flags.publish.call_args_list]
    assert isinstance(event, MouseButtonSwitchChangedEvent)
    assert event.old == old
    assert event.new == MouseButtonSwitchConfig(enabled=True, target_host=2)


def test_unchanged_value_publishes_and_writes_nothing(tmp_path):
    service, topics, writer = _service(tmp_path)
    service.set_enabled(True)
    topics.flags.publish.assert_not_called()
    assert not writer.path.exists()


def test_every_setter_is_saved(tmp_path):
    service, _, writer = _service(tmp_path, raw_text="hooks: {}\nmouse_button_switch: off\n")
    service.set_enabled(False)
    service.set_button(0x0056)
    service.set_divert(False)
    service.set_target_host(0)
    assert _saved(writer) == {
        "hooks": {},
        "mouse_button_switch": {"enabled": False, "button": "forward", "host": 1, "divert": False},
    }


def test_unknown_button_saved_as_hex_and_missing_host_left_out(tmp_path):
    service, _, writer = _service(tmp_path, mbs=MouseButtonSwitchConfig(enabled=True, target_host=None))
    service.set_button(0x01A0)
    assert _saved(writer)["mouse_button_switch"] == {"enabled": True, "button": "0x01A0", "divert": True}


@pytest.mark.parametrize("host", [-1, 3])
def test_out_of_range_host_rejected(host):
    service, _, _ = _service()
    with pytest.raises(ValueError):
        service.set_target_host(host)
    with pytest.raises(ValueError):
        service.set_host_name(host, "x")


def test_host_names_saved_and_cleared(tmp_path):
    service, topics, writer = _service(tmp_path)
    service.set_host_name(1, "  Mac ")
    service.set_host_name(0, "Notebook")
    assert service.host_names == {0: "Notebook", 1: "Mac"}
    assert _saved(writer)["host_names"] == {1: "Notebook", 2: "Mac"}
    service.set_host_name(1, "Mac")  # unchanged
    service.set_host_name(0, "")
    service.set_host_name(1, None)
    assert service.host_names == {}
    assert "host_names" not in _saved(writer)
    topics.flags.publish.assert_not_called()


def test_works_without_a_file():
    service, topics, _ = _service()
    service.set_enabled(False)
    service.set_host_name(0, "A")
    assert service.mouse_button_switch.enabled is False
    topics.flags.publish.assert_called_once()


def test_easy_switch_divert_saved_and_announced(tmp_path):
    from cleverswitch.event.easy_switch_mode_changed_event import EasySwitchModeChangedEvent

    service, topics, writer = _service(tmp_path, raw_text="easy_switch: on\n")
    assert service.easy_switch_divert is False
    service.set_easy_switch_divert(False)  # unchanged
    topics.flags.publish.assert_not_called()
    service.set_easy_switch_divert(True)
    assert service.easy_switch_divert is True
    assert _saved(writer)["easy_switch"] == {"divert": True}
    (event,) = [c.args[0] for c in topics.flags.publish.call_args_list]
    assert event == EasySwitchModeChangedEvent(slot=0, pid=0, divert=True)
