import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cleverswitch.model.config.config import Config
from cleverswitch.model.config.mouse_button_switch_config import MouseButtonSwitchConfig
from cleverswitch.settings.settings_service import SettingsService
from cleverswitch.tray.controller import TrayController
from cleverswitch.tray.strings import GERMAN


def _controller(mbs=None, names=None, *, options_plus=Path("/Applications/logioptionsplus.app"), autostart=True):
    config = Config(
        hooks=MagicMock(),
        arguments_settings=MagicMock(),
        cache_path=MagicMock(),
        mouse_button_switch=mbs or MouseButtonSwitchConfig(enabled=True, target_host=1),
        host_names=names or {},
        config_path=Path("/cfg/config.yaml"),
    )
    writer = MagicMock()
    writer.path = Path("/cfg/config.yaml")
    settings = SettingsService(config, MagicMock(), writer)
    desktop = MagicMock()
    desktop.options_plus.return_value = options_plus
    auto = None
    if autostart:
        auto = MagicMock()
        auto.is_enabled.return_value = False
    ask = MagicMock(return_value="Mac")
    shutdown = threading.Event()
    controller = TrayController(settings, shutdown, GERMAN, desktop, auto, ask, Path("/logs"))
    controller.refresh = MagicMock()
    return controller, settings, desktop, auto, ask, shutdown


def _find(entries, text):
    return next(e for e in entries if e.text == text)


def test_status_texts():
    controller, settings, *_ = _controller(names={1: "Mac"})
    assert controller.status() == "Daumentaste → 2 – Mac"
    assert controller.active and not controller.needs_host
    settings.set_target_host(2)
    assert controller.status() == "Daumentaste → Kanal 3"
    settings.set_button(0x01A0)
    assert controller.status() == "CID 0x01A0 → Kanal 3"
    settings.set_enabled(False)
    assert controller.status() == GERMAN.status_off
    assert not controller.active


def test_status_without_host():
    controller, *_ = _controller(MouseButtonSwitchConfig(enabled=True, target_host=None))
    assert controller.status() == "Daumentaste: Zielkanal wählen"
    assert controller.needs_host and not controller.active


def test_menu_layout():
    controller, *_ = _controller()
    texts = [e.text for e in controller.menu() if not e.separator]
    assert texts == [
        "Daumentaste → Kanal 2",
        GERMAN.enabled,
        GERMAN.target_host,
        GERMAN.name_hosts,
        GERMAN.button,
        GERMAN.keyboard_divert,
        GERMAN.open_options_plus,
        GERMAN.autostart,
        GERMAN.advanced,
        GERMAN.quit,
    ]
    assert controller.menu()[0].enabled is False


def test_toggle_enabled():
    controller, settings, *_ = _controller()
    _find(controller.menu(), GERMAN.enabled).action()
    assert settings.mouse_button_switch.enabled is False
    assert _find(controller.menu(), GERMAN.enabled).checked is False
    controller.refresh.assert_called_once()


def test_choose_host():
    controller, settings, *_ = _controller()
    hosts = _find(controller.menu(), GERMAN.target_host).submenu
    assert [h.checked for h in hosts] == [False, True, False]
    assert all(h.radio for h in hosts)
    hosts[0].action()
    assert settings.mouse_button_switch.target_host == 0
    controller.refresh.assert_called_once()


def test_choose_button():
    controller, settings, *_ = _controller()
    buttons = _find(controller.menu(), GERMAN.button).submenu
    assert _find(buttons, "Daumentaste").checked is True
    _find(buttons, "Vor-Taste").action()
    assert settings.mouse_button_switch.cid == 0x0056


def test_rename_runs_dialog_off_the_menu_thread():
    controller, settings, _, _, ask, _ = _controller()
    renames = _find(controller.menu(), GERMAN.name_hosts).submenu
    assert renames[1].text == "Kanal 2 …"
    with patch("cleverswitch.tray.controller.threading.Thread") as thread_cls:
        renames[1].action()
    thread_cls.assert_called_once()
    assert thread_cls.call_args.kwargs["args"] == (1,)
    thread_cls.return_value.start.assert_called_once()
    ask.assert_not_called()


def test_rename_host_saves_answer():
    controller, settings, _, _, ask, _ = _controller(names={1: "Alt"})
    controller.rename_host(1)
    ask.assert_called_once_with("CleverSwitch", "Name für Kanal 2 (leer = kein Name):", "Alt")
    assert settings.host_names == {1: "Mac"}
    controller.refresh.assert_called_once()


def test_rename_cancelled_changes_nothing():
    controller, settings, _, _, ask, _ = _controller(names={1: "Alt"})
    ask.return_value = None
    controller.rename_host(1)
    assert settings.host_names == {1: "Alt"}
    controller.refresh.assert_not_called()


def test_options_plus_entry():
    controller, _, desktop, *_ = _controller()
    _find(controller.menu(), GERMAN.open_options_plus).action()
    desktop.open_options_plus.assert_called_once()


def test_options_plus_missing_is_disabled():
    controller, *_ = _controller(options_plus=None)
    assert _find(controller.menu(), GERMAN.options_plus_missing).enabled is False


def test_autostart_toggle_and_absent():
    controller, _, _, auto, *_ = _controller()
    _find(controller.menu(), GERMAN.autostart).action()
    auto.set_enabled.assert_called_once_with(True)
    controller, *_ = _controller(autostart=False)
    assert GERMAN.autostart not in [e.text for e in controller.menu()]
    controller.toggle_autostart()  # nothing to toggle, still refreshes
    controller.refresh.assert_called_once()


def test_advanced_entries():
    controller, settings, desktop, *_ = _controller()
    advanced = _find(controller.menu(), GERMAN.advanced).submenu
    _find(advanced, GERMAN.divert).action()
    assert settings.mouse_button_switch.divert is False
    _find(advanced, GERMAN.open_config).action()
    _find(advanced, GERMAN.open_logs).action()
    assert [c.args[0] for c in desktop.open_path.call_args_list] == [Path("/cfg/config.yaml"), Path("/logs")]


def test_advanced_without_paths():
    controller, *_ = _controller()
    controller._log_dir = None
    controller._settings._writer = None
    advanced = _find(controller.menu(), GERMAN.advanced).submenu
    assert [e.text for e in advanced] == [GERMAN.divert]


def test_quit_sets_shutdown():
    controller, *_, shutdown = _controller()
    _find(controller.menu(), GERMAN.quit).action()
    assert shutdown.is_set()


@pytest.mark.parametrize("cid", [0x0052, 0x0053, 0x00C4])
def test_every_known_button_has_a_label(cid):
    controller, *_ = _controller()
    assert not controller.button_label(cid).startswith("CID")


def test_toggle_keyboard_divert():
    controller, settings, *_ = _controller()
    _find(controller.menu(), GERMAN.keyboard_divert).action()
    assert settings.easy_switch_divert is True
    assert _find(controller.menu(), GERMAN.keyboard_divert).checked is True
