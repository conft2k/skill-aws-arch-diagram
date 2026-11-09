#!/usr/bin/env python3
"""Find icons in assets/icons.json (the official AWS icons, downloaded on first use).

Usage:
  python scripts/find_icon.py ec2
  python scripts/find_icon.py "api gateway" lambda s3   # multiple at once
  python scripts/find_icon.py --list service            # list a whole set

Prints ranked matches as `set/name`. Icons live inside assets/icons.json
(one file, not hundreds), so reference them by `set/name` and let embed.py
inline the actual SVG/PNG when you build a diagram. Matches whole words,
case/hyphen-insensitive, with common AWS abbreviation aliases (also the names and
Korean words a first-time author types, word by word in a longer query). A query that
matches nothing prints the closest names.
"""
import difflib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_icons import load_sets  # noqa: E402

SETS = load_sets()  # downloads the official AWS icons on first use

ALIASES = {
    # alb/nlb/gwlb resolve to their resource icon; the generic service icon is "elb".
    "alb": "application load balancer", "nlb": "network load balancer",
    "gwlb": "gateway load balancer",
    "elb": "elastic load balancing", "load balancer": "elastic load balancing",
    "ecs": "elastic container service", "ecr": "elastic container registry",
    "eks": "elastic kubernetes service", "s3": "simple storage service",
    "sqs": "simple queue service", "sns": "simple notification service",
    "ses": "simple email service", "rds": "relational database service",
    "vpc": "virtual private cloud", "ddb": "dynamodb", "apigw": "api gateway",
    "asg": "ec2 auto scaling", "iam": "identity and access management",
    "kms": "key management service", "acm": "certificate manager", "efs": "elastic file system",
    "ebs": "elastic block store", "msk": "managed streaming for apache kafka",
    "sfn": "step functions", "step functions": "step functions",
    # VPC resources live in the resource set (Amazon-VPC_*)
    "igw": "internet gateway", "nat": "nat gateway", "natgw": "nat gateway",
    "vgw": "vpn gateway", "cgw": "customer gateway", "eni": "elastic network interface",
    "nacl": "network access control list", "pcx": "peering connection",
    # AWS draws a TGW peering attachment with the VPC peering connection icon
    "vpc peering": "vpc peering connection", "tgw peering": "vpc peering connection",
    "transit gateway peering": "vpc peering connection",
    "peering attachment": "vpc peering connection", "tgw peering attachment": "vpc peering connection",
    "vpce": "vpc endpoints", "endpoint": "vpc endpoints",
    "gateway endpoint": "vpc endpoints", "interface endpoint": "vpc endpoints",
    "s3 gateway endpoint": "vpc endpoints", "dynamodb gateway endpoint": "vpc endpoints",
    "s3 endpoint": "vpc endpoints", "dynamodb endpoint": "vpc endpoints",
    "eice": "vpc endpoints", "instance connect endpoint": "vpc endpoints",
    # the package files its only route table icon under Route 53; it is also the VPC/TGW route table
    "route table": "route 53 route table", "routing table": "route 53 route table",
    "rtb": "route 53 route table", "vpc route table": "route 53 route table",
    "tgw route table": "route 53 route table",
    "ec2 instance connect endpoint": "vpc endpoints", "tgw": "transit gateway",
    "gwlbe": "vpc endpoints", "gwlb endpoint": "vpc endpoints",
    "gateway load balancer endpoint": "vpc endpoints",
    "aws cloud": "aws cloud logo", "cloud": "aws cloud logo",
    "on-prem": "corporate data center", "on-premises": "corporate data center",
    "onprem": "corporate data center", "data center": "corporate data center",
    "datacenter": "corporate data center",
    "agentcore": "bedrock agentcore",
}

