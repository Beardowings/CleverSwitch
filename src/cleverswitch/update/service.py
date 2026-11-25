"""What the tray's Info window needs from the update package, behind one object."""

from __future__ import annotations

import urllib.request

from .. import __version__
from .installer import Installer
from .release import Opener, Release, fetch_latest


class Updates:
    def __init__(
        self,
        system: str,
        installer: Installer | None = None,
        current_version: str = __version__,
        opener: Opener = urllib.request.urlopen,
    ) -> None:
        self.system = system
        self.current_version = current_version
        self._installer = installer or Installer(system, opener=opener)
        self._opener = opener

    def latest(self) -> Release:
        return fetch_latest(self.system, self._opener)

    def can_update(self) -> bool:
        return self._installer.can_update()

    def install(self, release: Release) -> None:
        self._installer.install(release)

    def restart(self) -> None:
        self._installer.restart()
