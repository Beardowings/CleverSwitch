from unittest.mock import MagicMock

from cleverswitch.update.service import Updates

from .test_release import RELEASE_JSON, opener_for


def test_updates_delegates():
    installer = MagicMock()
    installer.can_update.return_value = True
    updates = Updates("Windows", installer, current_version="1.0.0", opener=opener_for(RELEASE_JSON))
    release = updates.latest()
    assert release.version == "v1.1.0"
    assert updates.can_update()
    updates.install(release)
    installer.install.assert_called_once_with(release)
    updates.restart()
    installer.restart.assert_called_once()


def test_updates_builds_its_own_installer():
    assert Updates("Linux").can_update() is False
