"""Renders TrayController with pystray. GUI glue: exercised on real desktops, not in unit tests."""

from __future__ import annotations

import logging
import signal
import threading

import pystray

from . import icon_image
from .controller import TrayController
from .menu import MenuEntry

log = logging.getLogger(__name__)


def _handler(action):
    # pystray inspects the argument count, so the handler takes exactly (icon, item).
    def handle(_icon, _item) -> None:
        action()

    return handle


def _to_pystray(entries: list[MenuEntry]) -> pystray.Menu:
    items = []
    for entry in entries:
        if entry.separator:
            items.append(pystray.Menu.SEPARATOR)
            continue
        action = entry.action
        kwargs = {"enabled": entry.enabled}
        if entry.checked is not None:
            checked = entry.checked
            kwargs["checked"] = lambda _item, value=checked: value
            kwargs["radio"] = entry.radio
        if entry.submenu is not None:
            items.append(pystray.MenuItem(entry.text, _to_pystray(list(entry.submenu)), **kwargs))
        else:
            handler = _handler(action) if action else None
            items.append(pystray.MenuItem(entry.text, handler, **kwargs))
    return pystray.Menu(*items)


class PystrayTray:
    def __init__(self, controller: TrayController, system: str, shutdown: threading.Event, hint: str) -> None:
        self._controller = controller
        self._system = system
        self._shutdown = shutdown
        self._hint = hint
        self._icon = self._create_icon()
        controller.refresh = self.refresh

    def _image(self):
        active = self._controller.active
        return icon_image.mac_template(active) if self._system == "Darwin" else icon_image.windows_icon(active)

    def _menu(self) -> pystray.Menu:
        # A callable menu is rebuilt by pystray on every update_menu(), so it always shows the current settings.
        return pystray.Menu(lambda: tuple(_to_pystray(self._controller.menu()).items))

    def _create_icon(self):
        if self._system == "Darwin":
            icon_class = _mac_icon_class()
            return icon_class("CleverSwitch", self._image(), "CleverSwitch", self._menu(), shutdown=self._shutdown)
        return pystray.Icon("CleverSwitch", self._image(), "CleverSwitch", self._menu())

    def refresh(self) -> None:
        def apply() -> None:
            self._icon.icon = self._image()
            self._icon.title = f"CleverSwitch – {self._controller.status()}"
            self._icon.update_menu()

        self._on_ui_thread(apply)

    def _on_ui_thread(self, func) -> None:
        if self._system == "Darwin":
            from PyObjCTools import AppHelper

            AppHelper.callAfter(func)
        else:
            func()

    def run(self) -> None:
        """Blocks on the calling (main) thread until stop()."""

        def setup(icon) -> None:
            self._on_ui_thread(lambda: setattr(icon, "visible", True))
            self.refresh()
            if self._controller.needs_host:
                try:
                    icon.notify(self._hint, "CleverSwitch")
                except Exception as e:
                    log.debug(f"Notification failed: {e}")

        self._icon.run(setup=setup)

    def stop(self) -> None:
        self._on_ui_thread(self._icon.stop)


def _mac_icon_class():
    import AppKit
    from PyObjCTools import MachSignals
    from pystray import _darwin

    class MacIcon(_darwin.Icon):
        """pystray's macOS icon with a template image, no Dock icon, and signals that shut down cleanly.

        pystray's own SIGINT handler terminates NSApp at once, which would skip the shutdown
        un-divert and leave the button dead. NSApp.run() blocks the interpreter, so Python's signal
        module never runs our handler either; MachSignals delivers it through the run loop.
        """

        def __init__(self, *args, shutdown: threading.Event, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self._shutdown = shutdown

        def _assert_image(self) -> None:
            super()._assert_image()
            self._icon_image.setTemplate_(True)

        def _run(self) -> None:
            self._app.setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
            self._mark_ready()
            for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                MachSignals.signal(sig, self._on_signal)
            try:
                self._app.run()
            except Exception:
                log.exception("Menu bar loop failed")
            finally:
                self._status_bar.removeStatusItem_(self._status_item)

        def _on_signal(self, *_args) -> None:
            self._shutdown.set()

    return MacIcon
