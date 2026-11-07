#!/usr/bin/env python3
"""layout_solve (W2): constraints, longest path, hug, border nodes, flow rows, overlays, draw.

    python3 tests/test_layout_solve.py [-v]

Specs are built here as layout_model dataclasses (no W1 loader): the ALB example (flow row,
ASG overlay, IGW on the left border, two AZs), the NFW example (two spoke VPCs, TGW,
inspection VPC AZ template, IGW on the right border) and a minimal VPC. Solved coordinates
are compared with the examples' drafts (docs/examples/*.svg after embed.unembed): the y
chain of insets exactly or within the design's tolerance, x within wider bounds (the engine
reserves 0.6 em per Latin character where the hand-made examples used ≈ 0.55 em and routes
are not planned here). Also: every constraint holds in the result, positive cycles are
reported by why/owner, soft requirements are dropped first, output is deterministic, and
the groups and nodes drawn alone pass check_layout. Standard library only.
"""
import math
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_layout as CL  # noqa: E402
import embed  # noqa: E402
import layout_const as K  # noqa: E402
import layout_model as M  # noqa: E402
import layout_solve as LS  # noqa: E402
from layout_model import Group, Node, NoteBlock, Requirement, SolveError, Spec, Track  # noqa: E402

VERBOSE = "-v" in sys.argv


# =======================================================================================
# Fixture builder (what W1 would produce: expanded, ranges computed)

def build(name, cols, rows, groups, nodes, mode="document"):
    def track(t, axis, i):
        if isinstance(t, str):
            return Track(t, axis, i)
        tid, kw = t
        return Track(tid, axis, i, **kw)

    spec = Spec(name, mode=mode, cols=[track(t, "col", i) for i, t in enumerate(cols)],
                rows=[track(t, "row", i) for i, t in enumerate(rows)])
    for i, g in enumerate(groups):
        g = dict(g)
        st = K.style(g["type"])
        g.setdefault("label", st.label)
        g.setdefault("dash", st.dash)
        spec.groups[g["id"]] = Group(src=f"groups[{i}]", **g)
    for i, n in enumerate(nodes):
        spec.nodes[n["id"]] = Node(src=f"nodes[{i}]", **n)
    for g in spec.groups.values():
        if g.parent:
            spec.groups[g.parent].children.append(g.id)
    for n in spec.nodes.values():
        if n.parent and n.on is None:
            spec.groups[n.parent].nodes.append(n.id)
    idx = {t.id: t.index for t in spec.cols + spec.rows}

    def merge(cur, ids):
        ids = [i for i in ids if i is not None]
        if not ids:
            return cur
        lo, hi = min(ids, key=idx.get), max(ids, key=idx.get)
        if cur is None:
            return (lo, hi)
        return (min(cur[0], lo, key=idx.get), max(cur[1], hi, key=idx.get))

    def visit(gid):
        g = spec.groups[gid]
        c = r = None
        for k in g.children:
            cc, rr = visit(k)
            c, r = merge(c, list(cc or ())), merge(r, list(rr or ()))
        for n in spec.nodes.values():
            if (n.parent == gid and n.on is None and n.id in g.nodes) or (n.on and n.parent == gid):
                c, r = merge(c, [n.col, n.col2]), merge(r, [n.row])
        g.cols, g.rows = c, r
        return c, r

    for g in spec.groups.values():
        if g.parent is None and not g.over:
            visit(g.id)
        g.depth = len(spec.ancestors(g.id)) - 1 if not g.over else 0
    for g in spec.groups.values():
        if g.over:
            c = r = None
            for m in g.over:
                n = spec.nodes[m]
                c, r = merge(c, [n.col, n.col2]), merge(r, [n.row])
            g.cols, g.rows = c, r
    for n in spec.nodes.values():
        if n.on:
            v = spec.groups[n.on]
            n.side = "left" if idx[n.col] < idx[v.cols[0]] else "right"
    return spec


def per(template_groups, template_nodes, rows, base):
    """Instances of a `per` template rooted at group `base` (ids .1, .2 …)."""
    gs, ns = [], []
    tids = {g["id"] for g in template_groups}
    for n_, row in enumerate(rows, 1):
        for g in template_groups:
            g = dict(g)
            g["id"] = f"{g['id']}.{n_}"
            if g.get("parent") in tids:
                g["parent"] = f"{g['parent']}.{n_}"
            if g.get("label") and "{n}" in g["label"]:
                g["label"] = g["label"].replace("{n}", str(n_))
            g["template"], g["instance"] = base, n_
            gs.append(g)
        for nd in template_nodes:
            nd = dict(nd)
            nd["id"] = f"{nd['id']}.{n_}"
            nd["parent"] = f"{nd['parent']}.{n_}"
            nd["row"] = row
            nd["template"], nd["instance"] = base, n_
            if isinstance(nd.get("label"), dict):
                nd["label"] = nd["label"][n_]
            ns.append(nd)
    return gs, ns


def alb_spec(mode="document"):
    tg, tn = per(
        [dict(id="az", type="az", label="Availability Zone {n}", parent="vpc"),
         dict(id="pubsn", type="public", label="Public subnet", parent="az"),
         dict(id="appsn", type="private", label="App subnet", parent="az"),
         dict(id="dbsn", type="private", label="DB subnet", parent="az")],
        [dict(id="nat", icon="resource/Amazon-VPC_NAT-Gateway", label="NAT gateway", parent="pubsn", col="pub"),
         dict(id="ec2a", icon="service/Amazon-EC2", label="EC2", parent="appsn", col="app1"),
         dict(id="ec2b", icon="service/Amazon-EC2", label="EC2", parent="appsn", col="app2"),
         dict(id="rds", icon="service/Amazon-RDS", label={1: "RDS Primary", 2: "RDS Standby"}, parent="dbsn",
              col="db")],
        ["az1", "az2"], "az")
    groups = [dict(id="cloud", type="cloud"),
              dict(id="region", type="region", label="Region", parent="cloud"),
              dict(id="vpc", type="vpc", label="VPC", cidr="10.0.0.0/16", parent="region")] + tg + [
              dict(id="asg", type="asg", label="ASG · target group", over=["ec2a.1", "ec2b.1", "ec2a.2", "ec2b.2"],
                   header="right")]
    svc = [dict(id=i, icon=ic, label=lb, sub=[s], parent="region", row="svc", flow_index=k)
           for k, (i, ic, lb, s) in enumerate([
               ("acm", "service/AWS-Certificate-Manager", "ACM", "HTTPS 리스너 인증서"),
               ("waf", "service/AWS-WAF", "AWS WAF", "ALB에 연결한 Web ACL"),
               ("cw", "service/Amazon-CloudWatch", "CloudWatch", "지표 · 경보"),
               ("s3", "service/Amazon-Simple-Storage-Service", "S3", "ALB 액세스 로그")])]
    nodes = [dict(id="users", icon="resource/Users", label="Users", col="users", row="main"),
             dict(id="r53", icon="service/Amazon-Route-53", label="Route 53", sub=["alias → ALB"], parent="cloud",
                  col="r53", row="svc")] + svc + tn + [
             dict(id="alb", icon="resource/Elastic-Load-Balancing_Application-Load-Balancer", label="ALB",
                  parent="vpc", col="pub", row="main"),
             dict(id="igw", icon="resource/Amazon-VPC_Internet-Gateway", label="IGW", parent="region", on="vpc",
                  col="igw", row="main")]
    return build("alb-reference-architecture", ["users", "r53", "igw", "pub", "app1", "app2", "db"],
                 [("svc", {"flow": 160}), "az1", "main", "az2"], groups, nodes, mode)


