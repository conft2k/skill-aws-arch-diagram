#!/usr/bin/env python3
"""layout_spec.load / parse_expr: a size, gap, coordinate, offset, width or expression that is
not a finite number (YAML .nan / .inf / -.inf, the same floats in a dict, an int or a digit
string too big for a float) is a SpecError naming the field, never a crash in layout.build.

    python3 tests/test_spec_finite.py

Needs PyYAML (`uv run --with pyyaml python3 tests/test_spec_finite.py` where it is missing)
and the icon bundle, like every script of the skill.
"""
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import layout_model as M  # noqa: E402
import layout_spec as L  # noqa: E402
from layout_model import SpecError  # noqa: E402

NF = " (not a finite number)"
HOLE = "__V__"
YAML_VALUES = {".nan": "nan", ".NaN": "nan", ".inf": "inf", "+.inf": "inf", "-.inf": "-inf", "-.Inf": "-inf"}
FLOAT_VALUES = (float("nan"), float("inf"), float("-inf"))


def base():
    """A small valid spec: VPC with a 2-AZ template, a border IGW, the Internet, one step."""
    return {
        "name": "t", "cols": ["a", "b", "c"], "rows": ["az1", "main", "az2"],
        "groups": [{"id": "cloud", "type": "cloud"},
                   {"id": "region", "type": "region", "in": "cloud"},
                   {"id": "vpc", "type": "vpc", "in": "region", "cidr": "10.0.0.0/16"},
                   {"id": "az", "type": "az", "in": "vpc", "per": ["az1", "az2"]},
                   {"id": "sn", "type": "private", "label": "App subnet", "in": "az"}],
        "nodes": [{"id": "ec2", "icon": "service/Amazon-EC2", "label": "EC2", "in": "sn", "col": "b"},
                  {"id": "igw", "icon": "resource/Amazon-VPC_Internet-Gateway", "label": "IGW", "on": "vpc",
                   "at": ["a", "main"]},
                  {"id": "inet", "icon": "resource/Internet", "label": "Internet", "at": ["c", "main"]}],
        "edges": [{"e": "igw -> ec2.*", "step": 1}, {"e": "inet -> igw"}],
        "note": {"steps": [["IGW → EC2", "들어옵니다."]]},
    }


def xy(d, v):
    del d["nodes"][2]["at"]
    d["nodes"][2]["xy"] = v


