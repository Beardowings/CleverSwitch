import io
import json
import ssl
import urllib.error

import pytest

from cleverswitch.update.release import (
    LATEST_URL,
    Asset,
    Release,
    UpdateError,
    fetch_latest,
    is_newer,
    open_url,
    parse_version,
    ssl_context,
)


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def opener_for(payload, seen=None):
    def opener(request, timeout, context):
        if seen is not None:
            seen.append((request, timeout, context))
        return FakeResponse(payload if isinstance(payload, bytes) else json.dumps(payload).encode())

    return opener


RELEASE_JSON = {
    "tag_name": "v1.1.0",
    "html_url": "https://github.com/Beardowings/CleverSwitch/releases/tag/v1.1.0",
    "assets": [
        {
            "name": "cleverswitch_windows_x64.zip",
            "browser_download_url": "https://example/win.zip",
            "size": 10,
            "digest": "sha256:ABCD",
        },
        {"name": "cleverswitch_macOS.tar.gz", "browser_download_url": "https://example/mac.tgz", "size": 20},
    ],
}


@pytest.mark.parametrize(
    "text, expected",
    [("v1.2.3", (1, 2, 3)), ("1.0.0", (1, 0, 0)), ("0.1.dev168", (0, 1, 0)), ("1.1", (1, 1, 0)), ("dev", None)],
)
def test_parse_version(text, expected):
    assert parse_version(text) == expected


@pytest.mark.parametrize(
    "latest, current, newer",
    [
        ("v1.1.0", "1.0.0", True),
        ("v1.0.0", "1.0.0", False),
        ("v1.0.0", "1.1.0", False),
        ("v1.0.0", "1.0.0.dev3", True),
        ("v1.0.0", "0.0.0+unknown", True),
        ("v1.0.0", "unknown", True),
        ("nightly", "1.0.0", False),
    ],
)
def test_is_newer(latest, current, newer):
    assert is_newer(latest, current) is newer


def test_fetch_latest_parses_release_and_digests():
    seen = []
    release = fetch_latest("Windows", opener_for(RELEASE_JSON, seen))
    assert release.version == "v1.1.0"
    assert release.asset_for("Windows") == Asset("cleverswitch_windows_x64.zip", "https://example/win.zip", 10, "abcd")
    assert release.asset_for("Darwin").sha256 is None
    assert release.asset_for("Linux") is None
    request, timeout, context = seen[0]
    assert request.full_url == LATEST_URL
    assert request.get_header("User-agent") == "CleverSwitch-updater"
    assert timeout > 0 and isinstance(context, ssl.SSLContext)


@pytest.mark.parametrize("payload", [b"not json", {"assets": []}, {"tag_name": "v1", "assets": [{"name": "x"}]}])
def test_fetch_latest_rejects_odd_answers(payload):
    with pytest.raises(UpdateError, match="Unexpected answer"):
        fetch_latest("Windows", opener_for(payload))


def test_network_failure_becomes_update_error():
    def offline(request, timeout, context):
        raise urllib.error.URLError("proxy refused")

    with pytest.raises(UpdateError, match="proxy refused"):
        open_url("https://x", "Windows", offline)


def test_mac_context_falls_back_to_system_pem(monkeypatch):
    loaded = []

    class Context:
        def cert_store_stats(self):
            return {"x509_ca": 0}

        def load_verify_locations(self, path):
            loaded.append(path)

    monkeypatch.setattr(ssl, "create_default_context", Context)
    ssl_context("Darwin", ca_file_exists=lambda path: True)
    assert loaded == ["/etc/ssl/cert.pem"]
    ssl_context("Windows", ca_file_exists=lambda path: True)
    assert loaded == ["/etc/ssl/cert.pem"]  # Windows uses its own store


def test_release_without_matching_asset():
    assert Release("v1", "u", ()).asset_for("Windows") is None
