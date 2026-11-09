# Ticket 02: ticket 01이 남긴 crossing에 새 후보 이동 두 가지

기준은 main `4b0da21`(ticket 01 병합)의 `~/.cache/skill-design/baseline/main-4b0da21.json`과 `main-4b0da21-drafts/`다. 그 draft는 main `601099d`와 같다. 기준과 최종 실행 모두 `-j 6`이고, 최종 corpus는 pytest·렌더와 겹치지 않게 한 번 실행했다. 기준 json이 이미 F6을 판정하므로 ticket 01처럼 재판정 기준은 필요 없다. 독립 리뷰(Codex)는 이 문서 뒤에 별도로 한다.

증거: `~/.cache/skill-design/improve/line-cross/t02/final/`(`corpus.json`, `corpus.log`, `drafts/`, `pytest.log`), PNG는 `~/.cache/skill-design/improve/line-cross/t02/png/`.

## 완료 조건

- [x] bad 태그 사례의 F6 합계가 ticket 01 뒤(30)보다 적다: **30 → 28**. 태그를 바꾼 사례는 `qa/t3-ssm-trunk`뿐이고 이유는 아래 "태그"에 적었다.
- [x] 기준 대비 corpus: **better 7 / same 786 / worse 0**, 새 tier-0 identity가 생긴 run **0**, 태그 불일치 **0**. 바뀐 draft 7개는 모두 기준에 F6이 있던 run이다. F6이 없던 run의 draft는 모두 byte-identical이다.
- [x] 시간: 3×·30초 초과 0. 합계 **0.983×**, 0.5초 이상 run 중 최대 비율 **1.073×**, 최악 run **17.86초**.
- [ ] Codex PNG 재판정: 이 문서 뒤 독립 리뷰가 한다.
- [ ] Codex review: 이 문서 뒤.

## 무엇을 만들었나

두 이동은 `layout.line_over_node_moves`에 있다. `select_drawing`의 hill-climb와 winner repair가 끝난 뒤, 가장 바깥 선택에서만, **승자에 F6이 있을 때만** 돈다. 그래서 승자에 F6이 없는 run은 예전과 똑같이 그려진다. 후보는 최대 `MAX_LINE_OVER_MOVES = 4`개이고, 기존 후보 예산(12/16)과 따로 센다.

### (b) 통로 넓히기 (channel move)

- `channel_widenings`: F6마다, crossing piece가 crossed node의 **옆 gap**을 지나면(노드 중심을 지나면 아님) 그 piece가 놓인 track gap(`bracket`, flow column이면 `stack_bracket`)을 고른다.
  - 넓히는 양: piece와 노드 footprint(icon + 이름 줄)의 겹침 + 2·ICON_CLEAR.
  - 노드의 자기 track 위를 지나는 piece(같은 행/열의 노드를 곧게 지나는 선)는 넓힐 gap이 없어서 후보가 없다.
  - 손으로 둔 선(`layout_route.skippable`이 아닌 edge: `points`, `bend_*`, `shape`, side/offset, `label_at`, `step_at`)은 후보를 만들지 않는다. `try:` 값으로만 안내한다.
- **trunk 줄기:** F6 owner가 trunk의 instance면, 그 trunk의 lead에 `Decisions.stems`를 준다. router(`layout_route._bends`)는 그 lead의 공유 bend를 **모든 member의 run 전체**를 따라 장애물을 피해 찾는다(`_stem_spans`).
  - 이유: follower는 lead의 bend를 받아 stem을 lead의 끝보다 더 길게 늘린다. 그런데 lead의 bend 탐색은 lead 자신의 run만 본다. 그래서 늘어난 stem이 이름 줄을 지난다(ssm-trunk: lead `ep.1 <..> ssm`의 stem이 `ep.2`까지 내려가며 Session Manager의 이름을 지남).
  - gap만 넓혀서는 이것이 풀리지 않았다. bend가 target에서 arrow_target(48px) 떨어진 곳에 그대로 놓였기 때문이다(실험: 넓히기만 한 후보 4개 모두 F6 그대로).
- 각 후보는 승자의 spec·요구·decision에 그 gap 하나(와 stems)만 바꿔 다시 build한다. 모든 후보는 같은 승자에서 한 번씩 바꾼 것이고, 가장 좋은 것이 이긴다.

### (a) trunk 풀기

