"""The latest release on GitHub and whether it is newer than this build."""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import re
import ssl
import urllib.request
from collections.abc import Callable

log = logging.getLogger(__name__)

REPO = "Beardowings/CleverSwitch"
REPO_URL = f"https://github.com/{REPO}"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAMES = {"Windows": "cleverswitch_windows_x64.zip", "Darwin": "cleverswitch_macOS.tar.gz"}
TIMEOUT_S = 15
_MAC_CA_FILE = "/etc/ssl/cert.pem"

Opener = Callable[..., object]


class UpdateError(Exception):
    """Anything that stops a check or an update; the message is shown to the user as is."""


@dataclasses.dataclass(frozen=True)
class Asset:
    name: str
    url: str
    size: int
    sha256: str | None


@dataclasses.dataclass(frozen=True)
class Release:
    version: str
    page_url: str
    assets: tuple[Asset, ...]

    def asset_for(self, system: str) -> Asset | None:
        name = ASSET_NAMES.get(system)
        return next((asset for asset in self.assets if asset.name == name), None)


def parse_version(text: str) -> tuple[int, int, int] | None:
    """'v1.2.3' or '1.2.3' (a local build's '0.1.dev168' too) → (1, 2, 3); None when it has no X.Y."""
    match = re.match(r"v?(\d+)\.(\d+)(?:\.(\d+))?", text.strip())
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def is_newer(latest: str, current: str) -> bool:
    latest_version = parse_version(latest)
    if latest_version is None:
        return False
    current_version = parse_version(current)
    if current_version is None:
        return True
    if latest_version != current_version:
        return latest_version > current_version
    return "dev" in current  # a test build of the same number is older than the release


def ssl_context(system: str, ca_file_exists: Callable[[str], bool] = os.path.exists) -> ssl.SSLContext:
    """The system's trust store. A frozen macOS build's OpenSSL may know no roots; macOS ships them as a PEM."""
    context = ssl.create_default_context()
    if system == "Darwin" and not context.cert_store_stats().get("x509_ca") and ca_file_exists(_MAC_CA_FILE):
        context.load_verify_locations(_MAC_CA_FILE)
    return context


def open_url(url: str, system: str, opener: Opener = urllib.request.urlopen, accept: str = "*/*"):
    """GET through the system proxy settings (urllib reads them on Windows and macOS)."""
    request = urllib.request.Request(url, headers={"Accept": accept, "User-Agent": "CleverSwitch-updater"})
    try:
        return opener(request, timeout=TIMEOUT_S, context=ssl_context(system))
    except OSError as e:  # URLError, HTTPError, timeouts and TLS failures are all OSErrors
        raise UpdateError(f"GitHub not reachable: {getattr(e, 'reason', e)}") from e


def fetch_latest(system: str, opener: Opener = urllib.request.urlopen) -> Release:
    with open_url(LATEST_URL, system, opener, accept="application/vnd.github+json") as response:
        try:
            data = json.loads(response.read())
            assets = tuple(_asset(item) for item in data.get("assets", []))
            return Release(version=data["tag_name"], page_url=data.get("html_url", REPO_URL), assets=assets)
        except (ValueError, KeyError, TypeError) as e:
            raise UpdateError(f"Unexpected answer from GitHub: {e}") from e


def _asset(item: dict) -> Asset:
    digest = item.get("digest") or ""
    sha256 = digest.removeprefix("sha256:").lower() if digest.startswith("sha256:") else None
    return Asset(name=item["name"], url=item["browser_download_url"], size=int(item["size"]), sha256=sha256)
