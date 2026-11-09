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
    # (t3-dns-trunk slide's F1 is gone since line-cross 03's shape move: order-14steps keeps one)
    ("qa/t4-order-14steps", "slide", "R-flow", "F1", "from_offset / to_offset"),
    ("qa/t3-cache-label", "slide", "R-flow", "F5", "label_at: above|below|left|right"),
    ("qa/t4-order-14steps", "slide", "R-flow", "F5", "label_at: above|below|left|right"),
    # line-cross 01: F6 leads with its own try value (the piece or the node moved clear)
    # (t3-ssm-trunk slide's F6 is gone since line-cross 02's channel move, t3-dns-trunk slide's
    # and nat-route-table's rt.1 since line-cross 03's shape move; rt.2 keeps its own)
    ("qa/t3-nat-route-table", "slide", "R-flow", "F6", "rt.2 (NAT RT (Availability Zone 2)): dy: "),
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
    assert "edges[0] (a → b): step_at: start|end|gap|[x, y]" in warning


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


# stage 5 (actionable hints): F3 / F4 / F5 lead with a value; applied to the spec and drawn
# again, that violation is gone (the hint names a real field that moves the thing)

def applied(source, tmp_path, item, key, value):
    import yaml
    spec = yaml.safe_load(source.read_text())
    kind, idx = re.match(r"(\w+)\[(\d+)\]", item).groups()
    spec[kind][int(idx)][key] = yaml.safe_load(value)
    out = tmp_path / "applied.layout.yaml"
    out.write_text(yaml.safe_dump(spec, allow_unicode=True))
    return out


def hint_value(line, item, key):
    m = re.search(re.escape(item) + r"(?: \S+ \S+:)? [^;]*?\b" + re.escape(key) + r": (\{[^}]*\}|[^\s;,()]+)", line)
    assert m, line
    return m.group(1)


@pytest.mark.parametrize(("case", "mode", "code", "owner", "item", "key"), [
    ("ports/u3", "document", "F3", "edge:3", "edges[3]", "from_offset"),
    ("ports/g1", "slide", "F3", "edge:0", "edges[0]", "bend_y"),
    ("qa/t2-false-junction", "slide", "F5", "edge:1", "edges[1]", "label_at"),
    ("qa/t4-order-14steps", "slide", "F5", "edge:14", "edges[14]", "label_at"),
])
def test_flow_hint_value_clears_the_violation_when_applied(tmp_path, capsys, case, mode, code, owner, item, key):
    source = ROOT / f"tests/corpus/{case}.layout.yaml"
    _, _, text = draw(source, tmp_path, capsys, "--mode", mode)
    # messages name the edge by its spec entry and ends (layout_model.edge_name)
    owner = layout.M.edge_name(layout.layout_spec.load(source, mode=mode), int(owner.split(":")[1]))
    rule = f"rule: R-flow {code} {owner}"
    assert any(line.startswith(rule) for line in text.splitlines())
    warning = next(line for line in text.splitlines()
                   if line.startswith(f"warning: unresolved R-flow {code} ({owner}"))
    hint = warning.split("spec hint (not a guarantee): ", 1)[1]
    assert hint.startswith(item), hint          # the value leads, before the generic fields
    value = hint_value(hint, item, key)
    _, _, again = draw(applied(source, tmp_path, item, key, value), tmp_path, capsys, "--mode", mode)
    assert not any(line.startswith(rule) for line in again.splitlines()), again


def test_label_hint_is_relative_to_an_end_node(tmp_path, capsys):
    source = ROOT / "tests/corpus/qa/t2-false-junction.layout.yaml"
    _, _, text = draw(source, tmp_path, capsys, "--mode", "slide")
    warning = next(line for line in text.splitlines() if line.startswith("warning: unresolved R-flow F5 "))
    assert re.search(r"label_at: \{x: \w+\.cx[+-]\d+, y: \w+\.cy[+-]\d+, anchor: \w+\}", warning), warning


def test_label_point_is_not_suggested_for_a_line_drawn_several_times(tmp_path, capsys):
    # t3-ssm-trunk's edges[1] is `ec2.* ..> ep.*`: one point would stack both labels
    source = ROOT / "tests/corpus/qa/t3-ssm-trunk.layout.yaml"
    _, _, text = draw(source, tmp_path, capsys, "--mode", "document")
    warning = next(line for line in text.splitlines() if line.startswith("warning: unresolved R-flow F5 "))
    assert "label_at: {" not in warning