- F6 owner가 trunk line의 instance면, 그 line의 member를 따로 그린 spec(`trunk: false`, `fork` 없음)으로 한 번 build해 같은 판정을 한다.
- corpus의 trunk는 모두 저자가 쓴 `trunk: true`(또는 `fork:`)다. 저자의 trunk key는 그대로 둔다는 결정에 따라 **채택하지 않는다.** 판정을 통과하고 F6을 줄이면 경고로만 알린다:
  `warning: author trunk edges[2] (trunk: true) keeps R-flow F6; try: drop `trunk: true` from edges[2] so its 2 lines are drawn separately (tried: F6 −1, no new tier-0 violation, verdict better)`
- 최종 corpus에서는 이 경고가 나오는 run이 없다. 풀어서 F6이 줄던 유일한 사례 ssm-trunk는 이미 channel move가 F6을 없앴다. dns-trunk·nat-route-table은 풀어도 각 선이 같은 행의 노드를 곧게 지나 F6이 그대로다. three-az-writer는 풀면 6건으로 늘어난다.
- 테스트(`test_author_trunk_is_reported_not_unbundled`)는 channel move를 끈 ssm-trunk slide에서 이 경고가 나오고 F6이 남는 것(trunk를 그대로 그림)을 확인한다.

### 채택 조건

후보는 다음을 모두 만족해야 승자를 바꾼다(`better` + `admits`).
- enabled verdict와 전체 verdict가 모두 승자보다 엄격히 낮다. check problem 수는 늘지 않는다. `rule_guard.admits(later=False)`를 통과한다.
- tier-0 identity 집합이 승자 집합의 **진부분집합**이고, 빠진 것에 F6이 하나 이상 있다. 즉 F6을 줄이고 어떤 tier-0도 새로 만들지 않는다(ticket 01 리뷰 교훈).
- 가장 작은 글자가 medium floor(slide 8pt, document 9px) 이상이었으면 그 아래로 내려가지 않는다. target 아래에서 1% 넘게 줄어드는 것은 허용한다. tier-0가 엄격히 줄어드는 경우라서 Glossary(Candidate)의 기존 정책과 같다. 첫 시도에서는 1% 규칙도 걸었는데 v-fork slide·document의 F6 제거(6.06→5.94pt, 이미 floor 아래)를 막았다. 그래서 기존 정책에 맞췄다.

### 그 밖의 변경

- `rules.Violation.at`: F6의 (p, q, footprint box). `compare=False`라서 identity·동등성에 들지 않는다.
- `layout_solve.Decisions.stems`, `layout_route.draw(stems=)`, `_build`/`redraw_routes`가 넘긴다. 비어 있으면 router 동작은 예전과 같다.
- selection 줄: `selection: candidate 0 (trunk stem along every member: edge:3; gap col:endpoint → col:service ≥ 217.9 (F6 channel)); removed R-flow F6 ×1; …`
- PRE_SELECTION_IGNORED는 그대로다. F6은 default drawing과 원본 spec 재평가 guard에서 여전히 숨는다. 새 이동은 selection이 끝난 뒤에만 F6을 본다.
- GLOSSARY에 **Channel move**, rules-design §1 F6·§6에 두 이동을 적었다. layout.py 모듈 docstring도 고쳤다.

## Bad 태그 사례: F6 01 → 02

| Case | Mode | 01 → 02 | 없앤 이동 | 남은 F6과 이유 |
|---|---|---:|---|---|
| `qa/t3-ssm-trunk` | slide | 1 → **0** | channel move: `col:endpoint → col:service` 173.9 → 217.9, stem along edge:3·4 | 없음. R-flow F5 (edge:2, edge:0)은 main과 같이 남는다 |
| | slide-no-title | 1 → **0** | 같음 | 같음 |
| `qa/t3-dns-trunk` | slide | 2 → 2 | | (2, inbound.1), (3, inbound.2): outbound → VGW 선이 같은 행의 Inbound ENI를 곧게 지난다. piece가 노드 자기 행 위라 넓힐 gap이 없다. trunk를 풀어도 각 선이 같은 행을 지나 2건 그대로라서 try 경고도 없다 |
| | slide-no-title | 2 → 2 | | 같음 |
| `qa/t3-nat-route-table` | slide | 2 → 2 | | (0, rt.1), (1, rt.2): NAT → IGW가 같은 행의 NAT RT를 곧게 지난다. 이유는 dns와 같다 |
| | slide-no-title | 2 → 2 | | 같음 |
| `qa/t4-three-az-writer` | document | 5 → 5 | | 가로 piece가 각 AZ 행에서 Endpoint·reader를 지나고(노드 자기 행), 세로 stem은 db 열 안(중심에서 10px, trunk lane)을 지난다. db가 마지막 열이라 옆 gap도 없다. 풀면 6건으로 늘어 판정에서 떨어진다 |
| | slide | 5 → 5 | | 같음 |
| | slide-no-title | 6 → 6 | | 같음과 (0, ep.1) |
| `qa/t1-privatelink` | slide | 2 → 2 | | edge:12는 손으로 둔 VHV(`shape`, `bend_y`, sides)라 후보를 만들지 않는다. `try: edges[11] bend_y: 340` 등 ticket 01의 안내가 그대로 나온다 |
| | slide-no-title | 2 → 2 | | 같음 |

