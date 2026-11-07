#!/usr/bin/env python3
"""layout_spec.load / parse_expr: the DESIGN 3 example specs expand as traced, and every
kind of spec problem gives its exact message.

    python3 tests/test_layout_spec.py

Needs PyYAML (`uv run --with pyyaml python3 tests/test_layout_spec.py` where it is missing)
and the icon bundle, like every script of the skill.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import layout_model as M  # noqa: E402
import layout_solve  # noqa: E402
import layout_spec as L  # noqa: E402
from layout_model import SpecError  # noqa: E402

# DESIGN 3.1 NFW, 3.2 ALB, 3.3 TGW, verbatim.
NFW = """\
name: nfw-reference-architecture
mode: document
cols: [spoke, tgw, eni, fw, nat, igw, inet]
rows: [az1, main, az2]

groups:
  - {id: cloud,  type: cloud}
  - {id: region, type: region, label: Region ap-northeast-2, in: cloud}
  - {id: vpca,   type: vpc, label: VPC A, cidr: 10.1.0.0/16, in: region}
  - {id: sna,    type: private, label: App subnet, in: vpca}
  - {id: vpcb,   type: vpc, label: VPC B, cidr: 10.2.0.0/16, in: region}
  - {id: snb,    type: private, label: App subnet, in: vpcb}
  - {id: insp,   type: vpc, label: Inspection VPC, cidr: 100.64.0.0/16, in: region}
  - {id: az,     type: az, in: insp, per: [az1, az2]}
  - {id: tgwsn,  type: private, label: TGW subnet, in: az}
  - {id: fwsn,   type: private, label: Firewall subnet, in: az}
  - {id: pubsn,  type: public,  label: Public subnet, in: az}

nodes:
  - {id: ec2a, icon: service/Amazon-EC2, label: EC2, sub: "0.0.0.0/0 → TGW", in: sna, at: [spoke, az1]}
  - {id: ec2b, icon: service/Amazon-EC2, label: EC2, sub: "0.0.0.0/0 → TGW", in: snb, at: [spoke, az2]}
  - {id: tgw,  icon: service/AWS-Transit-Gateway, label: TGW, in: region, at: [tgw, main]}
  - {id: rtfw, icon: resource/Amazon-Route-53_Route-Table, label: Firewall RT, sub: "VPC A · B 전파", in: region, at: [tgw, az1]}
  - {id: rtsp, icon: resource/Amazon-Route-53_Route-Table, label: Spoke RT, sub: "0.0.0.0/0 → 검사 VPC", in: region, at: [tgw, az2]}
  - {id: eni,  icon: resource/AWS-Transit-Gateway_Attachment, label: TGW ENI, sub: "0.0.0.0/0 → 같은 AZ 방화벽", in: tgwsn, col: eni}
  - {id: fwe,  icon: resource/AWS-Network-Firewall_Endpoints, label: Firewall endpoint, sub: ["0.0.0.0/0 → 같은 AZ NAT", "10.0.0.0/8 → TGW"], in: fwsn, col: fw}
  - {id: nat,  icon: resource/Amazon-VPC_NAT-Gateway, label: NAT gateway, sub: ["0.0.0.0/0 → IGW", "10.0.0.0/8 → 같은 AZ 방화벽"], in: pubsn, col: nat}
  - {id: nfw,  icon: service/AWS-Network-Firewall, label: AWS Network Firewall, in: insp, at: [fw, main]}
  - {id: igw,  icon: resource/Amazon-VPC_Internet-Gateway, label: IGW, on: insp, at: [igw, main]}
  - {id: inet, icon: resource/Internet, label: Internet, at: [inet, main]}

edges:
  - {e: "vpca <-> tgw", verb: VPC attachment, step: 1, step_at: end}
  - {e: "vpcb <-> tgw"}
  - {e: "tgw <-> eni.*", step: 2, step_at: start}
  - {e: "eni.* <-> fwe.*", step: 3}
  - {e: "fwe.* -> nat.*", step: 4}
  - {e: "nat.* -> igw", trunk: true, step: 5}
  - {e: "igw -> inet"}

note:
  steps:
    - [VPC → TGW, "VPC A·B의 App 서브넷 RT가 0.0.0.0/0을 TGW로 보내, VPC 간 트래픽과 인터넷행 트래픽이 모두 TGW로 들어옵니다."]
    - [TGW → 검사 VPC, "Spoke VPC attachment에 연결된 Spoke RT의 0.0.0.0/0이 검사 VPC attachment를 가리킵니다. appliance mode로 한 흐름의 양방향이 같은 AZ를 지납니다."]
    - [TGW ENI → 방화벽, "TGW 서브넷 RT 0.0.0.0/0 → 같은 AZ 방화벽 엔드포인트. 검사를 통과한 VPC 간 트래픽은 10.0.0.0/8 → TGW로 돌아가고, Firewall RT가 목적지 VPC로 보냅니다."]
    - [방화벽 → NAT, "인터넷행 트래픽은 방화벽 서브넷 RT 0.0.0.0/0 → 같은 AZ NAT 게이트웨이로 가고, NAT가 출발지 주소를 퍼블릭 IP로 바꿉니다."]
    - [NAT → IGW, "퍼블릭 서브넷 RT 0.0.0.0/0 → IGW로 인터넷에 나갑니다. 응답은 10.0.0.0/8 → 같은 AZ 방화벽을 거쳐 다시 검사된 뒤 VPC로 돌아옵니다."]
"""

ALB = """\
name: alb-reference-architecture
mode: document
cols: [users, r53, igw, pub, app1, app2, db]
rows: [{id: svc, flow: 160}, az1, main, az2]

groups:
  - {id: cloud,  type: cloud}
  - {id: region, type: region, label: Region, in: cloud}
  - {id: vpc,    type: vpc, label: VPC, cidr: 10.0.0.0/16, in: region}
  - {id: az,     type: az, in: vpc, per: [az1, az2]}
  - {id: pubsn,  type: public,  label: Public subnet, in: az}
  - {id: appsn,  type: private, label: App subnet, in: az}
  - {id: dbsn,   type: private, label: DB subnet, in: az}
  - {id: asg,    type: asg, label: ASG · target group, over: [ec2a.*, ec2b.*], header: right}

nodes:
  - {id: users, icon: resource/Users, label: Users, at: [users, main]}
  - {id: r53,  icon: service/Amazon-Route-53, label: Route 53, sub: alias → ALB, in: cloud, at: [r53, svc]}
  - {id: acm,  icon: service/AWS-Certificate-Manager, label: ACM, sub: HTTPS 리스너 인증서, in: region, row: svc}
  - {id: waf,  icon: service/AWS-WAF, label: AWS WAF, sub: ALB에 연결한 Web ACL, in: region, row: svc}
  - {id: cw,   icon: service/Amazon-CloudWatch, label: CloudWatch, sub: 지표 · 경보, in: region, row: svc}
  - {id: s3,   icon: service/Amazon-Simple-Storage-Service, label: S3, sub: ALB 액세스 로그, in: region, row: svc}
  - {id: nat,  icon: resource/Amazon-VPC_NAT-Gateway, label: NAT gateway, in: pubsn, col: pub}
  - {id: ec2a, icon: service/Amazon-EC2, label: EC2, in: appsn, col: app1}
  - {id: ec2b, icon: service/Amazon-EC2, label: EC2, in: appsn, col: app2}
  - {id: rds,  icon: service/Amazon-RDS, label: {1: RDS Primary, 2: RDS Standby}, in: dbsn, col: db}
  - {id: alb,  icon: resource/Elastic-Load-Balancing_Application-Load-Balancer, label: ALB, in: vpc, at: [pub, main]}
  - {id: igw,  icon: resource/Amazon-VPC_Internet-Gateway, label: IGW, on: vpc, at: [igw, main]}

