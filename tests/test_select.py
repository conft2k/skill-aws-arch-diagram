"""Selection is judged through the CLI's draft, violations and summary."""
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
