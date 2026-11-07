"""Later stages keep the retained draft when a repair adds a rule violation."""
import copy
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import layout
import layout_spec
import rules


def spec_data(gap=300):
    return {
        "name": "guard", "text_scale": "off",
        "cols": ["a", {"id": "b", "min_gap_before": gap}], "rows": ["r"],
        "nodes": [{"id": n, "icon": "service/AWS-Lambda", "label": n.upper(),
                   "at": [n, "r"]} for n in ("a", "b")],
        "edges": [{"e": "a -> b"}],
    }


@pytest.mark.parametrize("rule,code", [
    ("R-flow", "F3"), ("R-rt", "RT1"), ("R-twin", "T1"),
    ("R-label", "L1"), ("R-border", "B2"), ("R-fit", "FIT"),
])
def test_feedback_rejects_new_violation(tmp_path, monkeypatch, rule, code):
    spec = layout_spec.load(spec_data())
    before = layout.build(spec, [], {}, None, "guard.json")
    after = layout.build(layout_spec.load(spec_data(350)), [], {}, None, "guard.json")
    problem = layout.Problem(SimpleNamespace(kind="SHORT ARROW"), ["edge:0"], [])
    monkeypatch.setattr(layout, "problems_of",
                        lambda data, *a, **kw: ([problem] if data == before.svg else [], None, []))
    monkeypatch.setattr(layout, "feedback", lambda *a: True)
    builds = iter((before, after))
    monkeypatch.setattr(layout, "build", lambda *a, **kw: next(builds))
    monkeypatch.setattr(rules, "check", lambda sp, geom, data: [
        rules.Violation(rule, ("edge:0",), "new violation", code=code)
    ] if geom is after.geom else [])
    result = layout.render_checked(spec, "guard.json", tmp_path / "round.svg", max_rounds=1)
    assert result[1] == before.svg


def test_header_repair_rejects_new_violation(tmp_path, monkeypatch):
    spec = layout_spec.load(spec_data())
    before = layout.build(spec, [], {}, None, "guard.json")
    after = layout.build(layout_spec.load(spec_data(350)), [], {}, None, "guard.json")
    old = layout.Problem(SimpleNamespace(kind="LINE IN HEADER"), ["edge:0"], [])
    monkeypatch.setattr(layout, "problems_of",
                        lambda data: ([old] if data == before.svg else [], None, []))
    monkeypatch.setattr(layout, "feedback", lambda *a: True)
    monkeypatch.setattr(layout, "build", lambda *a, **kw: after)
    monkeypatch.setattr(rules, "check", lambda sp, geom, data: [
        rules.Violation("R-border", ("edge:0",), "B2 crossing", code="B2")
    ] if geom is before.geom else [
        rules.Violation("R-flow", ("edge:0",), "F3 new crossing", code="F3")
    ])
    result = layout.repair_headers(before, 0, [], {}, "guard.json",
                                   tmp_path / "round.svg", max_rounds=1)
    assert result[1].svg == before.svg


def test_fixed_answer_rejects_new_violation(tmp_path, monkeypatch):
    document = spec_data()
    document["raw"] = [{"layer": "above", "svg":
                       '<text x="150" y="90" font-size="8">Tiny annotation</text>'}]
    spec = layout_spec.load(document)
    before = layout.build(spec, [], {}, None, "guard.json").svg
    monkeypatch.setattr(rules, "check", lambda sp, geom, data: [
        rules.Violation("R-label", ("raw:0",), "L1 new violation", code="L1")
    ] if b'font-size="12">Tiny annotation' in data else [])
    result = layout.render_checked(spec, "guard.json", tmp_path / "round.svg")
    assert result[1] == before
    assert result[2] == 0


