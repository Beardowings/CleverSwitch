"""Starts the tray icon on the main thread while discovery runs on its own thread."""

from __future__ import annotations

import logging
import threading

from ..model.context.app_context import AppContext
from .autostart import create_autostart
from .controller import TrayController
from .desktop import Desktop, ask_text_mac
from .strings import detect_language, strings_for

log = logging.getLogger(__name__)

SUPPORTED_SYSTEMS = frozenset({"Windows", "Darwin"})


def tray_supported(system: str) -> bool:
    return system in SUPPORTED_SYSTEMS


def build_controller(context: AppContext, system: str) -> TrayController:
    logging_config = context.config.logging
    log_dir = logging_config.file_path.parent if logging_config.file_enabled else None
    if system == "Darwin":
        ask_text = ask_text_mac
    else:
        from .desktop import ask_text_windows

        ask_text = ask_text_windows
    return TrayController(
        settings=context.settings,
        shutdown=context.shutdown,
        strings=strings_for(detect_language()),
        desktop=Desktop(system),
        autostart=create_autostart(system),
        ask_text=ask_text,
        log_dir=log_dir,
    )


def run_tray(context: AppContext, discovery_thread: threading.Thread, system: str) -> bool:
    """Runs the icon until discovery ends (Quit, a signal, or a failure). False if no icon could be shown."""
    if context.settings is None or not tray_supported(system):
        return False
    try:
        from .pystray_tray import PystrayTray
    except Exception as e:  # pystray, Pillow or the platform backend missing
        log.warning(f"No tray icon ({e}); running without one")
        return False

    controller = build_controller(context, system)
    strings = strings_for(detect_language())
    try:
        tray = PystrayTray(controller, system, context.shutdown, strings.choose_host_hint)
    except Exception as e:
        log.warning(f"No tray icon ({e}); running without one")
        return False

    def stop_when_discovery_ends() -> None:
        discovery_thread.join()
        tray.stop()

    threading.Thread(target=stop_when_discovery_ends, name="tray-watch", daemon=True).start()
    log.info("Tray icon shown")
    try:
        tray.run()
    finally:
        context.shutdown.set()  # the icon is gone: never leave the daemon running invisibly
    return True