def nfw_spec(mode="document"):
    tg, tn = per(
        [dict(id="az", type="az", label="Availability Zone {n}", parent="insp"),
         dict(id="tgwsn", type="private", label="TGW subnet", parent="az"),
         dict(id="fwsn", type="private", label="Firewall subnet", parent="az"),
         dict(id="pubsn", type="public", label="Public subnet", parent="az")],
        [dict(id="eni", icon="resource/AWS-Transit-Gateway_Attachment", label="TGW ENI",
              sub=["0.0.0.0/0 → 같은 AZ 방화벽"], parent="tgwsn", col="eni"),
         dict(id="fwe", icon="resource/AWS-Network-Firewall_Endpoints", label="Firewall endpoint",
              sub=["0.0.0.0/0 → 같은 AZ NAT", "10.0.0.0/8 → TGW"], parent="fwsn", col="fw"),
         dict(id="nat", icon="resource/Amazon-VPC_NAT-Gateway", label="NAT gateway",
              sub=["0.0.0.0/0 → IGW", "10.0.0.0/8 → 같은 AZ 방화벽"], parent="pubsn", col="nat")],
        ["az1", "az2"], "az")
    groups = [dict(id="cloud", type="cloud"),
              dict(id="region", type="region", label="Region ap-northeast-2", parent="cloud"),
              dict(id="vpca", type="vpc", label="VPC A", cidr="10.1.0.0/16", parent="region"),
              dict(id="sna", type="private", label="App subnet", parent="vpca"),
              dict(id="vpcb", type="vpc", label="VPC B", cidr="10.2.0.0/16", parent="region"),
              dict(id="snb", type="private", label="App subnet", parent="vpcb"),
              dict(id="insp", type="vpc", label="Inspection VPC", cidr="100.64.0.0/16", parent="region")] + tg
    nodes = [dict(id="ec2a", icon="service/Amazon-EC2", label="EC2", sub=["0.0.0.0/0 → TGW"], parent="sna",
                  col="spoke", row="az1"),
             dict(id="ec2b", icon="service/Amazon-EC2", label="EC2", sub=["0.0.0.0/0 → TGW"], parent="snb",
                  col="spoke", row="az2"),
             dict(id="tgw", icon="service/AWS-Transit-Gateway", label="TGW", parent="region", col="tgw", row="main"),
             dict(id="rtfw", icon="resource/Amazon-Route-53_Route-Table", label="Firewall RT", sub=["VPC A · B 전파"],
                  parent="region", col="tgw", row="az1"),
             dict(id="rtsp", icon="resource/Amazon-Route-53_Route-Table", label="Spoke RT",
                  sub=["0.0.0.0/0 → 검사 VPC"], parent="region", col="tgw", row="az2")] + tn + [
             dict(id="nfw", icon="service/AWS-Network-Firewall", label="AWS Network Firewall", parent="insp",
                  col="fw", row="main"),
             dict(id="igw", icon="resource/Amazon-VPC_Internet-Gateway", label="IGW", parent="region", on="insp",
                  col="igw", row="main"),
             dict(id="inet", icon="resource/Internet", label="Internet", col="inet", row="main")]
    return build("nfw-reference-architecture", ["spoke", "tgw", "eni", "fw", "nat", "igw", "inet"],
                 ["az1", "main", "az2"], groups, nodes, mode)


def mini_spec(mode="document"):
    """Minimal VPC: 2 AZs, public + app subnet, ALB in the gap row, ASG over the EC2s, IGW."""
    tg, tn = per(
        [dict(id="az", type="az", label="Availability Zone {n}", parent="vpc"),
         dict(id="pub", type="public", label="Public subnet", parent="az"),
         dict(id="app", type="private", label="App subnet", parent="az")],
        [dict(id="nat", icon="resource/Amazon-VPC_NAT-Gateway", label="NAT gateway", parent="pub", col="pub"),
         dict(id="ec2", icon="service/Amazon-EC2", label="EC2", parent="app", col="app")],
        ["az1", "az2"], "az")
    groups = [dict(id="cloud", type="cloud"),
              dict(id="region", type="region", label="Region ap-northeast-2", parent="cloud"),
              dict(id="vpc", type="vpc", label="VPC", cidr="10.0.0.0/16", parent="region")] + tg + [
              dict(id="asg", type="asg", label="ASG · target group", over=["ec2.1", "ec2.2"], header="right")]
    nodes = tn + [
        dict(id="alb", icon="resource/Elastic-Load-Balancing_Application-Load-Balancer", label="ALB", parent="vpc",
             col="pub", row="main"),
        dict(id="igw", icon="resource/Amazon-VPC_Internet-Gateway", label="IGW", parent="region", on="vpc",
             col="igw", row="main")]
    return build("mini", ["igw", "pub", "app"], ["az1", "main", "az2"], groups, nodes, mode)


def flowcol_spec(mode="slide", pitch=100, align="center", n=4):
    """mini_spec plus regional services in a flow column right of the VPC (alb slide)."""
    base = mini_spec(mode)
    svc = [("acm", "service/AWS-Certificate-Manager", "ACM", "인증서"),
           ("waf", "service/AWS-WAF", "AWS WAF", "Web ACL"),
           ("cw", "service/Amazon-CloudWatch", "CloudWatch", "지표 · 경보"),
           ("s3", "service/Amazon-Simple-Storage-Service", "S3", "액세스 로그")][:n]
    groups = [{k: getattr(g, k) for k in ("id", "type", "label", "cidr", "parent", "over", "header", "template",
                                          "instance")} for g in base.groups.values()]
    nodes = [{k: getattr(nd, k) for k in ("id", "icon", "label", "sub", "parent", "col", "row", "on", "template",
                                          "instance")} for nd in base.nodes.values()]
    nodes += [dict(id=i, icon=ic, label=lb, sub=[sb], parent="region", col="svc", flow_index=k)
              for k, (i, ic, lb, sb) in enumerate(svc)]
    return build("flowcol", ["igw", "pub", "app", ("svc", {"flow": pitch, "align": align})],
                 ["az1", "main", "az2"], groups, nodes, mode)


# =======================================================================================
# The example drafts

class Draft:
    def __init__(self, name):
        src = (ROOT / "docs/examples" / f"{name}.svg").read_text(encoding="utf-8")
        out, _, problems = embed.unembed(src)
        assert not problems, problems
        root = ET.fromstring(out)
        ns = "{http://www.w3.org/2000/svg}"
        self.rects, self.images, self.texts = [], [], []
        for el in root.iter():
            tag = el.tag.replace(ns, "")
            a = {k: el.get(k) for k in el.keys()}
            if tag == "rect" and a.get("stroke") and a.get("fill") == "none":
                self.rects.append(M.Box.xywh(*(float(a[k]) for k in ("x", "y", "width", "height"))))
            elif tag == "image":
                self.images.append((a["href"][len("bundle:"):], float(a["x"]), float(a["y"])))
            elif tag == "text":
                self.texts.append((el.text or "", float(a["x"]), float(a["y"]), a.get("fill")))

    def group(self, label, k=0):
        """The k-th container whose title reads `label` → its rect."""
        hits = []
        for s, x, y, _ in self.texts:
            if s != label:
                continue
            for r in self.rects:
                if abs(r.y0 + 18 - y) < 0.6 and (abs(r.x0 + 32 - x) < 0.6 or abs(r.x0 + 12 - x) < 0.6) \
                        or abs(r.y0 + 22 - y) < 0.6 and abs(r.x0 + 42 - x) < 0.6:
                    hits.append(r)
                    break
        return hits[k]

    def icon(self, ref, label, k=0):
        """(cx, cy) of the k-th icon `ref` whose label reads `label`."""
        hits = []
        for r, x, y in self.images:
            if r != ref:
                continue
            if any(s == label and abs(tx - (x + 24)) < 0.6 and abs(ty - (y + 66)) < 0.6 for s, tx, ty, _ in self.texts):
                hits.append((x + 24, y + 24))
        return hits[k]


# =======================================================================================
# Helpers

