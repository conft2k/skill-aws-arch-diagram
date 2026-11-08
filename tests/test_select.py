"""Selection is judged through the CLI's draft, violations and summary."""
import copy
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import layout
import layout_spec
import rules
import check_layout as CL


def invoke(source, tmp_path, capsys, *args):
    draft = tmp_path / "selected.svg"
    status = layout.main([str(source), "-o", str(draft), *args])
    return status, draft.read_bytes(), capsys.readouterr().out


def default(source, tmp_path, mode=None, title=None):
    spec = layout_spec.load(source, mode=mode, title=title)
    return layout.render_readable(spec, str(source), tmp_path / "round.svg",
                                  rule_guard=layout.RuleGuard(protect=False))


def test_best_default_is_byte_unchanged(tmp_path, capsys):
    source = tmp_path / "simple.json"
    source.write_text(json.dumps({
        "name": "simple", "text_scale": "off", "cols": ["a", "b"], "rows": ["r"],
        "nodes": [{"id": n, "icon": "service/AWS-Lambda", "label": n, "at": [n, "r"]}
                  for n in ("a", "b")], "edges": [{"e": "a -> b"}],
    }))
    expected = default(source, tmp_path)[1]
    status, draft, text = invoke(source, tmp_path, capsys)
    assert status == 0
    assert draft == expected
    assert "selection: default kept" in text
    assert text.splitlines()[-1] == "Layout OK"


def test_winner_summary_and_determinism(tmp_path, capsys):
    source = ROOT / "tests/corpus/trunk/merge-v3az.layout.yaml"
    before = default(source, tmp_path, "document")
    old = rules.check(before[0].spec, before[0].geom, before[1])
    status, draft, text = invoke(source, tmp_path, capsys, "--mode", "document")
    assert status == 0
    assert "selection: candidate " in text
    assert "skip edges[" in text
    assert "removed R-flow" in text
    assert draft != before[1]
    # The final line remains the delivery status of the selected draft.
    assert text.splitlines()[-1].startswith("Layout OK")
    assert old
    again = invoke(source, tmp_path, capsys, "--mode", "document")
    assert again[1] == draft
    assert [s for s in again[2].splitlines() if s.startswith("selection:")] == [
        s for s in text.splitlines() if s.startswith("selection:")]
    evaluated, budget = map(int, re.search(r"evaluated (\d+)/(\d+) candidates", text).groups())
    assert 0 < evaluated <= budget == 12


def test_failure_on_a_new_draft_restores_default(tmp_path, capsys, monkeypatch):
    source = ROOT / "tests/corpus/trunk/merge-v3az.layout.yaml"
    known = set()
    real_check = rules.check

    def record(spec, geom, data, **kwargs):
        known.add(data)
        return real_check(spec, geom, data, **kwargs)

    monkeypatch.setattr(rules, "check", record)
    expected = default(source, tmp_path, "document")[1]

    def broken_on_new(spec, geom, data, **kwargs):
        if data not in known:
            raise RuntimeError("new draft unavailable")
        return real_check(spec, geom, data, **kwargs)

    monkeypatch.setattr(rules, "check", broken_on_new)
    _, draft, text = invoke(source, tmp_path, capsys, "--mode", "document")
    assert draft == expected
    assert "selection: default kept" in text
    assert text.count("rule: checker error") == 1


def test_hard_route_is_kept_and_warned(tmp_path, capsys):
    source = ROOT / "tests/corpus/qa/t2-false-junction.layout.yaml"
    expected = default(source, tmp_path, "slide")[1]
    _, draft, text = invoke(source, tmp_path, capsys, "--mode", "slide")
    assert draft == expected
    assert "selection: default kept" in text
    assert "warning: hard placement" in text
    assert "shape" in text and "R-flow" in text
    assert "rule violation" in text.splitlines()[-1]
    evaluated, budget = map(int, re.search(r"evaluated (\d+)/(\d+) candidates", text).groups())
    assert 0 <= evaluated <= budget == 16