# Names and abbreviations a first-time author types when looking an icon up (find_icon.py, a
# spec's bare `icon:`). Keys match case-, hyphen- and space-insensitively, and each word of a
# longer query is spelled out too ("ecs task"). Every target is an official icon in
# assets/icons.json. Lookup only: the SERVICE AS TEXT check (search(..., lookup=False)) reads
# connector labels with ALIASES alone, so "VPC attachment", "VPN" or "사용자" on a line stay labels.
LOOKUP_ALIASES = {
    "tgw attachment": "transit gateway attachment", "tgw attach": "transit gateway attachment",
    "tgw vpc attachment": "transit gateway attachment", "vpc attachment": "transit gateway attachment",
    "tgw vpn attachment": "transit gateway attachment", "tgw dx attachment": "transit gateway attachment",
    "transitgateway attachment": "transit gateway attachment",
    "dx": "direct connect", "aws dx": "direct connect", "dx connection": "direct connect",
    "direct connect connection": "direct connect", "dx link": "direct connect",
    "dxgw": "direct connect gateway", "dx gateway": "direct connect gateway",
    "dx gw": "direct connect gateway", "dcgw": "direct connect gateway",
    # "VPN" alone ties Client VPN and Site-to-Site VPN; in an architecture diagram it is the S2S one
    "vpn": "site-to-site vpn", "s2s": "site-to-site vpn", "s2s vpn": "site-to-site vpn",
    "aws vpn": "site-to-site vpn",
    "virtual private gateway": "vpn gateway", "vpg": "vpn gateway",
    "customer gateway device": "customer gateway",
    "nat gw": "nat gateway", "ngw": "nat gateway",
    "internet gw": "internet gateway",
    "vpc endpoint": "vpc endpoints", "vpc interface endpoint": "vpc endpoints",
    "vpc gateway endpoint": "vpc endpoints", "privatelink endpoint": "vpc endpoints",
    "endpoint service": "privatelink", "vpc endpoint service": "privatelink",
    "aws privatelink": "privatelink",
    "internal alb": "application load balancer", "internal nlb": "network load balancer",
    "loadbalancer": "elastic load balancing", "lb": "elastic load balancing",
    "ecs task": "elastic container service task", "fargate task": "elastic container service task",
    "ecs service": "elastic container service service",
    "fargate service": "elastic container service service",
    "aurora writer": "aurora instance", "aurora reader": "aurora instance",
    "aurora primary": "aurora instance", "aurora replica": "aurora instance",
    "aurora read replica": "aurora instance", "aurora cluster": "aurora",
    "rds primary": "rds instance", "rds standby": "rds instance", "rds replica": "rds instance",
    "web acl": "waf", "waf web acl": "waf", "webacl": "waf", "aws waf": "waf",
    "cloudfront distribution": "cloudfront", "cf": "cloudfront",
    "ram": "resource access manager", "aws ram": "resource access manager",
    "org": "organizations", "aws organizations": "organizations",
    "member account": "organizations account", "org account": "organizations account",
    "workload account": "organizations account",
    "management account": "organizations management account",
    "payer account": "organizations management account",
    "ou": "organizations organizational unit", "organizational unit": "organizations organizational unit",
    "on prem": "corporate data center", "on premise": "corporate data center",
    "corporate": "corporate data center", "corporate network": "corporate data center",
    "corp": "corporate data center", "idc": "corporate data center", "dc": "corporate data center",
    "office": "office building", "branch office": "office building",
    "end user": "users", "end users": "users", "customers": "users",
    "mobile": "mobile client", "mobile app": "mobile client",
    "r53": "route 53", "route53": "route 53",
    "nfw": "network firewall", "anfw": "network firewall",
    "ga": "global accelerator", "aga": "global accelerator",
    "cw": "cloudwatch", "kds": "kinesis data streams", "api gw": "api gateway",
    "sso": "iam identity center", "aws sso": "iam identity center",
    "identity center": "iam identity center", "ssm": "systems manager", "cfn": "cloudformation",
    "firehose": "data firehose", "kinesis firehose": "data firehose", "kdf": "data firehose",
    "cwl": "cloudwatch logs", "lambda function": "lambda lambda function",
    "opensearch": "opensearch service",
    # Korean labels are common in customer diagrams; the AWS Korean console names
    "사용자": "users", "사용자들": "users", "고객": "users", "최종 사용자": "users",
    "온프레미스": "corporate data center", "온프렘": "corporate data center",
    "데이터센터": "corporate data center", "데이터 센터": "corporate data center",
    "전산센터": "corporate data center",
    "사무실": "office building", "지점": "office building",
    "인터넷": "internet", "서버": "server", "모바일": "mobile client",
    "전용선": "direct connect", "다이렉트 커넥트": "direct connect",
    "전송 게이트웨이": "transit gateway", "트랜짓 게이트웨이": "transit gateway",
    "인터넷 게이트웨이": "internet gateway", "nat 게이트웨이": "nat gateway",
    "고객 게이트웨이": "customer gateway", "가상 프라이빗 게이트웨이": "vpn gateway",
    "로드밸런서": "elastic load balancing", "로드 밸런서": "elastic load balancing",
    "라우팅 테이블": "route 53 route table", "라우트 테이블": "route 53 route table",
    "엔드포인트": "vpc endpoints", "계정": "aws account",
}


