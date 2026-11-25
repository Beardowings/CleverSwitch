"""Gives a windowed (no-console) Windows build usable stdout/stderr when it is started from a terminal.

PyInstaller's ``--windowed`` exe starts with ``sys.stdout``/``sys.stderr`` set to None. When the caller
redirected them (``cleverswitch.exe --version > out.txt``, a build script's ``for /f``), the inherited
handles are used; when it was typed in a console, that console is attached. Started by double-click
or at login there is neither, and the streams stay None, which the logging setup already handles.
"""

from __future__ import annotations

import sys

_STD_OUTPUT_HANDLE = -11
_STD_ERROR_HANDLE = -12
_ATTACH_PARENT_PROCESS = -1
_INVALID_HANDLE = (0, -1, 0xFFFFFFFF, 0xFFFFFFFFFFFFFFFF)


def attach_console_streams() -> None:
    if sys.platform != "win32" or (sys.stdout is not None and sys.stderr is not None):
        return
    _attach()  # pragma: no cover - Windows only


def _attach() -> None:  # pragma: no cover - Windows console API
    import ctypes
    import msvcrt

    kernel32 = ctypes.windll.kernel32
    kernel32.GetStdHandle.restype = ctypes.c_void_p

    def from_handle(which: int):
        handle = kernel32.GetStdHandle(which)
        if handle in _INVALID_HANDLE or handle is None:
            return None
        try:
            return open(msvcrt.open_osfhandle(handle, 0), "w", buffering=1, encoding="utf-8", errors="replace")
        except OSError:
            return None

    out, err = from_handle(_STD_OUTPUT_HANDLE), from_handle(_STD_ERROR_HANDLE)
    if out is None and err is None and kernel32.AttachConsole(_ATTACH_PARENT_PROCESS):
        try:
            out = open("CONOUT$", "w", buffering=1, encoding="utf-8", errors="replace")
            err = out
        except OSError:
            out = err = None
    if sys.stdout is None and out is not None:
        sys.stdout = out
    if sys.stderr is None and (err or out) is not None:
        sys.stderr = err or out
