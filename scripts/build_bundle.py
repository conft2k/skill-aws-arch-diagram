#!/usr/bin/env python3
"""Pack an extracted AWS Architecture Icons package into assets/icons.json.

fetch_icons.py downloads the pinned package and calls build(); run this directly only
to pack a package folder you extracted yourself:

    python scripts/build_bundle.py <extracted-package-dir> <package-name>

Sets built from the package (64px service/category, 48px resource, 32px group):
  service   Arch_<Name>_64.svg              -> service/<Name>
  resource  Res_<Name>_48.svg               -> resource/<Name>
            Res_<Name>_48_Light.svg         -> resource/<Name>        (general icons)
            Res_<Name>_48_Dark.svg          -> resource/<Name>_Dark
  group     <Name>_32[_Dark].svg            -> group/<Name>_32[_Dark]
  category  Arch-Category_<Name>_64.svg     -> category/<Name>
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from outfile import write_atomic  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "icons.json"


def svg(path: Path):
    return {"type": "svg", "data": path.read_text(encoding="utf-8")}


def collect(pkg: Path, pattern: str, rename):
    entries = {}
    for p in sorted(pkg.glob(pattern)):
        if "__MACOSX" in p.parts:
            continue
        name = rename(p.stem)
        if name:
            entries.setdefault(name, svg(p))
    return entries


def resource_name(stem: str):
    m = re.fullmatch(r"Res_(.+)_48(?:_(Light|Dark))?", stem)
    if not m:
        return None
    return m.group(1) + ("_Dark" if m.group(2) == "Dark" else "")


def build(pkg: Path, package: str):
    """Pack the extracted package at `pkg` into icons.json, labelled with `package`."""
    sets = {
        "service": collect(pkg, "Architecture-Service-Icons_*/*/64/Arch_*_64.svg",
                           lambda s: s[len("Arch_"):-len("_64")]),
        "resource": collect(pkg, "Resource-Icons_*/**/Res_*.svg", resource_name),
        "group": collect(pkg, "Architecture-Group-Icons_*/*.svg", lambda s: s),
        "category": collect(pkg, "Category-Icons_*/Arch-Category_64/Arch-Category_*_64.svg",
                            lambda s: s[len("Arch-Category_"):-len("_64")]),
    }
    if not sets["service"]:
        sys.exit(f"No service icons found under {pkg} — is it the extracted Icon package?")

    # A failed run never leaves a half-written bundle, and concurrent runs never collide.
    write_atomic(OUT, json.dumps({"version": 3, "package": package, "sets": sets},
                                 ensure_ascii=False))
    for name, entries in sets.items():
        print(f"  {name}: {len(entries)}", file=sys.stderr)
    total = sum(len(v) for v in sets.values())
    print(f"Wrote {OUT} — {total} icons from {package}, {OUT.stat().st_size / 1024 / 1024:.2f} MB",
          file=sys.stderr)


def main():
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    build(Path(sys.argv[1]), sys.argv[2])


if __name__ == "__main__":
    main()