def value(geom, spec, var, axis, side="lo"):
    """A Requirement variable's value in a Geometry (colspan: the conservative side)."""
    if var == "origin":
        return 0.0
    kind, _, rest = var.partition(":")
    if kind in ("col", "row"):
        return geom.track(rest)
    if kind == "group":
        gid, _, e = rest.rpartition(".")
        r = geom.groups[gid].rect
        return {"L": r.x0, "R": r.x1, "T": r.y0, "B": r.y1}[e]
    if kind == "node":
        n = geom.nodes[rest]
        return n.cx if axis == "x" else n.cy
    raise KeyError(var)


def to_svg(spec, geom, elements):
    """A minimal SVG around Elements (what W5's emit does, without <g> wrapping)."""
    lines = [f'<svg viewBox="0 0 {M.fmt_num(geom.canvas_w)} {M.fmt_num(geom.canvas_h)}" '
             f'xmlns="http://www.w3.org/2000/svg" font-family={quoteattr(spec.font)}>',
             f'<rect width="{M.fmt_num(geom.canvas_w)}" height="{M.fmt_num(geom.canvas_h)}" fill="#FFFFFF"/>']
    for e in sorted(elements, key=lambda e: e.z):
        attrs = " ".join(f'{k}={quoteattr(v if isinstance(v, str) else M.fmt_num(v))}' for k, v in e.attrs.items())
        if e.kind == "text":
            lines.append(f"<text {attrs}>{escape(e.text)}</text>")
        else:
            lines.append(f"<{e.kind} {attrs}/>")
    lines.append("</svg>")
    return "\n".join(lines)


def check(spec, geom):
    root = ET.fromstring(to_svg(spec, geom, LS.draw(spec, geom)))
    return [i.msg for i in CL.run_checks(root)]


def contains(outer: M.Box, inner: M.Box, gap=0.0):
    return (outer.x0 + gap <= inner.x0 + 1e-6 and outer.y0 + gap <= inner.y0 + 1e-6
            and inner.x1 + gap <= outer.x1 + 1e-6 and inner.y1 + gap <= outer.y1 + 1e-6)


# =======================================================================================
# Tests

class ExampleTest(unittest.TestCase):
    """Solved coordinates against the example drafts."""

    def report(self, name, rows):
        if VERBOSE:
            print(f"\n{name}: what  engine  example  diff")
            for what, a, b in rows:
                print(f"  {what:34s} {M.fmt_num(a):>8s} {M.fmt_num(b):>8s} {M.fmt_num(a - b):>7s}")

    def test_nfw(self):
        spec = nfw_spec()
        g = LS.solve(spec, [])
        d = Draft("nfw-reference-architecture")
        rows = []

        def grp(gid, label, k=0, tol_y=4, tol_x=None, tol_h=None, tol_w=None):
            r, e = g.groups[gid].rect, d.group(label, k)
            for what, a, b, tol in (("y0", r.y0, e.y0, tol_y), ("h", r.h, e.h, tol_h if tol_h is not None else 2 * tol_y),
                                    ("x0", r.x0, e.x0, tol_x), ("w", r.w, e.w, tol_w)):
                rows.append((f"{gid}.{what}", a, b))
                if tol is not None:
                    with self.subTest(group=gid, what=what):
                        self.assertLessEqual(abs(a - b), tol, f"{gid}.{what} {a} vs {b}")

        # Above the AZ gap row the inset chain matches within decision k (Region → VPC 32,
        # example 34). The gap row itself is the design's minimum here; the example opened
        # it to 132 for the TGW fan-out (a W3 route requirement), so everything that spans
        # or sits below it gets TOL_GAP. x: no routes are planned in this test (the example
        # leaves 120-150 px corridors for labelled arrows), so only leaf widths are bounded.
        gap = 24
        grp("cloud", "AWS Cloud", tol_x=0, tol_h=gap)
        grp("region", "Region ap-northeast-2", tol_x=4, tol_h=gap)      # decision a: 16, example 20
        grp("vpca", "VPC A", tol_x=12, tol_w=24)
        grp("sna", "App subnet", 0, tol_x=16, tol_w=24)
        grp("vpcb", "VPC B", tol_y=gap)
        grp("insp", "Inspection VPC", tol_h=gap)
        grp("az.1", "Availability Zone 1", tol_y=4)
        grp("tgwsn.1", "TGW subnet", 0, tol_y=4, tol_w=24)
        grp("fwsn.1", "Firewall subnet", 0, tol_y=4, tol_w=24)
        grp("pubsn.1", "Public subnet", 0, tol_y=4, tol_w=24)
        for nid, ref, label, k in (("ec2a", "service/Amazon-EC2", "EC2", 0),
                                   ("eni.1", "resource/AWS-Transit-Gateway_Attachment", "TGW ENI", 0),
                                   ("fwe.1", "resource/AWS-Network-Firewall_Endpoints", "Firewall endpoint", 0),
                                   ("nat.1", "resource/Amazon-VPC_NAT-Gateway", "NAT gateway", 0)):
            ex = d.icon(ref, label, k)
            n = g.nodes[nid]
            rows += [(f"{nid}.cx", n.cx, ex[0]), (f"{nid}.cy", n.cy, ex[1])]
            with self.subTest(node=nid):
                self.assertLessEqual(abs(n.cy - ex[1]), 4)
        # AZ 2 row: the same insets as AZ 1 (template instances alike)
        for a, b in (("az.1", "az.2"), ("tgwsn.1", "tgwsn.2"), ("pubsn.1", "pubsn.2")):
            ra, rb = g.groups[a].rect, g.groups[b].rect
            self.assertEqual((ra.x0, ra.x1, ra.h), (rb.x0, rb.x1, rb.h), (a, b))
        self.assertEqual(g.rows["az2"] - g.groups["az.2"].rect.y0, g.rows["az1"] - g.groups["az.1"].rect.y0)
        self.assertGreaterEqual(g.groups["az.2"].rect.y0 - g.groups["az.1"].rect.y1, K.DOCUMENT.az_gap)
        # IGW centered on the inspection VPC's right border, on the main row, mask 48 × 72
        igw, insp = g.nodes["igw"], g.groups["insp"].rect
        self.assertEqual(igw.cx, insp.x1)
        self.assertEqual(igw.cy, g.rows["main"])
        self.assertEqual((igw.mask.w, igw.mask.h), (48, 72))
        self.assertEqual(igw.side, "right")
        ex = d.icon("resource/Amazon-VPC_Internet-Gateway", "IGW")
        rows.append(("igw.cy - az1 bottom", igw.cy - g.groups["az.1"].rect.y1, ex[1] - d.group("Availability Zone 1").y1))
        # spoke VPCs hug their row (DESIGN 4.3 hug): VPC A top = subnet top − 46
        self.assertEqual(g.groups["vpca"].rect.y0, g.groups["sna"].rect.y0 - 46)
        self.assertEqual(g.groups["sna"].rect.y0, g.nodes["ec2a"].icon.y0 - 32)
        # x order of the main columns is the example's
        xs = [g.cols[c] for c in ("spoke", "tgw", "eni", "fw", "nat", "igw", "inet")]
        self.assertEqual(xs, sorted(xs))
        rows.append(("canvas_w", g.canvas_w, 1372))
        self.report("nfw", rows)

    def test_alb(self):
        spec = alb_spec()
        g = LS.solve(spec, [])
        d = Draft("alb-reference-architecture")
        rows = []
        for gid, label, k, ty in (("cloud", "AWS Cloud", 0, 0), ("region", "Region", 0, 0), ("vpc", "VPC", 0, 6),
                                  ("az.1", "Availability Zone 1", 0, 6), ("pubsn.1", "Public subnet", 0, 6),
                                  ("appsn.1", "App subnet", 0, 6), ("dbsn.1", "DB subnet", 0, 6)):
            r, e = g.groups[gid].rect, d.group(label, k)
            rows += [(f"{gid}.y0", r.y0, e.y0), (f"{gid}.x0", r.x0, e.x0), (f"{gid}.w", r.w, e.w),
                     (f"{gid}.h", r.h, e.h)]
            with self.subTest(group=gid):
                self.assertLessEqual(abs(r.y0 - e.y0), ty)
                if gid.endswith(".1") and gid != "az.1":
                    self.assertLessEqual(abs(r.w - e.w), 50)     # DB subnet: the example widened it for "SQL"
        # flow row: four regional services 160 apart, on the svc row with Route 53, centered in the Region
        fx = [g.nodes[i].cx for i in ("acm", "waf", "cw", "s3")]
        self.assertEqual([b - a for a, b in zip(fx, fx[1:])], [160, 160, 160])
        reg = g.groups["region"].rect
        self.assertLessEqual(abs((fx[0] + fx[-1]) / 2 - reg.cx), 1)
        ex = [d.icon(r, lb)[0] for r, lb in (("service/AWS-Certificate-Manager", "ACM"), ("service/Amazon-Simple-Storage-Service", "S3"))]
        rows.append(("flow center - region center", (fx[0] + fx[-1]) / 2 - reg.cx,
                     (ex[0] + ex[1]) / 2 - d.group("Region").cx))
        self.assertEqual(g.nodes["acm"].cy, g.nodes["r53"].cy)
        self.assertEqual(g.nodes["acm"].cy, d.icon("service/AWS-Certificate-Manager", "ACM")[1])
        # the ASG: inside both app subnets by 8, right of their header titles + 8, icons +30 under its title
        asg, s1, s2 = g.groups["asg"].rect, g.groups["appsn.1"].rect, g.groups["appsn.2"].rect
        title_end = s1.x0 + 32 + M.layout_text_width("App subnet", 14)
        self.assertGreaterEqual(asg.x0, title_end + 8 - 1e-6)
        self.assertGreaterEqual(asg.y0, s1.y0 + 8)
        self.assertGreaterEqual(s2.y1, asg.y1 + 8)
        self.assertGreaterEqual(g.nodes["ec2a.1"].icon.y0 - asg.y0, 30)
        self.assertEqual(g.nodes["ec2a.1"].icon.y0 - asg.y0, max(30, 32))   # badge clearance 24 + 8 binds
        # both AZ rows alike
        self.assertEqual(s1.h, s2.h)
        self.assertEqual(g.rows["az2"] - s2.y0, g.rows["az1"] - s1.y0)
        # IGW on the VPC's left border, between the AZ boxes with 8 to spare
        igw, vpc = g.nodes["igw"], g.groups["vpc"].rect
        self.assertEqual((igw.cx, igw.side), (vpc.x0, "left"))
        self.assertGreaterEqual(igw.mask.y0, g.groups["az.1"].rect.y1 + 8)
        self.assertGreaterEqual(g.groups["az.2"].rect.y0, igw.mask.y1 + 8)
        # ALB centered in the AZ gap row (110 apart at the minimum, the example's)
        gap = g.groups["az.2"].rect.y0 - g.groups["az.1"].rect.y1
        rows.append(("az gap", gap, 110))
        self.assertLessEqual(abs(gap - 110), 2)
        for nid, ref, lb in (("users", "resource/Users", "Users"), ("r53", "service/Amazon-Route-53", "Route 53"),
                             ("nat.1", "resource/Amazon-VPC_NAT-Gateway", "NAT gateway"),
                             ("ec2a.1", "service/Amazon-EC2", "EC2"),
                             ("alb", "resource/Elastic-Load-Balancing_Application-Load-Balancer", "ALB"),
                             ("igw", "resource/Amazon-VPC_Internet-Gateway", "IGW")):
            ex = d.icon(ref, lb)
            rows += [(f"{nid}.cx", g.nodes[nid].cx, ex[0]), (f"{nid}.cy", g.nodes[nid].cy, ex[1])]
            if nid != "users" and nid != "r53":
                with self.subTest(node=nid):
                    self.assertLessEqual(abs(g.nodes[nid].cy - ex[1]), 24)   # example ASG top +26, here +8
        rows += [("canvas_w", g.canvas_w, 1110), ("canvas_h (no note)", g.canvas_h, 770)]
        self.report("alb", rows)