# (case, put v into the spec, the first problem for v printed as `got`)
FIELDS = (
    ("S", lambda d, v: d.update(S=v),
     "spec: S: expected a positive number (icon size, default 48), got {v}" + NF),
    ("track min_gap_before", lambda d, v: d["cols"].__setitem__(1, {"id": "b", "min_gap_before": v}),
     "cols[1] b: min_gap_before: expected a number ≥ 0 (px), got {v}" + NF),
    ("track min_w", lambda d, v: d["rows"].__setitem__(1, {"id": "main", "min_w": v}),
     "rows[1] main: min_w: expected a number ≥ 0 (px), got {v}" + NF),
    ("track flow", lambda d, v: d["cols"].__setitem__(2, {"id": "c", "flow": v}),
     "cols[2] c: flow: expected a pitch in px (e.g. 160) or true, got {v}" + NF),
    ("group pad", lambda d, v: d["groups"][2].update(pad=v),
     "groups[2] vpc: pad: expected a number ≥ 0 (px), got {v}" + NF),
    ("group pad_bottom", lambda d, v: d["groups"][4].update(pad_bottom=v),
     "groups[4] sn: pad_bottom: expected a number ≥ 0 (px), got {v}" + NF),
    ("group min_h", lambda d, v: d["groups"][2].update(min_h=v),
     "groups[2] vpc: min_h: expected a number ≥ 0 (px), got {v}" + NF),
    ("node dx", lambda d, v: d["nodes"][2].update(dx=v),
     "nodes[2] inet: dx: expected a number (px), got {v}" + NF),
    ("node dy", lambda d, v: d["nodes"][2].update(dy=v),
     "nodes[2] inet: dy: expected a number (px), got {v}" + NF),
    ("per-instance dx", lambda d, v: d["nodes"][0].update(dx={1: 0, 2: v}),
     "nodes[0] ec2: dx[2]: expected a number (px), got {v}" + NF),
    ("xy number", lambda d, v: xy(d, [v, 10]),
     "nodes[2] inet: xy: expected [cx, cy], each a number or an expression "
     "(col.<track>, row.<track>, <id>.<attr>, ±n), got [{v}, 10]" + NF),
    ("xy beside an expression", lambda d, v: xy(d, ["igw.cx", v]),
     "nodes[2] inet: xy: expected [cx, cy], each a number or an expression "
     "(col.<track>, row.<track>, <id>.<attr>, ±n), got ['igw.cx', {v}]" + NF),
    ("edge from_offset", lambda d, v: d["edges"][1].update(from_offset=v),
     "edges[1] inet -> igw: from_offset: expected a number (px along the side), got {v}" + NF),
    ("edge to_offset", lambda d, v: d["edges"][0].update(to_offset=v),
     "edges[0] igw -> ec2.*: to_offset: expected a number (px along the side), got {v}" + NF),
    ("expression bend_x", lambda d, v: d["edges"][1].update(bend_x=v),
     "edges[1] inet -> igw: bend_x: expression {v}: expected a finite number"),
    ("expression bend_y", lambda d, v: d["edges"][1].update(bend_y=v),
     "edges[1] inet -> igw: bend_y: expression {v}: expected a finite number"),
    ("expression points", lambda d, v: d["edges"][1].update(points=[[0, 0], [12.5, v]]),
     "edges[1] inet -> igw: points[1][1]: expression {v}: expected a finite number"),
    ("expression label_at", lambda d, v: d["edges"][1].update(label="x", label_at={"x": v, "y": 3}),
     "edges[1] inet -> igw: label_at.x: expression {v}: expected a finite number"),
    ("expression step_at", lambda d, v: d["edges"][0].update(step_at=[4, v]),
     "edges[0] igw -> ec2.*: step_at.y: expression {v}: expected a finite number"),
    ("note width", lambda d, v: d["note"].update(width=v),
     "note: width: expected a pane width in px or auto, got {v}" + NF),
)


def spec_yaml(f, token):
    """The base spec as YAML text with `token` written bare where f puts the value."""
    import yaml
    d = base()
    f(d, HOLE)
    text = yaml.safe_dump(d, allow_unicode=True, sort_keys=False)
    assert text.count(HOLE) == 1, text
    return text.replace(HOLE, token)


def load_text(text):
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "t.layout.yaml"
        p.write_text(text, encoding="utf-8")
        return L.load(p)


class YamlNonFinite(unittest.TestCase):
    def test_every_field(self):
        for case, f, want in FIELDS:
            for token, shown in YAML_VALUES.items():
                with self.subTest(case, value=token):
                    with self.assertRaises(SpecError) as cm:
                        load_text(spec_yaml(f, token))
                    self.assertEqual(cm.exception.problems[0], want.format(v=shown))


class DictNonFinite(unittest.TestCase):
    def test_every_field(self):
        for case, f, want in FIELDS:
            for v in FLOAT_VALUES:
                with self.subTest(case, value=v):
                    d = base()
                    f(d, v)
                    with self.assertRaises(SpecError) as cm:
                        L.load(d)
                    self.assertEqual(cm.exception.problems[0], want.format(v=repr(v)))

    def test_int_too_big_for_a_float(self):
        big = 10 ** 400
        for case, f, want in FIELDS:
            with self.subTest(case):
                d = base()
                f(d, big)
                with self.assertRaises(SpecError) as cm:
                    L.load(d)
                self.assertEqual(cm.exception.problems[0], want.format(v=repr(big)))


