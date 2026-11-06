#!/usr/bin/env python3
"""Golden run of the example specs (DESIGN 7.2): spec → draft → check → export → compare.

    python3 tests/test_examples.py [name ...] [--keep DIR] [--no-export] [--layout PY] [-v]

For every docs/examples/specs/*.layout.yaml (and specs/slides/*.layout.yaml, compared with
docs/examples/slides/) whose stem matches a name filter (substring; default all):
  yaml     the spec parses (yaml.safe_load)
  orig     the original example unembedded (embed.py --unembed docs/examples/<name>.svg;
           example.layout.yaml ↔ docs/example.svg) and compared with itself
  layout   python3 scripts/layout.py <spec> -o <tmp>/<name>.draft.svg, exit 0; run twice,
           the two drafts must be byte-identical (DESIGN 7.3)
  check    python3 scripts/check_layout.py on the generated draft, exit 0 ("Layout OK")
  export   uv run --with python-pptx --with cairosvg python scripts/export.py --svg --png
           --pptx (into <tmp>/out), exit 0
  struct   tests/compare_structure.py original vs generated: no differences
Prints one row per spec and the failure details below the table. While scripts/layout.py
does not exist the layout/check/export/struct columns read SKIP. Exits 1 if any cell is
FAIL, else 0.
"""
import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
SPECS = ROOT / "docs" / "examples" / "specs"
sys.path.insert(0, str(Path(__file__).resolve().parent))
import compare_structure  # noqa: E402

COLS = ("yaml", "orig", "layout", "check", "export", "struct")


def run(cmd, timeout=300):
    try:
        p = subprocess.run(cmd, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout, universal_newlines=True)
        return p.returncode, p.stdout
    except subprocess.TimeoutExpired:
        return 124, "timeout after %ds: %s" % (timeout, " ".join(map(str, cmd)))


def original_of(spec):
    stem = spec.name[: -len(".layout.yaml")]
    if spec.parent.name == "slides":
        return stem, ROOT / "docs" / "examples" / "slides" / (stem + ".svg")
    if stem == "example":
        return stem, ROOT / "docs" / "example.svg"
    return stem, ROOT / "docs" / "examples" / (stem + ".svg")


def tail(s, n=12):
    lines = [l for l in s.strip().splitlines() if l.strip()]
    return "\n".join(lines[-n:])