class ConstraintTest(unittest.TestCase):
    """Every generated constraint holds; structure invariants."""

    def all_hold(self, spec, reqs=()):
        g = LS.solve(spec, list(reqs))
        m = LS._Model(spec)
        m.build("x")
        xv = {}
        # re-check the generated system against the geometry (x side; y via invariants)
        for c in m.cons["x"]:
            a = self._val(spec, g, c.a, "x")
            b = self._val(spec, g, c.b, "x")
            if a is None or b is None:
                continue
            self.assertGreaterEqual(b - a, c.d - 0.01, f"{c.why} ({c.owner}): {c.a}={a} {c.b}={b}")
        del xv
        for r in reqs:
            a = value(g, spec, r.a, r.axis)
            b = value(g, spec, r.b, r.axis)
            self.assertGreaterEqual(b - a, r.d - 0.01, r.why)
        return g

    @staticmethod
    def _val(spec, g, var, axis):
        if var.startswith("node:"):
            return g.nodes[var[5:]].cx if axis == "x" else g.nodes[var[5:]].cy
        if var.startswith("col:") or var.startswith("row:") or var.startswith("group:") or var == "origin":
            return value(g, spec, var, axis)
        return None

    def invariants(self, spec, g):
        mc = spec.const
        for gid, grp in spec.groups.items():
            r = g.groups[gid].rect
            self.assertGreaterEqual(r.x0, mc.canvas_margin - 1e-6)
            self.assertLessEqual(r.x1, g.canvas_w - mc.canvas_margin + 1e-6)
            if grp.parent and not grp.over:
                self.assertTrue(contains(g.groups[grp.parent].rect, r), (gid, grp.parent))
            for nid in grp.nodes:
                self.assertTrue(contains(r, g.nodes[nid].footprint()), (gid, nid))
                self.assertLessEqual(g.nodes[nid].last_baseline + mc.label_bottom, r.y1 + 1e-6, (gid, nid))
            for m in grp.over:
                self.assertTrue(contains(r, g.nodes[m].icon), (gid, m))
        for nid, n in spec.nodes.items():
            if n.on:
                v = g.groups[n.on].rect
                self.assertEqual(g.nodes[nid].cx, v.x0 if n.side == "left" else v.x1)

    def test_all_examples_hold(self):
        for mk in (alb_spec, nfw_spec, mini_spec):
            for mode in ("document", "slide"):
                with self.subTest(spec=mk.__name__, mode=mode):
                    spec = mk(mode)
                    g = self.all_hold(spec)
                    self.invariants(spec, g)

    def test_side_by_side_vpcs_align_their_rows(self):
        """Two VPCs over the same AZ rows (gwlb): their AZ boxes and subnets share tops and
        bottoms although only one has an ASG header pushing its icons down."""
        tg, tn = per(
            [dict(id="az", type="az", label="Availability Zone {n}", parent="app"),
             dict(id="esn", type="public", label="GWLBe subnet", parent="az")],
            [dict(id="gwlbe", icon="resource/Amazon-VPC_Endpoints", label="GWLBe", parent="esn", col="e")],
            ["az1", "az2"], "az")
        sg, sn = per(
            [dict(id="saz", type="az", label="Availability Zone {n}", parent="sec"),
             dict(id="asn", type="private", label="Appliance subnet", parent="saz")],
            [dict(id="fw", icon="service/Amazon-EC2", label="방화벽", parent="asn", col="fw")],
            ["az1", "az2"], "saz")
        spec = build("gwlb", ["e", "lb", "fw"], ["az1", "main", "az2"],
                     [dict(id="cloud", type="cloud"), dict(id="region", type="region", label="Region", parent="cloud"),
                      dict(id="app", type="vpc", label="Application VPC", cidr="10.0.0.0/16", parent="region"),
                      dict(id="sec", type="vpc", label="Security VPC", cidr="10.1.0.0/16", parent="region")]
                     + tg + sg + [dict(id="asg", type="asg", label="Auto Scaling group", over=["fw.1", "fw.2"])],
                     tn + sn + [dict(id="gwlb", icon="resource/Elastic-Load-Balancing_Gateway-Load-Balancer",
                                     label="GWLB", parent="sec", col="lb", row="main")])
        g = LS.solve(spec, [])
        for a, b in (("app", "sec"), ("az.1", "saz.1"), ("esn.1", "asn.1"), ("az.2", "saz.2"), ("esn.2", "asn.2")):
            ra, rb = g.groups[a].rect, g.groups[b].rect
            self.assertEqual((ra.y0, ra.y1), (rb.y0, rb.y1), (a, b))
        self.assertGreaterEqual(g.nodes["fw.1"].icon.y0 - g.groups["asg"].rect.y0, 30)
        self.assertEqual(check(spec, g), [])

    def test_short_overlay_title_beside_first_member(self):
        """An ASG titled no wider than an icon puts its first member row right of the badge
        and title, at the subnet's own icon inset, its top 8 under the subnet top (ex gwlb);
        a longer title stays above the members and pushes them down."""
        def solved(label, mode):
            tg, tn = per(
                [dict(id="az", type="az", label="Availability Zone {n}", parent="vpc"),
                 dict(id="sn", type="private", label="Appliance subnet", parent="az")],
                [dict(id="fw", icon="service/Amazon-EC2", label="방화벽", parent="sn", col="fw")],
                ["az1", "az2"], "az")
            spec = build("asg", ["fw"], ["az1", "az2"],
                         [dict(id="cloud", type="cloud"), dict(id="region", type="region", label="Region", parent="cloud"),
                          dict(id="vpc", type="vpc", label="VPC", cidr="10.0.0.0/16", parent="region")]
                         + tg + [dict(id="asg", type="asg", label=label, over=["fw.1", "fw.2"])], tn, mode=mode)
            return spec, LS.solve(spec, [])
        st = K.style("asg")
        for mode in ("document", "slide"):
            with self.subTest(mode=mode):
                spec, g = solved("ASG", mode)
                a, sn, icon = g.groups["asg"].rect, g.groups["sn.1"].rect, g.nodes["fw.1"].icon
                title_end = a.x0 + st.title_dx + M.layout_text_width("ASG", st.title_size)
                self.assertGreaterEqual(icon.x0, title_end + K.HEADER_ICON_CLEAR)
                self.assertEqual(icon.y0 - sn.y0, K.top_inset("private", mode, "icon"))
                self.assertEqual(a.y0 - sn.y0, K.OVERLAY_HEADER_GAP)
                self.assertEqual(check(spec, g), [])
                spec, g = solved("ASG · target group", mode)
                a, sn, icon = g.groups["asg"].rect, g.groups["sn.1"].rect, g.nodes["fw.1"].icon
                self.assertLess(icon.x0, a.x0 + st.title_dx)
                self.assertGreaterEqual(icon.y0 - a.y0, K.top_inset("asg", mode, "icon"))
                self.assertGreater(icon.y0 - sn.y0, K.top_inset("private", mode, "icon"))
                self.assertEqual(check(spec, g), [])

    def test_az_gap_only_with_a_node_between(self):
        """Stacked AZs keep the sibling gap when nothing of their VPC sits between them, and
        get az_gap when a node of the VPC (here an NLB) does."""
        def spec_with(between):
            tg, tn = per(
                [dict(id="az", type="az", label="Availability Zone {n}", parent="vpc"),
                 dict(id="sn", type="private", label="Private subnet", parent="az")],
                [dict(id="ec2", icon="service/Amazon-EC2", label="EC2", parent="sn", col="app")],
                ["az1", "az2"], "az")
            extra = ([dict(id="nlb", icon="resource/Elastic-Load-Balancing_Network-Load-Balancer",
                           label="NLB", parent="vpc", col="app", row="main")] if between else [])
            return build("stack", ["app"], ["az1", "main", "az2"] if between else ["az1", "az2"],
                         [dict(id="cloud", type="cloud"), dict(id="region", type="region", label="Region",
                                                              parent="cloud"),
                          dict(id="vpc", type="vpc", label="VPC", cidr="10.0.0.0/16", parent="region")] + tg,
                         tn + extra)

        for between, lo, hi in ((False, K.DOCUMENT.sibling_gap, K.DOCUMENT.az_gap - 1),
                                (True, K.DOCUMENT.az_gap, None)):
            spec = spec_with(between)
            g = LS.solve(spec, [])
            d = g.groups["az.2"].rect.y0 - g.groups["az.1"].rect.y1
            self.assertGreaterEqual(d, lo, between)
            if hi is not None:
                self.assertLessEqual(d, hi, between)
            self.assertEqual(check(spec, g), [], between)

    def test_slide_subnet_badge_clear_on_x(self):
        """On a slide a subnet's first-row node sits right of the subnet badge (icon left ≥
        badge + 8) instead of a row lower; in a document the old y clearance stays."""
        def solved(mode):
            spec = build("b", ["a"], ["r"],
                         [dict(id="cloud", type="cloud"), dict(id="region", type="region", label="Region", parent="cloud"),
                          dict(id="vpc", type="vpc", label="VPC", cidr="10.0.0.0/16", parent="region"),
                          dict(id="sn", type="private", label="TGW subnet", parent="vpc")],
                         [dict(id="eni", icon="resource/AWS-Transit-Gateway_Attachment", label="ENI", parent="sn",
                               col="a", row="r")], mode=mode)
            return LS.solve(spec, [])
        g = solved("slide")
        sn, icon = g.groups["sn"].rect, g.nodes["eni"].icon
        self.assertGreaterEqual(icon.x0 - sn.x0, 24 + 8)
        self.assertEqual(icon.y0 - sn.y0, K.top_inset("private", "slide", "icon"))
        g = solved("document")
        self.assertLess(g.nodes["eni"].icon.x0 - g.groups["sn"].rect.x0, 24 + 8)

    def test_one_side_pad(self):
        """pad_right widens a box on its right only; pad_left on its left only."""
        def spec_with(**kw):
            return build("pad", ["a"], ["r"],
                         [dict(id="cloud", type="cloud"), dict(id="region", type="region", label="Region", parent="cloud"),
                          dict(id="vpc", type="vpc", label="VPC", cidr="10.0.0.0/16", parent="region", **kw)],
                         [dict(id="ec2", icon="service/Amazon-EC2", label="EC2", parent="vpc", col="a", row="r")])
        base = LS.solve(spec_with(), [])
        right = LS.solve(spec_with(pad_right=60), [])
        left = LS.solve(spec_with(pad_left=60), [])
        def gaps(g):
            v, i = g.groups["vpc"].rect, g.nodes["ec2"].cx
            return i - v.x0, v.x1 - i
        bl, br = gaps(base)
        self.assertEqual(gaps(right)[0], bl)                 # the left side keeps its pad
        self.assertGreaterEqual(gaps(right)[1], 60 + 24)     # pad 60 + half the icon
        self.assertGreaterEqual(gaps(left)[0], 60 + 24)
        self.assertLess(gaps(left)[1], 60 + 24)              # the right side keeps its own pad

    def test_pad_bottom(self):
        """pad_bottom replaces pad below a child box only (the sides keep pad); below a node
        it grows the box past label_bottom but never shrinks it under that."""
        def spec_with(**kw):
            return build("padb", ["a"], ["r"],
                         [dict(id="cloud", type="cloud"), dict(id="region", type="region", label="Region", parent="cloud"),
                          dict(id="vpc", type="vpc", label="VPC", cidr="10.0.0.0/16", parent="region", **kw),
                          dict(id="sn", type="private", label="App subnet", parent="vpc")],
                         [dict(id="ec2", icon="service/Amazon-EC2", label="EC2", parent="sn", col="a", row="r")])
        def gaps(g, inner, outer):
            i, o = g.groups[inner].rect, g.groups[outer].rect
            return i.x0 - o.x0, o.x1 - i.x1, o.y1 - i.y1
        bl, br, bb = gaps(LS.solve(spec_with(), []), "sn", "vpc")
        self.assertEqual(bb, K.DOCUMENT.pad)
        g = LS.solve(spec_with(pad_bottom=6), [])
        self.assertEqual(gaps(g, "sn", "vpc"), (bl, br, 6))
        self.assertEqual(check(spec_with(pad_bottom=6), g), [])
        g = LS.solve(spec_with(pad_bottom=40), [])
        self.assertEqual(gaps(g, "sn", "vpc"), (bl, br, 40))
        # nodes: label_bottom stays the floor, a larger pad_bottom wins from the footprint bottom
        def node_gap(**kw):
            spec = spec_with()
            for k, v in kw.items():
                setattr(spec.groups["sn"], k, v)
            g = LS.solve(spec, [])
            n = g.nodes["ec2"]
            return g.groups["sn"].rect.y1 - n.lines[-1].y, g.groups["sn"].rect.y1 - n.stack().y1
        self.assertEqual(node_gap()[0], K.DOCUMENT.label_bottom)
        self.assertEqual(node_gap(pad_bottom=2)[0], K.DOCUMENT.label_bottom)
        self.assertTrue(40 <= node_gap(pad_bottom=40)[1] < 41)   # from the footprint bottom (rounded up)

    def test_side_by_side_labels_by_line(self):
        """Two nodes on one row are kept apart by the label lines level with each other: a
        long last line below the neighbour's shorter stack sets nothing, and the result
        stays check_layout clean (slide tgw: Dev VPC beside TGW A RT)."""
        def solved(mode):
            spec = build("bands", ["a1", "a2"], ["bot"],
                         [dict(id="cloud", type="cloud"), dict(id="ra", type="region", label="Region", parent="cloud")],
                         [dict(id="dev", icon="service/Amazon-Virtual-Private-Cloud", label="Dev VPC",
                               sub=["10.3.0.0/16"], parent="ra", col="a1", row="bot"),
                          dict(id="rta", icon="resource/Amazon-Route-53_Route-Table", label="TGW A RT",
                               sub=["VPC·VPN 경로 전파", "10.16.0.0/13 → peering"], parent="ra", col="a2", row="bot")],
                         mode=mode)
            return spec, LS.solve(spec, [])
        spec, g = solved("slide")
        pitch = g.cols["a2"] - g.cols["a1"]
        # the old rule: sibling gap + both whole footprints (the long last line) = 134
        whole = 12 + math.ceil(M.layout_text_width("10.3.0.0/16", 12) / 2) + \
            math.ceil(M.layout_text_width("10.16.0.0/13 → peering", 12) / 2)
        self.assertLess(pitch, whole - 30)
        level = K.SLIDE.label_gap + (M.layout_text_width("10.3.0.0/16", 12) + M.layout_text_width("VPC·VPN 경로 전파", 12)) / 2
        self.assertEqual(pitch, math.ceil(level - 1e-9))
        self.assertEqual(check(spec, g), [])
        # a dy that puts the neighbour's long line level with dev's sub-caption brings it back
        spec.nodes["rta"].dy = -16
        g = LS.solve(spec, [])
        self.assertGreaterEqual(g.cols["a2"] - g.cols["a1"],
                                (M.layout_text_width("10.3.0.0/16", 12) + M.layout_text_width("10.16.0.0/13 → peering", 12)) / 2)
        spec, g = solved("document")
        self.assertEqual(check(spec, g), [])

    def test_xy_expressions_follow_the_solve(self):
        """`xy: [col.a2, row.bot]` ties the node to the solved tracks (and an offset, a
        node's icon edge, a group's edge), while it still pushes no row neighbour apart;
        containment keeps holding around it."""
        def spec_with(xy):
            return build("xy", ["a1", "a2", "a3"], ["top", "bot"],
                         [dict(id="cloud", type="cloud"), dict(id="ra", type="region", label="Region", parent="cloud")],
                         [dict(id="svc", icon="service/Amazon-Virtual-Private-Cloud", label="Services VPC with a long name",
                               parent="ra", col="a1", row="top"),
                          dict(id="dev", icon="service/Amazon-Virtual-Private-Cloud", label="Dev VPC", parent="ra",
                               col="a1", row="bot"),
                          dict(id="test", icon="service/Amazon-Virtual-Private-Cloud", label="Test VPC", parent="ra",
                               col="a3", row="bot"),
                          dict(id="rt", icon="resource/Amazon-Route-53_Route-Table", label="RT", parent="ra", xy=xy)])
        P = __import__("layout_spec").parse_expr
        g = LS.solve(spec_with((P("col.a2"), P("row.bot"))), [])
        self.assertEqual((g.nodes["rt"].cx, g.nodes["rt"].cy), (g.cols["a2"], g.rows["bot"]))
        g = LS.solve(spec_with((P("col.a2+10"), P("dev.y0"))), [])
        self.assertEqual((g.nodes["rt"].cx, g.nodes["rt"].cy), (g.cols["a2"] + 10, g.nodes["dev"].icon.y0))
        # a node's icon edge, a group's edge; the region still contains the node
        spec = spec_with((P("svc.x1"), M.Expr("group", "ra", "y1", offset=-80)))
        g = LS.solve(spec, [])
        self.assertEqual(g.nodes["rt"].cx, g.nodes["svc"].icon.x1)
        self.assertEqual(g.nodes["rt"].cy, g.groups["ra"].rect.y1 - 80)
        self.assertTrue(contains(g.groups["ra"].rect, g.nodes["rt"].footprint()))
        self.assertTrue(any(r.startswith("x col") for r in g.explain))
        # numbers keep working as before
        g = LS.solve(spec_with((400.0, 300.0)), [])
        self.assertEqual((g.nodes["rt"].cx, g.nodes["rt"].cy), (400, 300))

    def test_requirements_and_colspan(self):
        spec = nfw_spec()
        reqs = [Requirement("x", "node:igw", "node:inet", 48 + 24 + 4 + 24 + 4, "arrow 48 into inet", "edge:6"),
                Requirement("y", "group:az.1.B", "group:az.2.T", 132, "tgw fan-out", "edge:2"),
                Requirement("x", "col:tgw", "col:eni", 202, "trunk corridor", "edge:2")]
        g = self.all_hold(spec, reqs)
        self.assertEqual(g.nodes["inet"].cx - g.nodes["igw"].cx, max(104, g.nodes["inet"].cx - g.nodes["igw"].cx))
        self.assertGreaterEqual(g.groups["az.2"].rect.y0 - g.groups["az.1"].rect.y1, 132)
        # colspan: a node over two tracks sits between them; requirements hold at its center
        spec = mini_spec()
        spec.nodes["alb"].col, spec.nodes["alb"].col2 = "pub", "app"
        g = LS.solve(spec, [Requirement("x", "node:igw", "node:alb", 150, "arrow", "edge:0")])
        self.assertEqual(g.nodes["alb"].cx, (g.cols["pub"] + g.cols["app"]) / 2)
        self.assertGreaterEqual(g.nodes["alb"].cx - g.nodes["igw"].cx, 150)
        self.assertLess(g.cols["pub"] - g.nodes["igw"].cx, 150)

    def test_colspan_reserves_from_its_center(self):
        """A colspan node's half width is reserved from its center (b1 + b2) / 2, not left
        of b1 and right of b2 (slide tgw: TGW B RT's long route line under DR / Analytics
        VPC no longer widens Region B by the span)."""
        spec = build("span", ["b1", "b2"], ["top", "bot"],
                     [dict(id="cloud", type="cloud"), dict(id="rb", type="region", label="Region", parent="cloud")],
                     [dict(id="dr", icon="service/Amazon-Virtual-Private-Cloud", label="DR VPC", sub=["10.16.0.0/16"],
                           parent="rb", col="b1", row="top"),
                      dict(id="ana", icon="service/Amazon-Virtual-Private-Cloud", label="Analytics VPC",
                           sub=["10.17.0.0/16"], parent="rb", col="b2", row="top"),
                      dict(id="rtb", icon="resource/Amazon-Route-53_Route-Table", label="TGW B RT",
                           sub=["VPC 경로 전파", "10.0.0.0/13 · 192.168.0.0/16"], parent="rb", col="b1", col2="b2",
                           row="bot")], mode="slide")
        g = LS.solve(spec, [])
        rb, rtb = g.groups["rb"].rect, g.nodes["rtb"]
        half = math.ceil(M.layout_text_width("10.0.0.0/13 · 192.168.0.0/16", 12) / 2)
        self.assertEqual(rtb.cx, (g.cols["b1"] + g.cols["b2"]) / 2)
        self.assertGreaterEqual(rtb.cx - half - rb.x0, 8)                  # pad from the center's footprint
        self.assertGreaterEqual(rb.x1 - rtb.cx - half, 8)
        self.assertLess(rb.x1 - rb.x0, 2 * half + 16 + (g.cols["b2"] - g.cols["b1"]))   # the old reservation
        self.assertEqual(rb.x1 - rb.x0, 2 * half + 16)                      # nothing else is wider
        self.assertEqual(check(spec, g), [])

    @staticmethod
    def span_spec(t_label, flow=False):
        """t over b1..b2 beside l; a long bottom-row label (w) holds b0 → b2 wide, so the
        span g(s) found grows by half of every span s assumed (67 → 100.5 → 117.25 …)."""
        rows = ["main", "bot"] + ([("svc", {"flow": 100})] if flow else [])
        ec2 = "service/Amazon-EC2"
        nodes = [dict(id="l", icon=ec2, label="L", parent="vpc", col="b0", row="main"),
                 dict(id="t", icon=ec2, label=t_label, parent="vpc", col="b1", col2="b2", row="main"),
                 dict(id="w", icon=ec2, label="A bottom row node with an extremely long label that pushes",
                      parent="vpc", col="b0", row="bot"),
                 dict(id="z", icon=ec2, label="Z", parent="vpc", col="b2", row="bot")]
        if flow:
            nodes += [dict(id=f"f{k}", icon="service/Amazon-Simple-Storage-Service", label=f"F{k}", parent="vpc",
                           row="svc", flow_index=k) for k in range(2)]
        return build("spanconv", ["b0", "b1", "b2"], rows,
                     [dict(id="cloud", type="cloud"), dict(id="vpc", type="vpc", label="VPC", parent="cloud")], nodes)

    def test_colspan_span_reaches_its_fixed_point(self):
        """The span is the fixed point g(s) = s, not where 4 rounds of s ← g(s) stopped:
        t's center sits exactly the label pitch from l, b2 − b1 is 134, and a flow row in the
        same box is still centered (every round rebuilds the x model whole)."""
        calls = []
        orig = LS._solve_axis

        def counting(m, axis, cons):
            calls.append(axis)
            return orig(m, axis, cons)

        LS._solve_axis = counting
        try:
            g = LS.solve(self.span_spec("A colspan node with a very long label line", flow=True), [])
        finally:
            LS._solve_axis = orig
        self.assertEqual(g.cols["b2"] - g.cols["b1"], 134)
        self.assertEqual(g.nodes["t"].cx, (g.cols["b1"] + g.cols["b2"]) / 2)
        self.assertLessEqual(calls.count("x"), 4)                       # s = 0, plain step, secant, the answer
        vpc, f = g.groups["vpc"].rect, [g.nodes["f0"].cx, g.nodes["f1"].cx]
        self.assertAlmostEqual((f[0] + f[1]) / 2, vpc.cx, delta=1)
        self.assertEqual(g.warnings, [])

    def test_colspan_span_overshoot_brackets(self):
        """When the reservation stops pulling b1 left (b1 reaches b0), the secant step
        overshoots; regula falsi comes back to the smallest span that holds (284)."""
        g = LS.solve(self.span_spec("Short", flow=True), [])
        self.assertEqual(g.cols["b1"], g.cols["b0"])
        self.assertAlmostEqual(g.cols["b2"] - g.cols["b1"], 284, delta=LS.SPAN_TOL)
        self.assertEqual(g.warnings, [])

    def test_colspan_span_cap(self):
        """Out of rounds: a warning names the node, and the answer still holds its span and
        centers its flow row (nothing of the last round's model is lost)."""
        rounds = LS.SPAN_ROUNDS
        LS.SPAN_ROUNDS = 1
        try:
            g = LS.solve(self.span_spec("A colspan node with a very long label line", flow=True), [])
        finally:
            LS.SPAN_ROUNDS = rounds
        self.assertEqual([w for w in g.warnings if "did not settle" in w and " t:" in w], g.warnings)
        self.assertEqual(len(g.warnings), 1)
        self.assertGreaterEqual(g.cols["b2"] - g.cols["b1"], 67)
        vpc, f = g.groups["vpc"].rect, [g.nodes["f0"].cx, g.nodes["f1"].cx]
        self.assertAlmostEqual((f[0] + f[1]) / 2, vpc.cx, delta=1)

    def test_pane_note_block(self):
        spec = nfw_spec()
        nb = NoteBlock("pane", w=300, h=400, requirements=[
            Requirement("x", "origin", "group:cloud.L", K.PANE_X + 300 + K.PANE_GAP, "pane width", "note")])
        g = LS.solve(spec, [], note_block=nb)
        self.assertEqual(g.groups["cloud"].rect.x0, K.PANE_X + 300 + K.PANE_GAP)
        self.assertGreaterEqual(g.canvas_h, g.groups["cloud"].rect.y0 + 400 + 16)
        nb = NoteBlock("panel", w=0, h=140)
        g2 = LS.solve(spec, [], note_block=nb)
        self.assertEqual(g2.canvas_h, g2.drawing.y1 + 16 + 140 + 16)


