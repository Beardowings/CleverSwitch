"""Small desktop actions for the menu: open Logi Options+, open a file or folder, ask for a line of text."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Callable
from pathlib import Path

log = logging.getLogger(__name__)

_MAC_OPTIONS_PLUS = (
    Path("/Applications/logioptionsplus.app"),
    Path("~/Applications/logioptionsplus.app").expanduser(),
)


def _windows_options_plus(environ) -> list[Path]:
    roots = [environ.get("ProgramFiles"), environ.get("ProgramW6432"), r"C:\Program Files"]
    return [Path(root) / "LogiOptionsPlus" / "logioptionsplus.exe" for root in roots if root]


class Desktop:
    """Platform glue behind the menu. Every action logs and swallows its own failure."""

    def __init__(
        self,
        system: str,
        run: Callable[..., object] = subprocess.Popen,
        exists: Callable[[Path], bool] = Path.exists,
        environ=None,
        startfile: Callable[[str], None] | None = None,
    ) -> None:
        self._system = system
        self._run = run
        self._exists = exists
        self._environ = os.environ if environ is None else environ
        self._startfile = startfile or getattr(os, "startfile", None)

    def options_plus(self) -> Path | None:
        if self._system == "Darwin":
            candidates = list(_MAC_OPTIONS_PLUS)
        elif self._system == "Windows":
            candidates = _windows_options_plus(self._environ)
        else:
            return None
        return next((path for path in candidates if self._exists(path)), None)

    def open_options_plus(self) -> None:
        path = self.options_plus()
        if path is None:
            log.warning("Logi Options+ was not found")
            return
        if self._system == "Darwin":
            self._spawn(["open", "-a", str(path)])
        else:
            self._spawn([str(path)])

    def open_path(self, path: Path) -> None:
        if self._system == "Windows" and self._startfile is not None:
            try:
                self._startfile(str(path))
            except OSError as e:
                log.error(f"Could not open {path}: {e}")
        elif self._system == "Darwin":
            self._spawn(["open", str(path)])
        else:
            self._spawn(["xdg-open", str(path)])

    def _spawn(self, command: list[str]) -> None:
        try:
            self._run(command)
        except OSError as e:
            log.error(f"Could not run {command[0]}: {e}")


def ask_text_mac(title: str, prompt: str, default: str, run=subprocess.run) -> str | None:
    """A text field via AppleScript; None when cancelled. The values travel as arguments, not as script text."""
    script = (
        "on run argv\n"
        "  set r to display dialog (item 2 of argv) default answer (item 3 of argv) with title (item 1 of argv)\n"
        "  return text returned of r\n"
        "end run"
    )
    try:
        result = run(["osascript", "-e", script, title, prompt, default], capture_output=True, text=True, timeout=600)
    except (OSError, subprocess.TimeoutExpired) as e:
        log.error(f"Could not ask for text: {e}")
        return None
    if result.returncode != 0:
        return None  # cancelled
    return result.stdout.rstrip("\n")


def ask_text_windows(title: str, prompt: str, default: str) -> str | None:  # pragma: no cover - GUI
    import tkinter
    from tkinter import simpledialog

    root = tkinter.Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    try:
        return simpledialog.askstring(title, prompt, initialvalue=default, parent=root)
    finally:
        root.destroy()