def one(spec, tmp, export, verbose, layout):
    stem, orig_svg = original_of(spec)
    key = ("slides/" if spec.parent.name == "slides" else "") + stem
    res = {c: "-" for c in COLS}
    notes = []
    work = tmp / key.replace("/", "_")
    work.mkdir(parents=True, exist_ok=True)

    # yaml
    try:
        import yaml
        yaml.safe_load(spec.read_text(encoding="utf-8"))
        res["yaml"] = "PASS"
    except ImportError:
        res["yaml"] = "SKIP"
        notes.append("yaml: PyYAML not installed")
    except Exception as e:  # noqa: BLE001
        res["yaml"] = "FAIL"
        notes.append("yaml: %s" % e)

    # original draft
    orig = work / (stem + ".orig.draft.svg")
    if not orig_svg.exists():
        res["orig"] = "FAIL"
        notes.append("orig: %s not found" % orig_svg.relative_to(ROOT))
        orig = None
    else:
        rc, out = run([sys.executable, str(SCRIPTS / "embed.py"), "--unembed", str(orig_svg), str(orig)])
        if rc != 0:
            res["orig"] = "FAIL"
            notes.append("orig: embed.py --unembed exit %d\n%s" % (rc, tail(out)))
            orig = None
        else:
            A = compare_structure.Draft(orig)
            d = compare_structure.compare(A, compare_structure.Draft(orig))
            res["orig"] = "PASS" if not d else "FAIL"
            if d:
                notes.append("orig: self-compare found differences (comparator bug):\n" + "\n".join(d))

    # layout
    gen = work / (stem + ".draft.svg")
    if not layout.exists():
        for c in ("layout", "check", "export", "struct"):
            res[c] = "SKIP"
        return key, res, notes
    rc, out = run([sys.executable, str(layout), str(spec), "-o", str(gen)])
    if verbose:
        notes.append("layout output:\n" + out.rstrip())
    if rc != 0 or not gen.exists():
        res["layout"] = "FAIL"
        notes.append("layout: exit %d\n%s" % (rc, tail(out)))
        for c in ("check", "export", "struct"):
            res[c] = "SKIP"
        return key, res, notes
    gen2 = work / (stem + ".again.draft.svg")
    rc2, out2 = run([sys.executable, str(layout), str(spec), "-o", str(gen2)])
    if rc2 == 0 and gen2.exists() and gen2.read_bytes() == gen.read_bytes():
        res["layout"] = "PASS"
    else:
        res["layout"] = "FAIL"
        notes.append("layout: a second run gave a different draft (not deterministic)")

    # check_layout
    rc, out = run([sys.executable, str(SCRIPTS / "check_layout.py"), str(gen)])
    res["check"] = "PASS" if rc == 0 else "FAIL"
    if rc != 0:
        notes.append("check: exit %d\n%s" % (rc, tail(out, 20)))

    # export
    if not export:
        res["export"] = "SKIP"
    elif shutil.which("uv") is None:
        res["export"] = "SKIP"
        notes.append("export: uv not found")
    else:
        outdir = work / "out"
        rc, out = run(["uv", "run", "--with", "python-pptx", "--with", "cairosvg", "python",
                       str(SCRIPTS / "export.py"), str(gen), "--svg", "--png",
                       "--pptx", str(outdir / (stem + ".pptx")), "--out-dir", str(outdir)])
        res["export"] = "PASS" if rc == 0 else "FAIL"
        if rc != 0:
            notes.append("export: exit %d\n%s" % (rc, tail(out)))

    # structure
    if orig is None:
        res["struct"] = "SKIP"
    else:
        d = compare_structure.compare(compare_structure.Draft(orig), compare_structure.Draft(gen))
        res["struct"] = "PASS" if not d else "FAIL(%d)" % len(d)
        if d:
            notes.append("struct: %s vs %s\n%s" % (orig.name, gen.name, "\n".join(d)))
    return key, res, notes


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("names", nargs="*", help="only specs whose stem contains one of these")
    ap.add_argument("--keep", type=Path, help="write drafts and exports here instead of a temp dir")
    ap.add_argument("--no-export", action="store_true", help="skip export.py (faster)")
    ap.add_argument("--layout", type=Path, default=SCRIPTS / "layout.py",
                    help="the engine script to run (default scripts/layout.py; a stand-in for testing this runner)")
    ap.add_argument("-v", "--verbose", action="store_true", help="also print layout.py output")
    a = ap.parse_args(argv)

    specs = sorted(SPECS.glob("*.layout.yaml")) + sorted((SPECS / "slides").glob("*.layout.yaml"))
    if a.names:
        specs = [s for s in specs if any(n in s.name for n in a.names)]
    if not specs:
        print("no specs matched")
        return 1
    if not a.layout.exists():
        print("%s not found: layout, check, export and struct are SKIP\n" % a.layout)

    tmp_ctx = None
    if a.keep:
        tmp = a.keep.resolve()
        tmp.mkdir(parents=True, exist_ok=True)
    else:
        tmp_ctx = tempfile.TemporaryDirectory(prefix="layout-golden-")
        tmp = Path(tmp_ctx.name)
    rows, details = [], []
    try:
        for spec in specs:
            key, res, notes = one(spec, tmp, not a.no_export, a.verbose, a.layout)
            rows.append((key, res))
            if notes:
                details.append((key, notes))
    finally:
        if tmp_ctx:
            tmp_ctx.cleanup()

    w = max(len("spec"), max(len(k) for k, _ in rows))
    widths = [max(len(c), max(len(r[c]) for _, r in rows)) for c in COLS]
    print("%-*s  %s" % (w, "spec", "  ".join("%-*s" % (cw, c) for c, cw in zip(COLS, widths))))
    print("%s  %s" % ("-" * w, "  ".join("-" * cw for cw in widths)))
    for k, r in rows:
        print("%-*s  %s" % (w, k, "  ".join("%-*s" % (cw, r[c]) for c, cw in zip(COLS, widths))))
    for k, notes in details:
        print("\n== %s" % k)
        for n in notes:
            print(n)
    failed = sum(1 for _, r in rows if any(v.startswith("FAIL") for v in r.values()))
    passed = sum(1 for _, r in rows if all(v == "PASS" for v in r.values()))
    print("\n%d specs: %d all PASS, %d with FAIL, %d with SKIP" % (len(rows), passed, failed, len(rows) - passed - failed))
    if a.keep:
        print("outputs kept in %s" % tmp)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
