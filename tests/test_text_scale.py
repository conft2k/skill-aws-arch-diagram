"""Text fit at the reader's slide/page size, and opt-in/out layout scaling."""
import sys
import copy
from collections import Counter
from pathlib import Path
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import layout_const as K
import layout
import layout_spec
import layout_text


@pytest.mark.parametrize("width,size,actual", [
    (666, 12, 12), (760, 11, 11), (1520, 22, 11), (1520, 18, 9), (1780, 12, 12 * 760 / 1780),
])
def test_document_effective_text(width, size, actual):
    value, unit, target, floor = K.effective_text("document", width, 100, size, True)
    assert value == pytest.approx(actual)
    assert (unit, target, floor) == ("px", 11, 9)


@pytest.mark.parametrize("title", [True, False])
def test_slide_effective_text(title):
    value, unit, target, floor = K.effective_text("slide", 1200, 700, 12, title)
    assert value == K.slide_pt(1200, 700, title, 12)
    assert (unit, target, floor) == ("pt", 10, 8)


@pytest.mark.parametrize("title", [True, False])
@pytest.mark.parametrize("boundary", [8, 10])
def test_slide_threshold_boundaries(title, boundary):
    width = K.SLIDE_AVAIL_W_PT * 12 / boundary
    height = K.SLIDE_AVAIL_H_PT[title] * 12 / boundary
    assert K.effective_text("slide", width, height, 12, title)[0] == pytest.approx(boundary)


def wide_spec(mode="document"):
    return {"name": "wide", "mode": mode, "cols": ["a", {"id": "b", "min_gap_before": 950}],
            "rows": ["main"],
            "nodes": [{"id": "a", "icon": "service/AWS-Lambda", "label": "First", "sub": "Details",
                       "at": ["a", "main"]},
                      {"id": "b", "icon": "service/AWS-Lambda", "label": "Second", "sub": "Details",
                       "at": ["b", "main"]}]}


def test_large_document_enlarges_toward_target(tmp_path):
    sp = layout_spec.load(wide_spec())
    before = layout.render_checked(sp, "wide.yaml", tmp_path / "round.svg")
    after = layout.render_readable(sp, "wide.yaml", tmp_path / "round.svg")
    old = layout.drawn_text(sp, before[1])[0][0]
    new = layout.drawn_text(after[0].spec, after[1])[0][0]
    assert old < 9
    assert new > old
    assert new >= 10.5
    assert not after[3]


def test_small_example_and_off_are_byte_identical(tmp_path):
    for sp in (layout_spec.load(ROOT / "docs/examples/specs/example.layout.yaml"),
               layout_spec.load({**wide_spec(), "text_scale": "off"})):
        before = layout.render_checked(sp, "same.yaml", tmp_path / "round.svg")
        after = layout.render_readable(sp, "same.yaml", tmp_path / "round.svg")
        assert before[1] == after[1]
        assert after[0].spec.font_factor == 1


def test_slide_enlarges_and_fixed_multiplier_does_not_retry(tmp_path):
    document = wide_spec("slide")
    document["cols"][1]["min_gap_before"] = 1300
    sp = layout_spec.load(document)
    before = layout.render_checked(sp, "wide.yaml", tmp_path / "round.svg")
    after = layout.render_readable(sp, "wide.yaml", tmp_path / "round.svg")
    assert layout.drawn_text(after[0].spec, after[1])[0][0] > layout.drawn_text(sp, before[1])[0][0]
    fixed = layout_spec.load({**document, "text_scale": 1.5})
    result = layout.render_readable(fixed, "wide.yaml", tmp_path / "round.svg")
    assert result[0].spec.font_factor == 1.5
    assert {int(t.get("font-size")) for t in ET.fromstring(result[1]).iter()
            if t.tag.endswith("}text")} == {18, 21}


@pytest.mark.parametrize("scale,expected", [("auto", 20), (1.5, 24), ("off", 16)])
def test_raw_default_font_scales_with_nodes(tmp_path, scale, expected):
    document = {**wide_spec(), "text_scale": scale,
                "raw": [{"layer": "above", "svg": '<text x="400" y="60">Raw annotation</text>'}]}
    sp = layout_spec.load(document)
    result = layout.render_readable(sp, "wide.yaml", tmp_path / "round.svg")
    texts = list(layout.CL.slide_texts(ET.fromstring(result[1])))
    assert next(size for size, text in texts if text == "Raw annotation") == expected
    assert not result[3]
    if scale == "off":
        assert result[1] == layout.render_checked(sp, "wide.yaml", tmp_path / "round.svg")[1]
        assert '<text x="400" y="60">Raw annotation</text>' in result[1].decode()


