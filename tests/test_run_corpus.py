"""Baseline comparison: small reports exercise the runner's public results and CLI."""
import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_corpus as C


def run(path="a.layout.yaml", mode="document", **changes):
    rec = {
        "path": path, "mode": mode, "result": "drawn", "expect": "load", "codes": [],
        "violations": [], "canvas": [100, 100], "warnings": [], "time": 2,
        "text": {"actual": 11, "target": 11}, "rule_checked": True,
    }
    rec.update(changes)
    return rec


def report(*runs, wall=4):
    return {"runs": list(runs), "wall_s": wall, "summed_s": sum(r["time"] for r in runs)}


def violation(rule="R-flow", cost=1, tier=0):
    return {"rule": rule, "cost": cost, "tier": tier}


def drafts(directory, *runs, content=None):
    directory.mkdir(exist_ok=True)
    for r in runs:
        if r["result"] == "drawn":
            stem = r["path"].replace("/", "__").replace("..", "up")
            data = content
            if data is None:
                w, h = r["canvas"]
                fit = next((v["cost"] for v in r["violations"] if v["rule"] == "R-fit"), None)
                target = C.K.DOCUMENT_TARGET_PX if r["mode"] == "document" else C.K.SLIDE_MIN_PT
                actual = target - fit if fit is not None else r["text"]["actual"]
                factor = C.K.effective_text(
                    "document" if r["mode"] == "document" else "slide",
                    w, h, 1, r.get("title", r["mode"] != "slide-no-title"),
                )[0]
                data = (
                    f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
                    f'<text font-size="{actual / factor:.17f}">EC2</text></svg>'
                ).encode()
            (directory / f"{stem}.{r['mode']}.draft.svg").write_bytes(data)
    return directory


def compare(tmp_path, current, baseline, current_bytes=None, baseline_bytes=None):
    return C.compare_reports(
        current, baseline,
        drafts(tmp_path / "current", *current["runs"], content=current_bytes),
        drafts(tmp_path / "baseline", *baseline["runs"], content=baseline_bytes),
    )


def test_self_comparison_has_no_changes_or_deltas(tmp_path):
    source = report(
        run(violations=[violation(), violation("R-fit", 2, 2)],
            codes=["LINE OVER TEXT", "LINE OVER TEXT"]),
        run(mode="slide", result="rejected", expect="reject", canvas=None),
    )
    got = compare(tmp_path, source, copy.deepcopy(source))
    assert got["counts"] == {"better": 0, "same": 2, "worse": 0, "uncompared": 0, "unjudged": 0}
    assert got["changed_drafts"] == []
    assert got["check_problem_delta"] == 0
    assert all(d == 0 for d in got["code_deltas"].values())
    assert all(d == 0 for d in got["violation_deltas"].values())
    assert got["runtime"] == {
        "wall_ratio": 1, "summed_ratio": 1, "wall_delta_s": 0, "summed_delta_s": 0,
    }
    assert all(r["verdict"] == "same" for r in got["runs"])


@pytest.mark.parametrize("index", range(7))
@pytest.mark.parametrize("direction,expected", [(-1, "better"), (1, "worse")])
def test_verdict_uses_each_part_in_spec_order(tmp_path, index, direction, expected):
    # Every later part points the opposite way: only the first differing part wins.
    baseline_parts = [2, 2, 20, 4, 2, 2, 10000]
    current_parts = baseline_parts[:]
    current_parts[index] += direction
    for later in range(index + 1, 7):
        current_parts[later] -= direction

    def scored(parts):
        clipping, count, cost, checks, shortfall, misses, area = parts
        return run(
            violations=[violation(cost=cost / count) for _ in range(count)]
            + [violation("R-fit", shortfall, 2)],
            codes=["LINE OFF CANVAS"] * clipping + ["LINE OVER TEXT"] * (checks - clipping),
            warnings=["edge:0 drew VH instead of HV"] * misses,
            canvas=[area, 1],
        )

    got = compare(tmp_path, report(scored(current_parts)), report(scored(baseline_parts)))
    row = got["runs"][0]
    assert row["verdict"] == expected
    assert row["baseline_verdict"] == pytest.approx(baseline_parts)
    assert row["current_verdict"] == pytest.approx(current_parts)


