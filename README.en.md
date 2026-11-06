# skill-aws-arch-diagram

> 한국어: [README.md](README.md)

An unofficial, community-built [Claude Code](https://claude.com/claude-code) skill that
draws AWS architecture diagrams with the
[AWS Architecture Icons](https://aws.amazon.com/architecture/icons/) AWS publishes — real
service, resource and group icons instead of hand-drawn approximations or text chips —
and exports them as an **SVG**, a **PNG** and/or an editable **PowerPoint deck** from one
layout.

Not made or endorsed by AWS. The icons belong to AWS and are downloaded from AWS at
install time (see [License](#license)).

![Example output: AWS Cloud > Region > VPC > two AZs, the IGW on the VPC border, one ALB between the AZs, an ASG · target group spanning both AZs with EC2 in each](docs/example.png)

What it enforces:

- Every service **and every networking resource** (Internet gateway, NAT gateway, VPC
  endpoints, route tables, load balancers) is drawn with its official icon — connections
  such as Site-to-Site VPN and TGW peering too, with only protocols on connector labels —
  looked up by name in the official icon package downloaded from AWS at install time,
  never typed from memory.
- AWS's nesting convention (AWS Cloud > Region > VPC > subnets) with the group border
  colors and dash styles taken from the official package and its PowerPoint toolkit,
  including groups that have no icon (Availability Zone, security group).
- One icon size for every node; Internet gateways and virtual private gateways
  centered on the VPC border with the border masked behind icon and label.
- Traffic flows left → right (tiers as columns, AZs as rows); ALB/NLB/GWLB are one
  node across the AZs while zonal resources stay per AZ; detours get numbered steps.
- Square-cornered official group styles, compact containers and readable 14px/12px text.
- One draft subset (rect, image, text, line, polyline, circle) that maps 1:1 onto
  PowerPoint shapes, checked for lines crossing labels or icons before export.
- `export.py` writes any mix of formats: an SVG with all icons inlined as base64, a PNG,
  and a 16:9 deck whose containers, connectors and labels are PowerPoint shapes and
  whose icons are the official SVGs; slide text is kept at 10pt or larger (8pt only when
  unavoidable).

## Reference examples

Finished diagrams in [`docs/examples/`](docs/examples/) (SVG + PNG), drawn with the skill
and used as its starting layouts. [`reference-architectures.pptx`](docs/examples/reference-architectures.pptx)
holds the first five as slides, re-laid out to fit 16:9 with text at 10pt or larger (9.9pt on the GWLB slide);
their SVGs and a render of each slide are in [`docs/examples/slides/`](docs/examples/slides/).

| NLB | ALB |
|---|---|
| ![NLB reference architecture](docs/examples/nlb-reference-architecture.png) | ![ALB reference architecture](docs/examples/alb-reference-architecture.png) |
| Internet-facing NLB, TLS listener, ASG target group across two AZs | 3-tier: ALB with AWS WAF, app ASG, RDS Multi-AZ |

| GWLB | Transit Gateway |
|---|---|
| ![GWLB reference architecture](docs/examples/gwlb-reference-architecture.png) | ![Transit Gateway reference architecture](docs/examples/tgw-reference-architecture.png) |
| Distributed inspection: GWLBe per AZ, one GWLB and a firewall ASG in a security VPC | Hub and spoke in two Regions joined by inter-Region TGW peering (the peering connection icon), on-premises over Site-to-Site VPN across the Internet; attachment-type labels, a route-table node per TGW, and the on-premises → DR VPC flow numbered on the attachment lines |

| AWS Network Firewall | NLB mTLS |
|---|---|
| ![AWS Network Firewall centralized reference architecture](docs/examples/nfw-reference-architecture.png) | ![NLB mTLS reference architecture](docs/examples/nlb-mtls-reference-architecture.png) |
| Centralized inspection: spoke and firewall route tables on a Transit Gateway, one inspection VPC with a firewall endpoint per AZ inspecting both VPC-to-VPC traffic and Internet egress through NAT | Client-certificate verification: an ELB trust store built from a CA bundle and CRL in S3 on the :443 listener, forking to one EC2 per AZ; the landscape layout with the step legend in a left pane |

| Bedrock over Direct Connect |
|---|
| ![Private Amazon Bedrock access over a Direct Connect private VIF](docs/examples/bedrock-dx-reference-architecture.png) |
| Claude Code on premises calls Bedrock privately: DX private VIF → Direct Connect gateway → VGW → interface endpoints for bedrock-runtime, bedrock and sts, names resolved through a Route 53 Resolver inbound endpoint; global cross-Region inference from Seoul, a second-Region endpoint behind the same DX gateway, and the internet-bound aws sso login sign-in, each as a numbered step |

## Install

macOS and Linux are supported.

### macOS

With [Homebrew](https://brew.sh) it is three commands:

```bash
brew install uv cairo && brew install --cask font-noto-sans-cjk-kr
git clone https://github.com/conft2k/skill-aws-arch-diagram ~/.claude/skills/skill-aws-arch-diagram
python3 ~/.claude/skills/skill-aws-arch-diagram/scripts/fetch_icons.py
```

The first installs uv, cairo and a Korean font; the other two install the skill and
downloads the icons. git and python3 come with Homebrew's install. The scripts find
cairo in Apple Silicon's `/opt/homebrew/lib` themselves, so no shell setup is needed.

### Linux

```bash
# Amazon Linux / Fedora
sudo dnf install -y git python3 cairo google-noto-sans-cjk-ttc-fonts
# Debian / Ubuntu
sudo apt install -y git python3 libcairo2 fonts-noto-cjk

curl -LsSf https://astral.sh/uv/install.sh | sh && source $HOME/.local/bin/env
git clone https://github.com/conft2k/skill-aws-arch-diagram ~/.claude/skills/skill-aws-arch-diagram
python3 ~/.claude/skills/skill-aws-arch-diagram/scripts/fetch_icons.py
```

### After installing

- Claude Code watches skill folders live, so no restart is needed — except when
  `~/.claude/skills/` itself did not exist when the session started: then run
  `/reload-skills` once. The skill then triggers on requests like "draw the AWS
  architecture for …", "AWS 아키텍처 그려줘" or "이 구성도를 PPT 장표로 만들어줘".
- For one project only, clone into that project's `.claude/skills/skill-aws-arch-diagram`
  instead; cloning elsewhere and symlinking also works.
- **Update**: `git -C ~/.claude/skills/skill-aws-arch-diagram pull`
- **Uninstall**: `rm -rf ~/.claude/skills/skill-aws-arch-diagram`

### Details

- **Requirements**: git, Python 3.9+, [uv](https://docs.astral.sh/uv/), cairo and a Korean
  font (Noto Sans CJK KR or Pretendard). The export runs with
  `uv run --with python-pptx --with cairosvg`, so no Python packages are installed
  globally. cairo renders PNGs and slide previews; the font draws Korean labels in PNGs
  (without it they are dropped).
- **Icons**: the AWS icons are not in this repository. `fetch_icons.py` downloads the
  official package (~14 MB, pinned by URL and SHA-256) and builds `assets/icons.json`. If
  you skip it, Claude downloads them the first time it draws, which fails when a sandbox
  blocks the network or writes to the skill folder — so run it at install time.
  `icons.json` is not tracked, so it survives updates, and it is rebuilt on the next run
  if the pinned package changed.
- **Offline**: download the zip from the pinned URL below, copy it over and build with
  `--zip`. The latest package on the AWS icons page has a different SHA-256 and is rejected.

  ```bash
  # https://d1.awsstatic.com/onedam/marketing-channels/website/public/shared/architecture-icon-release/Icon-package_07312026.5846e92413caa21490223536cc97f1269e44fa92.zip
  python3 ~/.claude/skills/skill-aws-arch-diagram/scripts/fetch_icons.py --zip Icon-package_07312026.zip
  ```
- **Decks**: PowerPoint 2016 or later / Microsoft 365 draws the SVG icons as vectors;
  older viewers fall back to the embedded PNGs. Slides use Arial and Malgun Gothic
  (맑은 고딕) by default; change them with `--font` / `--ea-font`.

## Layout

```
SKILL.md                     the skill: workflow, rules, what not to do
references/diagram_guide.md  AWS visual grammar, group colors, VPC resource table,
                             draft subset and skeleton, layout, text-size and font rules
references/layout_spec.md    the layout spec (`*.layout.yaml`) format
assets/icons.json            857 icons in one JSON bundle (sets: service, resource,
                             group, category); built at install time (or on first
                             use), not committed
docs/examples/specs/         one layout spec per reference example plus the skeleton
                             `example.layout.yaml`; each regenerates its example's layout
scripts/find_icon.py         fuzzy lookup: `find_icon.py alb igw "s3 gateway endpoint"`
scripts/layout.py            the layout engine: spec -> draft SVG; computes every coordinate,
                             runs check_layout with feedback rounds, and names the spec item
                             and a spec change to try for each problem
scripts/layout_spec.py       load and validate a spec: schema, defaults, `per` templates, edge
                             strings, icon names
scripts/layout_solve.py      constraint solver: track, group and node coordinates by longest
                             path over difference constraints
scripts/layout_route.py      edge router: shape choice, the space routes need, lines, labels,
                             step badges
scripts/layout_note.py       the note (step legend): panel / pane / lines placement, size,
                             elements
scripts/layout_model.py      the engine's data model and module contract
scripts/layout_const.py      engine constants: mode tables, group styles, text, line and note
                             numbers
scripts/export.py            drafts -> any of SVG / PNG / PPTX (+ slide previews); checks
                             every draft first and writes nothing if one fails
scripts/embed.py             inline bundle: refs as base64; fails on unknown/external refs
                             and on rounded group containers
scripts/svg2pptx.py          drafts -> .pptx of native shapes; fails on anything it can't
                             convert exactly
scripts/render_pptx.py       render each slide of a deck to PNG
scripts/check_layout.py      flag lines over labels/icons, label overlap and spacing,
                             text off the canvas or < 12px, services written as
                             connector labels
scripts/fetch_icons.py       download the pinned AWS icon package and build icons.json
scripts/build_bundle.py      pack an extracted icon package into icons.json
scripts/macos_cairo.py       let cairosvg find Homebrew's cairo on Apple Silicon
```

### Drawing a new diagram with the layout engine

A new diagram is drawn from a layout spec, with no coordinates. Copy the closest example's
spec from [`docs/examples/specs/`](docs/examples/specs/) and edit its column and row
tracks, containers, nodes, edges and note; the format is in
[`references/layout_spec.md`](references/layout_spec.md).

```bash
cp docs/examples/specs/nlb-reference-architecture.layout.yaml arch.layout.yaml
python3 scripts/layout.py arch.layout.yaml -o arch.draft.svg
#   draft: arch.draft.svg
#   canvas: 888 × 806 (document); on a 16:9 slide (titled) 12px text → 6.7pt
#   note: panel, summary, 856 × 44 at (16,746)
#   icons (13 nodes): resource/Users, service/Amazon-Route-53, ...
#   Layout OK
```

The engine computes every coordinate, then runs `check_layout` in process and answers what
it finds with feedback rounds (wider gaps, other routes) before writing the draft. After a
summary it prints `Layout OK` (exit 0), or `N problems` (exit 1) with a `spec:` line naming
the spec item behind each problem and a `try:` line with the spec change to try. Export the
draft with `export.py` as below.

- `.yaml` specs need PyYAML; without it run
  `uv run --with pyyaml python scripts/layout.py ...`. A `.json` spec needs nothing extra.
- The same spec always gives a byte-identical draft. Once you hand-edit a generated draft,
  that draft is the source and is no longer regenerated.
- To change or convert an existing diagram, or for a layout the engine cannot express,
  write the SVG draft by hand as before — or turn an example back into a draft with
  `embed.py --unembed` and edit it.

### Using the scripts directly

Run these from the skill folder (`~/.claude/skills/skill-aws-arch-diagram`).

```bash
# find the exact reference for an icon
python3 scripts/find_icon.py ec2 "api gateway" igw nat "s3 gateway endpoint"
#   [ 95] service/Amazon-EC2
#   [ 85] resource/Amazon-VPC_Internet-Gateway
#   ...

# in your SVG, reference icons with the bundle: scheme
#   <image href="bundle:service/AWS-Lambda" x="200" y="200" width="48" height="48"/>

# check the layout (exit 1 lists every violation)
python3 scripts/check_layout.py draft.svg

# export any mix of formats (exit 1 lists anything that would not render or convert)
uv run --with python-pptx --with cairosvg python scripts/export.py \
  a.draft.svg b.draft.svg --svg --png --out-dir out \
  --pptx out/deck.pptx --title "Slide A" --title "Slide B" --preview

# or one format at a time
python3 scripts/embed.py a.draft.svg a.svg
uv run --with python-pptx --with cairosvg python scripts/svg2pptx.py a.draft.svg -o deck.pptx
uv run --with python-pptx --with cairosvg python scripts/render_pptx.py deck.pptx deck-preview
```

## Updating the icon set

AWS releases a new icon package a few times a year at
<https://aws.amazon.com/architecture/icons/>. The skill is pinned to
`Icon-package_07312026`. To move to a new package, set `PACKAGE`, `URL` and `SHA256` in
`scripts/fetch_icons.py` and rebuild:

```bash
python3 scripts/fetch_icons.py --force
```

Services dropped from the new package disappear from the bundle. After rebuilding,
update the package date and set counts in `SKILL.md`, and re-check the
group colors in `references/diagram_guide.md` (see the "Updating the icon set" section
of `SKILL.md`).

## License

The skill's code and documentation are licensed under the Apache License 2.0
(see [LICENSE](LICENSE)).

The AWS Architecture Icons belong to Amazon Web Services and are **not** part of this
repository or covered by that license: `scripts/fetch_icons.py` downloads them from AWS
on your machine, and your use of them is subject to AWS's terms. The example SVGs, PNGs
and deck are architecture diagrams drawn with those icons. See [NOTICE](NOTICE).
This project is not affiliated with or endorsed by AWS.