@pytest.mark.parametrize("scale,expected", [(1.5, [24, 24, 18]), ("off", [16, 16, 12])])
def test_raw_explicit_and_nested_inherited_fonts(tmp_path, scale, expected):
    fragment = ('<!-- 그대로 > 유지 -->'
                '<g font-size="16"><g transform="translate(0,0)">'
                '<text x="400" y="40">Inherited annotation</text>'
                '<text x="400" y="70" font-size="16">Explicit annotation</text>'
                '<g font-size="12"><text x="400" y="100" font-size="inherit">Nested annotation</text>'
                '</g></g></g>')
    sp = layout_spec.load({**wide_spec(), "text_scale": scale,
                           "raw": [{"layer": "above", "svg": fragment}]})
    result = layout.render_readable(sp, "wide.yaml", tmp_path / "round.svg")
    root = ET.fromstring(result[1])
    text_sizes = {text: size for size, text in layout.CL.slide_texts(root)}
    assert [text_sizes[text] for text in ("Inherited annotation", "Explicit annotation", "Nested annotation")] == expected
    assert "<!-- 그대로 > 유지 -->" in result[1].decode()
    assert all("font-size" not in group.attrib for group in root.iter() if group.tag.endswith("}g"))
    assert not result[3]


def test_raw_font_transform_preserves_unrelated_bytes_and_rounds_each_pass():
    source = '<g id="주석"><text x="400" y="60" font-size="12">한글 > text</text></g>'
    assert layout.scale_raw_text(source, 1) == source
    changed = layout.scale_raw_text(source, 3.24, (1.8, 1.8))
    assert changed == '<g id="주석"><text x="400" y="60" font-size="40">한글 > text</text></g>'
    quoted = '<text data-note="keep font-size=\'12\' > text" font-size=\'16\' x="400">Text</text>'
    assert layout.scale_raw_text(quoted, 1.5) == quoted.replace("font-size='16'", "font-size='24'")


@pytest.mark.parametrize("bad", [True, 0, -1, float("inf"), float("nan"), "large"])
def test_reject_invalid_scale(bad):
    with pytest.raises(layout.M.SpecError, match="text_scale"):
        layout_spec.load({**wide_spec(), "text_scale": bad})


def test_yaml_false_disables_scaling():
    assert layout_spec.load({**wide_spec(), "text_scale": False}).text_scale == "off"


def test_small_document_text_is_warning_without_check_problem(tmp_path, capsys):
    import json
    source = tmp_path / "wide.json"
    source.write_text(json.dumps({**wide_spec(), "text_scale": "off"}))
    assert layout.main([str(source), "-o", str(tmp_path / "wide.svg")]) == 0
    text = capsys.readouterr().out
    assert "in a 760px column (target 11)" in text
    assert "warning: smallest text" in text
    assert "split the diagram or write a mode: slide spec" in text
    assert "TEXT TOO SMALL" not in text
    assert "Layout OK" in text


def test_every_engine_font_uses_the_uniform_factor():
    sp = layout_spec.load(ROOT / "docs/examples/specs/centralized-egress.layout.yaml")
    before = layout.build(sp, [], {}, None, "same.yaml")
    scaled = copy.deepcopy(sp)
    scaled.font_factor = 1.5
    after = layout.build(scaled, [], {}, None, "same.yaml")
    def fonts(data):
        return {t.text: int(t.get("font-size")) for t in ET.fromstring(data).iter()
                if t.tag.endswith("}text")}
    original, enlarged = fonts(before.svg), fonts(after.svg)
    assert len(original) > 30  # node, sub, CIDR, titles, connector labels, note, badge
    # Larger notes may wrap into different strings; every unchanged label still
    # scales uniformly, and all newly wrapped fragments use the enlarged note font.
    assert all(enlarged[text] == layout_text.rounded(original[text], 1.5)
               for text in original.keys() & enlarged.keys())
    assert all(size == layout_text.rounded(K.TEXT_NOTE.size, 1.5)
               for text, size in enlarged.items() if text not in original)


