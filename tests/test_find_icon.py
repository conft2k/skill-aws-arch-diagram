#!/usr/bin/env python3
"""find_icon.py: the names and abbreviations a first-time author types find the official
icon as the top hit, and a search that finds nothing names the closest icons.

    python3 tests/test_find_icon.py

Needs the icon bundle, like every script of the skill (PyYAML for the layout_spec case).
"""
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import layout_spec as L  # noqa: E402
from layout_model import SpecError  # noqa: E402


def cli(*queries):
    """{query: [printed lines]} from one run of find_icon.py."""
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "find_icon.py"), *queries],
                         capture_output=True, text=True, check=True).stdout
    blocks, cur = {}, None
    for line in out.splitlines():
        if line.startswith("# "):
            cur = blocks.setdefault(line[2:], [])
        elif line.strip() and cur is not None:
            cur.append(line.strip())
    return blocks


def top(lines):
    """The ref of the first ranked hit, or None."""
    for line in lines:
        if line.startswith("["):
            return line.split("] ", 1)[1]
    return None


# query → the official icon it must print first
FIRST = {
    "TGW": "service/AWS-Transit-Gateway",
    "transit gateway attachment": "resource/AWS-Transit-Gateway_Attachment",
    "TGW attachment": "resource/AWS-Transit-Gateway_Attachment",
    "tgw-attachment": "resource/AWS-Transit-Gateway_Attachment",
    "VPC attachment": "resource/AWS-Transit-Gateway_Attachment",
    "DX": "service/AWS-Direct-Connect",
    "direct connect gateway": "resource/AWS-Direct-Connect_Gateway",
    "DX gateway": "resource/AWS-Direct-Connect_Gateway",
    "DXGW": "resource/AWS-Direct-Connect_Gateway",
    "VPN": "service/AWS-Site-to-Site-VPN",
    "S2S": "service/AWS-Site-to-Site-VPN",
    "S2S VPN": "service/AWS-Site-to-Site-VPN",
    "site-to-site vpn": "service/AWS-Site-to-Site-VPN",
    "client vpn": "service/AWS-Client-VPN",
    "customer gateway": "resource/Amazon-VPC_Customer-Gateway",
    "virtual private gateway": "resource/Amazon-VPC_VPN-Gateway",
    "NAT": "resource/Amazon-VPC_NAT-Gateway",
    "NAT GW": "resource/Amazon-VPC_NAT-Gateway",
    "IGW": "resource/Amazon-VPC_Internet-Gateway",
    "VPCE": "resource/Amazon-VPC_Endpoints",
    "VPC endpoint": "resource/Amazon-VPC_Endpoints",
    "PrivateLink": "service/AWS-PrivateLink",
    "endpoint service": "service/AWS-PrivateLink",
    "ALB": "resource/Elastic-Load-Balancing_Application-Load-Balancer",
    "internal ALB": "resource/Elastic-Load-Balancing_Application-Load-Balancer",
    "NLB": "resource/Elastic-Load-Balancing_Network-Load-Balancer",
    "GWLB": "resource/Elastic-Load-Balancing_Gateway-Load-Balancer",
    "Fargate": "service/AWS-Fargate",
    "ECS task": "resource/Amazon-Elastic-Container-Service_Task",
    "ECS service": "resource/Amazon-Elastic-Container-Service_Service",
    "Aurora writer": "resource/Amazon-Aurora-Instance",
    "Aurora reader": "resource/Amazon-Aurora-Instance",
    "WAF": "service/AWS-WAF",
    "web ACL": "service/AWS-WAF",
    "CloudFront distribution": "service/Amazon-CloudFront",
    "RAM": "service/AWS-Resource-Access-Manager",
    "Organizations": "service/AWS-Organizations",
    "Organizations account": "resource/AWS-Organizations_Account",
    "member account": "resource/AWS-Organizations_Account",
    "management account": "resource/AWS-Organizations_Management-Account",
    "OU": "resource/AWS-Organizations_Organizational-Unit",
    "SSO": "service/AWS-IAM-Identity-Center",
    "identity center": "service/AWS-IAM-Identity-Center",
    "KMS": "service/AWS-Key-Management-Service",
    "SSM": "service/AWS-Systems-Manager",
    "CFN": "service/AWS-CloudFormation",
    "R53": "service/Amazon-Route-53",
    "NFW": "service/AWS-Network-Firewall",
    "on-prem": "group/Corporate-data-center_32",
    "on prem": "group/Corporate-data-center_32",
    "data center": "group/Corporate-data-center_32",
    "corporate": "group/Corporate-data-center_32",
    "IDC": "group/Corporate-data-center_32",
    "users": "resource/Users",
    "end users": "resource/Users",
    "사용자": "resource/Users",
    "온프레미스": "group/Corporate-data-center_32",
    "데이터센터": "group/Corporate-data-center_32",
    "인터넷": "resource/Internet",
    "전용선": "service/AWS-Direct-Connect",
    "전송 게이트웨이": "service/AWS-Transit-Gateway",
    "라우팅 테이블": "resource/Amazon-Route-53_Route-Table",
}