class ParseExprNonFinite(unittest.TestCase):
    def test_numbers(self):
        for v in FLOAT_VALUES + (10 ** 400,):
            with self.subTest(value=v):
                with self.assertRaises(SpecError) as cm:
                    L.parse_expr(v)
                self.assertEqual(cm.exception.problems, [f"expression {v!r}: expected a finite number"])

    def test_digit_strings_too_long_for_a_float(self):
        big = "9" * 400
        for text, why in ((big, "the number"), (f"-{big}", "the number"),
                          (f"igw.cx+{big}", "the offset"), (f"col.a - {big}", "the offset"),
                          (f"br.label.y1-{big}", "the offset"), (f"gap(a, b)+{big}", "the offset")):
            with self.subTest(text[:12]):
                with self.assertRaises(SpecError) as cm:
                    L.parse_expr(text)
                self.assertEqual(cm.exception.problems,
                                 [f"expression {text!r}: {why} is too large to be a coordinate"])

    def test_in_a_spec(self):
        d = base()
        d["edges"][1]["points"] = [["igw.cx+" + "9" * 400, 0], [1, 2]]
        with self.assertRaises(SpecError) as cm:
            L.load(d)
        self.assertEqual(cm.exception.problems[0], "edges[1] inet -> igw: points[0][0]: expression 'igw.cx+"
                         + "9" * 400 + "': the offset is too large to be a coordinate")

    def test_finite_unchanged(self):
        P = L.parse_expr
        self.assertEqual(P(0), M.Expr("num", offset=0.0))
        self.assertEqual(P(-7.25), M.Expr("num", offset=-7.25))
        self.assertEqual(P("-0.5"), M.Expr("num", offset=-0.5))
        self.assertEqual(P("igw.cx-12.75"), M.Expr("node", "igw", "cx", offset=-12.75))
        self.assertEqual(P("col.a+" + "9" * 300), M.Expr("col", "a", offset=float("9" * 300)))


class FiniteUnchanged(unittest.TestCase):
    """0, the negatives a field allows and finite decimals load as before."""

    def test_zero_negative_decimal(self):
        d = base()
        d["S"] = 47.5
        d["cols"][1] = {"id": "b", "min_gap_before": 0, "min_w": 12.5}
        d["groups"][2].update(pad=0, pad_top=8.5, min_h=0)
        d["nodes"][2].update(dx=-12.5, dy=0)
        d["nodes"][0].update(dx={1: -3, 2: 4.25})
        d["edges"][1].update(from_offset=-6.5, to_offset=0, bend_x=-20.5, points=[[0, -4.5], ["igw.cx-8.5", 0]])
        d["note"]["width"] = 280.5
        s = L.load(d)
        self.assertEqual(s.S, 47.5)
        self.assertEqual((s.cols[1].min_gap_before, s.cols[1].min_w), (0.0, 12.5))
        self.assertEqual((s.nodes["inet"].dx, s.nodes["inet"].dy), (-12.5, 0.0))
        self.assertEqual((s.nodes["ec2.1"].dx, s.nodes["ec2.2"].dx), (-3.0, 4.25))
        self.assertEqual(s.note.width, 280.5)

    def test_yaml_xy_negative_decimal(self):
        d = base()
        xy(d, [-10.5, 0])
        s = load_text(spec_yaml(lambda d, v: d["nodes"][2].update(dx=v), "-0.0"))
        self.assertEqual(s.nodes["inet"].dx, 0.0)
        s = L.load(d)
        self.assertEqual(s.nodes["inet"].xy, (-10.5, 0.0))

    def test_number_label_still_text(self):
        d = base()
        d["nodes"][2]["label"] = 443
        self.assertEqual(L.load(d).nodes["inet"].label, "443")


class BuildNeverReached(unittest.TestCase):
    """The review repro: S: .nan / .inf stop at load, and a finite decimal S still builds."""

    def spec(self, S):
        return {"name": "review", "S": S, "cols": ["a"], "rows": ["r"],
                "nodes": [{"id": "n", "icon": "service/Amazon-EC2", "label": "EC2", "at": ["a", "r"]}]}

    def test_repro(self):
        for S in (float("nan"), float("inf")):
            with self.subTest(S=S):
                with self.assertRaises(SpecError) as cm:
                    L.load(self.spec(S))
                self.assertEqual(cm.exception.problems,
                                 [f"spec: S: expected a positive number (icon size, default 48), got {S!r}" + NF])

    def test_finite_decimal_builds(self):
        import layout
        layout.build(L.load(self.spec(40.5)), [], {}, None, "review.layout.yaml")


if __name__ == "__main__":
    unittest.main(verbosity=1)