edges:
  - {e: "users -> igw", label: "HTTPS :443"}
  - {e: "igw -> alb"}
  - {e: "alb -> asg", label: "HTTP :80"}
  - {e: "asg -> rds.1", label: SQL}
  - {e: "users ..> r53", verb: DNS 조회}
  - {e: "asg ..> nat.*", verb: 아웃바운드}
  - {e: "rds.1 ..> rds.2", verb: 동기식 복제, label_at: left}

note:
  summary: "Internet-facing ALB · 두 AZ에 걸친 단일 관리형 로드 밸런서 · AWS WAF 연결 · RDS Multi-AZ"
"""

TGW = """\
name: tgw-reference-architecture
mode: document
cols: [cgw, inet, vpn, a1, a2, a3, peer, b1, b2]
rows: [top, main, bot]

groups:
  - {id: onprem, type: onprem, label: On-premises}
  - {id: cloud,  type: cloud}
  - {id: ra,     type: region, label: Region ap-northeast-2, in: cloud}
  - {id: rb,     type: region, label: Region ap-northeast-1, in: cloud}

nodes:
  - {id: cgw,  icon: resource/Amazon-VPC_Customer-Gateway, label: Customer gateway, sub: 192.168.0.0/16, in: onprem, at: [cgw, main]}
  - {id: inet, icon: resource/Internet, label: Internet, at: [inet, main]}
  - {id: vpn,  icon: service/AWS-Site-to-Site-VPN, label: Site-to-Site VPN, at: [vpn, main]}
  - {id: tgwa, icon: service/AWS-Transit-Gateway, label: Transit Gateway A, in: ra, at: [a2, main]}
  - {id: svcs, icon: service/Amazon-Virtual-Private-Cloud, label: Services VPC, sub: 10.1.0.0/16, in: ra, at: [a1, top]}
  - {id: prod, icon: service/Amazon-Virtual-Private-Cloud, label: Prod VPC, sub: 10.2.0.0/16, in: ra, at: [a3, top]}
  - {id: dev,  icon: service/Amazon-Virtual-Private-Cloud, label: Dev VPC, sub: 10.3.0.0/16, in: ra, at: [a1, bot]}
  - {id: test, icon: service/Amazon-Virtual-Private-Cloud, label: Test VPC, sub: 10.4.0.0/16, in: ra, at: [a3, bot]}
  - {id: rta,  icon: resource/Amazon-Route-53_Route-Table, label: TGW A RT, sub: ["VPC·VPN 경로 전파", "10.16.0.0/13 → peering"], in: ra, at: [a2, bot]}
  - {id: peer, icon: resource/Amazon-VPC_Peering-Connection, label: TGW peering, sub: peering attachment, in: cloud, at: [peer, main]}
  - {id: tgwb, icon: service/AWS-Transit-Gateway, label: Transit Gateway B, in: rb, at: [b1..b2, main]}
  - {id: dr,   icon: service/Amazon-Virtual-Private-Cloud, label: DR VPC, sub: 10.16.0.0/16, in: rb, at: [b1, top]}
  - {id: ana,  icon: service/Amazon-Virtual-Private-Cloud, label: Analytics VPC, sub: 10.17.0.0/16, in: rb, at: [b2, top]}
  - {id: rtb,  icon: resource/Amazon-Route-53_Route-Table, label: TGW B RT, sub: ["VPC 경로 전파", "10.0.0.0/13 · 192.168.0.0/16 → peering"], in: rb, at: [b1..b2, bot]}

edges:                       # 위상도: '--' = 실선, 머리 없음
  - {e: "cgw -- inet"}
  - {e: "inet -- vpn", label: IPsec, step: 1}
  - {e: "vpn -- tgwa", verb: VPN attachment, step: 2}
  - {e: "tgwa -- svcs", verb: VPC attachment}
  - {e: "tgwa -- prod"}
  - {e: "tgwa -- dev"}
  - {e: "tgwa -- test"}
  - {e: "tgwa -- peer", step: 3, step_at: gap}
  - {e: "peer -- tgwb"}
  - {e: "tgwb -- dr", step: 4}
  - {e: "tgwb -- ana"}

note:
  steps:
    - [Customer gateway → VPN, "온프레미스 192.168.0.0/16의 트래픽을 고객 게이트웨이가 IPsec 터널로 Site-to-Site VPN에 보내고, 두 쪽은 BGP로 경로를 교환합니다."]
    - [VPN → TGW A, "VPN attachment로 TGW A에 들어오고, 온프레미스 경로는 BGP로 TGW A RT에 전파됩니다. 스포크 VPC 서브넷 RT: 10.0.0.0/8 · 192.168.0.0/16 → TGW."]
    - [TGW A → TGW B, "TGW A RT의 정적 경로 10.16.0.0/13 → peering으로 AWS 백본을 거쳐 ap-northeast-1의 TGW B에 닿습니다. 피어링은 경로 전파가 없어 양쪽 다 정적 경로입니다."]
    - [TGW B → DR VPC, "TGW B RT에 전파된 10.16.0.0/16 경로로 VPC attachment를 지나 DR VPC에 닿고, 반환은 TGW B RT의 정적 경로 192.168.0.0/16 → peering으로 같은 길입니다."]