@pytest.mark.parametrize("title", [True, False], ids=["slide", "slide-no-title"])
def test_return_flow_is_not_clipped_to_reduce_other_checks(tmp_path, capsys, title):
    source = ROOT / "tests/corpus/rt/gw-ret.layout.yaml"
    args = ["--mode", "slide"] + ([] if title else ["--no-title"])
    _, draft, _ = invoke(source, tmp_path, capsys, *args)
    root = ET.fromstring(draft)
    spec = layout_spec.load(source, mode="slide", title=title)
    edge = next(e for e in spec.edges if e.a == "ec2.2" and e.b == "users")
    group = root.find(f"{{{layout.SVG_NS}}}g[@id='edge:{edge.n}']")
    assert group is not None and any(e.tag.rsplit("}", 1)[-1] in {"polyline", "line"} for e in group)
    problems = CL.run_checks(root)
    assert not [p.msg for p in problems if p.kind in
                {"LINE OFF CANVAS", "OFF CANVAS", "BADGE OFF CANVAS"}]


@pytest.mark.parametrize("title", [True, False], ids=["slide", "slide-no-title"])
def test_hybrid_dns_keeps_existing_violation_owners_and_text(tmp_path, capsys, title):
    source = ROOT / "tests/corpus/qa/t3-hybrid-dns.layout.yaml"
    args = ["--mode", "slide"] + ([] if title else ["--no-title"])
    _, draft, text = invoke(source, tmp_path, capsys, *args)
    spec = layout_spec.load(source, mode="slide", title=title)
    violations = rules.flow_rules(spec, rules.Drawn.parse(draft))
    # main 36c7ea3: the junction and label conflict both involve edge:4/edge:12.
    allowed = {("R-flow", code, frozenset(("edge:4", "edge:12")))
               for code in ("F3", "F5")}
    assert {(v.rule, v.code, frozenset(v.owners)) for v in violations} <= allowed
    assert all(line.startswith(("rule: R-flow ", "rule: R-fit "))
               for line in text.splitlines() if line.startswith("rule:"))
    assert layout.drawn_text(spec, draft)[0][0] >= 6.26


def test_multiregion_slide_shrink_removes_tier_zero_violations(tmp_path, capsys, monkeypatch):
    source = ROOT / "tests/corpus/qa/t1-multiregion-dr.layout.yaml"
    admits = layout.RuleGuard.admits
    reductions = []

    def watch(guard, before, old, after, new, later=True):
        accepted = admits(guard, before, old, after, new, later=later)
        actual, _, target, _ = guard.text(before.spec, old)[0]
        if ((guard.protect or guard.selection) and later and accepted
                and actual < target and guard.text(after.spec, new)[0][0] < actual * 0.99 - 1e-9):
            old_count = sum(v.tier == 0 for v in guard.check(before.spec, before.geom, old))
            new_count = sum(v.tier == 0 for v in guard.check(after.spec, after.geom, new))
            assert new_count < old_count
            reductions.append((old_count, new_count))
        return accepted

    monkeypatch.setattr(layout.RuleGuard, "admits", watch)
    _, draft, text = invoke(source, tmp_path, capsys, "--mode", "slide")
    spec = layout_spec.load(source, mode="slide")
    assert reductions
    assert "rule: R-flow" not in text
    assert layout.drawn_text(spec, draft)[0][0] >= (12 * 924 / 3028) * 0.9


@pytest.mark.parametrize("case,area", [("rt/gw-ret", 874734), ("rt/rtsub", 710700)])
@pytest.mark.parametrize("title", [True, False], ids=["slide", "slide-no-title"])
def test_unchanged_text_keeps_clean_canvas_area(tmp_path, capsys, case, area, title):
    source = ROOT / f"tests/corpus/{case}.layout.yaml"
    _, draft, _ = invoke(source, tmp_path, capsys, "--mode", "slide",
                         *([] if title else ["--no-title"]))
    spec = layout_spec.load(source, mode="slide", title=title)
    width, height = layout.drawn_text(spec, draft)[2]
    assert width * height <= area


@pytest.mark.parametrize("title,minimum", [(True, 8.181818181818182), (False, 9.645933014354068)],
                         ids=["slide", "slide-no-title"])
def test_check_only_replay_keeps_completed_incumbent_text(tmp_path, capsys, title, minimum):
    source = ROOT / "tests/corpus/flowcol/r2-pin-bottom.layout.yaml"
    _, draft, text = invoke(source, tmp_path, capsys, "--mode", "slide",
                         *([] if title else ["--no-title"]))
    spec = layout_spec.load(source, mode="slide", title=title)
    assert layout.drawn_text(spec, draft)[0][0] >= minimum - 1e-9
    assert "rule: R-flow" not in text


