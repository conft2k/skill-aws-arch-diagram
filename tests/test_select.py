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


def default(source, tmp_path, mode=None):
    spec = layout_spec.load(source, mode=mode)
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
    assert "rule: R-rt" not in old_text and "rule: R-rt" not in text
    spec = layout_spec.load(source, mode="slide")
    assert layout.drawn_text(spec, after)[0][0] >= layout.drawn_text(spec, before)[0][0]
    assert len(CL.run_checks(ET.fromstring(after))) <= len(CL.run_checks(ET.fromstring(before)))
    evaluated, budget = map(int, re.search(r"evaluated (\d+)/(\d+) candidates", text).groups())
    assert evaluated <= budget == 16


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
    assert guard.accepts(before, before.svg, after, after.svg) is accepted
