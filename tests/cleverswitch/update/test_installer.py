import hashlib
import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from cleverswitch.update import installer as installer_module
from cleverswitch.update.installer import (
    Installer,
    download,
    mac_swap_script,
    old_copy,
    staged_copy,
    windows_swap_script,
)
from cleverswitch.update.release import Asset, Release, UpdateError


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def serving(data: bytes):
    return lambda request, timeout, context: FakeResponse(data)


def asset(name, data, sha=None):
    return Asset(name, "https://example/" + name, len(data), sha or hashlib.sha256(data).hexdigest())


def windows_zip(content=b"NEW EXE"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cleverswitch.exe", content)
        zf.writestr("README.md", "x")
    return buf.getvalue()


def mac_tgz(tmp_path, content=b"NEW APP"):
    src = tmp_path / "src" / "cleverswitch_macOS" / "CleverSwitch.app" / "Contents" / "MacOS"
    src.mkdir(parents=True)
    (src / "CleverSwitch").write_bytes(content)
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.add(tmp_path / "src" / "cleverswitch_macOS", arcname="cleverswitch_macOS")
    return buf.getvalue()


def test_copy_names():
    assert staged_copy(Path("/a/cleverswitch.exe")) == Path("/a/cleverswitch.exe.new")
    assert old_copy(Path("/a/cleverswitch.exe")) == Path("/a/cleverswitch.exe.old")
    assert staged_copy(Path("/Applications/CleverSwitch.app")) == Path("/Applications/.CleverSwitch-new.app")
    assert old_copy(Path("/Applications/CleverSwitch.app")) == Path("/Applications/.CleverSwitch-old.app")


def test_download_checks_size_and_hash(tmp_path):
    data = b"payload"
    good = asset("a.zip", data)
    assert download(good, tmp_path, "Windows", serving(data)).read_bytes() == data
    with pytest.raises(UpdateError, match="damaged"):
        download(asset("a.zip", data, sha="0" * 64), tmp_path, "Windows", serving(data))
    with pytest.raises(UpdateError, match="no SHA-256"):
        download(Asset("a.zip", "u", 1, None), tmp_path, "Windows", serving(data))


def test_target_per_platform():
    assert Installer("Windows", Path("C:/x/cleverswitch.exe"), frozen=False).target() is None
    assert Installer("Windows", Path("/x/cleverswitch.exe"), frozen=True).target() == Path("/x/cleverswitch.exe")
    app_exe = Path("/Applications/CleverSwitch.app/Contents/MacOS/CleverSwitch")
    assert Installer("Darwin", app_exe, frozen=True).target() == Path("/Applications/CleverSwitch.app")
    assert Installer("Darwin", Path("/usr/local/bin/cleverswitch"), frozen=True).target() is None
    assert Installer("Darwin", Path("/cs"), frozen=True).target() is None
    assert Installer("Linux", Path("/x/cs"), frozen=True).target() is None


def test_windows_install_stages_exe_and_restart_hands_over_to_script(tmp_path):
    exe = tmp_path / "cleverswitch.exe"
    exe.write_bytes(b"OLD EXE")
    data = windows_zip()
    spawned = []
    inst = Installer(
        "Windows",
        exe,
        frozen=True,
        opener=serving(data),
        spawn=lambda *a, **k: spawned.append((a, k)),
        script_dir=tmp_path,
    )
    assert inst.can_update()
    staged = inst.install(Release("v9.0.0", "page", (asset("cleverswitch_windows_x64.zip", data),)))
    assert exe.read_bytes() == b"OLD EXE"  # the running copy is untouched
    assert staged.read_bytes() == b"NEW EXE"
    inst.restart(pid=42)
    (command,), kwargs = spawned[0]
    script = tmp_path / "cleverswitch-update.cmd"
    assert command == ["cmd.exe", "/c", str(script)]
    assert "PID eq 42" in script.read_text()
    assert kwargs["close_fds"] is True


def test_mac_install_stages_bundle_and_restart_hands_over_to_script(tmp_path):
    apps = tmp_path / "Applications"
    binary = apps / "CleverSwitch.app" / "Contents" / "MacOS" / "CleverSwitch"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"OLD APP")
    (apps / ".CleverSwitch-new.app").mkdir()  # left over from an earlier attempt
    data = mac_tgz(tmp_path)
    spawned = []
    inst = Installer(
        "Darwin",
        binary,
        frozen=True,
        opener=serving(data),
        spawn=lambda *a, **k: spawned.append((a, k)),
        script_dir=tmp_path,
    )
    staged = inst.install(Release("v9.0.0", "page", (asset("cleverswitch_macOS.tar.gz", data),)))
    assert (staged / "Contents" / "MacOS" / "CleverSwitch").read_bytes() == b"NEW APP"
    assert binary.read_bytes() == b"OLD APP"
    inst.restart(pid=7)
    (command,), kwargs = spawned[0]
    assert command == ["/bin/sh", str(tmp_path / "cleverswitch-update.sh")]
    assert kwargs["start_new_session"] is True