def test_clean_document_font_retry_remains_available(tmp_path, capsys):
    source = ROOT / "docs/examples/specs/tgw-reference-architecture.layout.yaml"
    _, draft, _ = invoke(source, tmp_path, capsys, "--mode", "document")
    spec = layout_spec.load(source, mode="document")
    assert layout.drawn_text(spec, draft)[0][0] >= 7.735368956743002 - 1e-9


@pytest.mark.parametrize("checker", ["check", "score"])
def test_checker_failure_keeps_default(tmp_path, capsys, monkeypatch, checker):
    source = ROOT / "tests/corpus/ports/u3.layout.yaml"
    expected = default(source, tmp_path)[1]

    def broken(*args, **kwargs):
        raise RuntimeError("selection unavailable")

    monkeypatch.setattr(rules, checker, broken)
    _, draft, text = invoke(source, tmp_path, capsys)
    assert draft == expected
    assert "selection: default kept" in text
    assert text.count("rule: checker error") == 1


def test_route_table_counts_before_checks_and_fit(tmp_path):
    source = ROOT / "tests/corpus/rt/nd-single.layout.yaml"
    before = default(source, tmp_path, "document")
    b, draft, _, problems, *_ = before
    violations = rules.check(b.spec, b.geom, draft)
    guard = layout.RuleGuard(selection=True)
    verdict = guard.verdict(b, draft, problems)
    enabled = [v for v in violations if v.rule in {"R-border", "R-flow", "R-rt"}]
    assert any(v.rule == "R-rt" for v in enabled)
    assert verdict.tier_0_count == len(enabled)
    assert verdict.tier_0_cost == round(sum(v.cost for v in enabled), 3)


def test_single_association_keeps_readable_default_when_moves_shrink_text(tmp_path, capsys):
    source = ROOT / "tests/corpus/rt/nd-single.layout.yaml"
    before = default(source, tmp_path, "document")
    status, draft, text = invoke(source, tmp_path, capsys, "--mode", "document")
    assert status == 0
    assert draft == before[1]
    assert "rule: R-rt RT2" in text
    assert "selection: default kept" in text
    assert not CL.run_checks(ET.fromstring(draft))
    again = invoke(source, tmp_path, capsys, "--mode", "document")
    assert again[1] == draft


def test_pinned_route_table_keeps_its_position(tmp_path, capsys):
    source = ROOT / "tests/corpus/rt/nd-single.layout.yaml"
    document = layout_spec._read(source)[0]
    document["text_scale"] = "off"
    table = next(n for n in document["nodes"] if n["id"] == "rtsp")
    table.pop("at")
    table["xy"] = [350, 650]
    pinned = tmp_path / "pinned.json"
    pinned.write_text(json.dumps(document))
    expected = default(pinned, tmp_path, "document")[1]
    _, draft, text = invoke(pinned, tmp_path, capsys, "--mode", "document")

    def icon(data):
        root = ET.fromstring(data)
        return ET.tostring(root.find(f"{{{layout.SVG_NS}}}g[@id='node:rtsp']"))

    assert icon(draft) == icon(expected)
    assert "rule: R-rt" in text
    assert "hard placement node:rtsp (xy)" in text


def test_enabling_route_tables_keeps_the_previous_group_winner(tmp_path, capsys, monkeypatch):
    source = ROOT / "tests/corpus/ports/xnt.layout.yaml"
    with monkeypatch.context() as prior:
        prior.setattr(layout, "SELECTION_RULES", frozenset(("R-border", "R-flow")))
        _, before, old_text = invoke(source, tmp_path, capsys, "--mode", "slide")
    _, after, text = invoke(source, tmp_path, capsys, "--mode", "slide")
    # Gating the earlier group's repairs can leave its RT violations unresolved.
    # The enabled RT group must improve that held drawing without losing its flow win.
    assert "rule: R-rt" not in text
    assert text.count("rule: R-flow") <= old_text.count("rule: R-flow")
    spec = layout_spec.load(source, mode="slide")
    original = default(source, tmp_path, "slide")
    assert layout.drawn_text(spec, after)[0][0] >= min(
        layout.drawn_text(spec, original[1])[0][0] * 0.9, 10)
    assert len(CL.run_checks(ET.fromstring(after))) <= len(CL.run_checks(ET.fromstring(before)))
    evaluated, budget = map(int, re.search(r"evaluated (\d+)/(\d+) candidates", text).groups())
    assert evaluated <= budget == 16