class FirstTry(unittest.TestCase):
    def test_common_names_print_the_official_icon_first(self):
        got = cli(*FIRST)
        for q, ref in FIRST.items():
            with self.subTest(q=q):
                self.assertEqual(top(got[q]), ref)

    def test_every_alias_targets_an_icon(self):
        import find_icon
        empty = [k for k in {**find_icon.ALIASES, **find_icon.LOOKUP_ALIASES}
                 if not find_icon.search(k, k=1)]
        self.assertEqual(empty, [])

    def test_security_group_says_it_has_no_icon(self):
        self.assertEqual(cli("sg")["sg"],
                         ["(no icon: Security group is a label-only group — draw a rect in the color from "
                          "diagram_guide.md's group table, no corner badge)"])

    def test_vpc_origin_says_what_to_draw(self):
        for q in ("vpc origin", "CloudFront VPC origin"):
            lines = cli(q)[q]
            self.assertEqual(lines[0], "(no icon: there is no separate VPC origin icon: a CloudFront VPC origin "
                                       "is a CloudFront setting, so draw service/Amazon-CloudFront and the "
                                       "internal ALB/NLB/EC2 it reaches, and write 'VPC origin' as that node's "
                                       "sub or the line's label)")
            self.assertEqual(top(lines), "service/Amazon-CloudFront")

    def test_every_word_of_a_query_is_spelled_out(self):
        got = cli("S3 bucket", "ecs-task", "DDB table")
        self.assertEqual(top(got["S3 bucket"]), "resource/Amazon-Simple-Storage-Service_Bucket")
        self.assertEqual(top(got["ecs-task"]), "resource/Amazon-Elastic-Container-Service_Task")
        self.assertEqual(top(got["DDB table"]), "resource/Amazon-DynamoDB_Table")


class LabelsStayLabels(unittest.TestCase):
    """Lookup aliases are for finding icons; a connector label with these words is not a service."""

    def test_spec_verb_vpc_attachment_is_accepted(self):
        spec = {"name": "t", "mode": "document", "cols": ["a", "b"], "rows": ["r"],
                "nodes": [{"id": "tgw", "icon": "service/AWS-Transit-Gateway", "label": "TGW", "at": ["a", "r"]},
                          {"id": "x", "icon": "service/Amazon-EC2", "label": "EC2", "at": ["b", "r"]}],
                "edges": [{"e": "tgw -- x", "verb": "VPC attachment"}]}
        L.load(spec)

    def test_spec_verb_naming_a_service_is_still_service_as_text(self):
        spec = {"name": "t", "mode": "document", "cols": ["a", "b"], "rows": ["r"],
                "nodes": [{"id": "a", "icon": "service/AWS-Lambda", "label": "Fn", "at": ["a", "r"]},
                          {"id": "x", "icon": "service/Amazon-EC2", "label": "EC2", "at": ["b", "r"]}],
                "edges": [{"e": "a -> x", "label": "TGW"}]}
        with self.assertRaises(SpecError) as cm:
            L.load(spec)
        self.assertIn("names 'TGW', which has an official icon (service/AWS-Transit-Gateway)", str(cm.exception))


class NoMatch(unittest.TestCase):
    def test_typo_names_the_closest_icons(self):
        self.assertEqual(cli("lamda")["lamda"],
                         ["(no match — closest: service/AWS-Lambda ('lambda'))"])
        self.assertEqual(cli("transit gatway")["transit gatway"][0].split(", ")[0],
                         "(no match — closest: service/AWS-Transit-Gateway ('transit gateway')")

    def test_nothing_close_falls_back_to_the_lists(self):
        self.assertEqual(cli("xyzzyq")["xyzzyq"],
                         ["(no match — try: find_icon.py --list service, then --list resource)"])

    def test_spec_icon_with_no_match_names_the_closest_icons(self):
        spec = {"name": "t", "mode": "document", "cols": ["a"], "rows": ["r"],
                "nodes": [{"id": "f", "icon": "lamda", "label": "Fn", "at": ["a", "r"]}]}
        with self.assertRaises(SpecError) as cm:
            L.load(spec)
        self.assertIn("nodes[0] f: icon: alias 'lamda' has no match scoring ≥ 95; write the full ref — "
                      "closest: service/AWS-Lambda ('lambda')", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
