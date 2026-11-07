#!/usr/bin/env python3
"""Export layout drafts to SVG, PNG and/or PowerPoint in one step.

    uv run --with python-pptx --with cairosvg python scripts/export.py \\
        a.draft.svg [b.draft.svg ...] [--svg] [--png] [--pptx deck.pptx] \\
        [--out-dir DIR] [--title "Slide A" ...] [--preview]

  --svg          <out-dir>/<name>.svg per draft, every icon inlined (renders anywhere)
  --png          <out-dir>/<name>.png per draft, rendered from that SVG (--png-width px)
  --pptx DECK    one deck, one slide per draft in order, native editable shapes;
                 --title once per slide, --font / --ea-font set the typefaces
  --preview      with --pptx: render each slide back to <deck>-1.png, <deck>-2.png, ...

<name> is the draft's file name without ".draft" and ".svg" (architecture.draft.svg ->
architecture). Every output path is worked out first: if two different drafts would write
the same file (docs/arch.draft.svg and slides/arch.draft.svg, or arch.draft.svg and
arch.svg, all -> <out-dir>/arch.svg), a slide preview would land on a draft's PNG, or an
output would overwrite one of the drafts, the script names the clash, writes nothing and
exits with status 1. Names that differ only in case (Arch.svg, arch.svg) or in Unicode
normalisation (NFC or NFD Korean) count as the same file, as they are on macOS (and, for
case, on Windows); the same draft given twice, by any path or link, is not a clash. Two
outputs that already exist as one file under two names (hard links) are one output too.
An output open() could not write — an existing file that may not be written (chmod 444,
or a link to one), or a new file whose folder may not be written — is named the same way
and nothing is written; an existing file that may be written is fine even in a read-only
folder. These checks need no icons: the official icon bundle is loaded (and downloaded on
first use) only when the drafts are checked. Every draft is checked next — icon refs
(embed.py) and the shared draft subset (svg2pptx.py) — whatever formats are asked for, so
one draft always works for all of them. If any draft fails, nothing is written and the
script exits with status 1. Every result (SVG text, PNG, the deck, its previews) is then
built in memory, and only once all of them are complete is any file written, each with
a plain open(); --out-dir and the deck's directory are created at that point.
"""
import argparse
import os
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import macos_cairo  # noqa: E402,F401  (before cairosvg: finds Homebrew cairo on Apple Silicon)
import cairosvg  # noqa: E402
import embed  # noqa: E402
import render_pptx  # noqa: E402
import svg2pptx  # noqa: E402
from outfile import blocked, write  # noqa: E402


