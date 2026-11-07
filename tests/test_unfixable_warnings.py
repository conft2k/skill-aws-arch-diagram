"""Unresolved rules give the spec author guidance without changing the draft."""
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import layout
import rules


def draw(source, tmp_path, capsys, *args):
    draft = tmp_path / "warning.svg"
    status = layout.main([str(source), "-o", str(draft), *args])
    return status, draft.read_bytes(), capsys.readouterr().out


@pytest.mark.parametrize(("case", "mode", "rule", "code", "hint"), [
    ("ports/u3", "document", "R-flow", "F3", "shape / bend_x / bend_y"),
    ("sides/xy3", "document", "R-flow", "F4", "dx / dy"),
    ("qa/t2-alb-trunk-header", "slide", "R-border", "B2", "pad / min_w / min_h"),
    ("qa/t3-dns-trunk", "slide", "R-flow", "F1", "from_offset / to_offset"),
    ("qa/t3-cache-label", "slide", "R-flow", "F5", "label_at: above|below|left|right"),
    ("qa/t4-order-14steps", "slide", "R-flow", "F5", "label_at: above|below|left|right"),
])
def test_each_remaining_enabled_violation_has_an_owner_hint(
        tmp_path, capsys, case, mode, rule, code, hint):
    source = ROOT / f"tests/corpus/{case}.layout.yaml"
    _, first, text = draw(source, tmp_path, capsys, "--mode", mode)
    violations = [line for line in text.splitlines()
                  if re.match(r"rule: (R-flow|R-border|R-fit) ", line)]
    warnings = [line for line in text.splitlines() if line.startswith("warning: unresolved ")]
    assert violations and len(warnings) == len(violations)
    matching = [line for line in warnings if line.startswith(f"warning: unresolved {rule} {code} ")]
    assert matching and any(hint in line for line in matching)
    assert all("spec hint (not a guarantee):" in line for line in warnings)
    assert all("edges[" in line or "canvas" in line for line in warnings)
    assert "rule violation" in text.splitlines()[-1]
    _, again, repeated = draw(source, tmp_path, capsys, "--mode", mode)
    assert again == first
    assert warnings == [line for line in repeated.splitlines()
                        if line.startswith("warning: unresolved ")]


def simple_source(tmp_path):
    source = tmp_path / "simple.json"
    source.write_text(json.dumps({
        "name": "simple", "text_scale": "off", "cols": ["a", "b"], "rows": ["r"],
        "nodes": [{"id": n, "icon": "service/AWS-Lambda", "label": n, "at": [n, "r"]}
                  for n in ("a", "b")], "edges": [{"e": "a -> b"}],
    }))
    return source


def test_no_applicable_owner_hint_explains_why_and_keeps_drawing(tmp_path, capsys, monkeypatch):
    source = simple_source(tmp_path)
    _, expected, clean = draw(source, tmp_path, capsys)
    assert "warning: unresolved" not in clean
    monkeypatch.setattr(rules, "check", lambda *a, **kw: [
        rules.Violation("R-border", ("canvas",), "B4 unsupported owner", code="B4")])
    _, draft, text = draw(source, tmp_path, capsys)
    assert draft == expected
    assert ("warning: unresolved R-border B4 (canvas); no spec hint: "
            "the existing spec-fix hints do not apply to these owners") in text
    assert text.splitlines()[-1].startswith("Layout OK — 1 rule violation remains")


def test_fit_is_enabled_and_disabled_rules_do_not_get_unfixable_warnings(
        tmp_path, capsys, monkeypatch):
    source = simple_source(tmp_path)
    # Keep this reporting test independent of the next ticket's enabled group.
    monkeypatch.setattr(layout, "SELECTION_RULES", frozenset(("R-flow", "R-border")))
    monkeypatch.setattr(rules, "check", lambda *a, **kw: [
        rules.Violation("R-rt", ("node:a",), "RT1 outside bracket", code="RT1"),
        rules.Violation("R-fit", ("canvas",), "FIT text below target", tier=2, code="FIT")])
    _, _, text = draw(source, tmp_path, capsys)
    assert "warning: unresolved R-rt" not in text
    assert "warning: unresolved R-fit FIT (canvas); spec hint (not a guarantee):" in text
    assert "text_scale" in text
    assert "rule: R-rt RT1" in text
    assert "2 rule violations remain" in text.splitlines()[-1]


def test_badge_attribution_suggests_step_place(tmp_path, capsys, monkeypatch):
    source = simple_source(tmp_path)
    monkeypatch.setattr(rules, "check", lambda *a, **kw: [
        rules.Violation("R-flow", ("edge:0",), "F5 edge:0's badge '1' is too far", code="F5")])
    _, _, text = draw(source, tmp_path, capsys)
    warning = next(line for line in text.splitlines()
                   if line.startswith("warning: unresolved R-flow F5 "))
    assert "edges[0]: step_at: start|end|gap|[x, y]" in warning


def test_no_check_and_checker_failure_do_not_invent_spec_hints(tmp_path, capsys, monkeypatch):
    source = simple_source(tmp_path)
    _, _, skipped = draw(source, tmp_path, capsys, "--no-check")
    assert "warning: unresolved" not in skipped

    def broken(*args, **kwargs):
        raise RuntimeError("checker unavailable")

    monkeypatch.setattr(rules, "check", broken)
    _, _, text = draw(source, tmp_path, capsys)
    assert "warning: unresolved" not in text
    assert text.count("rule: checker error") == 1
