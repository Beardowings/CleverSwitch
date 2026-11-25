"""What the tray menu shows and does. Toolkit-free; pystray_tray.py renders it."""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path

from ..hidpp.constants import MOUSE_BUTTON_CIDS
from ..settings.settings_service import HOST_COUNT, SettingsService
from ..update.release import REPO_URL, UpdateError, is_newer
from ..update.service import Updates
from .autostart import Autostart
from .desktop import Desktop
from .menu import SEPARATOR, MenuEntry
from .strings import Strings

log = logging.getLogger(__name__)

AskText = Callable[[str, str, str], "str | None"]
Choose = Callable[[str, str, list[str]], "str | None"]


class TrayController:
    def __init__(
        self,
        settings: SettingsService,
        shutdown: threading.Event,
        strings: Strings,
        desktop: Desktop,
        autostart: Autostart | None,
        ask_text: AskText,
        log_dir: Path | None,
        updates: Updates | None = None,
        choose: Choose | None = None,
    ) -> None:
        self._settings = settings
        self._shutdown = shutdown
        self._s = strings
        self._desktop = desktop
        self._autostart = autostart
        self._ask_text = ask_text
        self._log_dir = log_dir
        self._updates = updates
        self._choose = choose
        self.refresh: Callable[[], None] = lambda: None  # set by the renderer: redraw menu and icon

    # ── State shown by the renderer ─────────────────────────────────────

    @property
    def active(self) -> bool:
        """Drives the icon: on, and with somewhere to switch to."""
        config = self._settings.mouse_button_switch
        return config.enabled and config.target_host is not None

    @property
    def needs_host(self) -> bool:
        config = self._settings.mouse_button_switch
        return config.enabled and config.target_host is None

    def host_label(self, host: int) -> str:
        name = self._settings.host_names.get(host)
        return f"{host + 1} – {name}" if name else self._s.host_default.format(n=host + 1)

    def button_label(self, cid: int) -> str:
        for key, value in MOUSE_BUTTON_CIDS.items():
            if value == cid:
                return self._s.buttons.get(key, key)
        return f"CID 0x{cid:04X}"

    def status(self) -> str:
        config = self._settings.mouse_button_switch
        if not config.enabled:
            return self._s.status_off
        button = self.button_label(config.cid)
        if config.target_host is None:
            return self._s.status_no_host.format(button=button)
        return self._s.status_on.format(button=button, host=self.host_label(config.target_host))

    def menu(self) -> list[MenuEntry]:
        config = self._settings.mouse_button_switch
        options_plus = self._desktop.options_plus()
        entries = [
            MenuEntry(self.status(), enabled=False),
            SEPARATOR,
            MenuEntry(self._s.enabled, self.toggle_enabled, checked=config.enabled),
            MenuEntry(self._s.target_host, submenu=tuple(self._host_entries(config.target_host))),
            MenuEntry(self._s.name_hosts, submenu=tuple(self._rename_entries())),
            MenuEntry(self._s.button, submenu=tuple(self._button_entries(config.cid))),
            MenuEntry(self._s.follow_keyboard, self.toggle_follow_keyboard, checked=config.follow_keyboard),
            SEPARATOR,
            MenuEntry(
                self._s.open_options_plus if options_plus else self._s.options_plus_missing,
                self._desktop.open_options_plus,
                enabled=options_plus is not None,
            ),
        ]
        if self._autostart is not None:
            entries.append(MenuEntry(self._s.autostart, self.toggle_autostart, checked=self._autostart.is_enabled()))
        entries.append(MenuEntry(self._s.advanced, submenu=tuple(self._advanced_entries(config.divert))))
        entries.append(SEPARATOR)
        if self._updates is not None and self._choose is not None:
            entries.append(MenuEntry(self._s.info, self.open_info))
        entries.append(MenuEntry(self._s.quit, self.quit))
        return entries

    def _host_entries(self, target: int | None):
        for host in range(HOST_COUNT):
            yield MenuEntry(self.host_label(host), self._choose_host(host), checked=target == host, radio=True)

    def _rename_entries(self):
        for host in range(HOST_COUNT):
            yield MenuEntry(self.host_label(host) + " …", self._rename_host(host))

    def _button_entries(self, current: int):
        for key, cid in MOUSE_BUTTON_CIDS.items():
            yield MenuEntry(self._s.buttons.get(key, key), self._choose_button(cid), checked=current == cid, radio=True)

    def _advanced_entries(self, divert: bool):
        yield MenuEntry(self._s.divert, self.toggle_divert, checked=divert)
        path = self._settings.config_path
        if path is not None:
            yield MenuEntry(self._s.open_config, lambda: self._desktop.open_path(path))
        if self._log_dir is not None:
            log_dir = self._log_dir
            yield MenuEntry(self._s.open_logs, lambda: self._desktop.open_path(log_dir))

    # ── Actions (run on the toolkit's thread) ───────────────────────────

    def toggle_enabled(self) -> None:
        self._settings.set_enabled(not self._settings.mouse_button_switch.enabled)
        self.refresh()

    def toggle_follow_keyboard(self) -> None:
        self._settings.set_follow_keyboard(not self._settings.mouse_button_switch.follow_keyboard)
        self.refresh()

    def toggle_divert(self) -> None:
        self._settings.set_divert(not self._settings.mouse_button_switch.divert)
        self.refresh()

    def toggle_autostart(self) -> None:
        if self._autostart is not None:
            self._autostart.set_enabled(not self._autostart.is_enabled())
        self.refresh()

    def _choose_host(self, host: int) -> Callable[[], None]:
        def choose() -> None:
            self._settings.set_target_host(host)
            self.refresh()

        return choose

    def _choose_button(self, cid: int) -> Callable[[], None]:
        def choose() -> None:
            self._settings.set_button(cid)
            self.refresh()

        return choose

    def _rename_host(self, host: int) -> Callable[[], None]:
        def rename() -> None:
            # Off the toolkit thread: the dialog must not freeze the menu bar while it is open.
            threading.Thread(target=self.rename_host, args=(host,), name="tray-rename", daemon=True).start()

        return rename

    def rename_host(self, host: int) -> None:
        current = self._settings.host_names.get(host, "")
        answer = self._ask_text(self._s.rename_title, self._s.rename_prompt.format(n=host + 1), current)
        if answer is None:
            return
        self._settings.set_host_name(host, answer)
        self.refresh()

    def open_info(self) -> None:
        # Off the toolkit thread: asking GitHub and the dialog must not freeze the menu bar.
        threading.Thread(target=self.show_info, name="tray-info", daemon=True).start()

    def show_info(self) -> None:
        updates, choose = self._updates, self._choose
        if updates is None or choose is None:
            return
        lines = ["CleverSwitch", self._s.info_installed.format(version=updates.current_version)]
        release = None
        try:
            release = updates.latest()
        except UpdateError as e:
            log.warning(f"Update check failed: {e}")
            lines.append(self._s.info_check_failed.format(error=e))
        buttons = [self._s.button_repo, self._s.button_close]
        if release is not None:
            lines.append(self._s.info_latest.format(version=release.version.removeprefix("v")))
            if not is_newer(release.version, updates.current_version):
                lines.append(self._s.info_up_to_date)
            elif updates.can_update():
                buttons.append(self._s.button_update)
                if updates.system == "Darwin":
                    lines.append(self._s.info_update_hint_mac)
            else:
                lines.append(self._s.info_source_build)
        answer = choose("CleverSwitch", "\n".join(lines), buttons)
        if answer == self._s.button_repo:
            self._desktop.open_url(REPO_URL)
        elif answer == self._s.button_update and release is not None:
            self.update(release)

    def update(self, release) -> None:
        updates, choose = self._updates, self._choose
        if updates is None or choose is None:
            return
        log.info(f"Updating from {updates.current_version} to {release.version}")
        try:
            updates.install(release)
        except UpdateError as e:
            log.error(f"Update failed: {e}")
            choose("CleverSwitch", self._s.update_failed.format(error=e), ["OK"])
            return
        if updates.system == "Darwin":
            choose("CleverSwitch", self._s.update_done_mac, ["OK"])
        # The new copy waits for this process to exit, so the button is given back before it starts.
        updates.restart()
        self._shutdown.set()

    def quit(self) -> None:
        log.info("Quit from the tray menu")
        self._shutdown.set()