def test_changed_drafts_use_bytes_and_keep_case_mode_identity(tmp_path):
    base = report(run(), run(mode="slide"), run(path="b.layout.yaml"))
    now = copy.deepcopy(base)
    before = drafts(tmp_path / "baseline", *base["runs"])
    after = drafts(tmp_path / "current", *now["runs"])
    # Equivalent XML still differs in bytes.
    path = after / "a.layout.yaml.slide.draft.svg"
    path.write_bytes(path.read_bytes().replace(b"<svg ", b"<svg\n"))
    got = C.compare_reports(now, base, after, before)
    assert got["changed_drafts"] == [{"path": "a.layout.yaml", "mode": "slide"}]
    assert got["counts"]["same"] == 3


def test_deltas_count_repeated_codes_rules_and_runtime(tmp_path):
    base = report(run(codes=["LINE OVER TEXT"] * 2,
                      violations=[violation(), violation("R-rt")]), wall=2)
    now = report(run(codes=["LINE OVER TEXT", "LINE IN HEADER"],
                     violations=[violation("R-rt")] * 3, time=6), wall=3)
    got = compare(tmp_path, now, base)
    assert got["check_problem_delta"] == 0
    assert got["code_deltas"] == {"LINE IN HEADER": 1, "LINE OVER TEXT": -1}
    assert got["violation_deltas"]["R-flow"] == -1
    assert got["violation_deltas"]["R-rt"] == 2
    assert got["runtime"] == {
        "wall_ratio": 1.5, "summed_ratio": 3, "wall_delta_s": 1, "summed_delta_s": 4,
    }


def test_filtered_run_compares_only_matching_baseline_runs(tmp_path):
    base = report(run(), run(path="b.layout.yaml", codes=["LINE IN HEADER"], time=50), wall=30)
    now = report(run(time=3), wall=2)
    got = compare(tmp_path, now, base)
    assert got["counts"]["same"] == 1
    assert got["check_problem_delta"] == 0
    assert got["runtime"]["summed_ratio"] == 1.5
    assert got["runtime"]["wall_ratio"] is None
    assert got["not_run"] == [{"path": "b.layout.yaml", "mode": "document"}]


def test_fit_uses_effective_text_when_no_fit_violation_was_recorded(tmp_path):
    base = report(run(text={"actual": 9, "target": 11}))
    now = report(run(text={"actual": 10, "target": 11}))
    got = compare(tmp_path, now, base)
    assert got["runs"][0]["verdict"] == "better"
    assert got["runs"][0]["baseline_verdict"][4] == 2
    assert got["runs"][0]["current_verdict"][4] == 1


def test_refused_shape_warning_does_not_count_as_shape_miss(tmp_path):
    base = report(run(warnings=["edge:0 drew VH instead of HV; refusing the requested shape"]))
    got = compare(tmp_path, report(run()), base)
    assert got["counts"]["same"] == 1


def test_crash_cannot_look_better_than_a_drawn_baseline(tmp_path):
    base = report(run(violations=[violation()] * 3))
    now = report(run(result="crash", canvas=None))
    got = compare(tmp_path, now, base)
    assert got["counts"]["worse"] == 1
    assert got["runs"][0]["current_verdict"] is None


def test_checker_error_is_reported_as_unjudged(tmp_path):
    now = report(run(violations=[{"rule": "checker-error", "msg": "broken"}]))
    got = compare(tmp_path, now, report(run()))
    assert got["counts"]["unjudged"] == 1
    assert "checker" in got["runs"][0]["reason"]


def test_new_run_is_not_silently_same(tmp_path):
    got = compare(tmp_path, report(run(path="new.layout.yaml")), report(run()))
    assert got["counts"]["uncompared"] == 1
    assert got["added"] == [{"path": "new.layout.yaml", "mode": "document"}]


def test_missing_draft_is_an_explicit_error(tmp_path):
    source = report(run())
    before = drafts(tmp_path / "baseline", *source["runs"])
    after = tmp_path / "current"
    after.mkdir()
    with pytest.raises(ValueError, match="draft.*a.layout.yaml"):
        C.compare_reports(source, source, after, before)