@pytest.mark.parametrize("title,minimum", [(True, 5.6485), (False, 5.9041)],
                         ids=["slide", "slide-no-title"])
def test_rule_clean_winner_keeps_text_after_a_gated_repair(tmp_path, capsys, title, minimum):
    source = ROOT / "tests/corpus/ports/xnt.layout.yaml"
    args = ["--mode", "slide"] + ([] if title else ["--no-title"])
    _, draft, text = invoke(source, tmp_path, capsys, *args)
    spec = layout_spec.load(source, mode="slide", title=title)
    assert all(line.startswith("rule: R-fit ") for line in text.splitlines()
               if line.startswith("rule:"))
    assert layout.drawn_text(spec, draft)[0][0] >= minimum


@pytest.mark.parametrize("case,expected,minimum", [
    ("flowcol/t9-tmpl-on-flowcol", 0, 7.7777),
    ("qa/t3-cache-label", 1, 11.25),
])
@pytest.mark.parametrize("title", [True, False], ids=["slide", "slide-no-title"])
def test_candidate_construction_keeps_completed_rule_wins(
        tmp_path, capsys, case, expected, minimum, title):
    source = ROOT / f"tests/corpus/{case}.layout.yaml"
    args = ["--mode", "slide"] + ([] if title else ["--no-title"])
    _, draft, text = invoke(source, tmp_path, capsys, *args)
    spec = layout_spec.load(source, mode="slide", title=title)
    assert text.count("rule: R-flow ") == expected
    assert layout.drawn_text(spec, draft)[0][0] >= minimum


@pytest.mark.parametrize("case", [
    "rt/nd-single", "bench/engine1-egress", "bench/v2-2-egress", "bench/v2-3-egress",
])
def test_selection_keeps_at_least_90_percent_of_default_text(tmp_path, capsys, case):
    source = ROOT / f"tests/corpus/{case}.layout.yaml"
    before = default(source, tmp_path, "document")
    _, draft, _ = invoke(source, tmp_path, capsys, "--mode", "document")
    original_size = layout.drawn_text(before[0].spec, before[1])[0][0]
    spec = layout_spec.load(source, mode="document")
    assert layout.drawn_text(spec, draft)[0][0] >= original_size * 0.9 - 1e-9


@pytest.mark.parametrize("rule", ["R-border", "R-flow", "R-rt"])
@pytest.mark.parametrize("ratio,accepted", [(0.9, True), (0.899, False)])
def test_better_rules_cannot_override_the_text_size_limit(monkeypatch, rule, ratio, accepted):
    spec = layout_spec.load({
        "name": "text-floor", "text_scale": "off",
        "cols": ["a", {"id": "b", "min_gap_before": 950}], "rows": ["r"],
        "nodes": [{"id": n, "icon": "service/AWS-Lambda", "label": n, "at": [n, "r"]}
                  for n in ("a", "b")], "edges": [{"e": "a -> b"}],
    })
    before = layout.build(spec, [], {}, None, "text-floor.json")
    root = ET.fromstring(before.svg)
    x, y, width, height = map(float, root.attrib["viewBox"].split())
    root.set("viewBox", f"{x} {y} {width / ratio} {height}")
    after = copy.copy(before)
    after.geom = copy.copy(before.geom)
    after.geom.canvas_w = width / ratio
    after.svg = ET.tostring(root)
    monkeypatch.setattr(rules, "check", lambda sp, geom, data: [
        rules.Violation(rule, ("edge:0",), "readability defect")
    ] if data == before.svg else [])
    guard = layout.RuleGuard(selection=True)
    guard.min_text_size = layout.drawn_text(spec, before.svg)[0][0] * 0.9
    assert guard.accepts(before, before.svg, after, after.svg, later=False) is accepted


