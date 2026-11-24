import sys
import threading
import types
from pathlib import Path
from unittest.mock import MagicMock

from cleverswitch.tray import runner
from cleverswitch.tray.controller import TrayController


def _context(settings=True):
    context = MagicMock()
    context.settings = MagicMock() if settings else None
    context.shutdown = threading.Event()
    context.config.logging.file_path = Path("/logs/cleverswitch.log")
    context.config.logging.file_enabled = True
    return context


def test_supported_systems():
    assert runner.tray_supported("Windows") and runner.tray_supported("Darwin")
    assert not runner.tray_supported("Linux")


def test_build_controller_for_mac():
    controller = runner.build_controller(_context(), "Darwin")
    assert isinstance(controller, TrayController)
    assert controller._log_dir == Path("/logs")
    assert controller._ask_text is runner.ask_text_mac


def test_build_controller_for_windows_without_log_file(monkeypatch):
    monkeypatch.setattr(runner, "create_autostart", lambda system: None)
    context = _context()
    context.config.logging.file_enabled = False
    controller = runner.build_controller(context, "Windows")
    assert controller._log_dir is None
    assert controller._ask_text.__name__ == "ask_text_windows"


def test_no_tray_on_linux_or_without_settings():
    thread = MagicMock()
    assert runner.run_tray(_context(), thread, "Linux") is False
    assert runner.run_tray(_context(settings=False), thread, "Darwin") is False


def _fake_pystray_module(monkeypatch, tray_cls):
    module = types.ModuleType("cleverswitch.tray.pystray_tray")
    module.PystrayTray = tray_cls
    monkeypatch.setitem(sys.modules, "cleverswitch.tray.pystray_tray", module)


def test_import_failure_falls_back(monkeypatch, caplog):
    monkeypatch.setitem(sys.modules, "cleverswitch.tray.pystray_tray", None)  # import raises ImportError
    assert runner.run_tray(_context(), MagicMock(), "Darwin") is False
    assert "No tray icon" in caplog.text


def test_icon_creation_failure_falls_back(monkeypatch, caplog):
    monkeypatch.setattr(runner, "create_autostart", lambda system: None)
    _fake_pystray_module(monkeypatch, MagicMock(side_effect=RuntimeError("no display")))
    assert runner.run_tray(_context(), MagicMock(), "Windows") is False
    assert "no display" in caplog.text


def test_runs_tray_and_stops_it_when_discovery_ends(monkeypatch):
    tray = MagicMock()
    _fake_pystray_module(monkeypatch, MagicMock(return_value=tray))
    context = _context()
    discovery = threading.Thread(target=lambda: None)
    discovery.start()
    stopped = threading.Event()
    tray.stop.side_effect = stopped.set
    tray.run.side_effect = lambda: stopped.wait(2)

    assert runner.run_tray(context, discovery, "Darwin") is True
    assert stopped.is_set()
    assert context.shutdown.is_set()