"""


def load_text(text, suffix=".layout.yaml", **kw):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / f"t{suffix}"
        p.write_text(text, encoding="utf-8")
        return L.load(p, **kw)


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


class ExampleSpecs(unittest.TestCase):
    """DESIGN 3.1-3.3 load and expand as the design traces them."""

    def test_nfw(self):
        s = load_text(NFW)
        self.assertEqual((s.name, s.mode, s.title, s.S), ("nfw-reference-architecture", "document", True, 48))
        self.assertEqual(len(s.nodes), 14)       # 8 plain + eni/fwe/nat × 2
        self.assertEqual(len(s.groups), 15)      # 7 plain + (az + 3 subnets) × 2
        self.assertEqual(list(s.groups)[:7], ["cloud", "region", "vpca", "sna", "vpcb", "snb", "insp"])
        self.assertEqual(list(s.groups)[7:], ["az.1", "tgwsn.1", "fwsn.1", "pubsn.1",
                                              "az.2", "tgwsn.2", "fwsn.2", "pubsn.2"])
        self.assertEqual(s.groups["insp"].children, ["az.1", "az.2"])
        az2 = s.groups["az.2"]
        self.assertEqual((az2.label, az2.template, az2.instance, az2.rows, az2.cols, az2.depth, az2.dash),
                         ("Availability Zone 2", "az", 2, ("az2", "az2"), ("eni", "nat"), 3, "8,4"))
        self.assertEqual(s.groups["region"].label, "Region ap-northeast-2")
        self.assertEqual(s.groups["cloud"].label, "AWS Cloud")
        self.assertEqual(s.groups["insp"].cidr, "100.64.0.0/16")
        fwe = s.nodes["fwe.1"]
        self.assertEqual((fwe.parent, fwe.col, fwe.row, fwe.sub, fwe.template, fwe.instance),
                         ("fwsn.1", "fw", "az1", ["0.0.0.0/0 → 같은 AZ NAT", "10.0.0.0/8 → TGW"], "az", 1))
        self.assertEqual(s.nodes["nat.2"].row, "az2")
        igw = s.nodes["igw"]
        self.assertEqual((igw.on, igw.parent, igw.side), ("insp", "region", "right"))
        self.assertNotIn("igw", s.groups["region"].nodes + s.groups["insp"].nodes)
        self.assertEqual(s.nodes["inet"].parent, None)
        self.assertEqual([(e.a, e.op, e.b) for e in s.edges], [
            ("vpca", "<->", "tgw"), ("vpcb", "<->", "tgw"), ("tgw", "<->", "eni.1"), ("tgw", "<->", "eni.2"),
            ("eni.1", "<->", "fwe.1"), ("eni.2", "<->", "fwe.2"), ("fwe.1", "->", "nat.1"),
            ("fwe.2", "->", "nat.2"), ("nat.1", "->", "igw"), ("nat.2", "->", "igw"), ("igw", "->", "inet")])
        self.assertEqual([e.step for e in s.edges], [1, None, 2, None, 3, None, 4, None, 5, None, None])
        self.assertEqual([e.n for e in s.edges], list(range(11)))
        self.assertEqual([(e.line, e.k) for e in s.edges][2:4], [(2, 0), (2, 1)])
        e0 = s.edges[0]
        self.assertEqual((e0.a_kind, e0.b_kind, e0.verb, e0.step_at, e0.head_start, e0.head_end),
                         ("group", "node", "VPC attachment", "end", True, True))
        self.assertEqual(s.edges[2].step_at, "start")
        self.assertTrue(s.edges[8].trunk and s.edges[9].trunk)
        self.assertEqual(len(s.note.steps), 5)
        self.assertEqual(s.note.steps[1][0], "TGW → 검사 VPC")
        self.assertEqual(s.warnings, [])

    def test_alb(self):
        s = load_text(ALB)
        self.assertEqual(len(s.nodes), 16)
        self.assertEqual(len(s.groups), 12)
        self.assertEqual(list(s.groups)[-1], "asg")      # overlays last
        asg = s.groups["asg"]
        self.assertEqual((asg.overlay, asg.parent, asg.over, asg.header, asg.cols, asg.rows, asg.label),
                         (True, None, ["ec2a.1", "ec2a.2", "ec2b.1", "ec2b.2"], "right", ("app1", "app2"),
                          ("az1", "az2"), "ASG · target group"))
        self.assertEqual(s.cols[0].id, "users")
        svc = s.rows[0]
        self.assertEqual((svc.id, svc.flow), ("svc", 160.0))
        self.assertEqual([(n.id, n.flow_index) for n in s.nodes.values() if n.flow_index is not None],
                         [("acm", 0), ("waf", 1), ("cw", 2), ("s3", 3)])
        self.assertEqual([s.nodes[i].col for i in ("acm", "s3")], [None, None])
        self.assertEqual((s.nodes["r53"].col, s.nodes["r53"].row, s.nodes["r53"].parent), ("r53", "svc", "cloud"))
        self.assertEqual((s.nodes["rds.1"].label, s.nodes["rds.2"].label), ("RDS Primary", "RDS Standby"))
        self.assertEqual(s.nodes["r53"].sub, ["alias → ALB"])
        self.assertEqual((s.nodes["igw"].side, s.nodes["igw"].parent), ("left", "region"))
        self.assertEqual(s.groups["appsn.2"].nodes, ["ec2a.2", "ec2b.2"])
        self.assertEqual([(e.a, e.op, e.b, e.a_kind, e.b_kind) for e in s.edges], [
            ("users", "->", "igw", "node", "node"), ("igw", "->", "alb", "node", "node"),
            ("alb", "->", "asg", "node", "group"), ("asg", "->", "rds.1", "group", "node"),
            ("users", "..>", "r53", "node", "node"), ("asg", "..>", "nat.1", "group", "node"),
            ("asg", "..>", "nat.2", "group", "node"), ("rds.1", "..>", "rds.2", "node", "node")])
        self.assertEqual(s.edges[7].label_at, "left")
        self.assertTrue(s.edges[7].dashed)
        self.assertEqual(s.edges[0].label, "HTTPS :443")
        self.assertEqual(s.edges[4].verb, "DNS 조회")
        self.assertTrue(all(e.step is None for e in s.edges))
        self.assertEqual((s.note.summary, s.note.steps, s.note.place), (s.note.summary, [], "auto"))
        self.assertTrue(s.note.summary.startswith("Internet-facing ALB"))
        self.assertEqual(s.warnings, [])

    def test_tgw(self):
        s = load_text(TGW)
        self.assertEqual(len(s.nodes), 14)
        self.assertEqual(list(s.groups), ["onprem", "cloud", "ra", "rb"])
        self.assertEqual(s.groups["onprem"].label, "On-premises")
        tgwb = s.nodes["tgwb"]
        self.assertEqual((tgwb.col, tgwb.col2, tgwb.row), ("b1", "b2", "main"))
        self.assertEqual(s.groups["rb"].cols, ("b1", "b2"))
        self.assertEqual(s.groups["cloud"].cols, ("a1", "b2"))
        self.assertEqual(s.groups["cloud"].rows, ("top", "bot"))
        self.assertTrue(all(e.op == "--" and not e.head_end and not e.dashed for e in s.edges))
        self.assertEqual([(e.a, e.b) for e in s.edges][6:9], [("tgwa", "test"), ("tgwa", "peer"), ("peer", "tgwb")])
        self.assertEqual([(e.n, e.step) for e in s.edges if e.step], [(1, 1), (2, 2), (7, 3), (9, 4)])
        self.assertEqual(s.edges[7].step_at, "gap")
        self.assertEqual(s.edges[1].label, "IPsec")
        self.assertEqual(len(s.note.steps), 4)
        self.assertEqual(s.cloud_id(), "cloud")

    def test_json_file_and_overrides(self):
        s = load_text(json.dumps(base()), suffix=".json", mode="slide", title=False)
        self.assertEqual((s.name, s.mode, s.title), ("t", "slide", False))
        self.assertEqual(s.const.name, "slide")
        self.assertTrue(s.source.endswith("t.json"))

    def test_dict_defaults(self):
        s = L.load(base())
        self.assertEqual((s.source, s.font, s.S), ("<dict>", L.default_font(), 48))
        self.assertEqual(s.groups["az.1"].label, "Availability Zone 1")
        self.assertEqual(s.groups["vpc"].label, "VPC")
        self.assertEqual(s.groups["region"].dash, "3,3")
        self.assertEqual([(e.a, e.b, e.step) for e in s.edges],
                         [("igw", "ec2.1", 1), ("igw", "ec2.2", None), ("inet", "igw", None)])

    def test_name_from_file_stem(self):
        d = base()
        del d["name"]
        s = load_text(json.dumps(d), suffix=".layout.json")
        self.assertEqual(s.name, "t")

    def test_yaml_on_key_stays_a_string(self):
        s = load_text("name: t\ncols: [a, b]\nrows: [r]\n"
                      "groups:\n  - {id: vpc, type: vpc}\n  - {id: sn, type: private, in: vpc}\n"
                      "nodes:\n  - {id: x, icon: service/Amazon-EC2, label: on, in: sn, at: [b, r]}\n"
                      "  - {id: igw, icon: resource/Amazon-VPC_Internet-Gateway, label: IGW, on: vpc, at: [a, r]}\n")
        self.assertEqual(s.nodes["igw"].on, "vpc")
        self.assertEqual(s.nodes["igw"].side, "left")
        self.assertEqual(s.nodes["x"].label, "on")

    def test_icon_alias(self):
        d = base()
        d["nodes"][0]["icon"] = "ec2"
        d["nodes"][2]["icon"] = "Internet"      # 100 beats Internet_Dark 95
        s = L.load(d)
        self.assertEqual((s.nodes["ec2.1"].icon, s.nodes["ec2.1"].icon_query), ("service/Amazon-EC2", "ec2"))
        self.assertEqual(s.nodes["inet"].icon, "resource/Internet")
        self.assertIsNone(s.nodes["igw"].icon_query)

    def test_per_instance_and_n(self):
        d = base()
        d["groups"][4].update(label="Subnet {n}", cidr={1: "10.0.1.0/24", 2: "10.0.2.0/24"})
        d["nodes"][0].update(label={1: "Primary", 2: "Standby"}, sub="AZ {n}", dx={1: 0, 2: 8})
        s = L.load(d)
        self.assertEqual([(g.label, g.cidr) for g in (s.groups["sn.1"], s.groups["sn.2"])],
                         [("Subnet 1", "10.0.1.0/24"), ("Subnet 2", "10.0.2.0/24")])
        self.assertEqual([(n.label, n.sub, n.dx) for n in (s.nodes["ec2.1"], s.nodes["ec2.2"])],
                         [("Primary", ["AZ 1"], 0.0), ("Standby", ["AZ 2"], 8.0)])

    def test_only(self):
        """`only:` keeps an item in some instances; a group's `only` drops what is inside it;
        a.* pairs by shared number; per-instance maps need values only for kept instances."""
        d = base()
        d["groups"].append({"id": "db", "type": "private", "label": "DB subnet", "in": "az", "only": [2]})
        d["nodes"] += [{"id": "writer", "icon": "service/Amazon-Aurora", "label": {1: "Writer"}, "in": "sn",
                        "col": "c", "only": 1},
                       {"id": "reader", "icon": "service/Amazon-Aurora", "label": "Reader", "in": "db", "col": "c"}]
        d["edges"] += [{"e": "ec2.* -> writer.*"}, {"e": "ec2.* -> reader.*"}]
        s = L.load(d)
        self.assertEqual([g for g in s.groups if g.startswith("db")], ["db.2"])
        self.assertEqual(s.groups["az.2"].children, ["sn.2", "db.2"])
        self.assertEqual([n for n in s.nodes if n.startswith(("writer", "reader"))], ["writer.1", "reader.2"])
        self.assertEqual(s.nodes["writer.1"].label, "Writer")
        self.assertEqual([(e.a, e.b) for e in s.edges if e.b.startswith(("writer", "reader"))],
                         [("ec2.1", "writer.1"), ("ec2.2", "reader.2")])

    def test_folded_hop_warns(self):
        """A flow sub-resource with its own icon written into its service node's caption warns;
        the service's own resource (an SNS topic, an event bus) does not."""
        d = base()
        d["nodes"] += [{"id": "ddb", "icon": "service/Amazon-DynamoDB", "label": "DynamoDB",
                        "sub": ["Orders · Streams 켬"], "at": ["c", "az1"], "in": "region"},
                       {"id": "bus", "icon": "resource/Amazon-EventBridge_Custom-Event-Bus", "label": "EventBridge",
                        "sub": ["orders 버스", "규칙 → 2 대상"], "at": ["c", "az2"], "in": "region"},
                       {"id": "sns", "icon": "service/Amazon-Simple-Notification-Service", "label": "SNS",
                        "sub": ["토픽 order-status"], "at": ["a", "az1"], "in": "region"}]
        s = L.load(d)
        folded = [w for w in s.warnings if "sub-caption names" in w]
        self.assertEqual(len(folded), 2, folded)
        self.assertIn("resource/Amazon-DynamoDB_Stream", folded[0])
        self.assertIn("resource/Amazon-EventBridge_Rule", folded[1])

    def test_edge_forms(self):
        d = base()
        d["nodes"].append({"id": "s3", "icon": "service/Amazon-Simple-Storage-Service", "label": "S3",
                           "in": "region", "at": ["c", "az1"]})
        d["edges"] = [
            {"e": "igw -> ec2.*", "step": 1, "step_each": True},
            {"e": "ec2.1 <..> s3, inet", "label_at": {"x": "s3.cx", "y": "s3.y0-10", "anchor": "end"}},
            {"e": "ec2.* .. s3", "steps": {"ec2.2": 1}, "bend_x": "gap(b,c)", "shape": "HVH"},
            {"e": "s3 -- inet", "points": [["s3.x1+4", "s3.cy"], ["col.c+20", "row.main"], ["inet.x0-4", 440]],
             "from_side": "right", "to_offset": -8, "step_at": ["sn.1.cx", "vpc.y0+52"]},
            "inet -- igw",
        ]
        s = L.load(d)
        self.assertEqual([(e.a, e.op, e.b, e.step) for e in s.edges], [
            ("igw", "->", "ec2.1", 1), ("igw", "->", "ec2.2", 1), ("ec2.1", "<..>", "s3", None),
            ("ec2.1", "<..>", "inet", None), ("ec2.1", "..", "s3", None), ("ec2.2", "..", "s3", 1),
            ("s3", "--", "inet", None), ("inet", "--", "igw", None)])
        e = s.edges[2]
        self.assertEqual(e.label_at, M.Place(M.Expr("node", "s3", "cx"), M.Expr("node", "s3", "y0", offset=-10), "end"))
        self.assertEqual(s.edges[4].bend_x, M.Expr("gap", "b", ref2="c"))
        self.assertEqual(s.edges[4].shape, "HVH")
        p = s.edges[6]
        self.assertEqual(p.points[1], (M.Expr("col", "c", offset=20), M.Expr("row", "main")))
        self.assertEqual(p.points[2][1], M.Expr("num", offset=440))
        self.assertEqual(p.step_at, M.Place(M.Expr("group", "sn.1", "cx"), M.Expr("group", "vpc", "y0", offset=52)))
        self.assertEqual((p.from_side, p.to_offset), ("right", -8.0))

    def test_side_must_fit_the_shape(self):
        """from_side / to_side must leave along the shape's end pieces (HVH top / top would
        start a horizontal piece off a top port); points, or no shape, take any side."""
        d = base()
        d["edges"] = [{"e": "inet -> igw", "shape": "HVH", "from_side": "top", "to_side": "right"},
                      {"e": "inet -> igw", "shape": "VH", "from_side": "bottom", "to_side": "top"}]
        with self.assertRaises(SpecError) as cm:
            L.load(d)
        self.assertEqual(cm.exception.problems, [
            "edges[0] inet -> igw: from_side: top does not fit shape HVH, whose first piece is horizontal; use left or right, "
            "or drop shape and let the sides pick it",
            "edges[1] inet -> igw: to_side: top does not fit shape VH, whose last piece is horizontal; use left or right, "
            "or drop shape and let the sides pick it"])
        d["edges"] = [{"e": "igw -> ec2.*", "step": 1},
                      {"e": "inet -> igw", "shape": "VHV", "from_side": "top", "to_side": "top"},
                      {"e": "inet -> igw", "from_side": "top", "to_side": "top"},
                      {"e": "inet -> igw", "shape": "HV", "from_side": "left", "to_side": "bottom"}]
        self.assertEqual(len(L.load(d).edges), 5)

    def test_pad_bottom(self):
        d = base()
        d["groups"][2]["pad_bottom"] = 6
        d["groups"][4]["pad_bottom"] = {1: 20, 2: 30}
        s = L.load(d)
        self.assertEqual((s.groups["vpc"].pad_bottom, s.groups["vpc"].pad), (6.0, None))
        self.assertEqual((s.groups["sn.1"].pad_bottom, s.groups["sn.2"].pad_bottom), (20.0, 30.0))

    def test_raw(self):
        d = base()
        d["raw"] = [{"layer": "below", "svg": '<text x="{inet.label.cx}" y="{inet.y1 + 30}">x</text>'}]
        s = L.load(d)
        self.assertEqual(s.raw[0].layer, "below")
        self.assertEqual(s.raw[0].exprs, {"inet.label.cx": M.Expr("label", "inet", "cx"),
                                          "inet.y1 + 30": M.Expr("node", "inet", "y1", offset=30)})


    def test_xy_expressions(self):
        """xy takes numbers or expressions; numbers stay floats, expressions are resolved
        (node / group) like any hint's."""
        d = base()
        d["nodes"][2].pop("at")
        d["nodes"][2]["xy"] = ["col.c+10", "igw.cy"]
        d["nodes"].append({"id": "fn", "icon": "service/AWS-Lambda", "label": "Fn", "in": "region",
                           "xy": [300, "vpc.y1+40"]})
        s = L.load(d)
        self.assertEqual(s.nodes["inet"].xy, (M.Expr("col", "c", offset=10), M.Expr("node", "igw", "cy")))
        self.assertEqual(s.nodes["fn"].xy, (300.0, M.Expr("group", "vpc", "y1", offset=40)))
        self.assertIsNone(s.nodes["inet"].col)

    def test_xy_references_back(self):
        """A chain of xy references that comes back to its node on one axis is rejected
        (itself, or q → s → t → q), naming the loop; across the two axes it is fine."""
        def nodes(*xys):
            d = base()
            d["nodes"] += [{"id": nid, "icon": "service/AWS-Lambda", "label": nid.upper(), "in": "region", "xy": xy}
                           for nid, xy in xys]
            return d

        hint0 = ("xy[0] takes a number, col.<track>, <node>.(x0|cx|x1) or <group>.(x0|x1), each with an "
                 "optional ±n")
        with self.assertRaises(SpecError) as cm:
            L.load(nodes(("q", ["q.cx+10", "row.main"])))
        self.assertEqual(cm.exception.problems, [f"nodes[3] q: xy[0]: q.cx refers back to q (q → q); {hint0}"])
        with self.assertRaises(SpecError) as cm:
            L.load(nodes(("q", ["s.cx+10", "row.main"]), ("s", ["t.cx+10", "row.main"]),
                         ("t", ["q.cx+10", "row.main"])))
        self.assertEqual(cm.exception.problems, [
            f"nodes[3] q: xy[0]: s.cx refers back to q (q → s → t → q); {hint0}",
            f"nodes[4] s: xy[0]: t.cx refers back to s (s → t → q → s); {hint0}",
            f"nodes[5] t: xy[0]: q.cx refers back to t (t → q → s → t); {hint0}"])
        s = L.load(nodes(("q", ["col.b", "s.cy"]), ("s", ["q.cx", 300])))          # y on s, x on q: no loop
        self.assertEqual(s.nodes["q"].xy, (M.Expr("col", "b"), M.Expr("node", "s", "cy")))
        self.assertEqual(s.nodes["s"].xy, (M.Expr("node", "q", "cx"), 300.0))
        # a chain into a loop it is not on: only the loop's nodes are named
        with self.assertRaises(SpecError) as cm:
            L.load(nodes(("p", ["q.cx", "row.main"]), ("q", ["s.cx", "row.main"]), ("s", ["q.cx", "row.main"])))
        self.assertEqual([m.split(":")[0] for m in cm.exception.problems], ["nodes[4] q", "nodes[5] s"])

    def test_xy_on_a_colspan(self):
        d = base()
        d["nodes"] += [{"id": "w", "icon": "service/AWS-Lambda", "label": "W", "in": "region", "at": ["a..b", "main"]},
                       {"id": "q", "icon": "service/AWS-Lambda", "label": "Q", "in": "region", "xy": ["w.cx", "w.cy"]}]
        with self.assertRaises(SpecError) as cm:
            L.load(d)
        self.assertEqual(cm.exception.problems, [
            "nodes[4] q: xy[0]: w spans two columns (its center is no single variable); use col.<track>; xy[0] "
            "takes a number, col.<track>, <node>.(x0|cx|x1) or <group>.(x0|x1), each with an optional ±n"])
        d["nodes"][-1]["xy"] = ["col.c", "w.cy"]                                     # its y is a row: fine
        self.assertEqual(L.load(d).nodes["q"].xy, (M.Expr("col", "c"), M.Expr("node", "w", "cy")))

    def test_xy_in_a_template(self):
        """In a `per` template, xy names the item's own instance: a template sibling by its
        base id, `row.<per row>` as the instance's row; an explicit other instance stays on
        x and is rejected on y (it sits a row away)."""
        def tmpl(xy, **kw):
            d = base()
            d["nodes"].append(dict({"id": "e2", "icon": "service/Amazon-EC2", "label": "EC2 B", "in": "sn",
                                    "xy": xy}, **kw))
            return d

        s = L.load(tmpl(["col.c", "ec2.cy"]))
        self.assertEqual([s.nodes[f"e2.{n}"].xy for n in (1, 2)],
                         [(M.Expr("col", "c"), M.Expr("node", f"ec2.{n}", "cy")) for n in (1, 2)])
        s = L.load(tmpl(["ec2.1.cx+90", "row.az1"]))
        self.assertEqual([s.nodes[f"e2.{n}"].xy for n in (1, 2)],
                         [(M.Expr("node", "ec2.1", "cx", offset=90), M.Expr("row", r)) for r in ("az1", "az2")])
        s = L.load(tmpl(["sn.x1-40", "sn.y0+40"]))                      # a template group, per instance too
        self.assertEqual(s.nodes["e2.2"].xy, (M.Expr("group", "sn.2", "x1", offset=-40),
                                              M.Expr("group", "sn.2", "y0", offset=40)))
        with self.assertRaises(SpecError) as cm:
            L.load(tmpl(["col.c", "ec2.1.cy"]))
        self.assertEqual(cm.exception.problems, [
            "nodes[3] e2: xy[1]: ec2.1.cy is in instance 1 of the per template 'az', a row away from e2.2 "
            "(instance 2); write ec2.cy to follow each instance's own"])
        d = tmpl(["col.c", "ec2.cy"])
        d["nodes"][0]["only"] = [1]
        with self.assertRaises(SpecError) as cm:
            L.load(d)
        self.assertEqual(cm.exception.problems, [
            "nodes[3] e2: xy[1]: expression 'ec2.cy': ec2 has no instance 2 (left out by `only:`), so e2.2 has "
            "nothing to follow there"])
        # one y for every instance (a node or box outside the template, a row not in its
        # `per`, a number) puts them on one row: rejected unless one instance is drawn
        tail = (", so it puts all 2 instances of e2 on one y, a row away from every instance but one; follow "
                "each instance's own (another item of the template by its id, <item>.cy, or row.<az1|az2>), "
                "or keep e2 in one instance (only: [n])")
        for y, what in (("inet.cy", "inet.cy is outside the per template 'az'"),
                        ("vpc.y0+40", "vpc.y0 is outside the per template 'az'"),
                        ("row.main", "row.main is not a row of the per template 'az' (az1, az2)"),
                        (300, "300 is a fixed y")):
            with self.assertRaises(SpecError) as cm:
                L.load(tmpl(["col.c", y]))
            self.assertEqual(cm.exception.problems, [f"nodes[3] e2: xy[1]: {what}{tail}"], y)
        s = L.load(tmpl(["col.c", "inet.cy"], only=[2]))                # one instance: fine
        self.assertEqual(s.nodes["e2.2"].xy, (M.Expr("col", "c"), M.Expr("node", "inet", "cy")))
        s = L.load(tmpl(["inet.cx", "ec2.cy"]))                          # x outside the template: fine
        self.assertEqual(s.nodes["e2.1"].xy, (M.Expr("node", "inet", "cx"), M.Expr("node", "ec2.1", "cy")))
        # outside the template the base id still names nothing
        d = base()
        d["nodes"].append({"id": "q", "icon": "service/AWS-Lambda", "label": "Q", "in": "region",
                           "xy": ["col.c", "ec2.cy"]})
        with self.assertRaises(SpecError) as cm:
            L.load(d)
        self.assertEqual(cm.exception.problems, ["nodes[3] q: xy[1]: expression 'ec2.cy': no node or group 'ec2'"])