def test_label_rule_hint_gives_a_spot_above_the_line(tmp_path, capsys, monkeypatch):
    source = tmp_path / "l1.json"
    source.write_text(json.dumps({
        "name": "l1", "text_scale": "off", "cols": ["a", "b"], "rows": ["r"],
        "nodes": [{"id": n, "icon": "service/AWS-Lambda", "label": n, "at": [n, "r"]} for n in ("a", "b")],
        "edges": [{"e": "a -> b", "label": "HTTPS :443", "label_at": "below"}],
    }))
    real = rules.check
    monkeypatch.setattr(rules, "check", lambda *a, **kw: real(*a, **kw) + [
        rules.Violation("R-label", ("edge:0",), "L1 edge:0's label 'HTTPS :443' is below its line", code="L1")])
    _, draft, text = draw(source, tmp_path, capsys)
    warning = next(line for line in text.splitlines() if line.startswith("warning: unresolved R-label L1 "))
    m = re.search(r"label_at: \{x: (\S+), y: (\S+), anchor: (\w+)\}.*at \((-?[\d.]+),(-?[\d.]+)\) now", warning)
    assert m, warning
    line_y = float(re.search(rb'<g id="edge:0">\s*<line [^>]*y1="([\d.]+)"', draft).group(1))
    assert float(m.group(5)) < line_y        # the baseline it names sits above the line


def test_author_bend_collision_names_what_it_hits_and_the_nearest_clear_value(tmp_path, capsys):
    source = ROOT / "tests/corpus/qa/t1-privatelink.layout.yaml"
    _, _, text = draw(source, tmp_path, capsys, "--mode", "slide")
    warning = next(line for line in text.splitlines()
                   if line.startswith("warning: edges[11] s3b ..> s3 (") and "best of the candidates" in line)
    assert ("LINE OVER ICON of S3 gateway EP (Consumer A VPC)" in warning
            and "LINE OVER TEXT 'S3' of S3 (" in warning and "LINE HUGS BORDER of Provider AZ 1" in warning)
    value = re.search(r"try bend_y: (\S+) \(= [\d.]+; row\.main-90 = 180 now\), the nearest clear value",
                      warning).group(1)
    _, _, again = draw(applied(source, tmp_path, "edges[11]", "bend_y", value), tmp_path, capsys,
                       "--mode", "slide")
    assert "edges[11] s3b ..> s3 (" not in again
    assert "rule: R-flow F6 edge:12" not in again and "rule: R-flow F1 " not in again


def test_author_points_collision_suggests_the_nearest_clear_piece_value(tmp_path, capsys):
    import yaml
    spec = {"name": "pts", "mode": "document", "text_scale": "off",
            "cols": ["c1", {"id": "c2", "min_gap_before": 120}, {"id": "c3", "min_gap_before": 120}],
            "rows": ["r0", "r1"], "groups": [{"id": "cloud", "type": "cloud"}],
            "nodes": [{"id": "m", "icon": "service/AWS-Lambda", "label": "M", "in": "cloud", "at": ["c2", "r0"]},
                      {"id": "a", "icon": "service/AWS-Lambda", "label": "A", "in": "cloud", "at": ["c1", "r1"]},
                      {"id": "b", "icon": "service/AWS-Lambda", "label": "B", "in": "cloud", "at": ["c3", "r1"]}],
            "edges": [{"e": "a -> b", "points": [["a.cx", "a.y0"], ["a.cx", "m.cy"], ["b.cx", "m.cy"],
                                                 ["b.cx", "b.y0"]]}]}
    source = tmp_path / "pts.layout.yaml"
    source.write_text(yaml.safe_dump(spec))
    _, _, text = draw(source, tmp_path, capsys)
    warning = next(line for line in text.splitlines() if line.startswith("warning: edges[0] a -> b (A → B): points: "))
    assert "LINE OVER ICON of M" in warning and "of A" not in warning    # its own ends' touch is not a hit
    y = re.search(r"move the horizontal piece at y=[\d.]+ \(points 2–3\) to y=([\d.]+), the nearest clear value",
                  warning).group(1)
    spec["edges"][0]["points"] = [["a.cx", "a.y0"], ["a.cx", float(y)], ["b.cx", float(y)], ["b.cx", "b.y0"]]
    source.write_text(yaml.safe_dump(spec))
    _, _, again = draw(source, tmp_path, capsys)
    assert again.splitlines()[-1] == "Layout OK", again


