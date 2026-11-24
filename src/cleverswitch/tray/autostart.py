"""Start at login, in the user's own context: no admin rights, no scheduled task, no helper script.

- Windows: a value under HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run.
- macOS: a LaunchAgent in ~/Library/LaunchAgents, using the label install scripts already use, so
  turning it on from the menu replaces an agent set up by setup_startup.command instead of
  starting a second copy.
"""

from __future__ import annotations

import logging
import plistlib
import sys
from pathlib import Path
from typing import Protocol

log = logging.getLogger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_VALUE = "CleverSwitch"
MAC_LABEL = "com.user.cleverswitch"


class Autostart(Protocol):
    def is_enabled(self) -> bool: ...

    def set_enabled(self, enabled: bool) -> bool: ...


def launch_command() -> list[str]:
    """How to start this program again: the frozen binary itself, or this interpreter with -m."""
    if getattr(sys, "frozen", False):
        return [sys.executable]
    return [sys.executable, "-m", "cleverswitch"]


class WindowsAutostart:
    def __init__(self, winreg=None, command: list[str] | None = None) -> None:
        if winreg is None:  # pragma: no cover - Windows only
            import winreg as winreg_module

            winreg = winreg_module
        self._winreg = winreg
        self._command = command or launch_command()

    def is_enabled(self) -> bool:
        try:
            with self._winreg.OpenKey(self._winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
                self._winreg.QueryValueEx(key, RUN_VALUE)
            return True
        except OSError:
            return False

    def set_enabled(self, enabled: bool) -> bool:
        reg = self._winreg
        try:
            with reg.OpenKey(reg.HKEY_CURRENT_USER, RUN_KEY, 0, reg.KEY_SET_VALUE) as key:
                if enabled:
                    reg.SetValueEx(key, RUN_VALUE, 0, reg.REG_SZ, " ".join(f'"{part}"' for part in self._command))
                else:
                    try:
                        reg.DeleteValue(key, RUN_VALUE)
                    except FileNotFoundError:
                        pass
        except OSError as e:
            log.error(f"Could not change start at login: {e}")
            return False
        log.info(f"Start at login {'on' if enabled else 'off'}")
        return True


class MacAutostart:
    def __init__(self, agents_dir: Path | None = None, command: list[str] | None = None) -> None:
        self._plist = (agents_dir or Path("~/Library/LaunchAgents").expanduser()) / f"{MAC_LABEL}.plist"
        self._command = command or launch_command()

    def is_enabled(self) -> bool:
        return self._plist.exists()

    def set_enabled(self, enabled: bool) -> bool:
        try:
            if enabled:
                self._plist.parent.mkdir(parents=True, exist_ok=True)
                agent = {
                    "Label": MAC_LABEL,
                    "ProgramArguments": self._command,
                    "RunAtLoad": True,
                    # Restart after a crash, but not after "Quit" from the menu.
                    "KeepAlive": {"SuccessfulExit": False},
                    "LimitLoadToSessionType": "Aqua",
                    "ProcessType": "Interactive",
                }
                with open(self._plist, "wb") as f:
                    plistlib.dump(agent, f)
            else:
                self._plist.unlink(missing_ok=True)
        except OSError as e:
            log.error(f"Could not change start at login: {e}")
            return False
        # Not loaded now: this instance is already running. launchd picks the agent up at next login.
        log.info(f"Start at login {'on' if enabled else 'off'}")
        return True


def create_autostart(system: str) -> Autostart | None:
    if system == "Windows":
        return WindowsAutostart()  # pragma: no cover - needs winreg
    if system == "Darwin":
        return MacAutostart()
    return None