@pytest.mark.parametrize("factor", [1.5, 1.8 * 1.8])
def test_wrapped_footer_uses_enlarged_words_and_contains_badges(factor):
    import layout_note as note
    from layout_model import Box, Geometry, NoteSpec, Spec
    sp = Spec(name="wrapped", mode="slide", note=NoteSpec())
    geom = Geometry("slide", 48, 500, 200, {}, {}, drawing=Box(16, 16, 484, 160))
    text = "alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu " * 3
    normal = note._wrapped_lines(sp, geom, [text], [], 0)
    with layout_text.font_context(factor):
        enlarged = note._wrapped_lines(sp, geom, [text], [], 0)
        assert enlarged.h > normal.h
        assert all(float(e.attrs["font-size"]) == K.TEXT_NOTE.size
                   for e in enlarged.elements if e.kind == "text")
        for e in enlarged.elements:
            if e.kind == "text" and e.text != "1":
                assert (float(e.attrs["x"]) + layout.M.text_width(e.text, K.TEXT_NOTE.size)
                        <= geom.canvas_w - sp.const.canvas_margin)
            elif e.kind == "circle":
                assert float(e.attrs["cy"]) + float(e.attrs["r"]) <= enlarged.rect.y1
                assert float(e.attrs["cy"]) - float(e.attrs["r"]) >= enlarged.rect.y0


def test_enlarged_cidr_extends_checked_header_band():
    import check_layout as checker
    def header(factor):
        with layout_text.font_context(factor):
            root = ET.fromstring(
                f'<svg xmlns="{layout.SVG_NS}" viewBox="0 0 600 300" data-text-scale="{factor}">'
                '<g id="group:vpc"><rect x="100" y="100" width="400" height="180" '
                'fill="none" stroke="#00A4A6"/>'
                f'<text x="112" y="{100 + K.CIDR_DY}" font-size="{K.TEXT_CIDR.size}">'
                '2001:db8::/64</text></g>'
                '<line x1="110" y1="145" x2="350" y2="145" stroke="#232F3E"/></svg>')
        return [p for p in checker.run_checks(root) if p.kind == "LINE IN HEADER"]
    assert not header(1)
    issue, = header(1.5)
    assert issue.ctx["band"][3] == 100 + layout_text.rounded(34, 1.5) + 18 * K.GLYPH_DESCENT


def test_scaled_step_circle_is_not_a_group_badge():
    import check_layout as checker
    root = ET.fromstring(
        f'<svg xmlns="{layout.SVG_NS}" viewBox="0 0 200 200" data-text-scale="1.8">'
        '<g id="edge:0:badge"><circle cx="50" cy="50" r="18" fill="#232F3E"/></g>'
        '<image href="bundle:service/AWS-Lambda" x="72" y="32" width="48" height="48"/>'
        '</svg>')
    assert not any(p.kind == "BADGE NEAR ICON" for p in checker.run_checks(root))


def test_fixed_cidr_uses_scaled_size_in_final_draft(tmp_path):
    document = wide_spec("slide")
    document["rows"] = ["main", {"id": "bottom", "min_gap_before": 500}]
    document["nodes"][1]["at"] = ["b", "bottom"]
    document["raw"] = [{"layer": "above", "svg":
                        '<text x="30" y="200" font-size="20" font-weight="bold">'
                        'VPC 10.0.0.0/16</text>'}]
    document["text_scale"] = 1.5
    sp = layout_spec.load(document)
    result = layout.render_readable(sp, "raw.yaml", tmp_path / "round.svg")
    cidr, = [t for t in ET.fromstring(result[1]).iter()
             if t.tag.endswith("}text") and t.text == "10.0.0.0/16"]
    assert cidr.get("font-size") == "18"
    assert layout.drawn_text(sp, result[1])[1][0] == 18