def test_restart_without_staged_copy_does_nothing(tmp_path):
    spawned = []
    Installer("Windows", tmp_path / "cleverswitch.exe", frozen=True, spawn=spawned.append).restart()
    Installer("Windows", tmp_path / "x.exe", frozen=False, spawn=spawned.append).restart()
    assert spawned == []


def test_mac_swap_script_runs_for_real(tmp_path):
    target, staged, old = tmp_path / "A B.app", tmp_path / ".A B-new.app", tmp_path / ".A B-old.app"
    target.mkdir()
    (target / "v").write_text("old")
    staged.mkdir()
    (staged / "v").write_text("new")
    script = mac_swap_script(2**22 + 12345, target, staged, old).replace("open ", "echo ")
    import subprocess

    subprocess.run(["/bin/sh", "-c", script], check=True, capture_output=True)
    assert (target / "v").read_text() == "new"
    assert not staged.exists() and not old.exists()


def test_windows_swap_script_text():
    text = windows_swap_script(5, Path("C:/p/cleverswitch.exe"), Path("C:/p/cleverswitch.exe.new"), Path("C:/p/x.old"))
    assert text.startswith("@echo off\r\n")
    assert 'move /Y "C:/p/cleverswitch.exe" "C:/p/x.old"' in text
    assert 'start "" "C:/p/cleverswitch.exe"' in text


def test_install_refusals(tmp_path):
    with pytest.raises(UpdateError, match="Only the installed"):
        Installer("Windows", tmp_path / "x.exe", frozen=False).install(Release("v2", "p", ()))
    inst = Installer("Windows", tmp_path / "cleverswitch.exe", frozen=True)
    with pytest.raises(UpdateError, match="no download"):
        inst.install(Release("v2", "p", ()))


def test_archive_without_program(tmp_path):
    exe = tmp_path / "cleverswitch.exe"
    exe.write_bytes(b"OLD")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("README.md", "x")
    data = buf.getvalue()
    inst = Installer("Windows", exe, frozen=True, opener=serving(data))
    with pytest.raises(UpdateError, match="contains no cleverswitch.exe"):
        inst.install(Release("v2", "p", (asset("cleverswitch_windows_x64.zip", data),)))

    bad = b"not a zip"
    inst = Installer("Windows", exe, frozen=True, opener=serving(bad))
    with pytest.raises(UpdateError, match="Could not unpack"):
        inst.install(Release("v2", "p", (asset("cleverswitch_windows_x64.zip", bad),)))

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        tf.addfile(tarfile.TarInfo("readme"), io.BytesIO(b""))
    data = buf.getvalue()
    app = tmp_path / "CleverSwitch.app" / "Contents" / "MacOS" / "CleverSwitch"
    inst = Installer("Darwin", app, frozen=True, opener=serving(data))
    with pytest.raises(UpdateError, match="contains no CleverSwitch.app"):
        inst.install(Release("v2", "p", (asset("cleverswitch_macOS.tar.gz", data),)))


def test_unwritable_folder(tmp_path, monkeypatch, caplog):
    exe = tmp_path / "cleverswitch.exe"
    exe.write_bytes(b"OLD")
    data = windows_zip()
    inst = Installer("Windows", exe, frozen=True, opener=serving(data))

    def denied(src, dst):
        raise PermissionError("read-only")

    monkeypatch.setattr(installer_module.shutil, "move", denied)
    with pytest.raises(UpdateError, match="Cannot write"):
        inst.install(Release("v2", "p", (asset("cleverswitch_windows_x64.zip", data),)))

    def locked(self, missing_ok=False):
        raise PermissionError("in use")

    (tmp_path / "cleverswitch.exe.new").write_bytes(b"stale")
    monkeypatch.setattr(Path, "unlink", locked)
    with pytest.raises(UpdateError):
        inst.install(Release("v2", "p", (asset("cleverswitch_windows_x64.zip", data),)))
    assert "Could not remove" in caplog.text
