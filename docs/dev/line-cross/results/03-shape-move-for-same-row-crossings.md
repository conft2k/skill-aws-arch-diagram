# Ticket 03: 자기 행·열의 노드를 곧게 지나는 선에 shape 이동

기준은 main `7a3459e`(ticket 02 병합)의 `~/.cache/skill-design/baseline/main-7a3459e.json`과 `main-7a3459e-drafts/`다. 기준과 최종 실행 모두 `-j 6`이고, 최종 corpus는 pytest·렌더와 겹치지 않게 한 번 실행했다. 독립 리뷰(Codex 코드 리뷰, PNG 재판정)는 이 문서 뒤에 별도로 한다.

증거: `~/.cache/skill-design/improve/line-cross/t03/final/`(`corpus.json`, `corpus.log`, `drafts/`, `pytest.log`), PNG는 `~/.cache/skill-design/improve/line-cross/t03/png/`.

## 완료 조건

- [x] bad 태그 사례의 F6 합계가 ticket 02 뒤(28)보다 적다: **28 → 17**. dns-trunk(4 → 0), nat-route-table(4 → 2), three-az-writer(16 → 11)가 모두 crossing을 잃었다.
- [x] 기준 대비 corpus: **better 5 / same 788 / worse 0**, 새 tier-0 identity가 생긴 run **0**, 태그 불일치 **0**. 바뀐 draft 5개는 모두 기준에 F6이 있던 run이다. F6이 없던 run의 draft는 모두 byte-identical이다.
- [x] 시간: 3×·30초 초과 0. 합계 **0.997×**, 0.5초 이상 run 중 최대 비율 **1.045×**, 최악 run **17.84초**.
- [ ] Codex PNG 재판정: 이 문서 뒤 독립 리뷰가 한다.
- [ ] Codex review: 이 문서 뒤.

## 무엇을 만들었나

### step-around shape (router)

`layout_route`에 두 shape을 더했다. spec의 `shape:` 값이 아니고, selection이 `draw(steps=)`로 이름을 준 edge에만 후보로 붙는다.

- **VHVH**: source의 top/bottom 면으로 나가서, source 행 밖의 lane(가로)을 지나, 두 끝 사이의 leg(세로)를 타고, target의 마주 보는 left/right 면으로 들어간다.
- **HVHV**: 같은 것을 90° 돌린 모양이다.
- bend는 (lane, leg) 쌍이다.
  - lane: source port 바로 바깥의 첫 free stretch. 두 끝 사이 전체에서 icon과 이름 줄을 피하고, 두 끝을 담는 가장 안쪽 box(없으면 canvas) 안에 있어야 한다.
  - leg: 두 끝 사이의 free stretch. HVH의 bend처럼 target의 arrow_target을 먼저 본다.
  - 면마다 lane·leg를 4개까지 만들고, 짧은 것부터 시도한다.
- 순위:
  - `steps`에 든 edge에 깨끗한 step 후보가 있으면, 그 가운데 가장 좋은 것을 그린다. 이때 skip index는 무시한다. skip index는 원래 후보 목록의 번호여서, step 후보가 끼면 다른 경로를 가리킨다(three-az-writer edge:0이 UVHV로 바뀌던 원인).
  - 깨끗한 step 후보가 없으면 예전과 같다.
- trunk:
  - lead가 step shape이면 follower는 자기 lane으로 lead의 leg에 들어가 합쳐진다. merge follower는 lead의 leg 위에서 끝나서 화살표가 하나다.
  - follower가 다른 leg를 고르면 lead 옆 7.8px에 평행선과 F3이 생겼다(dns 첫 시도). 그래서 lead의 leg를 받게 했다.
- step shape에는 "drew X instead of Y" 경고를 내지 않는다. selection이 일부러 고른 모양이어서 shape miss와 feedback widen에 들지 않는다.

### shape 이동 (selection)

`layout.line_over_node_moves`의 (c)다. channel move (b) 뒤에, 그때까지의 승자에서 시작한다.

- `step_moves`가 후보 edge 집합을 만든다.
  - 대상: F6 owner 가운데 engine이 routing하는 edge(`layout_route.skippable`).
  - trunk면 그 spec line의 모든 member를 넣는다. 공유 stem이 함께 움직이게 하려는 것이다.
  - 순서: 모든 F6 line을 한꺼번에 → spec line 하나씩 → F6 owner edge 하나씩. 최대 `MAX_SHAPE_MOVES = 3`개다.