def test_structure_allows_scaled_note_reflow_but_checks_its_content(tmp_path):
    sys.path.insert(0, str(ROOT / "tests"))
    import compare_structure as compare
    import embed
    original, _, problems = embed.unembed(
        (ROOT / "docs/examples/nlb-mtls-reference-architecture.svg").read_text())
    assert not problems
    orig_path = tmp_path / "orig.svg"
    orig_path.write_text(original)
    sp = layout_spec.load(ROOT / "docs/examples/specs/nlb-mtls-reference-architecture.layout.yaml")
    enlarged = layout.render_readable(sp, "nlb.yaml", tmp_path / "round.svg")[1]
    gen_path = tmp_path / "enlarged.svg"
    gen_path.write_bytes(enlarged)
    old, new = compare.Draft(orig_path), compare.Draft(gen_path)
    assert (old.note_kind, new.note_kind) == ("pane", "panel")
    assert not compare.compare(old, new)
    new.note_text += " lost"
    assert any(line.startswith("(g)") for line in compare.compare(old, new))
    new.text_scale = 1
    assert any(line.startswith("(e)") for line in compare.compare(old, new))


def test_typography_scope_restores_after_exception():
    import layout_note
    before = (K.TEXT_NOTE, K.GROUP_STYLES, K.MODES, layout_note.SIZE, layout_note.wrap.__defaults__)
    with pytest.raises(RuntimeError):
        with layout_text.font_context(1.8):
            assert K.TEXT_NOTE.size == 22
            assert layout_note.SIZE == 22
            with layout_text.font_context(1):
                assert K.TEXT_NOTE.size == 12
            assert K.TEXT_NOTE.size == 22
            raise RuntimeError()
    assert (K.TEXT_NOTE, K.GROUP_STYLES, K.MODES, layout_note.SIZE, layout_note.wrap.__defaults__) == before


def test_each_automatic_pass_rounds_the_previous_font_size():
    assert layout_text.font_size(12, 1.8 * 1.8, (1.8, 1.8)) == 40
    with layout_text.font_context(1.8 * 1.8, (1.8, 1.8)):
        assert K.TEXT_SUB.size == 40
        assert K.TEXT_TITLE_SIZE == 45
    assert K.TEXT_SUB.size == 12


def test_standalone_checker_uses_scaled_header_metrics(tmp_path):
    import subprocess
    document = wide_spec()
    document["groups"] = [{"id": "vpc", "type": "vpc", "cidr": "10.0.0.0/16"}]
    for node in document["nodes"]:
        node["in"] = "vpc"
    document["text_scale"] = 1.5
    sp = layout_spec.load(document)
    result = layout.render_readable(sp, "scaled.yaml", tmp_path / "round.svg")
    draft = tmp_path / "scaled.svg"
    draft.write_bytes(result[1])
    checked = subprocess.run([sys.executable, str(ROOT / "scripts/check_layout.py"), str(draft)],
                             capture_output=True, text=True)
    assert checked.returncode == 0, checked.stdout
    assert "Layout OK" in checked.stdout


def test_trunk_badge_keeps_its_branch_attribution(tmp_path):
    sp = layout_spec.load(ROOT / "docs/examples/specs/centralized-egress.layout.yaml")
    before = layout.render_checked(sp, "same.yaml", tmp_path / "round.svg")
    after = layout.render_readable(sp, "same.yaml", tmp_path / "round.svg")
    assert layout.trunk_badge_branches(sp, before[1]) == layout.trunk_badge_branches(after[0].spec, after[1])


@pytest.mark.parametrize("regression", ["size", "checks", "rules"])
def test_rejected_candidate_keeps_previous_result(tmp_path, monkeypatch, regression):
    sp = layout_spec.load(wide_spec())
    original = layout.render_checked(sp, "wide.yaml", tmp_path / "round.svg")
    trial = copy.deepcopy(sp)
    trial.font_factor = 1.5
    candidate = list(layout.render_checked(trial, "wide.yaml", tmp_path / "round.svg"))
    if regression == "size":
        root = ET.fromstring(candidate[1])
        root.set("viewBox", "0 0 10000 100")
        candidate[1] = ET.tostring(root)
    elif regression == "checks":
        candidate[3] = [object()]
    else:
        monkeypatch.setattr(layout, "other_rule_counts",
                            lambda spec, *args: Counter({"R-flow": 1}) if spec.font_factor > 1 else Counter())
    calls = iter((original, tuple(candidate)))
    monkeypatch.setattr(layout, "render_checked", lambda *args: next(calls))
    assert layout.render_readable(sp, "wide.yaml", tmp_path / "round.svg")[1] == original[1]