@pytest.mark.parametrize("case", ["feedback", "header", "fixed", "text"])
def test_checker_failure_writes_draft_and_warns_once(tmp_path, monkeypatch, capsys, case):
    if case in {"feedback", "header"}:
        source = ROOT / f"tests/corpus/flowcol/{'r2-float-two-wide' if case == 'feedback' else 't7-xyref'}.layout.yaml"
    else:
        document = spec_data(950 if case == "text" else 300)
        if case == "text":
            document["text_scale"] = "auto"
            for node in document["nodes"]:
                node["sub"] = "Details"
        else:
            document["raw"] = [{"layer": "above", "svg":
                               '<text x="150" y="90" font-size="8">Tiny annotation</text>'}]
        source = tmp_path / "guard.json"
        source.write_text(json.dumps(document))
    monkeypatch.setattr(rules, "check", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("forced")))
    draft = tmp_path / "guard.svg"
    layout.main([str(source), "-o", str(draft)])
    output = capsys.readouterr().out
    assert draft.read_bytes().startswith(b"<svg")
    assert output.count("rule: checker error") == 1
    if case == "text":
        assert 'data-text-scale="' in draft.read_text()


def test_transient_checker_failure_is_reported_once(tmp_path, monkeypatch, capsys):
    source = tmp_path / "guard.json"
    source.write_text(json.dumps(spec_data()))
    real_check = rules.check
    calls = 0

    def check(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")
        return real_check(*args, **kwargs)

    monkeypatch.setattr(rules, "check", check)
    draft = tmp_path / "guard.svg"
    assert layout.main([str(source), "-o", str(draft)]) == 0
    assert draft.exists()
    assert capsys.readouterr().out.count("rule: checker error") == 1


def test_branch_checker_failure_keeps_text_scale_available(tmp_path, monkeypatch, capsys):
    document = spec_data(950)
    document["text_scale"] = "auto"
    for node in document["nodes"]:
        node["sub"] = "Details"
    source = tmp_path / "guard.json"
    source.write_text(json.dumps(document))

    def broken(*args):
        raise RuntimeError("branch information unavailable")

    monkeypatch.setattr(layout, "trunk_badge_branches", broken)
    draft = tmp_path / "guard.svg"
    layout.main([str(source), "-o", str(draft)])
    assert 'data-text-scale="' in draft.read_text()
    assert capsys.readouterr().out.count("rule: checker error") == 1


def test_text_scale_rejects_new_violation(tmp_path, monkeypatch):
    document = spec_data(950)
    document["text_scale"] = "auto"
    spec = layout_spec.load(document)
    original = layout.render_checked(spec, "guard.json", tmp_path / "round.svg")
    trial = copy.deepcopy(spec)
    trial.font_factor = 1.5
    candidate = layout.render_checked(trial, "guard.json", tmp_path / "round.svg")
    results = iter((original, candidate))
    monkeypatch.setattr(layout, "render_checked", lambda *a, **kw: next(results))
    monkeypatch.setattr(rules, "check", lambda sp, geom, data: [
        rules.Violation("R-flow", ("edge:0",), "F3 crossing", code="F3")
    ] if sp.font_factor > 1 else [])
    assert layout.render_readable(spec, "guard.json", tmp_path / "round.svg")[1] == original[1]


def test_guards_keep_the_chosen_readable_draft(tmp_path):
    """Guard later stages against the chosen draft, rather than an unfinished round."""
    spec = layout_spec.load(ROOT / "tests/corpus/rt/sgw-ret.layout.yaml", mode="slide")
    scratch = tmp_path / "round.svg"
    chosen = layout.render_readable(spec, "sgw-ret.layout.yaml", scratch,
                                    rule_guard=layout.RuleGuard(protect=False))
    b, draft, _, problems, *_ = layout.render_readable(
        chosen[0].spec, "sgw-ret.layout.yaml", scratch, chosen=chosen)
    violations = rules.check(b.spec, b.geom, draft)
    assert not [v for v in violations if v.tier == rules.TIER_HARD]
    assert [v for v in violations if v.rule == "R-fit"]
    assert not problems


def test_verdict_failure_still_writes_chosen_draft(tmp_path, monkeypatch, capsys):
    document = spec_data()
    document["raw"] = [{"layer": "above", "svg":
                       '<text x="150" y="240" font-size="12">Outside annotation</text>'}]
    source = tmp_path / "guard.json"
    source.write_text(json.dumps(document))

    def broken(*args):
        raise RuntimeError("verdict unavailable")

    monkeypatch.setattr(rules, "score", broken)
    draft = tmp_path / "guard.svg"
    layout.main([str(source), "-o", str(draft)])
    assert draft.read_bytes().startswith(b"<svg")
    assert capsys.readouterr().out.count("rule: checker error") == 1