- 각 후보는 승자의 spec·요구·skip·decision에 `Decisions.steps`만 더해 다시 build한다.
- 채택 조건은 ticket 02와 같다.
  - enabled verdict와 전체 verdict가 모두 엄격히 낮다. check problem 수가 늘지 않는다. `admits`를 통과한다.
  - tier-0 identity 집합이 승자 집합의 진부분집합이고, 빠진 것에 F6이 하나 이상 있다.
  - 가장 작은 글자가 medium floor 아래로 새로 내려가지 않는다.
- PRE_SELECTION_IGNORED는 그대로다. default drawing과 원본 spec 재평가 guard는 F6을 보지 않고, 이 이동도 selection이 끝난 뒤에만 돈다.
- selection 줄 예: `selection: candidate 0 (step-around shape tried: edge:2, edge:3); removed R-flow F1 ×2, R-flow F6 ×2; …`

### 손으로 둔 선: try 경고

저자가 쓴 필드(shape, bend_*, points, from/to_side, from/to_offset, label_at, step_at, trunk)는 바꾸지 않는다. 손으로 둔 F6 line은 한 번(`MAX_AUTHOR_PROBES = 1`) 다음 probe를 만든다.

- 그 line의 배치 필드를 뺀 spec(`unplaced`)을 step으로 다시 build한다.
- 채택하지 않는다. F6과 tier-0 개수가 모두 줄고 verdict가 나아지면 경고로만 알린다. 새로 생기는 tier-0이 있으면 그 이름을 적는다.
- 예(privatelink slide):
  `warning: hand placement edges[11] (shape, bend_y, from_side, to_side) keeps R-flow F6; try: drop `shape` / `bend_y` / `from_side` / `to_side` from edges[11] so selection can route it around the node (tried: F6 −2, tier-0 5 → 1, new R-flow F3 (edge:12, edge:14))`
- ticket 01의 F6 `try:` 값(`edges[11] bend_y: 340` 등)도 그대로 나온다.

## Bad 태그 사례: F6 02 → 03

| Case | Mode | 02 → 03 | 없앤 이동 | 남은 F6과 이유 |
|---|---|---:|---|---|
| `qa/t3-dns-trunk` | slide | 2 → **0** | shape 이동: outbound.1·2 → VGW trunk를 VHVH로. 각 member가 Outbound ENI의 bottom/top에서 AZ 행 밖 lane으로 나가 x=92의 한 leg에서 합쳐져 VGW 오른쪽으로 들어간다. F1 ×2도 함께 사라졌다 | 없음 |
| | slide-no-title | 2 → **0** | 같음 | 없음 |
| `qa/t3-nat-route-table` | slide | 2 → **1** | shape 이동: nat.1 → IGW가 NAT 아래로 나가 NAT RT 1 이름 아래 lane을 지나 stem으로 간다 | (1, rt.2): nat.2의 step 후보가 모두 깨끗하지 않다. 위쪽 lane은 subnet header("NAT subnet")를 지나고, 아래쪽은 이름 줄과 subnet·AZ·VPC 아래 border 사이에 lane이 없다. 그래서 HVH가 NAT RT 2를 그대로 지난다 |
| | slide-no-title | 2 → **1** | 같음 | 같음 |
| `qa/t4-three-az-writer` | document | 5 → **0** | shape 이동: orders.1·2·3 → db.1 세 줄 모두 VHVH. 서버 아래로 나가 App·Data 사이 gap의 한 leg를 타고 writer 왼쪽으로 들어간다. B2 ×3, F5 ×1도 사라져 rule violation이 0이다 | 없음 |
| | slide | 5 → 5 | | orders.3은 마지막 AZ라 아래 lane이 VPC 안에 없고, 위는 subnet header다. 그래서 step 후보가 모두 깨끗하지 않다. 세 줄 함께 바꾸면 F5 (0, 2)와 L1 (edge:1)이, orders.2만 바꾸면 F5 (0, 1)·(1, 2)가 새로 생겨 채택 조건에서 떨어진다 |
| | slide-no-title | 6 → 6 | | 행 간격이 더 좁아 세 줄 모두 깨끗한 step 후보가 없다. draft가 승자와 같다 |
| `qa/t1-privatelink` | slide | 2 → 2 | | edge:12는 손으로 둔 VHV다. 위 `warning: hand placement edges[11] … try: drop …` 경고가 나온다(probe: F6 −2, tier-0 5 → 1, 새 F3) |
| | slide-no-title | 2 → 2 | | 같음. probe: F6 −2, tier-0 6 → 4, 새 F1·F2·F3을 적는다 |
| `qa/t3-ssm-trunk` | slide 두 mode | 0 → 0 | (ticket 02 channel move) | 없음 |

