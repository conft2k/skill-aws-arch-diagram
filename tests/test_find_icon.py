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


# every alias → the official icon it must rank first (checked by hand against the package)
ALIAS_REF = {
    'alb': 'resource/Elastic-Load-Balancing_Application-Load-Balancer',
    'nlb': 'resource/Elastic-Load-Balancing_Network-Load-Balancer',
    'gwlb': 'resource/Elastic-Load-Balancing_Gateway-Load-Balancer',
    'elb': 'service/Elastic-Load-Balancing',
    'load balancer': 'service/Elastic-Load-Balancing',
    'ecs': 'service/Amazon-Elastic-Container-Service',
    'ecr': 'service/Amazon-Elastic-Container-Registry',
    'eks': 'service/Amazon-Elastic-Kubernetes-Service',
    's3': 'service/Amazon-Simple-Storage-Service',
    'sqs': 'service/Amazon-Simple-Queue-Service',
    'sns': 'service/Amazon-Simple-Notification-Service',
    'ses': 'service/Amazon-Simple-Email-Service',
    'rds': 'service/Amazon-RDS',
    'vpc': 'service/Amazon-Virtual-Private-Cloud',
    'ddb': 'service/Amazon-DynamoDB',
    'apigw': 'service/Amazon-API-Gateway',
    'asg': 'service/Amazon-EC2-Auto-Scaling',
    'iam': 'service/AWS-Identity-and-Access-Management',
    'kms': 'service/AWS-Key-Management-Service',
    'acm': 'service/AWS-Certificate-Manager',
    'efs': 'service/Amazon-EFS',
    'ebs': 'service/Amazon-Elastic-Block-Store',
    'msk': 'service/Amazon-Managed-Streaming-for-Apache-Kafka',
    'sfn': 'service/AWS-Step-Functions',
    'step functions': 'service/AWS-Step-Functions',
    'igw': 'resource/Amazon-VPC_Internet-Gateway',
    'nat': 'resource/Amazon-VPC_NAT-Gateway',
    'natgw': 'resource/Amazon-VPC_NAT-Gateway',
    'vgw': 'resource/Amazon-VPC_VPN-Gateway',
    'cgw': 'resource/Amazon-VPC_Customer-Gateway',
    'eni': 'resource/Amazon-VPC_Elastic-Network-Interface',
    'nacl': 'resource/Amazon-VPC_Network-Access-Control-List',
    'pcx': 'resource/Amazon-VPC_Peering-Connection',
    'vpc peering': 'resource/Amazon-VPC_Peering-Connection',
    'tgw peering': 'resource/Amazon-VPC_Peering-Connection',
    'transit gateway peering': 'resource/Amazon-VPC_Peering-Connection',
    'peering attachment': 'resource/Amazon-VPC_Peering-Connection',
    'tgw peering attachment': 'resource/Amazon-VPC_Peering-Connection',
    'vpce': 'resource/Amazon-VPC_Endpoints',
    'endpoint': 'resource/Amazon-VPC_Endpoints',
    'gateway endpoint': 'resource/Amazon-VPC_Endpoints',
    'interface endpoint': 'resource/Amazon-VPC_Endpoints',
    's3 gateway endpoint': 'resource/Amazon-VPC_Endpoints',
    'dynamodb gateway endpoint': 'resource/Amazon-VPC_Endpoints',
    's3 endpoint': 'resource/Amazon-VPC_Endpoints',
    'dynamodb endpoint': 'resource/Amazon-VPC_Endpoints',
    'eice': 'resource/Amazon-VPC_Endpoints',
    'instance connect endpoint': 'resource/Amazon-VPC_Endpoints',
    'route table': 'resource/Amazon-Route-53_Route-Table',
    'routing table': 'resource/Amazon-Route-53_Route-Table',
    'rtb': 'resource/Amazon-Route-53_Route-Table',
    'vpc route table': 'resource/Amazon-Route-53_Route-Table',
    'tgw route table': 'resource/Amazon-Route-53_Route-Table',
    'ec2 instance connect endpoint': 'resource/Amazon-VPC_Endpoints',
    'tgw': 'service/AWS-Transit-Gateway',
    'gwlbe': 'resource/Amazon-VPC_Endpoints',
    'gwlb endpoint': 'resource/Amazon-VPC_Endpoints',
    'gateway load balancer endpoint': 'resource/Amazon-VPC_Endpoints',
    'aws cloud': 'group/AWS-Cloud-logo_32',
    'cloud': 'group/AWS-Cloud-logo_32',
    'on-prem': 'group/Corporate-data-center_32',
    'on-premises': 'group/Corporate-data-center_32',
    'onprem': 'group/Corporate-data-center_32',
    'data center': 'group/Corporate-data-center_32',
    'datacenter': 'group/Corporate-data-center_32',
    'agentcore': 'service/Amazon-Bedrock-AgentCore',
    'tgw attachment': 'resource/AWS-Transit-Gateway_Attachment',
    'tgw attach': 'resource/AWS-Transit-Gateway_Attachment',
    'tgw vpc attachment': 'resource/AWS-Transit-Gateway_Attachment',
    'vpc attachment': 'resource/AWS-Transit-Gateway_Attachment',
    'tgw vpn attachment': 'resource/AWS-Transit-Gateway_Attachment',
    'tgw dx attachment': 'resource/AWS-Transit-Gateway_Attachment',
    'transitgateway attachment': 'resource/AWS-Transit-Gateway_Attachment',
    'dx': 'service/AWS-Direct-Connect',
    'aws dx': 'service/AWS-Direct-Connect',
    'dx connection': 'service/AWS-Direct-Connect',
    'direct connect connection': 'service/AWS-Direct-Connect',
    'dx link': 'service/AWS-Direct-Connect',
    'dxgw': 'resource/AWS-Direct-Connect_Gateway',
    'dx gateway': 'resource/AWS-Direct-Connect_Gateway',
    'dx gw': 'resource/AWS-Direct-Connect_Gateway',
    'dcgw': 'resource/AWS-Direct-Connect_Gateway',
    'vpn': 'service/AWS-Site-to-Site-VPN',
    's2s': 'service/AWS-Site-to-Site-VPN',
    's2s vpn': 'service/AWS-Site-to-Site-VPN',
    'aws vpn': 'service/AWS-Site-to-Site-VPN',
    'virtual private gateway': 'resource/Amazon-VPC_VPN-Gateway',
    'vpg': 'resource/Amazon-VPC_VPN-Gateway',
    'customer gateway device': 'resource/Amazon-VPC_Customer-Gateway',
    'nat gw': 'resource/Amazon-VPC_NAT-Gateway',
    'ngw': 'resource/Amazon-VPC_NAT-Gateway',
    'internet gw': 'resource/Amazon-VPC_Internet-Gateway',
    'vpc endpoint': 'resource/Amazon-VPC_Endpoints',
    'vpc interface endpoint': 'resource/Amazon-VPC_Endpoints',
    'vpc gateway endpoint': 'resource/Amazon-VPC_Endpoints',
    'privatelink endpoint': 'resource/Amazon-VPC_Endpoints',
    'endpoint service': 'service/AWS-PrivateLink',
    'vpc endpoint service': 'service/AWS-PrivateLink',
    'aws privatelink': 'service/AWS-PrivateLink',
    'internal alb': 'resource/Elastic-Load-Balancing_Application-Load-Balancer',
    'internal nlb': 'resource/Elastic-Load-Balancing_Network-Load-Balancer',
    'loadbalancer': 'service/Elastic-Load-Balancing',
    'lb': 'service/Elastic-Load-Balancing',
    'ecs task': 'resource/Amazon-Elastic-Container-Service_Task',
    'fargate task': 'resource/Amazon-Elastic-Container-Service_Task',
    'ecs service': 'resource/Amazon-Elastic-Container-Service_Service',
    'fargate service': 'resource/Amazon-Elastic-Container-Service_Service',
    'aurora writer': 'resource/Amazon-Aurora-Instance',
    'aurora reader': 'resource/Amazon-Aurora-Instance',
    'aurora primary': 'resource/Amazon-Aurora-Instance',
    'aurora replica': 'resource/Amazon-Aurora-Instance',
    'aurora read replica': 'resource/Amazon-Aurora-Instance',
    'aurora cluster': 'service/Amazon-Aurora',
    'rds primary': 'resource/Amazon-Aurora_Amazon-RDS-Instance',
    'rds standby': 'resource/Amazon-Aurora_Amazon-RDS-Instance',
    'rds replica': 'resource/Amazon-Aurora_Amazon-RDS-Instance',
    'web acl': 'service/AWS-WAF',
    'waf web acl': 'service/AWS-WAF',
    'webacl': 'service/AWS-WAF',
    'aws waf': 'service/AWS-WAF',
    'cloudfront distribution': 'service/Amazon-CloudFront',
    'cf': 'service/Amazon-CloudFront',
    'ram': 'service/AWS-Resource-Access-Manager',
    'aws ram': 'service/AWS-Resource-Access-Manager',
    'org': 'service/AWS-Organizations',
    'aws organizations': 'service/AWS-Organizations',
    'member account': 'resource/AWS-Organizations_Account',
    'org account': 'resource/AWS-Organizations_Account',
    'workload account': 'resource/AWS-Organizations_Account',
    'management account': 'resource/AWS-Organizations_Management-Account',
    'payer account': 'resource/AWS-Organizations_Management-Account',
    'ou': 'resource/AWS-Organizations_Organizational-Unit',
    'organizational unit': 'resource/AWS-Organizations_Organizational-Unit',
    'on prem': 'group/Corporate-data-center_32',
    'on premise': 'group/Corporate-data-center_32',
    'corporate': 'group/Corporate-data-center_32',
    'corporate network': 'group/Corporate-data-center_32',
    'corp': 'group/Corporate-data-center_32',
    'idc': 'group/Corporate-data-center_32',
    'dc': 'group/Corporate-data-center_32',
    'office': 'resource/Office-building',
    'branch office': 'resource/Office-building',
    'end user': 'resource/Users',
    'end users': 'resource/Users',
    'customers': 'resource/Users',
    'mobile': 'resource/Mobile-client',
    'mobile app': 'resource/Mobile-client',
    'r53': 'service/Amazon-Route-53',
    'route53': 'service/Amazon-Route-53',
    'nfw': 'service/AWS-Network-Firewall',
    'anfw': 'service/AWS-Network-Firewall',
    'ga': 'service/AWS-Global-Accelerator',
    'aga': 'service/AWS-Global-Accelerator',
    'cw': 'service/Amazon-CloudWatch',
    'kds': 'service/Amazon-Kinesis-Data-Streams',
    'api gw': 'service/Amazon-API-Gateway',
    'sso': 'service/AWS-IAM-Identity-Center',
    'aws sso': 'service/AWS-IAM-Identity-Center',
    'identity center': 'service/AWS-IAM-Identity-Center',
    'ssm': 'service/AWS-Systems-Manager',
    'cfn': 'service/AWS-CloudFormation',
    'firehose': 'service/Amazon-Data-Firehose',
    'kinesis firehose': 'service/Amazon-Data-Firehose',
    'kdf': 'service/Amazon-Data-Firehose',
    'cwl': 'resource/Amazon-CloudWatch_Logs',
    'lambda function': 'resource/AWS-Lambda_Lambda-Function',
    'opensearch': 'service/Amazon-OpenSearch-Service',
    '사용자': 'resource/Users',
    '사용자들': 'resource/Users',
    '고객': 'resource/Users',
    '최종 사용자': 'resource/Users',
    '온프레미스': 'group/Corporate-data-center_32',
    '온프렘': 'group/Corporate-data-center_32',
    '데이터센터': 'group/Corporate-data-center_32',
    '데이터 센터': 'group/Corporate-data-center_32',
    '전산센터': 'group/Corporate-data-center_32',
    '사무실': 'resource/Office-building',
    '지점': 'resource/Office-building',
    '인터넷': 'resource/Internet',
    '서버': 'resource/Server',
    '모바일': 'resource/Mobile-client',
    '전용선': 'service/AWS-Direct-Connect',
    '다이렉트 커넥트': 'service/AWS-Direct-Connect',
    '전송 게이트웨이': 'service/AWS-Transit-Gateway',
    '트랜짓 게이트웨이': 'service/AWS-Transit-Gateway',
    '인터넷 게이트웨이': 'resource/Amazon-VPC_Internet-Gateway',
    'nat 게이트웨이': 'resource/Amazon-VPC_NAT-Gateway',
    '고객 게이트웨이': 'resource/Amazon-VPC_Customer-Gateway',
    '가상 프라이빗 게이트웨이': 'resource/Amazon-VPC_VPN-Gateway',
    '로드밸런서': 'service/Elastic-Load-Balancing',
    '로드 밸런서': 'service/Elastic-Load-Balancing',
    '라우팅 테이블': 'resource/Amazon-Route-53_Route-Table',
    '라우트 테이블': 'resource/Amazon-Route-53_Route-Table',
    '엔드포인트': 'resource/Amazon-VPC_Endpoints',
    '계정': 'group/AWS-Account_32',
}