@pytest.mark.parametrize("rule", ["R-border", "R-flow", "R-rt"])
@pytest.mark.parametrize("mode", ["document", "slide"])
@pytest.mark.parametrize("above_target", [True, False])
def test_target_size_controls_the_text_shrink_exception(monkeypatch, rule, mode, above_target):
    spec = layout_spec.load({
        "name": "target-exception", "text_scale": 2,
        "cols": ["a", {"id": "b", "min_gap_before": 950}], "rows": ["r"],
        "nodes": [{"id": n, "icon": "service/AWS-Lambda", "label": n, "at": [n, "r"]}
                  for n in ("a", "b")], "edges": [{"e": "a -> b"}],
    }, mode=mode)
    before = layout.build(spec, [], {}, None, "target-exception.json")
    original, _, target, _ = layout.drawn_text(spec, before.svg)[0]
    desired = target + 1 if above_target else target - 0.5
    ratio = desired / original
    assert ratio < 0.9
    root = ET.fromstring(before.svg)
    x, y, width, height = map(float, root.attrib["viewBox"].split())
    root.set("viewBox", f"{x} {y} {width / ratio} {height}")
    after = copy.copy(before)
    after.geom = copy.copy(before.geom)
    after.geom.canvas_w = width / ratio
    after.svg = ET.tostring(root)
    assert layout.drawn_text(spec, after.svg)[0][0] == pytest.approx(desired)
    monkeypatch.setattr(rules, "check", lambda sp, geom, data: [
        rules.Violation(rule, ("edge:0",), "readability defect")
    ] if data == before.svg else [])
    guard = layout.RuleGuard(selection=True)
    guard.min_text_size = original * 0.9
    assert guard.accepts(before, before.svg, after, after.svg, later=False) is above_target


@pytest.mark.parametrize("mode", ["document", "slide"])
@pytest.mark.parametrize("candidate_build", [False, True], ids=["held", "candidate-internal"])
@pytest.mark.parametrize("benefit", ["hard-count", "hard-cost", "checks"])
@pytest.mark.parametrize("ratio,below_target,accepted", [
    (0.99, True, True), (0.989, True, False),
    (0.95, False, True),
])
def test_later_shrink_requires_fewer_tier_zero_violations(
        monkeypatch, mode, candidate_build, benefit, ratio, below_target, accepted):
    spec = layout_spec.load({
        "name": "repair-text", "text_scale": "off",
        "cols": ["a", {"id": "b", "min_gap_before": 1450}], "rows": ["r"],
        "nodes": [{"id": n, "icon": "service/AWS-Lambda", "label": n, "at": [n, "r"]}
                  for n in ("a", "b")], "edges": [{"e": "a -> b"}],
    }, mode=mode)
    before = layout.build(spec, [], {}, None, "repair-text.json")
    original, _, target, _ = layout.drawn_text(spec, before.svg)[0]
    desired = target - 1 if below_target else target
    root = ET.fromstring(before.svg)
    x, y, width, height = map(float, root.attrib["viewBox"].split())
    width *= original / desired
    before.geom.canvas_w = width
    root.set("viewBox", f"{x} {y} {width} {height}")
    before.svg = ET.tostring(root)
    after = copy.copy(before)
    after.geom = copy.copy(before.geom)
    after.geom.canvas_w = width / ratio
    root.set("viewBox", f"{x} {y} {width / ratio} {height}")
    after.svg = ET.tostring(root)
    old_violation = rules.Violation("R-flow", ("edge:0",), "F3 junction", code="F3", cost=2)
    new_violation = rules.Violation("R-flow", ("edge:0",), "F3 junction", code="F3",
                                    cost=1 if benefit == "hard-cost" else 2)
    monkeypatch.setattr(rules, "check", lambda sp, geom, data:
                        [old_violation] if data == before.svg else
                        [] if benefit == "hard-count" else [new_violation])
    guard = layout.RuleGuard(selection=True, min_text_size=desired * 0.9,
                             candidate_build=candidate_build)
    monkeypatch.setattr(guard, "problems", lambda data:
                        ["LINE OVER ICON", "LINE OVER TEXT"]
                        if benefit == "checks" and data == before.svg else [])
    expected = accepted or benefit == "hard-count"
    assert guard.accepts(before, before.svg, after, after.svg) is expected
    # Search retains ticket 06's fixed floor, rather than the repair tolerance.
    assert guard.accepts(before, before.svg, after, after.svg, later=False)


