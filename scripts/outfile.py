#!/usr/bin/env python3
"""Write an output file so a failure never loses the file already there.

The converters (embed.py, svg2pptx.py, export.py) and build_bundle.py write every result
through write_atomic(): the old file stays as it was until the complete new one replaces it.
same_file() is the check a converter runs before it reads its input, so an output given as
the input itself (by any path, symlink or hard link) is refused instead of overwritten.
unwritable() is the check it runs before writing anything, so an existing output the user
may not write (chmod 444) is refused and kept, as a plain open() for writing would.
"""
import errno
import os
import stat
import tempfile
import threading
from pathlib import Path

_umask_lock = threading.Lock()


def same_file(a: Path, b: Path) -> bool:
    """Whether `a` and `b` name one file: the same (device, inode) when both exist, else the
    same resolved path (symlinks followed)."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return Path(a).resolve() == Path(b).resolve()


def unwritable(paths) -> list:
    """The paths in `paths` that already exist (a symlink counts as the file it points at)
    but that this process may not write, in order. A missing path, or a dangling symlink, is
    writable here: whether its directory is writable shows when the file is created."""
    return [Path(p) for p in paths if os.path.exists(p) and not os.access(p, os.W_OK)]


def current_umask() -> int:
    """The process umask, read without changing it where the system allows (Linux 4.7+
    reports it in /proc/self/status), else by setting and restoring it. The fallback is
    serialised with every other caller here, but a thread elsewhere creating a file in that
    instant would see umask 077 and make its file private, never more open."""
    try:
        with open("/proc/self/status", encoding="ascii") as f:
            for line in f:
                if line.startswith("Umask:"):
                    return int(line.split()[1], 8)
    except (OSError, ValueError, IndexError):
        pass
    with _umask_lock:
        mask = os.umask(0o077)
        os.umask(mask)
    return mask


def write_atomic(out: Path, data):
    """Write `data` (str as UTF-8, or bytes) to `out` so readers only ever see the old file
    or the complete new one, creating `out`'s directory if needed.

    Each call writes its own temp file beside `out` (same directory, so the rename never
    crosses a filesystem) and renames it over `out`. Concurrent runs therefore never share
    a temp path: the last rename wins and every rename finds its own file. If anything
    fails before the rename, that run's temp file is removed and `out` is left as it was.
    A symlinked `out` is followed, so the file it points at is replaced and the link kept.
    An existing `out` this process may not write raises PermissionError before any temp
    file is made. The new file keeps the permission bits of the file it replaces; a new
    file gets 0666 less the umask, as open() would give it.
    """
    out = Path(os.path.realpath(out)) if os.path.islink(out) else Path(out)
    if unwritable([out]):
        raise PermissionError(errno.EACCES, os.strerror(errno.EACCES), str(out))
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        mode = stat.S_IMODE(out.stat().st_mode)
    except FileNotFoundError:
        mode = 0o666 & ~current_umask()  # mkstemp creates 0600 whatever the umask
    out.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=out.parent, prefix=f".{out.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, out)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise
