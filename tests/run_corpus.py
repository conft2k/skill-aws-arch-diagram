#!/usr/bin/env python3
"""Run the layout regression corpus (tests/corpus/MANIFEST.yaml) in every mode, in process.

    python3 tests/run_corpus.py [filter ...] [--topic T ...] [--mode M ...] [-j N] [--timeout S]
                                [--out REPORT.json] [--keep DIR] [--rule-checker MOD:FUNC] [-q]

Every manifest entry (a corpus case, or a docs/examples spec by reference) is run in each
of its modes — `document` (--mode document), `slide` (--mode slide) and `slide-no-title`
(--mode slide --no-title) — through scripts/layout.py's main() in this process (one worker
process per -j). A filter keeps the entries whose path contains it (substring).

Per run it records: load (ok / rejected, with the spec's problem lines), the result (drawn /
layout-error / crash / timeout, past --timeout s), check_layout's problem codes on the final
draft (plus SLIDE TOO SMALL), the engine's warnings, the canvas size, the size 12px text gets
on a 16:9 slide, the feedback rounds and the wall time. It prints one row per entry, then
the counts per problem code, the slowest runs and the total time, and writes the full JSON
report to --out (default <system temp dir>/corpus-report.json).

An entry's `expect` (one value, or a map mode → value) says what each run must end in:
`load` — the spec loads and a draft is drawn; `reject` — layout_spec refuses the spec at load;
`refuse` — the spec loads but the solve refuses it (a LayoutError naming the contradictory
constraints). An entry that rejects or refuses in some mode also needs `match` (a text, or a
map of those modes to texts) found in one of that refusal's lines, so a refusal for another
reason does not pass. Exit status: 1 when a run ends otherwise (a crash or a timeout never
matches), 2 when nothing matches the filters, else 0. Check problems and rule violations are
recorded, never judged here. A malformed manifest (unknown key, unknown rule, missing file,
a file listed twice, …), or a corpus or docs/examples spec it does not list, stops the run
before it starts. An entry with `known_fail: <why>` that does not end as expected is reported
as a known failure without failing the run, and is reported again once it passes.

The user rules (R-flow, R-rt, R-twin, R-label, R-fit) are judged by a rule checker plugged
into rule_violations() (scripts/rules.py:corpus is the one), by --rule-checker module:function (or path.py:function),
or, in process with -j 1 only, by appending to RULE_CHECKERS (worker processes load only the
--rule-checker ones; -j > 1 with appended checkers stops). Each checker gets (spec, build,
draft, run) — run a copy of the run's record — and returns a list of violations
({"rule": "R-rt", "msg": "..."} dicts); they land in the report's `violations`. An entry's
`good` (rules with no violation in any drawn run) and `bad` (rule → an owner id some violation
of it must name, in every drawn run, or a map of some modes to one) are compared with them:
the disagreeing runs, and those whose checker failed (a checker-error: their tags are not
judged), are printed and kept in the report's `tag_misses`, without changing the exit status.

Needs PyYAML (the manifest and the specs are YAML). Python 3.9+.
"""
import argparse
import contextlib
import copy
import importlib
import importlib.util
import io
import json
import shutil
import signal
import sys
import tempfile
import time
import traceback
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "tests" / "corpus"
MANIFEST = CORPUS / "MANIFEST.yaml"
EXAMPLES = ROOT / "docs" / "examples" / "specs"
sys.path.insert(0, str(ROOT / "scripts"))

import layout  # noqa: E402
import layout_const as K  # noqa: E402
import layout_model as M  # noqa: E402
import layout_spec  # noqa: E402

MODES = {"document": ["--mode", "document"], "slide": ["--mode", "slide"],
         "slide-no-title": ["--mode", "slide", "--no-title"]}
ALL_MODES = list(MODES)
# expect → the run result it requires
EXPECT = {"load": "drawn", "reject": "rejected", "refuse": "layout-error"}
# the keys a manifest entry may have
ENTRY_KEYS = {"path", "modes", "expect", "match", "rules", "what", "from", "note", "known_fail", "good", "bad"}
RULES = ("R-flow", "R-rt", "R-twin", "R-label", "R-fit", "R-reject")
# the rules a rule checker judges (good / bad tags name these)
CHECKED = ("R-flow", "R-rt", "R-twin", "R-label", "R-fit")


# =======================================================================================
# The rule hook

# A rule checker: (spec, build, draft, run) -> [{"rule": "R-…", "msg": "…", …}, …], where
# spec is the loaded layout_model.Spec, build the layout.Build whose draft was written
# (build.geom is the solved Geometry, build.elements what was drawn), draft the written SVG
# bytes (after check_layout --fix's repairs) and run this run's record so far (case path,
# mode, the rules the case guards, problem codes, …). Checkers run only on drawn runs.
RuleChecker = Callable[[Any, Any, bytes, Dict[str, Any]], List[Dict[str, Any]]]
RULE_CHECKERS: List[RuleChecker] = []


def rule_violations(spec, build, draft: bytes, run: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Every plugged-in checker's violations for one drawn run (none plugged in: [])."""
    out: List[Dict[str, Any]] = []
    for fn in RULE_CHECKERS:
        name = getattr(fn, "__name__", repr(fn))
        try:
            got = fn(spec, build, draft, run) or []
        except Exception as e:  # noqa: BLE001 — a checker bug must not hide the other results
            got = [{"rule": "checker-error", "msg": f"{name}: {e!r}"}]
        if not isinstance(got, (list, tuple)):
            got = [{"rule": "checker-error", "msg": f"{name}: returned {type(got).__name__}, not a list"}]
        for v in got:
            if not (isinstance(v, dict) and isinstance(v.get("rule"), str)):
                v = {"rule": "checker-error", "msg": f"{name}: not a {{'rule': str, …}} dict: {v!r}"[:300]}
            # keep the report JSON- and pickle-safe: anything else becomes its text
            out.append({(k if isinstance(k, str) else str(k)):
                        (x if isinstance(x, (str, int, float, bool, type(None))) else str(x))
                        for k, x in v.items()})
    return out


def load_checker(ref: str, n: int = 0) -> RuleChecker:
    """`module:function` (importable) or `path/to/file.py:function`; function defaults to check."""
    mod, _, fn = ref.partition(":")
    if mod.endswith(".py") or "/" in mod:
        p = Path(mod).resolve()
        spec = importlib.util.spec_from_file_location(f"corpus_rule_checker_{n}", p)
        if spec is None or spec.loader is None:
            raise ImportError(f"cannot load {p}")
        m = importlib.util.module_from_spec(spec)
        if str(p.parent) not in sys.path:        # so the checker can import files beside it
            sys.path.insert(0, str(p.parent))
        sys.modules[spec.name] = m               # dataclasses and pickling look modules up here
        spec.loader.exec_module(m)
    else:
        m = importlib.import_module(mod)
    f = getattr(m, fn or "check")
    if not callable(f):
        raise TypeError(f"{ref} is not callable")
    return f


# =======================================================================================
# Manifest

def load_manifest(path: Path = MANIFEST) -> List[Dict[str, Any]]:
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or set(data) - {"defaults", "cases", "examples"}:
        raise SystemExit(f"{path}: expected a mapping of defaults / cases / examples, "
                         f"got {sorted(data) if isinstance(data, dict) else type(data).__name__}")
    defaults = data.get("defaults") or {}
    if not isinstance(defaults, dict) or set(defaults) - {"modes"}:
        raise SystemExit(f"{path}: defaults: only `modes` is known, got {defaults!r}")
    default_modes = defaults.get("modes", ALL_MODES)
    for sect in ("cases", "examples"):
        if data.get(sect) is not None and not isinstance(data[sect], list):
            raise SystemExit(f"{path}: {sect}: expected a list of entries")
    entries = []
    seen = set()
    for sect in ("cases", "examples"):
        for e in data.get(sect) or []:
            if not isinstance(e, dict) or not isinstance(e.get("path"), str):
                raise SystemExit(f"{path}: {sect}: an entry without a path: {e!r}")
            unknown = sorted(set(e) - ENTRY_KEYS)
            if unknown:
                raise SystemExit(f"{path}: {e['path']}: unknown keys {unknown} (known: {', '.join(sorted(ENTRY_KEYS))})")
            if not isinstance(e.get("rules", []), list):
                raise SystemExit(f"{path}: {e['path']}: rules must be a list")
            bad_rules = [r for r in e.get("rules") or [] if r not in RULES]
            if bad_rules:
                raise SystemExit(f"{path}: {e['path']}: unknown rules {bad_rules} (known: {', '.join(RULES)})")
            e = dict(e)
            e["section"] = sect
            e["topic"] = e["path"].split("/")[0] if sect == "cases" else "examples"
            e.setdefault("expect", "load")
            e.setdefault("modes", default_modes)
            e["file"] = str((path.parent / e["path"]).resolve())
            if not Path(e["file"]).is_file():
                raise SystemExit(f"{path}: {e['path']}: no such file")
            if e["file"] in seen:
                raise SystemExit(f"{path}: {e['path']}: listed twice")
            seen.add(e["file"])
            if not isinstance(e["modes"], list) or not e["modes"] or len(set(e["modes"])) != len(e["modes"]):
                raise SystemExit(f"{path}: {e['path']}: modes must be a non-empty list without repeats")
            bad = [m for m in e["modes"] if m not in MODES]
            ex = e["expect"] if isinstance(e["expect"], dict) else {m: e["expect"] for m in e["modes"]}
            if bad or set(ex) - set(e["modes"]) or set(e["modes"]) - set(ex) or set(ex.values()) - set(EXPECT):
                raise SystemExit(f"{path}: {e['path']}: bad modes {bad} or expect {e['expect']!r}")
            e["expect_by_mode"] = ex
            # match: one text for every refusing mode, or a map refusing mode -> text
            refusing = {m for m, v in ex.items() if v != "load"}
            if not refusing and "match" in e:
                raise SystemExit(f"{path}: {e['path']}: match on an entry that loads in every mode")
            mt = e.get("match")
            mt = {m: mt for m in refusing} if isinstance(mt, str) else mt
            if (refusing or mt is not None) and not (
                    isinstance(mt, dict) and set(mt) == refusing
                    and all(isinstance(t, str) and t for t in mt.values())):
                raise SystemExit(f"{path}: {e['path']}: an entry expected to reject or refuse in some mode "
                                 f"needs match (a non-empty text its refusal must contain, or a map of those "
                                 f"modes to such texts), and only such an entry")
            e["match_by_mode"] = mt or {}
            if "known_fail" in e and not (isinstance(e["known_fail"], str) and e["known_fail"]):
                raise SystemExit(f"{path}: {e['path']}: known_fail must be a non-empty text (why it fails)")
            good, bad = e.get("good", []), e.get("bad", {})

            def owner_ok(o):
                return (isinstance(o, str) and o) or (isinstance(o, dict) and o and set(o) <= set(e["modes"])
                                                     and all(isinstance(v, str) and v for v in o.values()))
            if not (isinstance(good, list) and all(r in CHECKED for r in good)) or not (
                    isinstance(bad, dict) and all(r in CHECKED and owner_ok(o) for r, o in bad.items())) \
                    or set(good) & set(bad):
                raise SystemExit(f"{path}: {e['path']}: good must be a list of rules ({', '.join(CHECKED)}) and bad a "
                                 f"map of other such rules to the owner id a violation must name (edge:3, node:rtsp, …), "
                                 f"or to a map of some of the entry's modes to one")
            e["expect_label"] = ex[e["modes"][0]] if len(set(ex.values())) == 1 else "mixed"
            entries.append(e)
    if path.resolve() == MANIFEST.resolve():
        listed = {e["file"] for e in entries}
        unlisted = sorted(str(p.relative_to(ROOT)) for d in (CORPUS, EXAMPLES)
                          for p in d.rglob("*") if p.is_file() and p.name != MANIFEST.name
                          and p.suffix in (".yaml", ".yml", ".json") and str(p.resolve()) not in listed)
        if unlisted:
            raise SystemExit(f"{path}: specs missing from the manifest: {', '.join(unlisted)}")
    return entries


# =======================================================================================
# One run

class RunTimeout(BaseException):
    """A run went past --timeout (a BaseException, so no `except Exception` in the engine eats it)."""


def _alarm(signum, frame):
    raise RunTimeout()


def run_one(entry: Dict[str, Any], mode: str, out_dir: str, timeout: float = 0) -> Dict[str, Any]:
    """One manifest entry in one mode; with timeout (s, Unix) a run past it ends as `timeout`."""
    timer = timeout > 0 and hasattr(signal, "setitimer")
    if timer:
        old = signal.signal(signal.SIGALRM, _alarm)
        signal.setitimer(signal.ITIMER_REAL, timeout)
    t0 = time.perf_counter()
    rec: Dict[str, Any] = {"path": entry["path"], "mode": mode, "expect": entry["expect_by_mode"][mode],
                           "rules": entry.get("rules", []), "load": None, "result": None,
                           "codes": [], "problems": [], "warnings": [], "canvas": None, "pt": None,
                           "rounds": 0, "exit": None, "title": None, "violations": [], "error": None}
    try:
        return _run_one(entry, mode, out_dir, rec)
    except RunTimeout:                  # rec keeps what was recorded before (load ok, …)
        rec["result"] = "timeout"
        rec["problems"] = [f"timeout: still running after {timeout:g}s"]
        rec["time"] = round(time.perf_counter() - t0, 3)
        return rec
    finally:
        if timer:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old)


def _run_one(entry: Dict[str, Any], mode: str, out_dir: str, rec: Dict[str, Any]) -> Dict[str, Any]:
    spec_file = Path(entry["file"])
    args = MODES[mode]
    t0 = time.perf_counter()
    # load on its own first: whether the spec is rejected, and with which lines
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            layout_spec.load(spec_file, mode=args[1], title=False if "--no-title" in args else None)
        rec["load"] = "ok"
    except M.LayoutError as e:
        rec["load"], rec["result"] = "rejected", "rejected"
        rec["problems"] = list(e.problems)
    except Exception as e:  # noqa: BLE001
        rec["load"], rec["result"] = "crash", "crash"
        rec["error"] = "".join(traceback.format_exception_only(type(e), e)).strip()
    if rec["load"] != "ok":
        rec["time"] = round(time.perf_counter() - t0, 3)
        return rec

    stem = entry["path"].replace("/", "__").replace("..", "up")
    draft = Path(out_dir) / f"{stem}.{mode}.draft.svg"
    cap: Dict[str, Any] = {}
    real_summary, real_problems = layout.summary, layout.problems_of

    def summary(spec, b, out_path):
        cap["spec"], cap["b"] = spec, b
        lines = real_summary(spec, b, out_path)
        cap["summary"] = lines
        return lines

    def problems_of(data, hints=False):
        res = real_problems(data, hints)
        if hints:                       # main()'s last call: the problems of the written draft
            cap["final"] = res[0]
        return res

    buf = io.StringIO()
    try:
        with mock.patch.object(layout, "summary", summary), \
                mock.patch.object(layout, "problems_of", problems_of), contextlib.redirect_stdout(buf):
            rec["exit"] = layout.main([str(spec_file), "-o", str(draft), *args])
    except Exception as e:  # noqa: BLE001
        rec["result"] = "crash"
        rec["error"] = traceback.format_exc(limit=-3).strip()
    rec["time"] = round(time.perf_counter() - t0, 3)
    text = buf.getvalue()
    if rec["result"] == "crash":
        return rec
    if "b" not in cap:                  # main() returned before the summary: a LayoutError
        rec["result"] = "layout-error"
        rec["problems"] = [l for l in text.splitlines() if l.strip()]
        return rec
    spec, b = cap["spec"], cap["b"]
    g = b.geom
    rec["result"] = "drawn"
    rec["canvas"] = [round(g.canvas_w, 1), round(g.canvas_h, 1)]
    pt = K.slide_pt(g.canvas_w, g.canvas_h, spec.title)
    rec["pt"] = round(pt, 2)
    rec["slide_small"] = rec["mode"] != "document" and pt < K.SLIDE_MIN_PT
    rec["title"] = bool(spec.title)
    rec["warnings"] = [l[len("warning: "):] for l in cap["summary"] if l.startswith("warning: ")]
    probs = cap.get("final", [])
    rec["codes"] = [p.iss.kind for p in probs]
    rec["problems"] = [p.iss.msg for p in probs]
    sp = layout.slide_problem(spec, g)
    if sp:
        rec["codes"].append("SLIDE TOO SMALL")
        rec["problems"].append(sp)
    for l in text.splitlines():
        if l.startswith("check: ") and "feedback round" in l:
            rec["rounds"] = int(l.split()[1])
    if RULE_CHECKERS:
        rec["violations"] = rule_violations(spec, b, draft.read_bytes(), copy.deepcopy(rec))
    return rec


def _init_worker(checkers: List[str]) -> None:
    """A worker process: load the --rule-checker refs (validated by the parent first)."""
    RULE_CHECKERS[:] = [load_checker(c, i) for i, c in enumerate(checkers)]


def _run_job(job):
    entry, mode, out_dir, timeout = job
    return run_one(entry, mode, out_dir, timeout)


# =======================================================================================
# Report

def failed(entry: Dict[str, Any], runs: List[Dict[str, Any]]) -> Optional[str]:
    """Why an entry fails the run (its expect / match not met, per mode), else None."""
    why = []
    for r in runs:
        want = r["expect"]
        text = entry["match_by_mode"].get(r["mode"])
        if r["result"] != EXPECT[want]:
            why.append(f"{r['mode']}: expected {want} ({EXPECT[want]}), got {r['result']}")
        elif text and not any(text in l for l in r["problems"]):
            why.append(f"{r['mode']}: {want} as expected, but no line contains {text!r}")
    return "; ".join(why) or None


def tag_misses(entry: Dict[str, Any], runs: List[Dict[str, Any]]) -> List[str]:
    """Where a drawn run's rule violations disagree with the entry's good / bad tags: a good
    rule violated, or a bad rule with no violation naming its owner."""
    out = []
    for r in runs:
        if r["result"] != "drawn":
            continue
        broke = [v for v in r["violations"] if v.get("rule") == "checker-error"]
        if broke:                       # no verdict to compare: every tag of the run is unjudged
            tags = [f"good {t}" for t in entry.get("good", [])] + [f"bad {t}" for t in entry.get("bad", {})]
            if tags:
                out.append(f"{r['mode']}: {', '.join(tags)} not judged — the checker failed: "
                           f"{broke[0].get('msg', '')[:160]}")
            continue
        for rule in entry.get("good", []):
            got = [v for v in r["violations"] if v.get("rule") == rule]
            if got:
                out.append(f"{r['mode']}: good {rule}, but {len(got)} violation{'s' if len(got) != 1 else ''}: "
                           f"{got[0].get('msg', '')[:160]}")
        for rule, owner in entry.get("bad", {}).items():
            if isinstance(owner, dict):
                if r["mode"] not in owner:
                    continue
                owner = owner[r["mode"]]
            if not any(v.get("rule") == rule and owner in str(v.get("owners", "")).split(",") for v in r["violations"]):
                out.append(f"{r['mode']}: bad {rule}, but no violation names {owner}")
    return out


def cell(r: Dict[str, Any]) -> str:
    if r["result"] == "rejected":
        return "REJ"
    if r["result"] in ("crash", "layout-error", "timeout"):
        return {"crash": "CRASH", "layout-error": "LERR", "timeout": "TIMEOUT"}[r["result"]]
    s = "ok" if not r["codes"] else f"{len(r['codes'])}p"
    if r["mode"] != "document":
        s += f" {r['pt']:.2f}pt" + ("<" if r.get("slide_small") else "")
    return s


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("filters", nargs="*", help="keep entries whose path contains one of these")
    ap.add_argument("--topic", action="append", help="keep cases of this topic (corpus subdirectory, or 'examples')")
    ap.add_argument("--mode", action="append", choices=ALL_MODES, help="run only these modes")
    ap.add_argument("-j", "--jobs", type=int, default=1, help="worker processes (default 1)")
    ap.add_argument("--out", type=Path, default=Path(tempfile.gettempdir()) / "corpus-report.json",
                    help="JSON report (default <temp dir>/corpus-report.json)")
    ap.add_argument("--keep", type=Path, help="write the drafts here and keep them (default: a temp dir, removed)")
    ap.add_argument("--rule-checker", action="append", default=[], metavar="MOD:FUNC",
                    help="plug a rule checker into rule_violations() (module or path.py, then :function)")
    ap.add_argument("--timeout", type=float, default=300,
                    help="seconds one run may take before it ends as `timeout` (0: no limit; default 300)")
    ap.add_argument("--manifest", type=Path, default=MANIFEST)
    ap.add_argument("-q", "--quiet", action="store_true", help="print only failing entries and the summary")
    a = ap.parse_args(argv)

    entries = load_manifest(a.manifest)
    if a.filters:
        entries = [e for e in entries if any(f in e["path"] for f in a.filters)]
    if a.topic:
        entries = [e for e in entries if e["topic"] in a.topic]
    picked = [(e, m) for e in entries for m in e["modes"] if not a.mode or m in a.mode]
    entries = [e for e in entries if any(pe is e for pe, _ in picked)]
    if not picked:
        print("no manifest entry matches the filters / --topic / --mode given", file=sys.stderr)
        return 2
    saved = list(RULE_CHECKERS)
    if saved and a.jobs > 1:
        raise SystemExit("RULE_CHECKERS appended in process reach no worker: use -j 1, or --rule-checker")
    try:                                # a bad --rule-checker fails here, not in a worker
        checkers = [load_checker(c, i) for i, c in enumerate(a.rule_checker)]
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"--rule-checker: {e!r}")
    out_dir = str(a.keep) if a.keep else tempfile.mkdtemp(prefix="corpus-drafts-")
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    jobs = [(e, m, out_dir, a.timeout) for e, m in picked]
    t0 = time.perf_counter()
    try:
        if a.jobs > 1:
            with ProcessPoolExecutor(a.jobs, initializer=_init_worker, initargs=(a.rule_checker,)) as ex:
                results = list(ex.map(_run_job, jobs, chunksize=1))
        else:
            RULE_CHECKERS[:] = saved + checkers
            results = [_run_job(j) for j in jobs]
    finally:
        RULE_CHECKERS[:] = saved
        if not a.keep:
            shutil.rmtree(out_dir, ignore_errors=True)
    total = time.perf_counter() - t0

    by_entry: Dict[str, List[Dict[str, Any]]] = {}
    for r in results:
        by_entry.setdefault(r["path"], []).append(r)
    fails, known, fixed = [], [], []
    width = max([len(e["path"]) for e in entries] + [20])
    head = f"{'case':{width}s} {'expect':6s} " + " ".join(f"{m:16s}" for m in ALL_MODES)
    if not a.quiet:
        print(head)
    for e in entries:
        runs = by_entry.get(e["path"], [])
        why = failed(e, runs)
        kf = e.get("known_fail")
        mark = ""
        if why and kf:                  # a recorded known failure: reported, not failing the run
            known.append((e["path"], why, kf))
            mark = f"  KNOWN {why} ({kf})"
        elif why:
            fails.append((e["path"], why))
            mark = f"  FAIL {why}"
        elif kf:                        # its expectation holds now: time to drop known_fail
            fixed.append((e["path"], kf))
            mark = f"  FIXED (known_fail no longer happens: {kf})"
        cells = {r["mode"]: cell(r) for r in runs}
        row = f"{e['path']:{width}s} {e['expect_label']:6s} " + " ".join(f"{cells.get(m, '-'):16s}" for m in ALL_MODES)
        if not a.quiet or mark:
            print(row + mark)

    codes = Counter(c for r in results for c in r["codes"])
    warn_runs = sum(1 for r in results if r["warnings"])
    drawn = [r for r in results if r["result"] == "drawn"]
    status = Counter(r["result"] for r in results)
    slide_small = [r for r in drawn if r.get("slide_small")]
    print()
    print(f"{len(entries)} entries, {len(results)} runs: " + ", ".join(f"{k} {v}" for k, v in sorted(status.items())))
    print(f"runs with check problems: {sum(1 for r in drawn if r['codes'])} of {len(drawn)} drawn; "
          f"problems {sum(codes.values())}; runs with warnings {warn_runs}; slide runs < {K.SLIDE_MIN_PT}pt: {len(slide_small)}")
    for k, v in codes.most_common():
        print(f"  {v:5d}  {k}")
    misses = []
    if saved or a.rule_checker:
        vio = Counter(v.get("rule", "?") for r in results for v in r["violations"])
        print("rule violations: " + (", ".join(f"{k} {v}" for k, v in vio.most_common()) or "none"))
        tagged = [e for e in entries if e.get("good") or e.get("bad")]
        for e in tagged:
            misses += [(e["path"], m) for m in tag_misses(e, by_entry.get(e["path"], []))]
        n_good = sum(len(e.get("good", [])) for e in tagged)
        n_bad = sum(len(e.get("bad", {})) for e in tagged)
        print(f"rule tags: {len(tagged)} tagged entries ({n_good} good, {n_bad} bad rule tags); "
              f"{len(misses)} run{'s' if len(misses) != 1 else ''} disagreeing (reported, not failing the run)")
        for p, m in misses:
            print(f"  tag: {p}: {m}")
    print("slowest runs:")
    for r in sorted(results, key=lambda r: -r["time"])[:8]:
        print(f"  {r['time']:7.2f}s  {r['path']} [{r['mode']}]")
    cpu = sum(r["time"] for r in results)
    print(f"total: {total:.1f}s wall ({cpu:.1f}s summed over runs, -j {a.jobs})")
    report = {"root": str(ROOT), "jobs": a.jobs, "wall_s": round(total, 2), "summed_s": round(cpu, 2),
              "entries": len(entries), "runs": results, "codes": dict(codes), "failures": fails,
              "known_failures": known, "known_fail_fixed": fixed, "tag_misses": misses}
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"report: {a.out}")
    for p, why, kf in known:
        print(f"known failure: {p}: {why} ({kf})")
    for p, kf in fixed:
        print(f"known failure gone (drop its known_fail): {p} ({kf})")
    if fails:
        print(f"{len(fails)} entr{'y' if len(fails) == 1 else 'ies'} not as expected:")
        for p, why in fails:
            print(f"  {p}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