def test_zero_baseline_runtime_has_no_infinite_json_value(tmp_path):
    got = compare(tmp_path, report(run(time=2), wall=1), report(run(time=0), wall=0))
    assert got["runtime"]["wall_ratio"] is None
    assert got["runtime"]["summed_ratio"] is None
    json.dumps(got, allow_nan=False)


def test_cli_writes_and_prints_comparison_before_temporary_drafts_are_removed(tmp_path, capsys):
    spec = tmp_path / "tiny.layout.yaml"
    spec.write_text(
        "cols: [a]\nrows: [r]\nnodes:\n"
        "  - {id: n, icon: service/Amazon-EC2, label: EC2, at: [a, r]}\n"
    )
    manifest = tmp_path / "MANIFEST.yaml"
    manifest.write_text(
        "defaults: {modes: [document]}\ncases:\n  - {path: tiny.layout.yaml}\n"
    )
    baseline = tmp_path / "baseline.json"
    before = tmp_path / "before"
    common = ["--manifest", str(manifest), "--rule-checker", "scripts/rules.py:corpus", "-q"]
    assert C.main([*common, "--keep", str(before), "--out", str(baseline)]) == 0
    old = json.loads(baseline.read_text())
    assert set(old) == {
        "root", "jobs", "wall_s", "summed_s", "entries", "runs", "codes", "failures",
        "known_failures", "known_fail_fixed", "tag_misses",
    }
    assert "baseline comparison:" not in capsys.readouterr().out
    output = tmp_path / "current.json"
    assert C.main([
        *common, "--baseline", str(baseline), "--baseline-drafts", str(before),
        "--out", str(output),
    ]) == 0
    got = json.loads(output.read_text())["comparison"]
    assert got["counts"]["same"] == 1
    assert got["changed_drafts"] == []
    assert "baseline comparison: 0 better, 1 same, 0 worse" in capsys.readouterr().out


@pytest.mark.parametrize("args", [["--baseline", "missing.json"], ["--baseline-drafts", "missing"]])
def test_cli_requires_result_and_drafts_together(args, capsys):
    with pytest.raises(SystemExit) as exc:
        C.main(args)
    assert exc.value.code == 2
    assert "together" in capsys.readouterr().err


@pytest.mark.parametrize("unchecked_side", ["current", "baseline"])
def test_missing_rule_checker_is_unjudged_without_false_violation_deltas(tmp_path, unchecked_side):
    checked = report(run(path="bench/engine1-egress.layout.yaml",
                         violations=[violation("R-rt")] * 4, rule_checked=True))
    unchecked = copy.deepcopy(checked)
    unchecked["runs"][0].update(violations=[], rule_checked=False)
    now, before = (unchecked, checked) if unchecked_side == "current" else (checked, unchecked)
    got = compare(tmp_path, now, before)
    assert got["counts"]["better"] == got["counts"]["worse"] == 0
    assert got["counts"]["unjudged"] == 1
    assert got["runs"][0]["verdict"] == "unjudged"
    assert got["runs"][0]["violation_deltas"] is None
    assert got["violation_deltas"]["R-rt"] == 0


@pytest.mark.parametrize("width", [1000.2, 1000.02])
def test_draft_shortfall_precedes_smaller_area_despite_rounded_fit_cost(tmp_path, width):
    from types import SimpleNamespace
    import rules

    def drawing(w, h):
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">'
            '<text x="20" y="20" font-size="12">EC2</text></svg>'
        ).encode()

    def recorded(w, h):
        svg = drawing(w, h)
        actual = C.K.effective_text("document", w, h, 12, False)[0]
        violations = rules.fit_rules(SimpleNamespace(mode="document", title=False), rules.Drawn.parse(svg))
        return report(run(canvas=[w, h], title=False, rule_checked=True,
                          violations=[v.as_dict() for v in violations],
                          text={"actual": round(actual, 3), "target": 11}))

    before, now = recorded(1000, 1000), recorded(width, 999)
    assert before["runs"][0]["violations"][0]["cost"] == now["runs"][0]["violations"][0]["cost"] == 1.88
    got = compare(tmp_path, now, before, drawing(width, 999), drawing(1000, 1000))
    assert got["runs"][0]["verdict"] == "worse"
    assert got["runs"][0]["current_verdict"][4] > got["runs"][0]["baseline_verdict"][4]
    assert got["runs"][0]["current_verdict"][4] == pytest.approx(11 - 12 * 760 / width)


