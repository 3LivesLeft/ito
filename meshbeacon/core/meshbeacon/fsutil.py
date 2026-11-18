# SPDX-License-Identifier: Apache-2.0
"""Crash-safe file writing and permission repair."""

from __future__ import annotations

import contextlib
import json
import os
import secrets
import stat
from pathlib import Path
from typing import Any

FILE_MODE = 0o600
DIR_MODE = 0o700
TMP_PREFIX = ".mbtmp-"


def fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic_write(path: Path, data: bytes, mode: int = FILE_MODE) -> None:
    """Write ``data`` to ``path`` so that a crash leaves either the old file or the new one.

    The data goes to a uniquely named temporary file in the same directory, which is fsynced,
    renamed over the target and followed by an fsync of the directory.
    """
    directory = path.parent
    tmp = directory / f"{TMP_PREFIX}{path.name}-{os.getpid()}-{secrets.token_hex(4)}"
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        view = memoryview(data)
        while view:
            written = os.write(fd, view)
            view = view[written:]
        os.fchmod(fd, mode)
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        tmp.unlink(missing_ok=True)
        raise
    os.close(fd)
    os.replace(tmp, path)
    fsync_dir(directory)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write(path, (json.dumps(value, sort_keys=True, indent=2) + "\n").encode())


def read_json(path: Path) -> Any:
    """Return parsed JSON, or None if the file is missing or unreadable/corrupt."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def remove_stale_temp_files(directory: Path) -> int:
    removed = 0
    if directory.is_dir():
        for entry in directory.iterdir():
            if entry.name.startswith(TMP_PREFIX) and entry.is_file():
                entry.unlink(missing_ok=True)
                removed += 1
    return removed


def ensure_dir(path: Path) -> None:
    path.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
    os.chmod(path, DIR_MODE)


def repair_permissions(root: Path) -> None:
    """Make every directory under ``root`` 0700 and every regular file 0600 (symlinks untouched)."""
    if not root.exists():
        return
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        current = Path(dirpath)
        os.chmod(current, DIR_MODE)
        for name in filenames:
            p = current / name
            st = p.lstat()
            if stat.S_ISREG(st.st_mode) and stat.S_IMODE(st.st_mode) != FILE_MODE:
                os.chmod(p, FILE_MODE)
        dirnames[:] = [d for d in dirnames if not (current / d).is_symlink()]


def tree_size(path: Path) -> int:
    total = 0
    if path.is_dir():
        for dirpath, _dirs, files in os.walk(path, followlinks=False):
            for name in files:
                with contextlib.suppress(OSError):
                    total += (Path(dirpath) / name).lstat().st_size
    return total


def clear_directory(path: Path) -> None:
    """Delete the contents of ``path`` (not the directory itself)."""
    if not path.is_dir():
        return
    for dirpath, dirnames, filenames in os.walk(path, topdown=False, followlinks=False):
        for name in filenames:
            (Path(dirpath) / name).unlink(missing_ok=True)
        for name in dirnames:
            p = Path(dirpath) / name
            if p.is_symlink():
                p.unlink(missing_ok=True)
            else:
                p.rmdir()