def akey(s: str) -> str:
    """An alias key: lowercase, hyphens/underscores/runs of spaces → one space."""
    return re.sub(r"[\s_\-]+", " ", s.lower()).strip()


_ALIAS = {akey(k): v for k, v in {**ALIASES, **LOOKUP_ALIASES}.items()}

# Things an author looks up that have no icon of their own: what to say, and the query whose
# icons the CLI prints instead. Not aliases, so a line labeled "VPC origin" stays a label.
NO_ICON_NOTES = {
    "vpc origin": ("there is no separate VPC origin icon: a CloudFront VPC origin is a CloudFront "
                   "setting, so draw service/Amazon-CloudFront and the internal ALB/NLB/EC2 it reaches, "
                   "and write 'VPC origin' as that node's sub or the line's label", "cloudfront"),
}
NO_ICON_NOTES["cloudfront vpc origin"] = NO_ICON_NOTES["vpc origin"]


# Logo-less AWS Cloud outlines: never offered, the AWS Cloud badge always has the logo.
NO_LOGO = {"group/AWS-Cloud_32", "group/AWS-Cloud_32_Dark"}
# Groups the official toolkit draws without a badge icon (see diagram_guide.md).
NO_ICON_GROUPS = {
    "az": "Availability Zone", "availability zone": "Availability Zone",
    "security group": "Security group", "sg": "Security group",
    "generic group": "Generic group", "step functions workflow": "Step Functions workflow",
}
VENDOR = {"amazon", "aws"}
# Size/theme suffixes on group icons (AWS-Cloud_32_Dark) are not part of the name.
SUFFIX = {"32", "dark", "light"}
# Tie-break order: a service icon beats a resource or category icon of the same score.
SET_ORDER = ["service", "resource", "group", "category"]


def norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def tokens(s: str) -> list:
    return re.findall(r"[a-z0-9]+", s.lower())


def bare(nt: list) -> list:
    """Name tokens without size/theme suffixes."""
    while nt and nt[-1] in SUFFIX:
        nt = nt[:-1]
    return nt


def core(nt: list) -> list:
    """Name tokens without the Amazon/AWS prefix and size/theme suffixes."""
    nt = bare(nt)
    while nt and nt[0] in VENDOR:
        nt = nt[1:]
    return nt


def has_run(qt: list, nt: list) -> bool:
    return any(nt[i:i + len(qt)] == qt for i in range(len(nt) - len(qt) + 1))


def score(query: str, name: str) -> int:
    """Match on whole words so `nat` finds NAT-Gateway, not Alter-nat-e."""
    qt, nt = tokens(query), tokens(name)
    if not qt:
        return 0
    if norm(query) == norm(name):
        return 100
    if qt in (core(nt), bare(nt)) or norm(query) == "".join(core(nt)):
        return 95
    if has_run(qt, core(nt)):
        # The query is the service name (or its tail, e.g. VPC_NAT-Gateway).
        return 85 if nt[-len(qt):] == qt else 75
    if all(t in nt for t in qt):
        return 65
    if all(any(n.startswith(t) for n in nt) for t in qt):
        return 50  # word prefixes: "dynamo" -> DynamoDB
    if len(norm(query)) >= 4 and norm(query) in norm(name):
        return 30
    return 0


def word_aliases(query: str):
    """The query with each word that is an alias spelled out ("ecs task" → "elastic container
    service task"), or None when no word is one."""
    words = akey(query).split(" ")
    if len(words) < 2:
        return None
    out = [a if isinstance(a, str) else w for w in words for a in [_ALIAS.get(w)]]
    return " ".join(out) if out != words else None