@pytest.mark.parametrize("expect,old_result,new_result", [
    ("reject", "rejected", "drawn"), ("refuse", "layout-error", "drawn"),
    ("load", "drawn", "rejected"),
])
def test_expected_result_regression_is_worse(tmp_path, expect, old_result, new_result):
    before = report(run(path="reject/col-list.layout.yaml", mode="slide",
                        expect=expect, result=old_result, rule_checked=True))
    now = report(run(path="reject/col-list.layout.yaml", mode="slide",
                     expect=expect, result=new_result, rule_checked=True))
    got = compare(tmp_path, now, before)
    assert got["counts"]["worse"] == 1
    assert got["counts"]["better"] == 0
    assert got["runs"][0]["verdict"] == "worse"


def test_empty_legacy_checker_results_are_not_assumed_judged(tmp_path):
    legacy = report(run())
    del legacy["runs"][0]["rule_checked"]
    got = compare(tmp_path, legacy, legacy)
    assert got["counts"]["unjudged"] == 1
    assert got["counts"]["same"] == 0


def test_legacy_report_checker_evidence_covers_empty_drawn_runs(tmp_path):
    legacy = report(run(), run(path="b.layout.yaml", violations=[violation()]))
    for r in legacy["runs"]:
        del r["rule_checked"]
    got = compare(tmp_path, legacy, legacy)
    assert got["counts"]["same"] == 2
    assert got["counts"]["unjudged"] == 0


@pytest.mark.parametrize("expect,result", [
    ("load", "crash"), ("refuse", "crash"), ("reject", "drawn"),
])
def test_same_existing_expect_failure_is_same(tmp_path, expect, result):
    before = report(run(expect=expect, result=result))
    got = compare(tmp_path, copy.deepcopy(before), before)
    assert got["counts"]["same"] == 1
    assert got["counts"]["worse"] == got["counts"]["better"] == 0
    assert got["changed_drafts"] == []


@pytest.mark.parametrize("expect,old_result,new_result", [
    ("load", "crash", "drawn"), ("reject", "drawn", "rejected"),
    ("refuse", "drawn", "layout-error"),
])
def test_restored_expected_result_is_better(tmp_path, expect, old_result, new_result):
    before = report(run(expect=expect, result=old_result))
    now = report(run(expect=expect, result=new_result))
    got = compare(tmp_path, now, before)
    assert got["counts"]["better"] == 1
    assert got["counts"]["worse"] == 0


def test_both_expect_misses_still_compare_the_drawing_verdict(tmp_path):
    before = report(run(expect="reject", codes=["LINE OVER TEXT"]))
    got = compare(tmp_path, report(run(expect="reject")), before)
    assert got["counts"]["better"] == 1


def test_cli_missing_checker_is_unjudged_even_with_byte_identical_draft(tmp_path, capsys):
    spec = tmp_path / "tiny.layout.yaml"
    spec.write_text(
        "cols: [a]\nrows: [r]\nnodes:\n"
        "  - {id: n, icon: service/Amazon-EC2, label: EC2, at: [a, r]}\n"
    )
    manifest = tmp_path / "MANIFEST.yaml"
    manifest.write_text("defaults: {modes: [document]}\ncases:\n  - {path: tiny.layout.yaml}\n")
    baseline, before = tmp_path / "baseline.json", tmp_path / "before"
    common = ["--manifest", str(manifest), "-q"]
    assert C.main([
        *common, "--rule-checker", "scripts/rules.py:corpus", "--keep", str(before),
        "--out", str(baseline),
    ]) == 0
    output = tmp_path / "current.json"
    assert C.main([
        *common, "--baseline", str(baseline), "--baseline-drafts", str(before),
        "--out", str(output),
    ]) == 0
    got = json.loads(output.read_text())["comparison"]
    assert got["counts"]["unjudged"] == 1
    assert got["counts"]["better"] == got["counts"]["worse"] == 0
    assert got["changed_drafts"] == []
    assert "1 unjudged" in capsys.readouterr().out