**합계 30 → 28.** 남은 28건 중 24건(dns 4, nat 4, three-az 16)은 선이 crossed node의 자기 행·열을 지난다. gap을 넓히거나 trunk를 풀어서는 없앨 수 없고, 모양(shape)을 바꾸는 이동이 필요하다. 나머지 4건(privatelink)은 손으로 둔 선이다.

## 태그

- `qa/t3-ssm-trunk` slide·slide-no-title: `bad: {R-flow: node:ssm}` → `bad: {R-flow: edge:2}`.
  - 근거: 최종 draft에 F6이 없다. PNG(`t3-ssm-trunk.slide{,-no-title}.new.png`)에서 trunk 줄기가 Session Manager 이름 왼쪽으로 지나는 것을 확인했다.
  - R-flow가 good이 되지는 않는다. main에도 있던 F5 (edge:2, edge:0)(`HTTPS :443` label이 Engineer 선에서 8px, 자기 선에서 6px)가 남기 때문이다. 그래서 bad owner를 그 F5로 바꿨다.
- 다른 bad 태그 사례는 F6이 그대로라 바꾸지 않았다.

## 바뀐 draft (기준 대비 7개, 모두 better)

| Case | Mode | 없앤 F6 | Verdict 전 → 후 | 가장 작은 글자 |
|---|---|---|---|---|
| `qa/t3-ssm-trunk` | slide | (4, ssm) | tier-0 2→1, checks 2→0, 면적 280734→299478 | 12.68pt 그대로 |
| | slide-no-title | (4, ssm) | 같음 | 14.2pt 그대로 |
| `trunk/v-fork` | document | (9, rtfw) | tier-0 1→0, checks 3→0, shortfall 6.10→6.20px | 4.90→4.80px (이미 floor 9px 아래) |
| | slide | (9, rtfw) | tier-0 1→0, checks 4→1, shape miss 1→2, shortfall 3.94→4.06pt | 6.06→5.94pt (이미 floor 8pt 아래) |
| | slide-no-title | (9, rtfw) | tier-0 1→0, checks 4→1 | 5.76pt 그대로 |
| `bench/latest2-pipeline` | slide | (24, sm) | tier-0 1→0, checks 2→1 | 5.10pt 그대로 |
| | slide-no-title | (24, sm) | tier-0 1→0, checks 2→1, shortfall 4.76→4.83pt | 5.24→5.17pt (이미 floor 아래) |

- 모두 trunk의 stem이 crossed node 이름 위를 지나던 사례다. v-fork는 TGW fork가 Firewall RT 이름을, latest2-pipeline은 endpoint trunk가 Secrets Manager 이름을 지났다. channel move가 stem을 이름 옆으로 옮겼다.
- 새 tier-0 identity가 생긴 run은 0이다. 바뀐 7개 run은 각각 F6 하나만 빠졌다.
- 글자가 floor 아래로 새로 내려간 run은 0이다. 줄어든 세 run(v-fork document·slide, latest2 slide-no-title)은 기준에서 이미 floor 아래였다. 줄어든 폭은 1.4–2%이고 tier-0가 엄격히 줄었다.
- v-fork slide의 shape miss +1: NAT → IGW merge가 AZ 1 NAT 아래로 내려가는 모양이 됐다. PNG에서 흐름은 그대로 읽힌다.

check problem 전체 −15(모두 LINE OVER TEXT), violation 증감: R-flow −7, 그 밖 0. 모든 F6: 39 → 32.

## 시간