def stem(path: Path) -> str:
    name = path.name
    for suffix in (".svg", ".draft"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def path_key(path: Path) -> str:
    """Where `path` lands, case-folded and Unicode-normalised: macOS APFS (and Windows) is
    case-insensitive, so Arch.svg and arch.svg are one file, and APFS also treats the NFC and
    NFD spellings of a name (a precomposed 아 or its decomposed jamo) as one file, so they are
    compared as one everywhere. NFC is applied before and after casefold(), which can
    leave a string unnormalised."""
    s = unicodedata.normalize("NFC", os.path.normcase(str(path.resolve())))
    return unicodedata.normalize("NFC", s.casefold())


def file_id(path: Path):
    """(device, inode) of an existing file, else None: the same file under two names."""
    try:
        st = path.stat()
    except OSError:
        return None
    return st.st_dev, st.st_ino


def draft_source(path: Path):
    """Identity of a draft's contents: its file (any path, case or link to it), else its key."""
    return file_id(path) or path_key(path)


def planned_outputs(drafts, svg, png, out_dir, pptx, preview):
    """[(output path, source, label)] for every file the export would write. `source` says
    which bytes go there (a draft's identity and format, the deck, or a slide preview),
    `label` names it."""
    plan = []
    for d in drafts:
        for on, ext in ((svg, "svg"), (png, "png")):
            if on:
                plan.append((out_dir / f"{stem(d)}.{ext}", (draft_source(d), ext), str(d)))
    if pptx:
        plan.append((pptx, "deck", "--pptx"))
        if preview:
            plan += [(out, f"slide {i}", f"--preview slide {i}") for i, out in
                     enumerate(render_pptx.preview_paths(pptx.with_suffix(""), len(drafts)), 1)]
    return plan


def clashes(drafts, plan):
    """Error lines for every output written from two different sources or landing on a draft.
    Two outputs are one file when their paths match case-folded and NFC-normalised (see
    path_key) or, for outputs that already exist, when they are one file under two names (a
    hard link); the same draft given twice writes identical bytes, so that alone is not a
    clash."""
    parent = list(range(len(plan)))  # union-find: plan entries that land on one file

    def root(n):
        while parent[n] != n:
            n = parent[n]
        return n

    seen = {}
    for n, (out, _, _) in enumerate(plan):
        for key in (path_key(out), file_id(out)):  # a str, and a (dev, inode) tuple or None
            if key is None:
                continue
            if key in seen:
                a, b = root(n), root(seen[key])
                parent[max(a, b)] = min(a, b)
            else:
                seen[key] = n
    groups = {}
    for n, (out, source, label) in enumerate(plan):
        first, sources, keys = groups.setdefault(root(n), (out, {}, set()))
        sources.setdefault(source, label if out == first else f"{label} (as {out})")
        keys.add(path_key(out))
    lines, overwritten = [], set()
    for out, sources, keys in groups.values():
        if len(sources) > 1:  # outputs under different names are one file only by a link
            lines.append(f"{out} would be written from each of"
                         + (" (hard links to one file):" if len(keys) > 1 else ":"))
            lines += [f"  {label}" for label in sources.values()]
    by_key = {path_key(d): d for d in drafts}
    by_file = {i: d for d in drafts if (i := file_id(d))}
    for out, _, _ in plan:  # an existing output may be a draft under another name (hard link)
        hit = by_key.get(path_key(out)) or by_file.get(file_id(out))
        if hit and path_key(out) not in overwritten:
            overwritten.add(path_key(out))
            lines.append(f"{out} would overwrite the draft {hit}")
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("drafts", nargs="+", type=Path, help="layout SVG drafts with bundle: icon refs")
    ap.add_argument("--svg", action="store_true", help="write a portable SVG per draft")
    ap.add_argument("--png", action="store_true", help="write a PNG per draft")
    ap.add_argument("--png-width", type=int, default=2000, help="PNG width in px (default 2000)")
    ap.add_argument("--pptx", type=Path, help="write one deck, one slide per draft")
    ap.add_argument("--title", action="append", default=[], help="slide title; repeat per slide")
    ap.add_argument("--font", default="Arial", help="slide Latin typeface (default Arial)")
    ap.add_argument("--ea-font", default="Malgun Gothic", help="slide Korean typeface (default Malgun Gothic)")
    ap.add_argument("--preview", action="store_true", help="render the deck's slides to PNG")
    ap.add_argument("--out-dir", type=Path, default=Path("."), help="where SVG/PNG files go (default .)")
    a = ap.parse_args()
    if not (a.svg or a.png or a.pptx):
        ap.error("pick at least one of --svg, --png, --pptx")
    if len(a.title) > len(a.drafts):
        ap.error("more --title values than drafts")

    # check everything before writing anything: output paths first, then the drafts
    plan = planned_outputs(a.drafts, a.svg, a.png, a.out_dir, a.pptx, a.preview)
    problems = clashes(a.drafts, plan)
    if problems:
        print("Output name clash:")
        print("\n".join(f"  {p}" for p in problems))
        sys.exit("Nothing written; rename a draft or the deck, or use a separate --out-dir.")
    refused = blocked(dict.fromkeys(out for out, _, _ in plan))
    if refused:
        print("Output not writable:")
        print("\n".join(f"  {path} {why}" for path, why in refused))
        sys.exit("Nothing written; make the file(s) writable or write somewhere else.")

    embedded, failed = {}, False
    for d in a.drafts:
        out, _, report = embed.embed(d.read_text(encoding="utf-8"))
        _, _, problems = svg2pptx.collect(ET.parse(d).getroot())
        report += [f"  {p}" for p in dict.fromkeys(problems)]
        if report:
            failed = True
            print(f"{d}:")
            print("\n".join(report))
        embedded[d] = out
    if failed:
        sys.exit("Nothing written; fix the draft(s) above and re-run.")

    # build every result in memory, so a conversion that fails writes nothing at all
    results = []  # [(path, bytes or str, line printed once written)] in writing order
    for d in a.drafts:
        if a.svg:
            out = a.out_dir / f"{stem(d)}.svg"
            results.append((out, embedded[d], out))
        if a.png:
            out = a.out_dir / f"{stem(d)}.png"
            png = cairosvg.svg2png(bytestring=embedded[d].encode("utf-8"), output_width=a.png_width)
            results.append((out, png, out))
    if a.pptx:
        deck = svg2pptx.convert(a.drafts, a.title, a.font, a.ea_font)
        if deck is None:
            sys.exit("Nothing written; fix the draft(s) above and re-run.")
        data, summary = deck
        results.append((a.pptx, data, f"Wrote {summary} -> {a.pptx}"))
        if a.preview:
            images = render_pptx.pngs(data)
            outs = render_pptx.preview_paths(a.pptx.with_suffix(""), len(images))
            results += [(out, image, out) for out, image in zip(outs, images)]

    # each write creates its file's directory (--out-dir, the deck's)
    for out, data, line in results:
        write(out, data)
        print(line)


if __name__ == "__main__":
    main()