class ParseExpr(unittest.TestCase):
    def test_grammar(self):
        P = L.parse_expr
        self.assertEqual(P("12.5"), M.Expr("num", offset=12.5))
        self.assertEqual(P(-8), M.Expr("num", offset=-8))
        self.assertEqual(P("igw.cx-20"), M.Expr("node", "igw", "cx", offset=-20))
        self.assertEqual(P("sn.1.y0+52"), M.Expr("node", "sn.1", "y0", offset=52))
        self.assertEqual(P("my-node.x1"), M.Expr("node", "my-node", "x1"))
        self.assertEqual(P("br.label.y1 + 4"), M.Expr("label", "br", "y1", offset=4))
        self.assertEqual(P("col.tgw"), M.Expr("col", "tgw"))
        self.assertEqual(P("row.main-16"), M.Expr("row", "main", offset=-16))
        self.assertEqual(P("gap(vgw, res)+2"), M.Expr("gap", "vgw", ref2="res", offset=2))

    def test_bad(self):
        with self.assertRaises(SpecError) as cm:
            L.parse_expr("igw.middle")
        self.assertTrue(cm.exception.problems[0].startswith("expression 'igw.middle': expected <number>"))

    def test_with_spec(self):
        s = L.load(base())
        self.assertEqual(L.parse_expr("vpc.x0", s), M.Expr("group", "vpc", "x0"))
        self.assertEqual(L.parse_expr("ec2.2.cy", s), M.Expr("node", "ec2.2", "cy"))
        for text, msg in (("gap(a, main)", "expression 'gap(a, main)': gap() needs two tracks of one axis "
                                           "(a is a col, main a row)"),
                          ("row.b", "expression 'row.b': no row track 'b'"),
                          ("vpc.label.cx", "expression 'vpc.label.cx': .label needs a node id, 'vpc' is not one")):
            with self.assertRaises(SpecError) as cm:
                L.parse_expr(text, s)
            self.assertEqual(cm.exception.problems, [msg])