class FlowColumnTest(unittest.TestCase):
    """Flow columns: col-only nodes stacked top → bottom, aligned in the parent's height,
    no rows of their own."""
    IDS = ["acm", "waf", "cw", "s3"]

    def test_stack_pitch_and_center(self):
        spec = flowcol_spec()
        g = LS.solve(spec, [])
        ns = [g.nodes[i] for i in self.IDS]
        self.assertEqual(len({n.cx for n in ns}), 1)                       # one column
        self.assertEqual([b.cy - a.cy for a, b in zip(ns, ns[1:])], [100, 100, 100])
        reg = g.groups["region"].rect
        self.assertLessEqual(abs((ns[0].icon.y0 + ns[-1].footprint().y1) / 2 - reg.cy), 1)
        for n in ns:
            self.assertTrue(contains(reg, n.footprint()), n.id)
            self.assertTrue(n.cx - spec.S / 2 > g.groups["vpc"].rect.x1, n.id)   # right of the VPC
        self.assertEqual(check(spec, g), [])

    def test_no_rows_of_its_own(self):
        """The stack moves no row track and leaves the Region's height to the VPC."""
        for mode in ("document", "slide"):
            with self.subTest(mode=mode):
                g0 = LS.solve(mini_spec(mode), [])
                g = LS.solve(flowcol_spec(mode), [])
                self.assertEqual(g.rows, g0.rows)
                self.assertEqual((g.groups["region"].rect.y0, g.groups["region"].rect.y1),
                                 (g0.groups["region"].rect.y0, g0.groups["region"].rect.y1))

    def test_label_stack_beats_a_small_pitch(self):
        spec = flowcol_spec(pitch=10)
        g = LS.solve(spec, [])
        f = LS._footprint(spec, spec.nodes["acm"])
        want = f.bot - (-spec.S / 2) + spec.const.stack_gap
        ns = [g.nodes[i] for i in self.IDS]
        self.assertEqual([b.cy - a.cy for a, b in zip(ns, ns[1:])], [want] * 3)
        for a, b in zip(ns, ns[1:]):
            self.assertGreaterEqual(b.icon.y0 - a.footprint().y1, spec.const.stack_gap)

    def test_align_top_and_bottom(self):
        top = LS.solve(flowcol_spec(align="top"), [])
        reg = top.groups["region"].rect
        inset = K.top_inset("region", top.mode, "icon")
        self.assertEqual(top.nodes["acm"].icon.y0 - reg.y0, inset)
        bot = LS.solve(flowcol_spec(align="bottom"), [])
        mc = K.mode("slide")
        reg = bot.groups["region"].rect
        self.assertEqual(reg.y1 - bot.nodes["s3"].last_baseline, mc.label_bottom)

    def test_taller_stack_grows_the_parent_down(self):
        g0 = LS.solve(mini_spec("slide"), [])
        g = LS.solve(flowcol_spec(pitch=200), [])
        self.assertEqual(g.rows, g0.rows)
        self.assertGreater(g.groups["region"].rect.y1, g0.groups["region"].rect.y1)
        self.assertEqual(g.nodes["s3"].cy - g.nodes["acm"].cy, 600)

    def test_requirement_on_a_stack_node(self):
        """A "node:" requirement on the y axis acts on the stacked center (feedback rounds)."""
        spec = flowcol_spec()
        g = LS.solve(spec, [Requirement("y", "node:waf", "node:cw", 140, "feedback: text too close", "node:cw")])
        self.assertGreaterEqual(g.nodes["cw"].cy - g.nodes["waf"].cy, 140)

    def test_explain(self):
        g = LS.solve(flowcol_spec(), [])
        lines = [e for e in g.explain if e.startswith("y flow svc")]
        self.assertEqual(len(lines), 4)
        self.assertIn("icon inset", lines[0])
        self.assertIn("flow pitch 100 acm ↓ waf", lines[1])
        self.assertIn("centered in region", lines[1])