def test_slide_too_small_names_the_note_and_drops_circular_slide_advice(tmp_path, capsys):
    source = ROOT / "tests/corpus/slide-fit/nfw-doc.layout.yaml"
    _, _, text = draw(source, tmp_path, capsys, "--mode", "slide")
    small = next(line for line in text.splitlines() if line.startswith("SLIDE TOO SMALL "))
    assert "too tall" in small and "— the note under the drawing takes 122px of the height: shorten the steps" in small
    floor = next(line for line in text.splitlines() if line.startswith("warning: smallest text "))
    assert floor.endswith("; split the diagram")       # the run is a slide already
    # a document spec drawn with --mode slide still learns it can become a slide spec
    assert "write a slide spec (see docs/examples/specs/slides/)" in text.splitlines()[-1]


@pytest.mark.parametrize(("case", "mode"), [
    ("lanes/a", "slide"),
    # r's dx is taken back by the solver here: only moves that clear it when drawn again
    ("xy/xy-off", "document"),
    # s is pinned with xy on q: its xy is moved past q's footprint
    ("sides/xy3", "document"),
])
def test_every_offered_f4_move_clears_it_when_applied(tmp_path, capsys, case, mode):
    source = ROOT / f"tests/corpus/{case}.layout.yaml"
    _, _, text = draw(source, tmp_path, capsys, "--mode", mode)
    warning = next(line for line in text.splitlines() if line.startswith("warning: unresolved R-flow F4 "))
    hint = warning.split("spec hint (not a guarantee): ", 1)[1].split(" (each drawn again", 1)[0]
    moves = re.findall(r"(nodes\[\d+\]) [^:;]*?: (dx|dy|xy): (\[[^\]]*\]|-?[\d.]+)", hint)
    assert moves, warning
    for item, key, value in moves:
        _, _, again = draw(applied(source, tmp_path, item, key, value), tmp_path, capsys, "--mode", mode)
        # each case has one F4 (that arrowhead): none may remain
        assert not any(line.startswith("rule: R-flow F4 ") for line in again.splitlines()), \
            (item, key, value, again)


def test_no_value_says_why(tmp_path, capsys):
    source = ROOT / "tests/corpus/trunk/merge-v3az-top.layout.yaml"
    _, _, text = draw(source, tmp_path, capsys, "--mode", "slide", "--no-title")
    warning = next(line for line in text.splitlines() if line.startswith("warning: unresolved R-flow F3 "))
    assert ("spec hint (not a guarantee): no value: edges[2] (ALB → EC2 (Availability Zone 1), ALB → EC2 "
            "(Availability Zone 2), ALB → EC2 (Availability Zone 3)) draws several lines (a trunk or a `.*` line)"
            in warning), warning


def test_f4_move_that_lands_the_arrowhead_on_a_third_node_is_not_offered(tmp_path, capsys):
    # sides/xy3 plus a node z where s's nearest xy move would put s: that move only trades q
    # for z (Codex re-review of s5-hints), so it must not be offered
    import yaml
    spec = yaml.safe_load((ROOT / "tests/corpus/sides/xy3.layout.yaml").read_text())
    q = next(n for n in spec["nodes"] if n["id"] == "q")
    spec["nodes"].append({**q, "id": "z", "label": "Z", "xy": ["q.cx+63", "q.cy"]})
    spec["nodes"][-1].pop("at", None)
    source = tmp_path / "xy3z.layout.yaml"
    source.write_text(yaml.safe_dump(spec))
    _, _, text = draw(source, tmp_path, capsys)
    warning = next(line for line in text.splitlines() if line.startswith("warning: unresolved R-flow F4 "))
    assert "xy: [q.cx+63, q.cy]" not in warning, warning
    hint = warning.split("spec hint (not a guarantee): ", 1)[1].split(" (each drawn again", 1)[0]
    for item, key, value in re.findall(r"(nodes\[\d+\]) [^:;]*?: (dx|dy|xy): (\[[^\]]*\]|-?[\d.]+)", hint):
        _, _, again = draw(applied(source, tmp_path, item, key, value), tmp_path, capsys)
        assert not any(line.startswith("rule: R-flow F4 ") for line in again.splitlines()), \
            (item, key, value, again)
