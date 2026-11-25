import subprocess
from pathlib import Path
from unittest.mock import MagicMock

from cleverswitch.tray.desktop import Desktop, ask_text_mac, choose_mac


def _desktop(system, existing=(), **kwargs):
    run = MagicMock()
    desktop = Desktop(system, run=run, exists=lambda p: p in existing, **kwargs)
    return desktop, run


def test_mac_options_plus_found_and_opened():
    app = Path("/Applications/logioptionsplus.app")
    desktop, run = _desktop("Darwin", {app})
    assert desktop.options_plus() == app
    desktop.open_options_plus()
    run.assert_called_once_with(["open", "-a", str(app)])


def test_windows_options_plus_under_program_files():
    exe = Path(r"D:\Programme") / "LogiOptionsPlus" / "logioptionsplus.exe"
    desktop, run = _desktop("Windows", {exe}, environ={"ProgramFiles": r"D:\Programme"})
    assert desktop.options_plus() == exe
    desktop.open_options_plus()
    run.assert_called_once_with([str(exe)])


def test_options_plus_missing(caplog):
    desktop, run = _desktop("Windows", environ={})
    assert desktop.options_plus() is None
    desktop.open_options_plus()
    run.assert_not_called()
    assert "not found" in caplog.text
    assert _desktop("Linux")[0].options_plus() is None


def test_open_path_per_platform():
    startfile = MagicMock()
    desktop, _ = _desktop("Windows", environ={}, startfile=startfile)
    desktop.open_path(Path("C:/x"))
    startfile.assert_called_once_with(str(Path("C:/x")))

    desktop, run = _desktop("Darwin")
    desktop.open_path(Path("/tmp/x"))
    run.assert_called_once_with(["open", "/tmp/x"])

    desktop, run = _desktop("Linux")
    desktop.open_path(Path("/tmp/x"))
    run.assert_called_once_with(["xdg-open", "/tmp/x"])


def test_open_failures_are_logged(caplog):
    desktop, _ = _desktop("Windows", environ={}, startfile=MagicMock(side_effect=OSError("no")))
    desktop.open_path(Path("x"))
    run = MagicMock(side_effect=OSError("missing"))
    Desktop("Darwin", run=run).open_path(Path("x"))
    assert "Could not open" in caplog.text
    assert "Could not run open" in caplog.text


def test_ask_text_mac_returns_answer_and_passes_values_as_arguments():
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, stdout='Mac "Pro"\n'))
    assert ask_text_mac("T", "P", 'd"q', run=run) == 'Mac "Pro"'
    args = run.call_args.args[0]
    assert args[0] == "osascript"
    assert args[-3:] == ["T", "P", 'd"q']


def test_ask_text_mac_cancel_and_failure(caplog):
    cancel = MagicMock(return_value=subprocess.CompletedProcess([], 1, stdout=""))
    assert ask_text_mac("T", "P", "", run=cancel) is None
    broken = MagicMock(side_effect=OSError("no osascript"))
    assert ask_text_mac("T", "P", "", run=broken) is None
    assert "Could not ask for text" in caplog.text


def test_open_url_per_platform():
    run = MagicMock()
    Desktop("Darwin", run=run).open_url("https://x")
    run.assert_called_with(["open", "https://x"])
    Desktop("Linux", run=run).open_url("https://x")
    run.assert_called_with(["xdg-open", "https://x"])
    started = []
    Desktop("Windows", startfile=started.append).open_url("https://x")
    assert started == ["https://x"]


def test_open_url_failure_on_windows_is_logged(caplog):
    def broken(url):
        raise OSError("no browser")

    Desktop("Windows", startfile=broken).open_url("https://x")
    assert "Could not open https://x" in caplog.text


def test_choose_mac_returns_button_and_passes_values_as_arguments():
    run = MagicMock(return_value=MagicMock(returncode=0, stdout="Aktualisieren\n"))
    assert choose_mac("T", "M", ["A", "B"], run=run) == "Aktualisieren"
    command = run.call_args.args[0]
    assert command[:2] == ["osascript", "-e"] and command[3:] == ["T", "M", "A", "B"]


def test_choose_mac_closed_or_failed(caplog):
    assert choose_mac("T", "M", ["OK"], run=MagicMock(return_value=MagicMock(returncode=1))) is None
    assert choose_mac("T", "M", ["OK"], run=MagicMock(side_effect=OSError("no osascript"))) is None
    assert "Could not show a dialog" in caplog.text