class CycleTest(unittest.TestCase):
    def test_positive_cycle_reports_why_and_owner(self):
        spec = mini_spec()
        reqs = [Requirement("x", "col:pub", "col:app", 400, "arrow 48 + label", "edge:1"),
                Requirement("x", "col:app", "col:pub", -350, "keep pub near app", "edge:2")]
        with self.assertRaises(SolveError) as cm:
            LS.solve(spec, reqs)
        text = "\n".join(cm.exception.problems)
        self.assertIn("arrow 48 + label", text)
        self.assertIn("keep pub near app", text)
        self.assertTrue(all(p.split(":")[0] for p in cm.exception.problems))

    def test_cycle_with_spec_constraints(self):
        spec = mini_spec()
        # the IGW is pinned on the VPC border; asking for it 40 right of the VPC's left edge contradicts it
        with self.assertRaises(SolveError) as cm:
            LS.solve(spec, [Requirement("x", "group:vpc.L", "node:igw", 40, "igw inside", "edge:0")])
        text = "\n".join(cm.exception.problems)
        self.assertIn("igw inside", text)
        self.assertIn("left border of vpc", text)
        self.assertTrue(any(p.startswith("nodes[") for p in cm.exception.problems), text)

    def test_soft_dropped_first(self):
        spec = mini_spec()
        reqs = [Requirement("x", "col:pub", "col:app", 400, "arrow 48 (soft)", "edge:1", soft=True),
                Requirement("x", "col:app", "col:pub", -300, "hard cap", "edge:2")]
        g = LS.solve(spec, reqs)
        self.assertLessEqual(g.cols["app"] - g.cols["pub"], 300)
        self.assertTrue(any("dropped soft" in w for w in g.warnings), g.warnings)

    def test_empty_box_without_span_warns(self):
        spec = mini_spec()
        spec.nodes = {k: v for k, v in spec.nodes.items() if not k.startswith("nat.")}
        for g in spec.groups.values():
            g.nodes = [n for n in g.nodes if n in spec.nodes]
            if g.id.startswith("pub."):
                g.cols = None
        g = LS.solve(spec, [])
        self.assertTrue(any("pub.1: no node inside and no span" in w for w in g.warnings), g.warnings)
        for i in ("1", "2"):
            spec.groups[f"pub.{i}"].cols = spec.groups[f"pub.{i}"].span_cols = ("pub", "pub")
        g = LS.solve(spec, [])
        self.assertFalse(g.warnings)
        self.assertGreaterEqual(g.groups["app.1"].rect.x0 - g.groups["pub.1"].rect.x1, K.DOCUMENT.sibling_gap)

    def test_unknown_variable(self):
        with self.assertRaises(SolveError) as cm:
            LS.solve(mini_spec(), [Requirement("x", "col:nope", "col:app", 1, "x", "edge:0")])
        self.assertIn("col:nope", cm.exception.problems[0])