**합계 28 → 17.** 남은 17건의 이유는 다음과 같다.
- 4건(privatelink): 손으로 둔 선이다.
- 11건(three-az slide 5, slide-no-title 6): 마지막 AZ 행에 lane이 들어갈 자리가 없다.
- 2건(nat rt.2): lane이 header와 box border 사이에 막혔다.

나머지 두 경우는 geometry가 lane 자리를 만들어야 풀린다. 아래 "남은 것"에 적었다.

## 태그

- `qa/t3-dns-trunk`: `bad: {R-flow: {slide: node:inbound.1, slide-no-title: node:inbound.1}}` → `good: [R-flow]`.
  - 근거: 세 mode 모두 R-flow 위반이 없다(document는 기준에서도 없었다).
  - PNG(`t3-dns-trunk.slide{,-no-title}.new.png`)에서 두 outbound 선이 Inbound ENI를 피해 한 leg로 합쳐져 VGW로 가는 것을 확인했다.
- `qa/t3-nat-route-table`: bad owner를 `node:rt.1` → `node:rt.2`(slide 두 mode)로 바꿨다. rt.1의 crossing은 사라졌고 rt.2가 남는다.
- `qa/t4-three-az-writer`: `bad: {R-flow: node:db.2}`(모든 mode) → `bad: {R-flow: {slide: node:db.2, slide-no-title: node:db.2}}`.
  - document는 R-flow 위반이 없다.
  - MANIFEST 형식상 mode별 good을 쓸 수 없어서, bad를 slide 두 mode로 좁혔다.
- 각 항목에 `line-cross 03` 주석으로 이유를 적었다.

## 바뀐 draft (기준 대비 5개, 모두 better)

| Case | Mode | 없앤 tier-0 | Verdict 전 → 후 | 가장 작은 글자 |
|---|---|---|---|---|
| `qa/t3-dns-trunk` | slide | F6 (2, inbound.1), (3, inbound.2), F1 (0, 2), (1, 3) | tier-0 4→0, checks 4→0, 면적 같음 | 10.8pt 그대로 |
| | slide-no-title | 같음 | 같음 | 12.1pt 그대로 |
| `qa/t3-nat-route-table` | slide | F6 (0, rt.1) | tier-0 2→1, checks 2→1 | 10.15pt 그대로 |
| | slide-no-title | 같음 | 같음 | 11.37pt 그대로 |
| `qa/t4-three-az-writer` | document | B2 ×3, F5 (1, 0), F6 ×5 | tier-0 9→0, checks 11→0, shape miss 1→1 | 5.82px 그대로 |

- 새 tier-0 identity가 생긴 run은 0이다. 모든 run에서 geometry(canvas 면적)와 글자 크기는 그대로다. 바뀐 것은 선뿐이다.
- check problem 전체 −21이다: LINE OVER ICON −10, LINE OVER TEXT −4, LINE ON LINE −4, LINE IN HEADER −3.
- violation 증감: R-flow −16, R-border −3, 그 밖 0. 모든 F6: 32 → 21.
- three-az document의 세 `PostgreSQL :5432` label은 공유 leg 옆에 하나씩 붙는다. 세 줄이 trunk가 아닌 별도 선(spec의 `trunk: true`지만 shape이 달라 trunk로 묶이지 않음)이라 label도 셋이다. rule·check 위반은 없다.

## 시간

| 항목 | 기준 7a3459e | 최종 |
|---|---:|---:|
| Corpus wall (s) | 114.62 | 114.24 (0.997×) |
| 합계 (s) | 658.76 | 656.99 (0.997×) |
| 최악 run (s) | 17.857 | 17.835 (`qa/t1-multiregion-dr` slide-no-title) |

- 0.5초 이상 run 중 최대 비율은 `rt/sgw-ret` slide-no-title 1.045×(1.88→1.97초)다. 승자에 F6이 남아 shape 후보 1개를 build한다.
- privatelink slide 10.34→10.51초(1.016×)는 hand-placement probe 한 번이다.
- 바뀐 run 가운데 가장 큰 비율은 nat-route-table slide 1.27×(0.14→0.18초)다.
- 전체 최대 비율 2.08×(`xy/v1up` slide-no-title, 0.012→0.025초)는 아주 짧은 run의 잡음이다. 그 run에는 F6이 없다.
- 3×·30초 초과는 0이다.