def mutate(f):
    d = base()
    f(d)
    return d


def three_azs(d):
    d["groups"] += [{"id": "az3", "type": "az", "in": "vpc", "per": ["az1", "main", "az2"]},
                    {"id": "sn3", "type": "private", "in": "az3"}]
    d["nodes"].append({"id": "x", "icon": "service/AWS-Lambda", "label": "Fn", "in": "sn3", "col": "c"})
    d["edges"].append({"e": "ec2.* -> x.*"})


def no_steps_field(d):
    del d["edges"][0]["step"]
    d["edges"][0]["steps"] = {"ec2.3": 1}


def node_in_cloud(d):
    d["nodes"][2]["in"] = "cloud"


def col_only(d):
    d["nodes"][2].pop("at")
    d["nodes"][2]["col"] = "c"


def flow_col(d, **kw):
    d["cols"] = ["a", "b", dict(id="c", flow=100, **kw)]


# (case, mutation, exact problems)
ERRORS = [
    ("unknown top-level key", lambda d: d.update(colz=1),
     ["spec: unknown key 'colz' (did you mean 'cols'?) (known: name, mode, title, S, font, cols, rows, groups, "
      "nodes, edges, note, raw)"]),
    ("unknown group key", lambda d: d["groups"][1].update(lable="x"),
     ["groups[1] region: unknown key 'lable' (did you mean 'label'?) (known: id, type, label, cidr, in, per, "
      "only, over, span, pad, pad_top, pad_left, pad_right, pad_bottom, min_w, min_h, dash, header)"]),
    ("type", lambda d: d.update(S="big"),
     ["spec: S: expected a positive number (icon size, default 48), got 'big'"]),
    ("id characters", lambda d: d["nodes"][0].update(id="nat.gw"),
     ["nodes[0]: id: expected an id of [A-Za-z0-9_-] (\".\" is for template instances), got 'nat.gw'",
      "edges[0] igw -> ec2.*: e: unknown id 'ec2' in 'ec2.*'"]),
    ("node id is a group id", lambda d: d["nodes"].append(
        {"id": "vpc", "icon": "service/AWS-Lambda", "label": "Fn", "at": ["c", "az1"]}),
     ["nodes[3] vpc: id 'vpc' is also a group (groups[2] vpc); node and group ids share one namespace"]),
    ("track names unique across cols and rows", lambda d: d.update(rows=["az1", "main", "az2", "a"]),
     ["rows[3] a: duplicate track 'a' (already a col track); track names are unique across cols and rows"]),
    ("unknown parent", lambda d: d["groups"][2].update({"in": "regoin"}),
     ["groups[2] vpc: in: unknown group 'regoin' (did you mean 'region'?)"]),
    ("containment cycle", lambda d: d["groups"][0].update({"in": "vpc"}),
     ["groups[0] cloud: in: containment cycle cloud → vpc → region → cloud"]),
    ("unknown track", lambda d: d["nodes"][2].update(at=["d", "main"]),
     ["nodes[2] inet: at[0]: unknown col track 'd'"]),
    ("row given inside a template", lambda d: (d["nodes"][0].pop("col"), d["nodes"][0].update(at=["b", "az1"])),
     ["nodes[0] ec2: at[1]: inside the per template 'az' give `col:` only (the row is the instance's)"]),
    ("on names a non-VPC", lambda d: d["nodes"][1].update(on="sn"),
     ["nodes[1] igw: on: 'sn' is a private group; `on` puts a gateway on a VPC border, so it must name a vpc group"]),
    ("on node inside the VPC columns", lambda d: d["nodes"][1].update(at=["b", "main"]),
     ["nodes[1] igw: on: column 'b' is inside 'vpc''s columns (b..b); put the node left or right of them "
      "(top/bottom borders are phase 2)"]),
    ("Internet inside the AWS Cloud", node_in_cloud,
     ["nodes[2] inet: resource/Internet is not in AWS; put it outside the AWS Cloud group ('cloud'), "
      "between on-premises and the Cloud"]),
    ("service name in a connector label", lambda d: d["edges"][1].update(label="TGW"),
     ["edges[1] inet -> igw: label 'TGW' names 'TGW', which has an official icon (service/AWS-Transit-Gateway); "
      "draw it as a node (SERVICE AS TEXT)"]),
    ("note row without an edge", lambda d: d["note"]["steps"].append(["x", "y"]),
     ["note.steps[1]: no edge has step 2 (each note.steps row needs one edge with that badge number)"]),
    ("step beyond the note", lambda d: d["edges"][1].update(step=2),
     ["edges[1]: step 2: note.steps has only 1 row"]),
    ("steps without a note", lambda d: d.pop("note"),
     ["note: steps: edges have step badges 1 but the note has no steps rows (one [hop, description] per number)"]),
    ("edge operator", lambda d: d["edges"][1].update(e="inet=>igw"),
     ["edges[1]: e: cannot parse 'inet=>igw'; write \"a OP b\" with spaces around OP (<..> <-> ..> -> -- ..), "
      "several targets as \"a -> b, c\""]),
    ("a.* -> b.* instance counts", three_azs,
     ["edges[2] ec2.* -> x.*: e: ec2.* has 2 instances and x.* has 3; a.* OP b.* pairs instances with the "
      "same number"]),
    ("template base id without .*", lambda d: d["edges"][1].update(e="inet -> ec2"),
     ["edges[1] inet -> ec2: e: 'ec2' is a per template (ec2.1, ec2.2); write ec2.* or one instance such as ec2.1"]),
    (".* on a plain node", lambda d: d["edges"][1].update(e="inet.* -> igw"),
     ["edges[1] inet.* -> igw: e: 'inet.*': 'inet' is not inside a per template, so it has no instances; "
      "write 'inet'"]),
    ("steps key not an endpoint", no_steps_field,
     ["edges[0] igw -> ec2.*: steps: 'ec2.3' is not an endpoint of this edge's instances (ec2.1, ec2.2, igw)"]),
    ("icon ref not in the bundle", lambda d: d["nodes"][0].update(icon="service/Amazon-EC3"),
     ["nodes[0] ec2: icon: 'service/Amazon-EC3' is not in the icon bundle (assets/icons.json)"]),
    ("ambiguous icon alias", lambda d: d["nodes"][0].update(icon="management console"),
     ["nodes[0] ec2: icon: alias 'management console' is ambiguous; write the full ref — candidates: "
      "service/AWS-Management-Console (95), resource/AWS-Management-Console (95), "
      "resource/AWS-Management-Console_Dark (95)"]),
    ("weak icon alias", lambda d: d["nodes"][0].update(icon="alb"),
     ["nodes[0] ec2: icon: alias 'alb' has no match scoring ≥ 95; write the full ref — candidates: "
      "resource/Elastic-Load-Balancing_Application-Load-Balancer (85)"]),
    ("per-instance value missing an instance", lambda d: d["nodes"][0].update(label={1: "A"}),
     ["nodes[0] ec2: label: no value for instance 2 (give 1..2)"]),
    ("per-instance value outside a template", lambda d: d["nodes"][2].update(label={1: "A", 2: "B"}),
     ["nodes[2] inet: label: per-instance values ({1: …, 2: …}) are only for items inside a per template"]),
    ("only outside a template", lambda d: d["nodes"][2].update(only=[1]),
     ["nodes[2] inet: only: is for items inside a per template (it picks the instances to draw)"]),
    ("only on the template group", lambda d: d["groups"][3].update(only=[1]),
     ["groups[3] az: only: the template group itself is drawn once per `per` row; shorten `per` instead"]),
    ("only names a missing instance", lambda d: d["nodes"][0].update(only=[3]),
     ["nodes[0] ec2: only: instance 3 does not exist (the template has 2 instances)"]),
    ("only not numbers", lambda d: d["nodes"][0].update(only="az1"),
     ["nodes[0] ec2: only: expected instance numbers 1..2 (e.g. only: [1]), got 'az1'"]),
    ("edge to an instance left out", lambda d: (d["nodes"][0].update(only=[1]),
                                                d["edges"].append({"e": "inet -> ec2.2"})),
     ["edges[2] inet -> ec2.2: e: 'ec2.2' is left out by `only:` (nodes[0] ec2); drawn instances: ec2.1"]),
    ("expression reference", lambda d: d["edges"][1].update(bend_x="igx.cx+8"),
     ["edges[1] inet -> igw: bend_x: expression 'igx.cx+8': no node or group 'igx'"]),
    ("col only on a grid column", col_only,
     ["nodes[2] inet: row: required (only nodes in a per template or on a flow column take no row; 'c' is a "
      "grid column: give it `flow: <pitch>` to stack its nodes)"]),
    ("align on a row", lambda d: d.update(rows=[{"id": "az1", "align": "top"}, "main", "az2"]),
     ["rows[0] az1: align: only a flow column takes align (top | center | bottom); a flow row is centered in "
      "its parent"]),
    ("align without flow", lambda d: d.update(cols=[{"id": "a", "align": "top"}, "b", "c"]),
     ["cols[0] a: align: 'a' is not a flow column; give `flow: <pitch>` too"]),
    ("align value", lambda d: flow_col(d, align="middle"),
     ["cols[2] c: align: expected one of top | center | bottom, got 'middle'"]),
    ("dy on a flow-column node", lambda d: (flow_col(d), col_only(d), d["nodes"][2].update(dy=10)),
     ["nodes[2] inet: dy: a node on the flow column 'c' takes its y from the stack; drop dy (the column's "
      "`flow:` pitch spaces the nodes)"]),
    ("border node on a flow column", lambda d: (d.update(cols=[{"id": "a", "flow": 100}, "b", "c"]),
                                                d["nodes"][1].pop("at"), d["nodes"][1].update(col="a")),
     ["nodes[1] igw: on: a border node needs a grid row; 'a' is a flow column (give `at: [col, row]`)"]),
    ("span without a row", lambda d: (flow_col(d), d["nodes"][2].pop("at"), d["nodes"][2].update(col="b..c")),
     ["nodes[2] inet: row: required (a span 'b..c' needs a row: `at: [b..c, <row>]`)"]),
    ("xy expression on the other axis", lambda d: (d["nodes"][2].pop("at"), d["nodes"][2].update(xy=["row.main", "row.main"])),
     ["nodes[2] inet: xy[0]: row.main is on the other axis; xy[0] takes a number, col.<track>, "
      "<node>.(x0|cx|x1) or <group>.(x0|x1), each with an optional ±n"]),
    ("xy expression on a group center", lambda d: (d["nodes"][2].pop("at"), d["nodes"][2].update(xy=["vpc.cx", "row.main"])),
     ["nodes[2] inet: xy[0]: vpc.cx: a group's center is no single variable; xy[0] takes a number, "
      "col.<track>, <node>.(x0|cx|x1) or <group>.(x0|x1), each with an optional ±n"]),
    ("xy expression on a gap", lambda d: (d["nodes"][2].pop("at"), d["nodes"][2].update(xy=["col.c", "gap(az1, az2)"])),
     ["nodes[2] inet: xy[1]: gap expressions depend on the drawn result; xy[1] takes a number, row.<track>, "
      "<node>.(y0|cy|y1) or <group>.(y0|y1), each with an optional ±n"]),
    ("dash on a fixed-style group", lambda d: d["groups"][2].update(dash="6,4"),
     ["groups[2] vpc: dash: only generic (and cloudwan) groups take a dash; vpc is always solid"]),
    ("{n} outside a template", lambda d: d["nodes"][2].update(label="Internet {n}"),
     ["nodes[2] inet: label: {n} is the instance number; only items inside a per template have one"]),
]


