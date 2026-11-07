#!/usr/bin/env python3
"""Write an output file so a failure never loses the file already there.

The converters (embed.py, svg2pptx.py, export.py) and build_bundle.py write every result
through write_atomic(): the old file stays as it was until the complete new one replaces it.
same_file() is the check a converter runs before it reads its input, so an output given as
the input itself (by any path, symlink or hard link) is refused instead of overwritten.
"""
import os
import stat
import tempfile
from pathlib import Path


def same_file(a: Path, b: Path) -> bool:
    """Whether `a` and `b` name one file: the same (device, inode) when both exist, else the
    same resolved path (symlinks followed)."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return Path(a).resolve() == Path(b).resolve()


def write_atomic(out: Path, data):
    """Write `data` (str as UTF-8, or bytes) to `out` so readers only ever see the old file
    or the complete new one, creating `out`'s directory if needed.

    Each call writes its own temp file beside `out` (same directory, so the rename never
    crosses a filesystem) and renames it over `out`. Concurrent runs therefore never share
    a temp path: the last rename wins and every rename finds its own file. If anything
    fails before the rename, that run's temp file is removed and `out` is left as it was.
    A symlinked `out` is followed, so the file it points at is replaced and the link kept.
    The new file keeps the permission bits of the file it replaces (0644 for a new file).
    """
    out = Path(os.path.realpath(out)) if os.path.islink(out) else Path(out)
    if isinstance(data, str):
        data = data.encode("utf-8")
    try:
        mode = stat.S_IMODE(out.stat().st_mode)
    except FileNotFoundError:
        mode = 0o644  # mkstemp creates 0600; an output is an ordinary readable file
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