## 테스트

- `tests/test_rules.py` `LineOverNodeShapeMove` 5개(엔진 seam: `layout.main` 출력과 그린 draft):
  - dns-trunk slide 두 mode: F6 없음. selection 줄에 `step-around shape tried: edge:2, edge:3`. edge 2·3이 Inbound ENI icon을 지나지 않는다. follower 끝이 lead의 세로 leg 위에 있다.
  - three-az-writer document: R-flow·R-border 위반 없음. 세 줄이 Endpoint·reader icon을 지나지 않는다.
  - nat-route-table slide: (0, rt.1)이 사라지고 (1, rt.2)가 남는다. edge 0이 NAT RT 1 icon을 지나지 않는다.
  - F6 없는 run(dns-trunk document)은 shape 이동을 하지 않는다.
  - privatelink slide: edge:12의 F6이 남고, step을 쓰지 않으며, hand-placement try 경고가 나온다.
- `LineOverNodeMoves.test_author_trunk_is_reported_not_unbundled`: 이제 shape 이동도 ssm-trunk의 F6을 없앤다. 그래서 channel move와 함께 `step_moves`도 꺼야 trunk 풀기 경고 경로를 시험할 수 있다.
- `tests/test_unfixable_warnings.py`: dns-trunk slide에 F1·F6이 없어졌다. F1 hint 사례는 `qa/t4-order-14steps` slide로, F6 hint 사례는 nat-route-table slide의 `rt.2: dy: `로 바꿨다.
- 전체 pytest(`uv run --with pyyaml --with pytest --with cairosvg --with python-pptx --with lxml python -m pytest -q`): **909 passed, 1 xfailed, 2581 subtests passed**, 301.12초(`final/pytest.log`). golden은 바꾸지 않았다.

## PNG

`~/.cache/skill-design/improve/line-cross/t03/png/<name>.<mode>.{old,new}.png`. old는 main 7a3459e draft, new는 최종 draft이고 아이콘을 넣어 렌더했다.

- 요청한 사례:
  - `t1-privatelink.slide`: draft 변화 없음, old = new
  - `t3-dns-trunk.slide`
  - `t3-nat-route-table.slide`
  - `t4-three-az-writer.document`
  - `t4-three-az-writer.slide`: draft 변화 없음, old = new
- 그 밖에 바뀐 draft: `t3-dns-trunk.slide-no-title`, `t3-nat-route-table.slide-no-title`

## 재현

worktree 루트에서:

```bash
uv run --with pyyaml python tests/run_corpus.py --rule-checker scripts/rules.py:corpus -q -j 6 \
  --baseline ~/.cache/skill-design/baseline/main-7a3459e.json \
  --baseline-drafts ~/.cache/skill-design/baseline/main-7a3459e-drafts \
  --keep ~/.cache/skill-design/improve/line-cross/t03/final/drafts \
  --out ~/.cache/skill-design/improve/line-cross/t03/final/corpus.json
```

측정·디버그 스크립트는 `~/.cache/skill-design/improve/line-cross/t03/scratch/tools/`에 있다.
- `f6count.py`, `ids.py`, `times.py`, `pngs.py`: ticket 02에서 가져왔다.
- `cands.py`: edge 하나의 모든 route 후보와 문제를 보여 준다.
- `dbgstep.py`: shape 후보마다 verdict를 보여 준다.
- `dbgprobe.py`: hand-placement probe를 보여 준다.

## 남은 것

- three-az-writer slide 두 mode, nat-route-table의 rt.2: step-around lane이 들어갈 자리가 없다. 마지막 AZ 행 아래가 VPC border에 막혔거나, 위가 subnet header이거나, 이름 줄과 box border 사이가 좁다.
  - 다음 이동 후보: lane 자리를 만드는 geometry 이동이다. 예를 들어 행 아래 box padding을 lane 폭만큼 늘리는 Requirement를 shape 후보와 함께 건다.
- `trunk/merge-vfan` (7, nat.2), `rt/sgw-ret` slide-no-title (8, gwlbe.1): shape 후보를 build했지만 그 edge에 깨끗한 step 후보가 없어 draft가 승자와 같았다. 그래서 기준과 byte-identical이다.
- step shape은 spec 언어로 쓸 수 없다(`shape:`는 6가지뿐). hand-placement 경고는 그래서 "배치 필드를 빼라"고만 안내한다. 점으로 쓰는 `points:` 안내는 하지 않는다.