class FlowColumns(unittest.TestCase):
    def test_col_only_nodes_stack_in_spec_order(self):
        def f(d):
            flow_col(d, align="bottom")
            d["nodes"] += [{"id": "s3", "icon": "service/Amazon-Simple-Storage-Service", "label": "S3",
                            "in": "region", "col": "c"},
                           {"id": "cw", "icon": "service/Amazon-CloudWatch", "label": "CloudWatch",
                            "in": "region", "col": "c"},
                           {"id": "kms", "icon": "service/AWS-Key-Management-Service", "label": "KMS",
                            "in": "region", "at": ["c", "az1"]}]          # pinned to a grid row
        s = L.load(mutate(f))
        c = s.cols[2]
        self.assertEqual((c.id, c.flow, c.align), ("c", 100.0, "bottom"))
        self.assertEqual([(n.id, n.col, n.row, n.flow_index) for n in s.nodes.values() if n.parent == "region"],
                         [("igw", "a", "main", None), ("s3", "c", None, 0), ("cw", "c", None, 1),
                          ("kms", "c", "az1", None)])
        self.assertEqual(s.flow_stacks(), {("region", "c"): ["s3", "cw"]})
        self.assertEqual(s.groups["region"].rows, ("az1", "az2"))     # the stack adds no rows
        self.assertEqual(s.warnings, [])
        # solved: KMS, pinned on the column, keeps off the bottom stack (above it)
        g = layout_solve.solve(s, [])
        kms = g.nodes["kms"].footprint()
        for i in ("s3", "cw"):
            self.assertFalse(kms.overlaps(g.nodes[i].footprint()), i)
        self.assertLess(kms.y1, g.nodes["s3"].icon.y0)

    def test_flow_true_takes_the_mode_pitch(self):
        s = L.load(mutate(lambda d: d.update(cols=["a", "b", {"id": "c", "flow": True}])))
        self.assertEqual((s.cols[2].flow, s.cols[2].align), (float(s.const.flow_pitch), "center"))