def search(query: str, k: int = 5, lookup: bool = True):
    """[(score, ref)], best first. lookup=False: the query's own words and ALIASES only."""
    if lookup:
        alias = _ALIAS.get(akey(query), [])
    else:
        alias = ALIASES.get(query.lower().strip(), [])
    queries = [query] + ([alias] if isinstance(alias, str) else alias)
    spelled = word_aliases(query) if lookup else None
    if spelled:
        queries.append(spelled)
    results = []
    for setname, entries in SETS.items():
        for name in entries:
            s = max(score(q, name) for q in queries)
            if f"{setname}/{name}" in NO_LOGO:
                continue  # embed.py rejects these; the -logo variant is the AWS Cloud badge
            if s > 0:
                rank = SET_ORDER.index(setname) if setname in SET_ORDER else len(SET_ORDER)
                results.append((s, rank, len(name), f"{setname}/{name}"))
    results.sort(key=lambda r: (-r[0], r[1], r[2]))
    return [(s, ref) for s, _, _, ref in results[:k]]


def _names():
    """{spelled name: ref or None} for close-match suggestions: each icon's name in words, and
    each alias key (None: resolved by search() only when it is suggested)."""
    out = {}
    for setname, entries in SETS.items():
        for name in entries:
            ref = f"{setname}/{name}"
            if ref not in NO_LOGO:
                out.setdefault(" ".join(core(tokens(name))), ref)
    for key in _ALIAS:
        out.setdefault(key, None)
    return out


_NAMES = None


def _shared_start(a: str, b: str) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


def closest(query: str, k: int = 3):
    """[(name, ref)] for the names nearest to a query that matched nothing (typos, near words)."""
    global _NAMES
    if _NAMES is None:
        _NAMES = _names()
    out, seen = [], set()
    words = akey(query).split(" ")
    while len(words) > 1 and words[0] in VENDOR:
        words = words[1:]  # icon names are spelled without Amazon/AWS
    q = " ".join(words)
    near = difflib.get_close_matches(q, list(_NAMES), n=k * 3, cutoff=0.6)
    # ties (ec3: ec2, ecr, ecs) go to the longest shared start, then the alphabet
    near.sort(key=lambda n: (-round(difflib.SequenceMatcher(None, q, n).ratio(), 3),
                             -_shared_start(q, n), n))
    for name in near:
        ref = _NAMES[name]
        if ref is None:
            hits = search(name, k=1)
            ref = hits[0][1] if hits else None
        if ref and ref not in seen:
            seen.add(ref)
            out.append((name, ref))
    return out[:k]


def no_match_hint(query: str) -> str:
    """What to try when a search finds nothing: the closest names, else the --list commands."""
    near = closest(query)
    if near:
        return "closest: " + ", ".join(f"{ref} ({name!r})" for name, ref in near)
    return "try: find_icon.py --list service, then --list resource"


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        print("Available sets:", ", ".join(f"{k} ({len(v)})" for k, v in SETS.items()))
        sys.exit(1)
    if args[0] == "--list":
        setname = args[1] if len(args) > 1 else "service"
        if setname not in SETS:
            sys.exit(f"Unknown set {setname!r}. Sets: {', '.join(SETS)}")
        for name in sorted(SETS.get(setname, {})):
            if f"{setname}/{name}" not in NO_LOGO:
                print(f"{setname}/{name}")
        return
    for query in args:
        print(f"# {query}")
        group = NO_ICON_GROUPS.get(query.lower().strip())
        if group:
            print(f"  (no icon: {group} is a label-only group — draw a rect in the color from "
                  "diagram_guide.md's group table, no corner badge)")
            print()
            continue
        note, instead = NO_ICON_NOTES.get(akey(query), (None, None))
        if note:
            print(f"  (no icon: {note})")
        hits = search(instead or query)
        if not hits and not note:
            print(f"  (no match — {no_match_hint(query)})")
        for s, ref in hits:
            print(f"  [{s:3}] {ref}")
        print()


if __name__ == "__main__":
    main()
