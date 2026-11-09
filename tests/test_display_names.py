"""Engine output names spec items as the drawing shows them, not by draft owner ids.

A first-time author reads `rule:` lines, warnings, spec hints and the feedback summary
against the picture and the spec: an edge is its spec line plus its ends' labels
("edges[0] (Order 2 → Aurora writer)"), a node its label (with which copy when copies share
it), a box its title. Owner ids stay in machine-read fields (run_corpus owners, MANIFEST
tags) only.
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import layout
import layout_spec

OWNER_ID = re.compile(r"\b(?:edge|node|group):[\w.\-]+")


def draw(case, tmp_path, capsys, *args):
    draft = tmp_path / "names.svg"
    layout.main([str(ROOT / f"tests/corpus/{case}.layout.yaml"), "-o", str(draft), *args])
    return capsys.readouterr().out.splitlines()


def author_lines(out):
    """Everything the author reads but the draft path: summary, warnings, selection, check
    rounds, --explain, problems with their fix / spec / try lines, rule verdicts."""
    return [line for line in out if line and not line.startswith("draft: ")]


# spec locators the author searches for ("nodes[2] db db.2", "edges[0] orders.2 -> db.1"),
# quoted text and `keys`, tracks ("row:az2", "x col app", "{id: db"): ids belong there
LOCATOR = re.compile(r"(?:nodes|groups)\[\d+\](?: [\w.\-]+,?)+|edges\[\d+\] [\w.\-*]+ \S+ [\w.\-*]+")
QUOTED = re.compile(r"(?<![\w)])'[^']*'|`[^`]*`")
TRACK = re.compile(r"(?:\b(?:row|col|rows|cols|column|flow \S+|id)[ :.]|\bid: )[\w.\-]+")
WORD = re.compile(r"(?<![\w.\-])[A-Za-z_][\w\-]*(?:\.\d+)?(?![\w\-])(?!\.[A-Za-z_\d])")


def bare_ids(spec, line):
    """Node / group ids a line shows where a display name differs from the id."""
    for pat in (QUOTED, LOCATOR, TRACK):
        line = pat.sub(" ", line)
    # words of the display names themselves ("S3 raw" is a label, not the id raw)
    names = {layout.M.item_name(spec, i) for i in list(spec.nodes) + list(spec.groups)}
    for name in sorted(names, key=len, reverse=True):
        line = line.replace(name, " ")
    return [w for w in WORD.findall(line)
            if (w in spec.nodes or w in spec.groups) and layout.M.item_name(spec, w) != w]


CASES = [
    ("qa/t4-three-az-writer", ("--mode", "slide")),       # F5, F6, B2 and feedback rounds on template copies
    ("qa/t3-nat-route-table", ("--mode", "slide")),       # F6 over a copy whose label repeats in each AZ
    ("bench/engine1-egress", ("--mode", "document")),     # RT1 / RT4 on route tables and their hub
    ("flowcol/r3-xy-30", ("--mode", "document", "--explain")),   # moved-xy warnings, --explain chains
    ("twin/grid", ("--mode", "document")),                # an overlay header warning naming a subnet copy
    ("qa/t2-false-junction", ("--mode", "slide")),        # hard placement warnings
    ("qa/t1-privatelink", ("--mode", "slide")),           # hand placement try, selection skips, B1 / F1 / F3
    ("twin/three", ("--mode", "slide")),                  # selection: an overlay header flipped
]


@pytest.mark.parametrize(("case", "args"), CASES)
def test_guidance_names_no_owner_or_bare_ids(tmp_path, capsys, case, args):
    lines = author_lines(draw(case, tmp_path, capsys, *args))
    spec = layout_spec.load(ROOT / f"tests/corpus/{case}.layout.yaml", mode=args[1])
    assert any(line.startswith(("rule: ", "warning: ")) for line in lines)
    assert [line for line in lines if OWNER_ID.search(line)] == []
    assert [(line, bare_ids(spec, line)) for line in lines if bare_ids(spec, line)] == []


def test_edges_by_spec_line_and_ends_nodes_by_label(tmp_path, capsys):
    out = draw("qa/t4-three-az-writer", tmp_path, capsys, "--mode", "slide")
    assert ("rule: R-flow F6 edges[0] (Order 2 → Aurora writer) runs over Endpoint 2's icon "
            "(120,436)→(401,436): the flow reads as passing through Endpoint 2; try: edges[0] (Order 2 → "
            "Aurora writer) shape / "
            "from_side / to_side (the horizontal piece at y=436 leaves Order 2 on Endpoint 2's row), or "
            "nodes[1] ep ep.2 (Endpoint 2): dy: 32 (moves Endpoint 2 off the piece)") in out
    # a box title shared by its AZ copies says which copy
    assert any(line.startswith("rule: R-border B2 edges[0] (Order 2 → Aurora writer) passes through "
                               "Data (Availability Zone 2)'s header band ") for line in out)
    assert any(line.startswith("warning: unresolved R-flow F6 (edges[0] (Order 2 → Aurora writer), "
                               "Aurora reader 2); spec hint (not a guarantee): ") for line in out)
    # engine route warnings keep their spec locator and gain the ends' names
    assert any(line.startswith("warning: edges[0] orders.2 -> db.1 (Order 2 → Aurora writer): ")
               for line in out)
    # the feedback summary names the spec line (there is one: edges[0]), not the instance number
    check = next(line for line in out if line.startswith("check: "))
    assert "next routing candidate for edges[0] (Order 2 → Aurora writer) ×3" in check
    assert "edges[1]" not in check and "edges[2]" not in check


def test_repeated_label_names_its_copy(tmp_path, capsys):
    out = draw("qa/t3-nat-route-table", tmp_path, capsys, "--mode", "slide")
    f6 = next(line for line in out if line.startswith("rule: R-flow F6 "))
    assert f6.startswith("rule: R-flow F6 edges[0] (NAT (Availability Zone 2) → IGW) runs over "
                         "NAT RT (Availability Zone 2)'s icon ")
    assert "nodes[1] rt rt.2 (NAT RT (Availability Zone 2)): dy: " in f6


def test_route_table_rules_name_tables_hubs_and_lines(tmp_path, capsys):
    out = draw("bench/engine1-egress", tmp_path, capsys, "--mode", "document")
    rt1 = [line for line in out if line.startswith("rule: R-rt RT1 ")]
    assert rt1
    # the associated lines by spec line and ends, not by instance number ("edges 8, 9")
    assert all(re.search(r"associated lines at \S.* draw \(edges\[\d+\] \(", line) for line in rt1)