class FirstTry(unittest.TestCase):
    def test_common_names_print_the_official_icon_first(self):
        got = cli(*FIRST)
        for q, ref in FIRST.items():
            with self.subTest(q=q):
                self.assertEqual(top(got[q]), ref)

    def test_every_alias_prints_its_official_icon_first(self):
        import find_icon
        keys = list(find_icon.ALIASES) + list(find_icon.LOOKUP_ALIASES)
        self.assertEqual(sorted(keys), sorted(ALIAS_REF))     # a new alias needs its row here
        got = cli(*keys)
        for k in keys:
            with self.subTest(alias=k):
                self.assertEqual(top(got[k]), ALIAS_REF[k])

    def test_a_phrase_with_a_korean_word_ranks_the_whole_phrase_first(self):
        got = cli("인터넷 게이트웨이", "고객 게이트웨이", "Internet-Gateway", "customer  gateway")
        self.assertEqual(top(got["인터넷 게이트웨이"]), "resource/Amazon-VPC_Internet-Gateway")
        self.assertEqual(top(got["고객 게이트웨이"]), "resource/Amazon-VPC_Customer-Gateway")
        self.assertEqual(top(got["Internet-Gateway"]), "resource/Amazon-VPC_Internet-Gateway")
        self.assertEqual(top(got["customer  gateway"]), "resource/Amazon-VPC_Customer-Gateway")

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