class Errors(unittest.TestCase):
    def test_each_kind(self):
        for case, f, want in ERRORS:
            with self.subTest(case):
                with self.assertRaises(SpecError) as cm:
                    L.load(mutate(f))
                self.assertEqual(cm.exception.problems, want)

    def test_every_problem_collected(self):
        def many(d):
            d.update(S=-1)
            d["groups"][1]["type"] = "regoin"
            d["edges"].append({"e": "inet -> nowhere"})
        with self.assertRaises(SpecError) as cm:
            L.load(mutate(many))
        p = cm.exception.problems
        self.assertEqual(len(p), 3)
        self.assertEqual(p[0], "spec: S: expected a positive number (icon size, default 48), got -1")
        self.assertTrue(p[1].startswith("groups[1] region: type: expected one of cloud, account, region,"))
        self.assertTrue(p[1].endswith("got 'regoin' (did you mean 'region'?)"))
        self.assertEqual(p[2], "edges[2] inet -> nowhere: e: unknown id 'nowhere'")
        self.assertEqual(str(cm.exception), "\n".join(p))

    def test_load_balancer_in_az_template_warns(self):
        s = L.load(mutate(lambda d: d["nodes"].append(
            {"id": "alb", "icon": "resource/Elastic-Load-Balancing_Application-Load-Balancer", "label": "ALB",
             "in": "sn", "col": "c"})))
        self.assertEqual(s.warnings, [
            "nodes[3] alb: alb (resource/Elastic-Load-Balancing_Application-Load-Balancer) is inside the AZ template "
            "'az', so it is drawn once per AZ; a load balancer or firewall spans the AZs — put it in the VPC on the "
            "row between them (in: <vpc>, at: [<col>, <row>])"])

    def test_yaml_errors(self):
        with self.assertRaises(SpecError) as cm:
            load_text("name: t\ncols: [a\n")
        self.assertRegex(cm.exception.problems[0], r"t\.layout\.yaml: line \d+: invalid YAML")
        with self.assertRaises(SpecError) as cm:
            load_text("{", suffix=".json")
        self.assertRegex(cm.exception.problems[0], r"t\.json: line 1: invalid JSON")

    def test_no_pyyaml(self):
        orig = L._yaml_loader
        L._yaml_loader = lambda: None
        try:
            with self.assertRaises(SpecError) as cm:
                load_text("name: t\n")
        finally:
            L._yaml_loader = orig
        self.assertIn("PyYAML is not installed; run with `uv run --with pyyaml python3 scripts/layout.py",
                      cm.exception.problems[0])


if __name__ == "__main__":
    unittest.main(verbosity=1)