class DeterminismTest(unittest.TestCase):
    def test_same_result_twice(self):
        for mk in (alb_spec, nfw_spec):
            a, b = LS.solve(mk(), []), LS.solve(mk(), [])
            self.assertEqual(a, b)
            sa = to_svg(mk(), a, LS.draw(mk(), a))
            sb = to_svg(mk(), b, LS.draw(mk(), b))
            self.assertEqual(sa, sb)


class ExplainTest(unittest.TestCase):
    def test_every_track_explained(self):
        spec = nfw_spec()
        g = LS.solve(spec, [Requirement("x", "col:tgw", "col:eni", 320, "trunk corridor 76 + insets", "edge:2")])
        self.assertEqual(len(g.explain), len(spec.cols) + len(spec.rows))
        line = next(e for e in g.explain if e.startswith("x col eni"))
        self.assertIn("trunk corridor", line)
        if VERBOSE:
            print("\n" + "\n".join(g.explain))


class DrawTest(unittest.TestCase):
    def test_elements(self):
        spec = nfw_spec()
        g = LS.solve(spec, [])
        els = LS.draw(spec, g)
        owners = [e.owner for e in els]
        # contiguous runs per owner, groups (Z_GROUP) before nodes (Z_NODE), spec order
        runs = [o for i, o in enumerate(owners) if i == 0 or owners[i - 1] != o]
        self.assertEqual(runs, [f"group:{k}" for k in spec.groups] + [f"node:{k}" for k in spec.nodes])
        self.assertTrue(all(e.z == K.Z_GROUP for e in els if e.owner.startswith("group:")))
        self.assertTrue(all(e.z == K.Z_NODE for e in els if e.owner.startswith("node:")))
        insp = [e for e in els if e.owner == "group:insp"]
        self.assertEqual([e.kind for e in insp], ["rect", "image", "text", "text"])
        self.assertEqual(insp[0].attrs["stroke"], "#8C4FFF")
        self.assertEqual(insp[1].attrs["href"], "bundle:group/Virtual-private-cloud-VPC_32")
        self.assertEqual(insp[3].attrs["fill"], K.TEXT_CIDR.fill)
        igw = [e for e in els if e.owner == "node:igw"]
        self.assertEqual([e.kind for e in igw], ["rect", "image", "text"])
        self.assertEqual(igw[0].attrs["fill"], "#FFFFFF")
        fwe = [e for e in els if e.owner == "node:fwe.1"]
        self.assertEqual([(e.attrs["font-size"], e.attrs["fill"]) for e in fwe[1:]],
                         [(14, K.INK), (12, K.GRAY), (12, K.GRAY)])
        self.assertEqual(fwe[2].attrs["y"] - fwe[1].attrs["y"], 16)
        az = [e for e in els if e.owner == "group:az.1"]
        self.assertEqual(az[0].attrs["stroke-dasharray"], "8,4")
        self.assertEqual(az[1].attrs["x"], az[0].attrs["x"] + 12)

    def test_check_layout_clean(self):
        for mk in (alb_spec, nfw_spec, mini_spec):
            for mode in ("document", "slide"):
                with self.subTest(spec=mk.__name__, mode=mode):
                    spec = mk(mode)
                    g = LS.solve(spec, [])
                    self.assertEqual(check(spec, g), [])


if __name__ == "__main__":
    argv = [a for a in sys.argv if a != "-v"]
    unittest.main(argv=argv, verbosity=2 if VERBOSE else 1)