def test_candidate_feedback_shrink_requires_tier_zero_reduction(tmp_path, capsys, monkeypatch):
    """Candidate feedback may shrink only to remove a hard violation."""
    admits = layout.RuleGuard.admits
    comparisons = []

    def watch(guard, before, old, after, new, later=True):
        accepted = admits(guard, before, old, after, new, later=later)
        if guard.candidate_build and later:
            actual, _, target, _ = guard.text(before.spec, old)[0]
            next_actual = guard.text(after.spec, new)[0][0]
            comparisons.append((actual, next_actual, accepted))
            if accepted and actual < target and next_actual < actual * layout.REPAIR_TEXT_RETENTION - 1e-9:
                old_count = sum(v.tier == 0 for v in guard.check(before.spec, before.geom, old))
                new_count = sum(v.tier == 0 for v in guard.check(after.spec, after.geom, new))
                assert new_count < old_count
        return accepted

    monkeypatch.setattr(layout.RuleGuard, "admits", watch)
    source = ROOT / "tests/corpus/qa/t1-privatelink.layout.yaml"
    _, draft, _ = invoke(source, tmp_path, capsys, "--mode", "slide")
    assert comparisons
    spec = layout_spec.load(source, mode="slide")
    baseline = default(source, tmp_path, "slide")
    assert layout.drawn_text(spec, draft)[0][0] >= (
        layout.drawn_text(spec, baseline[1])[0][0] * layout.MIN_TEXT_RETENTION)


def test_build_cache_reuses_effective_decisions(monkeypatch):
    spec = layout_spec.load({
        "name": "build-cache", "cols": ["a", "b"], "rows": ["r"],
        "nodes": [{"id": n, "icon": "service/AWS-Lambda", "label": n, "at": [n, "r"]}
                  for n in ("a", "b")], "edges": [{"e": "a -> b"}],
        "note": {"place": "auto", "summary": "same note"},
    })
    real_build = layout.build
    calls = []

    def watch(*args, **kwargs):
        calls.append(1)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(layout, "build", watch)
    guard = layout.RuleGuard(build_cache={})
    first = guard.build(spec, [], {0: 1}, "pane", "cache.yaml")
    explicit = layout.layout_solve.Decisions(skip=((0, 1),), place="pane")
    replay = guard.build(spec, [], {}, None, "cache.yaml", decisions=explicit)
    assert replay.svg == first.svg
    assert replay.decisions == first.decisions
    assert len(calls) == 1
    # Font changes still need a new solve and drawing.
    scaled = copy.deepcopy(spec)
    scaled.font_factor = 1.1
    assert guard.build(scaled, [], {}, None, "cache.yaml", decisions=explicit) is not first
    assert len(calls) == 2


def test_fixed_answer_cache_is_shared_only_with_the_same_policy(tmp_path, monkeypatch):
    source = ROOT / "tests/corpus/ports/xnt.layout.yaml"
    spec = layout_spec.load(source)
    b = layout.build(spec, [], {}, None, str(source))
    real_fix = layout.fix_pass
    calls = []

    def watch(*args, **kwargs):
        calls.append(1)
        return real_fix(*args, **kwargs)

    monkeypatch.setattr(layout, "fix_pass", watch)
    first = layout.RuleGuard(selection=True)
    replay = layout.RuleGuard(selection=True)
    replay._checked = first._checked
    expected = layout.fixed_build(b, tmp_path / "fix.svg", first)
    assert layout.fixed_build(b, tmp_path / "fix.svg", replay) == expected
    assert len(calls) == 1
    # The fixed default floor can change whether an edit is eligible.
    replay.min_text_size = 11
    layout.fixed_build(b, tmp_path / "fix.svg", replay)
    assert len(calls) == 2


def test_fixed_answer_cache_preserves_explicit_held_draft(tmp_path):
    source = ROOT / "tests/corpus/ports/xnt.layout.yaml"
    spec = layout_spec.load(source)
    b = layout.build(spec, [], {}, None, str(source))
    guard = layout.RuleGuard(selection=True)
    data, _ = layout.fixed_build(b, tmp_path / "fix.svg", guard)
    held = data.replace(b"</svg>", b"<!-- selected incumbent --></svg>")
    # render_checked hands over an already selected/fixed drawing this way.
    b._fixed_draft = (b.svg, guard, (held, 7))
    assert layout.fixed_build(b, tmp_path / "fix.svg", guard) == (held, 7)


