#!/usr/bin/env python3
"""Inline bundled icons into an SVG, producing a portable standalone file.

In your draft SVG, reference icons from the bundle with the `bundle:` scheme:

    <image href="bundle:service/AWS-Lambda"  x="200" y="200" width="48" height="48"/>
    <image href="bundle:group/AWS-Cloud-logo_32"  x="20"  y="20"  width="32" height="32"/>

Then:  python scripts/embed.py draft.svg final.svg

The reverse, to start a draft from an exported diagram such as a reference example:

    python scripts/embed.py --unembed docs/examples/alb-reference-architecture.svg arch.draft.svg

turns every inlined official icon back into its bundle: ref (a ~100 KB export becomes a
~10 KB draft whose <image> lines show x/y). An inlined image that is not a bundled
icon is reported and nothing is written.

Each bundle: ref is replaced with a data: URI pulled from assets/icons.json,
so the final SVG renders anywhere with no external files. The output is written
only when every icon resolves: refs that don't resolve, image hrefs that point at
external files or URLs, and refs to the logo-less AWS Cloud outline (the badge
must carry the AWS logo) are reported instead,
nothing is written, and the script exits with status 1. A file already at the output
path is left as it was then: the result is built in memory and written only once it is
complete. An output that is the input itself (by any path or link), or one open() could
not write (a read-only file, or a new file in a folder that may not be written), is
refused the same way.
"""
import base64
import re
import sys
from functools import cache
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_icons import load_sets  # noqa: E402
from outfile import blocked, same_file, write  # noqa: E402


@cache
def icon_sets():
    """The icon sets, loaded on the first icon lookup (downloading the official AWS icons if
    the bundle isn't built yet), not at import: export.py's checks and --help stay offline."""
    return load_sets()


# Attribute values may be single- or double-quoted; group 1 is the quote.
REF_RE = re.compile(r'(?:xlink:)?href\s*=\s*(["\'])bundle:([^"\']+)\1')
# The AWS Cloud container always carries the AWS logo; these are the logo-less outlines.
REPLACED = {"group/AWS-Cloud_32": "group/AWS-Cloud-logo_32",
            "group/AWS-Cloud_32_Dark": "group/AWS-Cloud-logo_32_Dark"}
# Group containers are square-cornered in the official style; a rounded rect with a
# group badge pinned to its top-left corner leaves the badge's corner sticking out.
RECT_RE = re.compile(r'<rect\b[^>]*>')
GROUP_IMG_RE = re.compile(r'<image\b[^>]*?href\s*=\s*(["\'])bundle:group/[^"\']+\1[^>]*>')


def attr(tag: str, name: str):
    m = re.search(rf'\b{name}\s*=\s*["\']([^"\']*)["\']', tag)
    return m.group(1) if m else None


def rounded_groups(svg: str):
    """(x, y) of rounded rects whose top-left corner holds a group badge."""
    badges = {(attr(m.group(0), "x"), attr(m.group(0), "y")) for m in GROUP_IMG_RE.finditer(svg)}
    out = []
    for m in RECT_RE.finditer(svg):
        tag = m.group(0)
        r = attr(tag, "rx") or attr(tag, "ry")
        if r and float(r) > 0 and (attr(tag, "x"), attr(tag, "y")) in badges:
            out.append((attr(tag, "x"), attr(tag, "y")))
    return out


# <image> hrefs that would still need a file or network fetch after embedding.
EXTERNAL_RE = re.compile(
    r'<image\b[^>]*?(?:xlink:)?href\s*=\s*(["\'])(?!data:|bundle:|#)([^"\']+)\1')


def data_uri(setname: str, name: str):
    entry = icon_sets().get(setname, {}).get(name)
    if entry is None:
        return None
    if entry["type"] == "svg":
        b64 = base64.b64encode(entry["data"].encode("utf-8")).decode("ascii")
        return f"data:image/svg+xml;base64,{b64}"
    return f"data:image/png;base64,{entry['data']}"


def embed(svg: str):
    """Inline every bundle: ref. Returns (embedded SVG or None, icon count, problem lines)."""
    missing, replaced, embedded = [], [], 0

    def repl(m):
        nonlocal embedded
        ref = m.group(2)
        if ref in REPLACED:
            replaced.append(ref)
            return m.group(0)
        setname, _, name = ref.partition("/")
        uri = data_uri(setname, name)
        if uri is None:
            missing.append(ref)
            return m.group(0)
        embedded += 1
        return m.group(0).replace(f"bundle:{ref}", uri)

    out = REF_RE.sub(repl, svg)
    report = []
    if missing:
        report.append("MISSING (fix these refs — check names with find_icon.py):")
        report += [f"  bundle:{r}" for r in missing]
    external = [m.group(2) for m in EXTERNAL_RE.finditer(out)]
    if external:
        report.append("EXTERNAL (won't render standalone — switch to bundle: refs):")
        report += [f"  {r}" for r in external]
    if replaced:
        report.append("NO AWS LOGO (the AWS Cloud badge must include the AWS logo):")
        report += [f"  bundle:{r} -> use bundle:{REPLACED[r]}" for r in replaced]
    rounded = rounded_groups(svg)
    if rounded:
        report.append("ROUNDED GROUP (group containers are square-cornered — drop rx/ry):")
        report += [f"  <rect x=\"{x}\" y=\"{y}\" ...> carries a group badge" for x, y in rounded]
    return (None if report else out), embedded, report


DATA_RE = re.compile(r'((?:xlink:)?href\s*=\s*)(["\'])data:image/(svg\+xml|png);base64,([^"\']*)\2')


def unembed(svg: str):
    """Turn inlined bundle icons back into bundle: refs. Returns (SVG or None, count, problems)."""
    ref = {e["data"]: f"{s}/{n}" for s, icons in icon_sets().items() for n, e in icons.items()}
    unknown, count = [], 0

    def back(m):
        nonlocal count
        prefix, q, kind, b64 = m.groups()
        key = base64.b64decode(b64).decode("utf-8") if kind == "svg+xml" else b64
        if key not in ref:
            unknown.append(f"{kind} image ({len(b64)} base64 chars)")
            return m.group(0)
        count += 1
        return f"{prefix}{q}bundle:{ref[key]}{q}"

    out = DATA_RE.sub(back, svg)
    report = ["UNKNOWN (inlined image that is not a bundled icon):"] + [f"  {u}" for u in unknown] if unknown else []
    return (None if report else out), count, report


def main():
    args = sys.argv[1:]
    reverse = "--unembed" in args
    args = [a for a in args if a != "--unembed"]
    if len(args) != 2:
        print(__doc__)
        sys.exit(1)
    src, dst = Path(args[0]), Path(args[1])
    if same_file(src, dst):
        sys.exit(f"Nothing written: the output {dst} is the input {src}; name a different output.")
    for path, why in blocked([dst]):
        sys.exit(f"Nothing written: the output {path} {why}; "
                 "make it writable or name a different output.")
    if reverse:
        out, n, report = unembed(src.read_text(encoding="utf-8"))
        if report:
            print("\n".join(report))
            sys.exit(f"Nothing written to {dst}.")
        write(dst, out)
        print(f"Restored {n} bundle: ref(s) -> {dst}")
        return
    out, embedded, report = embed(src.read_text(encoding="utf-8"))
    if report:
        print("\n".join(report))
        sys.exit(f"Nothing written to {dst}; fix the refs above and re-run.")
    write(dst, out)
    print(f"Embedded {embedded} icon(s) -> {dst}")


if __name__ == "__main__":
    main()