class SpecIcon(unittest.TestCase):
    """A bare `icon:` in a spec gets the same help as find_icon.py."""

    @staticmethod
    def error(icon):
        spec = {"name": "t", "mode": "document", "cols": ["a"], "rows": ["r"],
                "nodes": [{"id": "f", "icon": icon, "label": "X", "at": ["a", "r"]}]}
        try:
            L.load(spec)
        except SpecError as e:
            return str(e)
        raise AssertionError(f"icon {icon!r} loaded")

    def test_vpc_origin_says_there_is_no_icon_and_what_to_draw(self):
        self.assertIn("nodes[0] f: icon: 'vpc origin' has no icon of its own — there is no separate VPC "
                      "origin icon: a CloudFront VPC origin is a CloudFront setting, so draw "
                      "service/Amazon-CloudFront and the internal ALB/NLB/EC2 it reaches, and write "
                      "'VPC origin' as that node's sub or the line's label", self.error("vpc origin"))

    def test_security_group_says_to_make_it_a_group(self):
        self.assertIn("nodes[0] f: icon: 'sg' has no icon of its own — Security group is a label-only group "
                      "with no icon: make it a group (`groups:` entry with `type: sg`), not a node",
                      self.error("sg"))

    def test_korean_gateway_candidates_start_with_the_gateway(self):
        self.assertIn("nodes[0] f: icon: alias '고객 게이트웨이' has no match scoring ≥ 95; write the full ref — "
                      "candidates: resource/Amazon-VPC_Customer-Gateway (85)", self.error("고객 게이트웨이"))

    def test_lookup_aliases_resolve(self):
        spec = {"name": "t", "mode": "document", "cols": ["a", "b", "c"], "rows": ["r"],
                "nodes": [{"id": "d", "icon": "DX", "label": "DX", "at": ["a", "r"]},
                          {"id": "m", "icon": "RAM", "label": "RAM", "at": ["b", "r"]},
                          {"id": "t", "icon": "ecs task", "label": "Task", "at": ["c", "r"]}]}
        s = L.load(spec)
        self.assertEqual([s.nodes[i].icon for i in "dmt"],
                         ["service/AWS-Direct-Connect", "service/AWS-Resource-Access-Manager",
                          "resource/Amazon-Elastic-Container-Service_Task"])


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