| 항목 | 기준 4b0da21 | 최종 |
|---|---:|---:|
| Corpus wall (s) | 116.66 | 114.62 (0.983×) |
| 합계 (s) | 670.31 | 658.76 (0.983×) |
| 최악 run (s) | 18.285 | 17.857 (`qa/t1-multiregion-dr` slide-no-title) |

- 0.5초 이상 run 중 최대 비율은 `bench/latest2-pipeline` slide-no-title 1.073×(5.09→5.47초)다. channel 후보 하나를 더 build한다.
- 전체 최대 비율은 아주 짧은 run의 잡음이다: `trunk/fp` slide 2.1×(0.016→0.034초). 이 run의 승자에는 F6이 없어 새 코드가 build를 하지 않는다.
- 이동은 승자에 F6이 있는 run(기준 20 run)에서만 build한다. run당 최대 4개다.
- 3×·30초 초과는 0이다.

## 테스트

- `tests/test_rules.py` `LineOverNodeMoves` 4개(엔진 seam: `layout.main` 출력과 그린 draft):
  - ssm-trunk slide 두 mode: F6 없음, F5 남음, selection 줄에 stem·gap, edge 3·4가 Session Manager의 이름 두 줄을 지나지 않음
  - F6 없는 run(ssm-trunk document)은 이동에 들어가지 않음
  - 손으로 둔 privatelink edge:12에는 channel 후보가 없고 F6이 남음
  - channel move를 끄면 저자 trunk는 풀지 않고 `try: drop trunk: true` 경고만 나옴
- `LineOverNodeEngine.test_a_winner_with_only_f6_still_tries_text_scale`: v-fork slide의 14px 확대가 유지되고, 이제 F6은 channel move로 사라진다.
- `tests/test_unfixable_warnings.py`: F6 hint 사례를 ssm-trunk slide(F6이 사라짐)에서 dns-trunk slide(`inbound.1: dy: `)로 바꿨다.
- 전체 pytest(`uv run --with pyyaml --with pytest --with cairosvg --with python-pptx --with lxml python -m pytest -q`): **905 passed, 1 xfailed, 2581 subtests passed**, 278.85초(`final/pytest.log`). golden은 바꾸지 않았다.

## PNG

`~/.cache/skill-design/improve/line-cross/t02/png/<name>.<mode>.{old,new}.png`. old는 main 601099d draft, new는 최종 draft이고 아이콘을 넣어 렌더했다.
- 요청한 사례(draft 변화 없음, old = new): `t1-privatelink.slide`, `t3-dns-trunk.slide`, `t3-nat-route-table.slide`, `t4-three-az-writer.document`, `t4-three-az-writer.slide`
- 바뀐 draft: `t3-ssm-trunk.slide`, `t3-ssm-trunk.slide-no-title`, `v-fork.document`, `v-fork.slide`, `v-fork.slide-no-title`, `latest2-pipeline.slide`, `latest2-pipeline.slide-no-title`

## 재현

worktree 루트에서:

```bash
uv run --with pyyaml python tests/run_corpus.py --rule-checker scripts/rules.py:corpus -q -j 6 \
  --baseline ~/.cache/skill-design/baseline/main-4b0da21.json \
  --baseline-drafts ~/.cache/skill-design/baseline/main-4b0da21-drafts \
  --keep ~/.cache/skill-design/improve/line-cross/t02/final/drafts \
  --out ~/.cache/skill-design/improve/line-cross/t02/final/corpus.json
```

측정 스크립트(`~/.cache/skill-design/improve/line-cross/t02/scratch/tools/`): `f6count.py`(bad 태그 F6), `ids.py`(새 tier-0 identity와 글자), `times.py`(시간), `pngs.py`(PNG), `variant.py`(spec 하나를 바꿔 그려 보기).

## 남은 것

- 같은 행·열의 노드를 곧게 지나는 선(dns 4, nat 4, three-az 16): shape을 바꾸는 이동(예: 노드 위/아래로 도는 VHV)이 필요하다. 이 ticket의 두 이동 범위 밖이다.
- `trunk/merge-vfan` (7, nat.2), `rt/sgw-ret` slide-no-title (8, gwlbe.1): channel 후보를 만들었지만 F6이 남거나(merge-vfan) 새 tier-0가 생겨(sgw-ret: B2·F1 추가) 판정에서 떨어졌다.
- trunk 풀기는 저자 trunk만 있는 지금 spec 언어에서는 경고로만 쓰인다. 최종 corpus에서 그 경고가 나오는 run은 없다.
