"""Download a release, check it against GitHub's SHA-256, stage it beside the running copy, restart.

The running copy is never touched while it runs: a frozen build may still read its own files
(the onefile exe its archive, the app its bundle). ``restart()`` hands the swap to a small
detached script that waits until this process has given the mouse button back and exited, moves
the staged copy into place and starts it.
"""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path

from .release import Asset, Opener, Release, UpdateError, open_url

log = logging.getLogger(__name__)

EXE_NAME = "cleverswitch.exe"
APP_NAME = "CleverSwitch.app"
_CHUNK = 1 << 16


def staged_copy(target: Path) -> Path:
    """Where the downloaded version waits, in the target's own folder so the final move is a rename."""
    if target.suffix == ".app":
        return target.with_name(f".{target.stem}-new.app")
    return target.with_name(target.name + ".new")


def old_copy(target: Path) -> Path:
    if target.suffix == ".app":
        return target.with_name(f".{target.stem}-old.app")
    return target.with_name(target.name + ".old")


def download(asset: Asset, directory: Path, system: str, opener: Opener = urllib.request.urlopen) -> Path:
    if not asset.sha256:
        raise UpdateError(f"GitHub lists no SHA-256 for {asset.name}")
    path = directory / asset.name
    digest = hashlib.sha256()
    size = 0
    with open_url(asset.url, system, opener) as response, open(path, "wb") as f:
        while chunk := response.read(_CHUNK):
            digest.update(chunk)
            size += len(chunk)
            f.write(chunk)
    if size != asset.size or digest.hexdigest() != asset.sha256:
        raise UpdateError(f"{asset.name} is damaged (size or SHA-256 does not match)")
    log.info(f"Downloaded {asset.name} ({size} bytes, SHA-256 {asset.sha256})")
    return path


def mac_swap_script(pid: int, target: Path, staged: Path, old: Path) -> str:
    t, s, o = (_sh_quote(str(p)) for p in (target, staged, old))
    return (
        f"while kill -0 {pid} 2>/dev/null; do sleep 0.2; done\n"
        f"rm -rf {o}\n"
        f"if mv {t} {o}; then\n"
        f"  if mv {s} {t}; then rm -rf {o}; else mv {o} {t}; fi\n"
        f"fi\n"
        f"open {t}\n"
    )


def windows_swap_script(pid: int, target: Path, staged: Path, old: Path) -> str:
    t, s, o = (f'"{p}"' for p in (target, staged, old))
    return (
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {pid}" /NH | find "{pid}" >nul && (ping -n 2 127.0.0.1 >nul & goto wait)\r\n'
        f"del /F /Q {o} >nul 2>&1\r\n"
        f"move /Y {t} {o} >nul && (move /Y {s} {t} >nul || move /Y {o} {t} >nul)\r\n"
        f'start "" {t}\r\n'
        f"del /F /Q {o} >nul 2>&1\r\n"
        '(goto) 2>nul & del "%~f0"\r\n'
    )


def _sh_quote(text: str) -> str:
    return "'" + text.replace("'", "'\\''") + "'"


class Installer:
    def __init__(
        self,
        system: str,
        executable: Path | None = None,
        frozen: bool | None = None,
        opener: Opener = urllib.request.urlopen,
        spawn: Callable[..., object] = subprocess.Popen,
        script_dir: Path | None = None,
    ) -> None:
        self._system = system
        self._executable = Path(executable or sys.executable)
        self._frozen = getattr(sys, "frozen", False) if frozen is None else frozen
        self._opener = opener
        self._spawn = spawn
        self._script_dir = script_dir

    def target(self) -> Path | None:
        """The file or bundle an update replaces, or None when this is not a built exe/app."""
        if not self._frozen:
            return None
        if self._system == "Windows":
            return self._executable
        if self._system == "Darwin":
            bundle = self._executable.parents[2] if len(self._executable.parents) > 2 else None
            return bundle if bundle is not None and bundle.suffix == ".app" else None
        return None

    def can_update(self) -> bool:
        return self.target() is not None

    def install(self, release: Release) -> Path:
        """Downloads, checks and stages the release beside the running copy; restart() puts it in place."""
        target = self.target()
        if target is None:
            raise UpdateError("Only the installed exe or app can update itself")
        asset = release.asset_for(self._system)
        if asset is None:
            raise UpdateError(f"Release {release.version} has no download for this system")
        staged = staged_copy(target)
        with tempfile.TemporaryDirectory(prefix="cleverswitch-update-") as tmp:
            archive = download(asset, Path(tmp), self._system, self._opener)
            new = self._unpack(archive, Path(tmp) / "unpacked")
            try:
                _remove(staged)
                shutil.move(str(new), str(staged))
            except OSError as e:
                _remove(staged)
                raise UpdateError(f"Cannot write to {target.parent}: {e}") from e
        log.info(f"Staged {release.version} at {staged}")
        return staged

    def _unpack(self, archive: Path, into: Path) -> Path:
        into.mkdir()
        try:
            if self._system == "Windows":
                with zipfile.ZipFile(archive) as zf:
                    member = next((n for n in zf.namelist() if n.rsplit("/", 1)[-1] == EXE_NAME), None)
                    if member is None:
                        raise UpdateError(f"{archive.name} contains no {EXE_NAME}")
                    new = into / EXE_NAME
                    with zf.open(member) as src, open(new, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    return new
            with tarfile.open(archive) as tf:
                tf.extractall(into, filter="data")
        except (OSError, zipfile.BadZipFile, tarfile.TarError) as e:
            raise UpdateError(f"Could not unpack {archive.name}: {e}") from e
        bundle = next((p for p in into.rglob(APP_NAME) if p.is_dir()), None)
        if bundle is None:
            raise UpdateError(f"{archive.name} contains no {APP_NAME}")
        return bundle

    def restart(self, pid: int | None = None) -> None:
        """Starts the swap script; it waits for this process (``pid``) to exit, then starts the new copy."""
        target = self.target()
        if target is None or not staged_copy(target).exists():
            return
        pid = os.getpid() if pid is None else pid
        directory = self._script_dir or Path(tempfile.gettempdir())
        if self._system == "Darwin":
            script = directory / "cleverswitch-update.sh"
            script.write_text(mac_swap_script(pid, target, staged_copy(target), old_copy(target)))
            self._spawn(["/bin/sh", str(script)], start_new_session=True, close_fds=True)
        else:
            script = directory / "cleverswitch-update.cmd"
            script.write_text(windows_swap_script(pid, target, staged_copy(target), old_copy(target)), newline="")
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            self._spawn(["cmd.exe", "/c", str(script)], creationflags=flags, close_fds=True)
        log.info(f"Update script started; the new version replaces {target} once this process exits")


def _remove(path: Path) -> None:
    try:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)
    except OSError as e:
        log.warning(f"Could not remove {path}: {e}")