def test_build_cache_reuses_the_note_place_the_same_solve_already_chose(monkeypatch):
    source = ROOT / "tests/corpus/bench/engine2-egress.layout.yaml"
    spec = layout_spec.load(source, mode="slide", title=False)
    real_build = layout.build
    calls = []

    def watch(*args, **kwargs):
        calls.append(1)
        return real_build(*args, **kwargs)

    monkeypatch.setattr(layout, "build", watch)
    guard = layout.RuleGuard(build_cache={})
    first = guard.build(spec, [], {}, None, str(source))
    explicit = layout.dataclasses.replace(first.decisions, place=first.nb.place)
    expected = real_build(spec, [], {}, None, str(source), decisions=explicit)
    replay = guard.build(spec, [], {}, None, str(source), decisions=explicit)
    assert replay.svg == expected.svg
    assert replay.decisions == expected.decisions
    assert len(calls) == 1


@pytest.mark.parametrize("change,accepted", [
    ("owners", False), ("code", False), ("rule", False),
    ("reordered-owners", True), ("coordinates", True), ("lower-count", True),
])
def test_tier_zero_identity_gate_precedes_the_verdict(monkeypatch, change, accepted):
    spec = layout_spec.load({
        "name": "identity", "text_scale": "off",
        "cols": ["a", "b"], "rows": ["r"],
        "nodes": [{"id": n, "icon": "service/AWS-Lambda", "label": n, "at": [n, "r"]}
                  for n in ("a", "b")], "edges": [{"e": "a -> b"}],
    })
    before = layout.build(spec, [], {}, None, "identity.json")
    old = rules.Violation("R-flow", ("edge:0", "edge:1"), "junction at (100,100)",
                          cost=2, code="F3")
    next_rule = "R-label" if change == "rule" else "R-flow"
    next_code = "F5" if change == "code" else "F3"
    owners = (("edge:1", "edge:0") if change == "reordered-owners" else
              ("edge:0", "edge:2") if change in {"owners", "lower-count"} else old.owners)
    new = rules.Violation(next_rule, owners, "junction at (200,200)", cost=1, code=next_code)
    old_viol = [old]
    if change == "lower-count":
        old_viol.append(rules.Violation("R-flow", ("edge:3",), "other junction", code="F3"))
    new_data = before.svg.replace(b"</svg>", b"<!-- new drawing --></svg>")
    monkeypatch.setattr(rules, "check", lambda sp, geom, data:
                        old_viol if data == before.svg else [new])
    # R-label is not enabled for search, but its new identity must still be gated.
    guard = layout.RuleGuard(selection=True, enabled_rules={"R-flow"})
    assert guard.verdict(before, new_data) < guard.verdict(before, before.svg)
    assert guard.accepts(before, before.svg, before, new_data) is accepted
    assert guard.accepts(before, before.svg, before, new_data, later=False) is accepted


@pytest.mark.parametrize("title", [True, False], ids=["slide", "slide-no-title"])
def test_shared_lane_target_sized_winner_restores_label_attribution(tmp_path, capsys, title):
    source = ROOT / "tests/corpus/qa/t4-shared-lane.layout.yaml"
    before = default(source, tmp_path, "slide", title)
    args = ["--mode", "slide"] + ([] if title else ["--no-title"])
    _, draft, text = invoke(source, tmp_path, capsys, *args)
    original = layout.drawn_text(before[0].spec, before[1])[0][0]
    actual, _, target, _ = layout.drawn_text(before[0].spec, draft)[0]
    assert "rule: R-flow" not in text
    assert actual >= target
    if title:
        assert actual < original * 0.9
    assert not CL.run_checks(ET.fromstring(draft))


def test_multiregion_document_keeps_the_flow_improvement(tmp_path, capsys):
    source = ROOT / "tests/corpus/qa/t1-multiregion-dr.layout.yaml"
    status, draft, text = invoke(source, tmp_path, capsys, "--mode", "document")
    assert status == 0
    assert "rule: R-flow" not in text
    assert not CL.run_checks(ET.fromstring(draft))


@pytest.mark.xfail(strict=True, raises=AssertionError,
                   reason="Backlog: check_layout lacks text occlusion by later opaque fills")
