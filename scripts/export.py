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
exits with status 1. Every draft is checked next — icon refs (embed.py) and the shared
draft subset (svg2pptx.py) — whatever formats are asked for, so one draft always works for
all of them. If any draft fails, nothing is written and the script exits with status 1.
"""
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import macos_cairo  # noqa: E402,F401  (before cairosvg: finds Homebrew cairo on Apple Silicon)
import cairosvg  # noqa: E402
import embed  # noqa: E402
import render_pptx  # noqa: E402
import svg2pptx  # noqa: E402


def stem(path: Path) -> str:
    name = path.name
    for suffix in (".svg", ".draft"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
    return name


def planned_outputs(drafts, svg, png, out_dir, pptx, preview):
    """[(output path, source, label)] for every file the export would write. `source` says
    which input the bytes come from (a draft's resolved path, or the deck), `label` names it."""
    plan = []
    for d in drafts:
        for on, ext in ((svg, "svg"), (png, "png")):
            if on:
                plan.append((out_dir / f"{stem(d)}.{ext}", d.resolve(), str(d)))
    if pptx:
        plan.append((pptx, "deck", "--pptx"))
        if preview:
            base = pptx.with_suffix("")
            plan += [(base.with_name(f"{base.name}-{i}.png"), f"slide {i}", f"--preview slide {i}")
                     for i in range(1, len(drafts) + 1)]
    return plan


def clashes(drafts, plan):
    """Error lines for every output written from two different sources or landing on a draft.
    The same draft given twice writes identical bytes, so that alone is not a clash."""
    by_path = {}
    for out, source, label in plan:
        by_path.setdefault(out.resolve(), (out, {}))[1].setdefault(source, label)
    inputs = {d.resolve(): d for d in drafts}
    lines = []
    for key, (out, sources) in by_path.items():
        if len(sources) > 1:
            lines.append(f"{out} would be written from each of:")
            lines += [f"  {label}" for label in sources.values()]
        if key in inputs:
            lines.append(f"{out} would overwrite the draft {inputs[key]}")
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
    problems = clashes(a.drafts, planned_outputs(a.drafts, a.svg, a.png, a.out_dir, a.pptx, a.preview))
    if problems:
        print("Output name clash:")
        print("\n".join(f"  {p}" for p in problems))
        sys.exit("Nothing written; give the drafts distinct file names or export them "
                 "with separate --out-dir runs.")

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

    a.out_dir.mkdir(parents=True, exist_ok=True)
    for d in a.drafts:
        svg_text = embedded[d]
        if a.svg:
            out = a.out_dir / f"{stem(d)}.svg"
            out.write_text(svg_text, encoding="utf-8")
            print(out)
        if a.png:
            out = a.out_dir / f"{stem(d)}.png"
            cairosvg.svg2png(bytestring=svg_text.encode("utf-8"), write_to=str(out), output_width=a.png_width)
            print(out)
    if a.pptx:
        if not svg2pptx.build(a.drafts, a.title, a.pptx, a.font, a.ea_font):
            sys.exit(1)
        if a.preview:
            for out in render_pptx.render(a.pptx, a.pptx.with_suffix("")):
                print(out)


if __name__ == "__main__":
    main()
