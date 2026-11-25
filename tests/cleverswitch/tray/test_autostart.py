import plistlib
import sys

from cleverswitch.tray.autostart import (
    MAC_LABEL,
    RUN_KEY,
    RUN_VALUE,
    MacAutostart,
    WindowsAutostart,
    create_autostart,
    launch_command,
)


def test_launch_command_from_source(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    assert launch_command() == [sys.executable, "-m", "cleverswitch"]


def test_launch_command_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert launch_command() == [sys.executable]


def test_mac_toggle(tmp_path):
    autostart = MacAutostart(tmp_path / "LaunchAgents", ["/Applications/CleverSwitch.app/Contents/MacOS/CleverSwitch"])
    assert autostart.is_enabled() is False
    assert autostart.set_enabled(True) is True
    plist = tmp_path / "LaunchAgents" / f"{MAC_LABEL}.plist"
    agent = plistlib.loads(plist.read_bytes())
    assert agent["ProgramArguments"] == ["/Applications/CleverSwitch.app/Contents/MacOS/CleverSwitch"]
    assert agent["RunAtLoad"] is True
    assert agent["KeepAlive"] == {"SuccessfulExit": False}
    assert autostart.is_enabled() is True
    assert autostart.set_enabled(False) is True
    assert not plist.exists()
    assert autostart.set_enabled(False) is True  # already off


def test_mac_write_failure(tmp_path, caplog):
    blocker = tmp_path / "file"
    blocker.write_text("")
    assert MacAutostart(blocker, ["x"]).set_enabled(True) is False
    assert "Could not change start at login" in caplog.text


class FakeWinreg:
    HKEY_CURRENT_USER = "HKCU"
    KEY_SET_VALUE = 2
    REG_SZ = 1

    def __init__(self):
        self.values = {}
        self.fail = False

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def OpenKey(self, root, path, *args):
        assert (root, path) == ("HKCU", RUN_KEY)
        if self.fail:
            raise PermissionError("denied")
        return self._Key()

    def QueryValueEx(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        return self.values[name], self.REG_SZ

    def SetValueEx(self, key, name, reserved, kind, value):
        self.values[name] = value

    def DeleteValue(self, key, name):
        if name not in self.values:
            raise FileNotFoundError(name)
        del self.values[name]


def test_windows_toggle():
    reg = FakeWinreg()
    autostart = WindowsAutostart(reg, [r"C:\Tools\cleverswitch.exe"])
    assert autostart.is_enabled() is False
    assert autostart.set_enabled(True) is True
    assert reg.values[RUN_VALUE] == r'"C:\Tools\cleverswitch.exe"'
    assert autostart.is_enabled() is True
    assert autostart.set_enabled(False) is True
    assert autostart.set_enabled(False) is True  # deleting a missing value is fine
    assert autostart.is_enabled() is False


def test_windows_failure(caplog):
    reg = FakeWinreg()
    reg.fail = True
    autostart = WindowsAutostart(reg, ["x"])
    assert autostart.is_enabled() is False
    assert autostart.set_enabled(True) is False
    assert "Could not change start at login" in caplog.text


def test_create_autostart_per_platform():
    assert isinstance(create_autostart("Darwin"), MacAutostart)
    assert create_autostart("Linux") is None


NEW_APP = ["/Applications/CleverSwitch.app/Contents/MacOS/CleverSwitch"]


def test_mac_refresh_repoints_an_old_agent(tmp_path, caplog):
    MacAutostart(tmp_path, ["/Users/me/Downloads/CleverSwitch.app/Contents/MacOS/CleverSwitch"]).set_enabled(True)
    autostart = MacAutostart(tmp_path, NEW_APP)
    assert autostart.refresh() is True
    agent = plistlib.loads((tmp_path / f"{MAC_LABEL}.plist").read_bytes())
    assert agent["ProgramArguments"] == NEW_APP
    assert "updating it" in caplog.text
    assert autostart.refresh() is False  # already current


def test_mac_refresh_leaves_a_missing_or_broken_agent_alone(tmp_path):
    autostart = MacAutostart(tmp_path, NEW_APP)
    assert autostart.refresh() is False
    assert not autostart.is_enabled()
    (tmp_path / f"{MAC_LABEL}.plist").write_bytes(b"not a plist")
    assert autostart.refresh() is False


def test_windows_refresh():
    reg = FakeWinreg()
    autostart = WindowsAutostart(reg, [r"C:\New\cleverswitch.exe"])
    assert autostart.refresh() is False  # off stays off
    assert RUN_VALUE not in reg.values
    reg.values[RUN_VALUE] = r'"C:\Old\cleverswitch.exe"'
    assert autostart.refresh() is True
    assert reg.values[RUN_VALUE] == r'"C:\New\cleverswitch.exe"'
    assert autostart.refresh() is False
