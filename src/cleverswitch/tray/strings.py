"""User-facing menu texts, German or English after the system language."""

from __future__ import annotations

import dataclasses
import locale
import os
from collections.abc import Callable


@dataclasses.dataclass(frozen=True)
class Strings:
    status_on: str  # {button}, {host}
    status_no_host: str  # {button}
    status_off: str
    enabled: str
    target_host: str
    name_hosts: str
    host_default: str  # {n}
    rename_title: str
    rename_prompt: str  # {n}
    button: str
    buttons: dict[str, str]
    open_options_plus: str
    options_plus_missing: str
    autostart: str
    advanced: str
    follow_keyboard: str
    divert: str
    open_config: str
    open_logs: str
    quit: str
    choose_host_hint: str
    info: str
    info_installed: str  # {version}
    info_latest: str  # {version}
    info_up_to_date: str
    info_check_failed: str  # {error}
    info_source_build: str
    info_update_hint_mac: str
    button_update: str
    button_repo: str
    button_close: str
    update_failed: str  # {error}
    update_done_mac: str


GERMAN = Strings(
    status_on="{button} → {host}",
    status_no_host="{button}: Zielkanal wählen",
    status_off="Umschalten per Maustaste ist aus",
    enabled="Umschalten per Maustaste",
    target_host="Zielkanal",
    name_hosts="Kanäle benennen",
    host_default="Kanal {n}",
    rename_title="CleverSwitch",
    rename_prompt="Name für Kanal {n} (leer = kein Name):",
    button="Taste",
    buttons={
        "gesture": "Daumentaste",
        "forward": "Vor-Taste",
        "back": "Zurück-Taste",
        "middle": "Mittlere Taste",
        "smartshift": "SmartShift-Taste",
    },
    open_options_plus="Logi Options+ öffnen",
    options_plus_missing="Logi Options+ nicht gefunden",
    autostart="Bei Anmeldung starten",
    advanced="Erweitert",
    follow_keyboard="Maus folgt den Easy-Switch-Tasten der Tastatur",
    divert="Taste selbst umleiten",
    open_config="Konfigurationsdatei öffnen",
    open_logs="Log-Ordner öffnen",
    quit="CleverSwitch beenden",
    choose_host_hint="Bitte im CleverSwitch-Menü den Zielkanal wählen.",
    info="Info …",
    info_installed="Installiert: {version}",
    info_latest="Neueste Version: {version}",
    info_up_to_date="Du hast die neueste Version.",
    info_check_failed="Neueste Version konnte nicht geprüft werden ({error}).",
    info_source_build="Diese Kopie läuft aus dem Quellcode und kann sich nicht selbst aktualisieren.",
    info_update_hint_mac="Nach dem Update fragt macOS eventuell erneut nach der Eingabeüberwachung.",
    button_update="Aktualisieren",
    button_repo="GitHub öffnen",
    button_close="Schließen",
    update_failed="Das Update hat nicht geklappt: {error}",
    update_done_mac=(
        "Das Update ist installiert. CleverSwitch startet jetzt neu.\n\n"
        "Tut die Maustaste danach nichts: unter Systemeinstellungen → Datenschutz & Sicherheit → "
        "Eingabeüberwachung CleverSwitch entfernen, /Applications/CleverSwitch.app neu hinzufügen "
        "und die App neu öffnen."
    ),
)

ENGLISH = Strings(
    status_on="{button} → {host}",
    status_no_host="{button}: choose a target channel",
    status_off="Mouse button switch is off",
    enabled="Switch with mouse button",
    target_host="Target channel",
    name_hosts="Name channels",
    host_default="Channel {n}",
    rename_title="CleverSwitch",
    rename_prompt="Name for channel {n} (empty = no name):",
    button="Button",
    buttons={
        "gesture": "Thumb button",
        "forward": "Forward button",
        "back": "Back button",
        "middle": "Middle button",
        "smartshift": "SmartShift button",
    },
    open_options_plus="Open Logi Options+",
    options_plus_missing="Logi Options+ not found",
    autostart="Start at login",
    advanced="Advanced",
    follow_keyboard="Mouse follows the keyboard's Easy-Switch keys",
    divert="Divert the button myself",
    open_config="Open config file",
    open_logs="Open log folder",
    quit="Quit CleverSwitch",
    choose_host_hint="Please choose the target channel in the CleverSwitch menu.",
    info="About …",
    info_installed="Installed: {version}",
    info_latest="Latest version: {version}",
    info_up_to_date="You have the latest version.",
    info_check_failed="Could not check for the latest version ({error}).",
    info_source_build="This copy runs from source and cannot update itself.",
    info_update_hint_mac="After the update macOS may ask for Input Monitoring again.",
    button_update="Update",
    button_repo="Open GitHub",
    button_close="Close",
    update_failed="The update did not work: {error}",
    update_done_mac=(
        "The update is installed. CleverSwitch restarts now.\n\n"
        "If the mouse button does nothing afterwards: remove CleverSwitch under System Settings → "
        "Privacy & Security → Input Monitoring, add /Applications/CleverSwitch.app again and reopen it."
    ),
)


def strings_for(language: str | None) -> Strings:
    # POSIX/macOS give "de_DE" or "de-DE"; Windows' locale.getlocale() gives "German_Germany".
    code = (language or "").lower()
    return GERMAN if code.startswith("de") or code.startswith("german") else ENGLISH


def detect_language(
    environ: dict[str, str] | None = None,
    system_language: Callable[[], str | None] | None = None,
) -> str | None:
    """The user's language code, e.g. ``de_DE``; None when nothing says."""
    env = os.environ if environ is None else environ
    for key in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = env.get(key)
        if value and value not in ("C", "POSIX", "C.UTF-8"):
            return value
    lookup = system_language or _system_language
    try:
        return lookup()
    except Exception:
        return None


def _system_language() -> str | None:  # pragma: no cover - OS lookup
    try:
        from Foundation import NSLocale  # macOS app bundles get no LANG

        languages = NSLocale.preferredLanguages()
        if languages:
            return str(languages[0])
    except ImportError:
        pass
    return locale.getlocale()[0]
