#!/usr/bin/env python3
"""Checks the converters run on their outputs before writing, and the write itself.

The converters (embed.py, svg2pptx.py, export.py, render_pptx.py) build every result in
memory first and check every output path, so a run that fails — a bad draft, a clash, an
output that is the input or may not be written — writes nothing and leaves the files
already there as they were. Only then is each result written with a plain open(): new
files get 0666 less the umask, an existing file keeps its mode, owner and links (it is
written in place), and names, folders and permissions behave exactly as for open().

  same_file()  an output that is the input itself (by any path, symlink or hard link)
  blocked()    outputs open() could not write: an existing file this process may not
               write (chmod 444, or a link to one), a folder, or a new file whose folder
               (the nearest one that exists) may not be written
  write()      create the output's folders, then write the bytes with open(path, "wb")
"""
import os
from pathlib import Path


def same_file(a: Path, b: Path) -> bool:
    """Whether `a` and `b` name one file: the same (device, inode) when both exist, else the
    same resolved path (symlinks followed)."""
    try:
        return os.path.samefile(a, b)
    except OSError:
        return Path(a).resolve() == Path(b).resolve()


def blocked(paths) -> list:
    """[(path, reason)] for each path in `paths` that open(path, "wb") could not write, in
    order, so a run can refuse before writing any of them. A symlink counts as the file it
    points at (a dangling one as the new file open() would create there). An existing file
    needs write permission on itself only, not on its folder; a new file needs its folder,
    or the nearest folder above it that exists (the ones below are created), to be
    writable and searchable."""
    found = []
    for p in paths:
        real = Path(os.path.realpath(p))
        if real.is_dir():
            found.append((Path(p), "is a folder"))
        elif real.exists():
            if not os.access(real, os.W_OK):
                found.append((Path(p), "exists and is not writable"))
        else:
            up = real.parent
            while not up.exists() and up != up.parent:
                up = up.parent
            if not up.is_dir():
                found.append((Path(p), f"cannot be created: {up} is not a folder"))
            elif not os.access(up, os.W_OK | os.X_OK):
                found.append((Path(p), f"cannot be created: the folder {up} is not writable"))
    return found


def write(out: Path, data):
    """Write `data` (str as UTF-8, or bytes) to `out` with a plain open(), creating `out`'s
    folders first (for a symlink, the folders of the file it points at). Run blocked() on
    every output of a run before the first write."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    Path(os.path.realpath(out)).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as f:
        f.write(data)