def test_gw_ret_response_label_is_not_covered_by_note_background(tmp_path, capsys):
    source = ROOT / "tests/corpus/rt/gw-ret.layout.yaml"
    _, draft, _ = invoke(source, tmp_path, capsys, "--mode", "document")
    root = ET.fromstring(draft)
    order = {id(el): n for n, el in enumerate(root.iter())}
    texts = [t for t in CL.collect(root)[0]
             if t["s"] == "응답" and (t["own"] or "").startswith("edge:")]
    assert len(texts) == 2
    for text in texts:
        for rect in root.iter(f"{{{layout.SVG_NS}}}rect"):
            if (order[id(rect)] <= order[id(text["el"])]
                    or rect.get("fill", "none") == "none"):
                continue
            x, y, w, h = (float(rect.get(k, 0)) for k in ("x", "y", "width", "height"))
            a, b, c, d = text["box"]
            assert not (max(x, a) < min(x + w, c) and max(y, b) < min(y + h, d)), (
                f"{text['own']} at y={text['y']} is occluded by later rect at y={y}")


BEDROCK_DX = ROOT / "docs/examples/specs/bedrock-dx-reference-architecture.layout.yaml"


def test_all_tier_zero_rules_count_in_the_verdict(tmp_path):
    before = default(BEDROCK_DX, tmp_path, "slide")
    b, draft, _, problems, *_ = before
    violations = rules.check(b.spec, b.geom, draft)
    verdict = layout.RuleGuard(selection=True).verdict(b, draft, problems)
    hard = [v for v in violations if v.tier == 0]
    assert any(v.rule == "R-label" for v in hard)
    assert verdict.tier_0_count == len(hard)
    assert verdict.tier_0_cost == round(sum(v.cost for v in hard), 3)


def test_label_violation_skips_its_edge_route(tmp_path, capsys):
    before = default(BEDROCK_DX, tmp_path, "slide")
    assert any(v.rule == "R-label" and v.owners == ("edge:2",)
               for v in rules.check(before[0].spec, before[0].geom, before[1]))
    status, draft, text = invoke(BEDROCK_DX, tmp_path, capsys, "--mode", "slide")
    assert "rule: R-label" not in text
    assert "skip edges[2]=" in text and "removed R-label L1 ×1" in text
    assert len(CL.run_checks(ET.fromstring(draft))) <= len(CL.run_checks(ET.fromstring(before[1])))
    assert invoke(BEDROCK_DX, tmp_path, capsys, "--mode", "slide")[1] == draft


def test_header_conflict_flips_the_overlay_header(tmp_path, capsys):
    source = ROOT / "tests/corpus/twin/three.layout.yaml"
    before = default(source, tmp_path, "slide")
    assert any(v.rule == "R-border" and "group:asg" in v.owners
               for v in rules.check(before[0].spec, before[0].geom, before[1]))
    _, draft, text = invoke(source, tmp_path, capsys, "--mode", "slide")
    assert "overlay asg header beside" in text
    assert "rule: R-border" not in text
    assert len(CL.run_checks(ET.fromstring(draft))) < len(CL.run_checks(ET.fromstring(before[1])))


def test_pinned_overlay_header_is_not_flipped(tmp_path, capsys):
    source = ROOT / "tests/corpus/twin/three.layout.yaml"
    document = layout_spec._read(source)[0]
    overlay = next(g for g in document["groups"] if g["id"] == "asg")
    overlay["header"] = "right"
    pinned = tmp_path / "pinned.json"
    pinned.write_text(json.dumps(document))
    _, _, text = invoke(pinned, tmp_path, capsys, "--mode", "slide")
    assert "overlay asg header" not in text


def test_enabling_twins_and_labels_keeps_the_previous_groups_winner(tmp_path, capsys, monkeypatch):
    with monkeypatch.context() as prior:
        prior.setattr(layout, "SELECTION_RULES", frozenset(("R-border", "R-flow", "R-rt")))
        _, before, old_text = invoke(BEDROCK_DX, tmp_path, capsys, "--mode", "slide")
    _, after, text = invoke(BEDROCK_DX, tmp_path, capsys, "--mode", "slide")
    for rule in ("R-border", "R-flow", "R-rt"):
        assert text.count(f"rule: {rule}") <= old_text.count(f"rule: {rule}")
    assert text.count("rule: R-label") < old_text.count("rule: R-label")
    assert len(CL.run_checks(ET.fromstring(after))) <= len(CL.run_checks(ET.fromstring(before)))
