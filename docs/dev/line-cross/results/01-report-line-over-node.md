# Ticket 01: 노드 위를 지나는 선을 tier-0 R-flow 위반(F6)으로 보고

기준은 main `601099d`의 `~/.cache/skill-design/baseline/main-601099d.json`과 `main-601099d-drafts/`이다(브랜치 시작점 eb86fe3는 그 뒤 문서 커밋만 있다). 기준과 최종 실행 모두 `-j 6`이다. 최종 corpus는 한 번 실행했고, 그동안 pytest·렌더를 겹치지 않았다. 독립 리뷰(Codex)는 이 문서 뒤에 별도로 한다.

기준 json에는 F6이 없다. 그래서 공정하게 비교하려고 **기준 draft를 이 브랜치의 F6으로 다시 판정한 기준**(`main-601099d-rejudged-f6.json`)을 만들어 `run_corpus.compare_reports`로 다시 비교했다. 아래 "전/후"는 모두 이 재판정 기준 대비다.

## 완료 조건

- [x] 새 코드 **F6**이 rule checker에 있다. R-flow, tier 0, owners `(edge:n, node:x)`, 메시지는 표시 이름(label)을 쓰고 `try:` 값을 붙인다. GLOSSARY(Line over node, Attach piece)와 rules-design(§1 R-flow F6, §6 사용자 결정)에 적었다.
- [x] Corpus 태그: dns-trunk·nat-route-table·privatelink·ssm-trunk의 slide 두 mode, three-az-writer 세 mode가 `bad: {R-flow: node:…}`다. 각각 crossing을 없앤 good 짝(`qa/lc-*-clear`)이 있고, 자기 끝 icon에 붙는 곳에서만 닿는 good 사례(`qa/lc-own-end-touch`)가 있다. 태그 불일치 **0**.
- [ ] 기준 대비 악화 0, 새 tier-0 identity 0(F6이 기존 crossing을 새로 보고하는 것 제외). **두 건이 남는다**: `trunk/v-fork` slide 악화 1건, `qa/t4-three-az-writer` slide-no-title의 새 F5 identity 1건. 아래 "의도하지 않은 변화"에 원인을 적었다. crossing이 없는 draft는 `rt/gw-ret` slide 두 mode를 빼고 모두 byte-identical이다(그 둘은 verdict상 better).
- [x] 시간: run 최대 비율 **1.647×**, 최악 run **18.16초**, wall **1.008×**. 3×·30초 초과 0.
- [x] 아래 표가 bad 태그 사례마다 선택 전/후 crossing 수와 남은 이유를 적는다.
- [ ] Codex review: 이 문서 뒤에 한다.

## 구현

- **규칙(`scripts/rules.py` `_over_nodes`):** 각 spec edge instance의 drawn piece가 노드 icon box(2px 줄임)나 이름 줄(`node_stacks`: label과 sub 줄, 1px 줄임)에 닿으면 위반이다. 상자와 mask 처리는 check_layout의 LINE OVER ICON / LINE OVER TEXT와 같다. (edge, node) 쌍마다 하나, cost 1이다.
- **자기 끝 면제:** edge의 spec 끝 노드 x에 대해, 끝점이 x의 footprint에서 END_REACH 안에 있는 첫/마지막 piece(attach piece)만 x의 icon에서 면제된다. 그것도 줄인 icon 안으로 `ATTACH_DEPTH` 이하만 들어갈 때다. x의 이름 줄은 면제되지 않는다.
- **세지 않는 것:** group 제목과 CIDR 줄은 node 그룹의 글이 아니다(B2). edge label과 badge 숫자는 `edge:n:label`/`edge:n:badge` 그룹이다(F5, R-label). 그래서 F6에 들어오지 않는다.
- **`try:` 값(`_over_try`):** 지나는 piece를 crossing 노드의 footprint 가까운 쪽에서 ICON_CLEAR(8px) 밖으로 옮기는 값을 그 piece를 쥔 필드로 준다.
  - `points` 선: `points: move the vertical piece at x=… to x=…`
  - 노드 면에 붙는 끝 piece이고 값이 그 면 안에 있으면 `from_offset`/`to_offset`
  - 그 밖은 `bend_x`/`bend_y`
  - 끝 piece가 자기 노드 면 안에서 비킬 수 없으면 routing 필드와 crossing 노드의 `dx`/`dy`(flow column이면 dy는 주지 않는다)
- **선택:** 새 선택 코드는 없다. F6은 R-flow라서 `neighbours`의 일반 edge 분기(다음 routing alternative), `wanted`, `hard_placement_warnings`, tier-0 점수에 그대로 들어간다. `layout_route.skippable`이 손으로 둔 edge를 제외한다.
- **경고 문구(`scripts/layout.py` `unfixable_warnings`):** `check_kind`에 `F6: (LINE OVER ICON, LINE OVER TEXT)`를 넣었다. F6의 spec hint는 규칙의 `try:` 값을 먼저 주고, 그 뒤에 맞는 check 문제의 기존 spec_fix 힌트를 붙인다.
  - 예: `edges[0] shape / from_side / to_side (…), or nodes[1] rt rt.1: dy: 32; nodes[1] rt rt.1: dx / dy; …`
- LINE OVER ICON / LINE OVER TEXT check는 바꾸지 않았다.

## Attach 허용치

main 601099d의 corpus 전체 draft(759 drawn)에서, 자기 끝 노드에 붙는 piece 11,027개가 줄인 icon 안으로 들어간 길이를 쟀다.
- 0px: **11,025개**
- 44px: **2개**. privatelink slide·slide-no-title의 edge:12가 자기 끝 S3를 세로로 관통하는 경우다.
- 그래서 0–43px 사이 어떤 값이든 corpus 판정은 같다. `ATTACH_DEPTH = 4px`(LINE_CLEAR)로 정했다.
  - 손으로 둔 `points` 끝이 icon 가장자리에서 몇 px 들어가는 것은 허용한다.
  - icon 가운데(22px 이상)까지 그린 선은 잡는다.
  - 단위 테스트가 4px(통과)와 22px(위반)을 둘 다 확인한다.
- 측정 스크립트: `judge_drafts.py`. 결과: `baseline-f6.txt`.

## Bad 태그 사례: 선택 전/후 crossing

"전"은 main 601099d 최종 draft를 F6으로 판정한 수, "후"는 이 브랜치의 최종 draft다.

| Case | Mode | 전 → 후 | 남은 F6 (edge, node) | 남은 이유 |
|---|---|---:|---|---|
| `qa/t3-dns-trunk` | slide | 2 → 2 | (2, inbound.1), (3, inbound.2) | trunk `outbound.* ..> vgw`. follower는 skip 대상이 아니다. lead의 후보도 모두 crossing이 있어 clean alternative가 없다(`best of the candidates`). 후보 1개를 평가했지만 default가 남았다 |
| | slide-no-title | 2 → 2 | 같음 | 같음 |
| | document | 0 → 0 | | |
| `qa/t3-nat-route-table` | slide | 2 → 2 | (0, rt.1), (1, rt.2) | trunk `nat.* -> igw`. RT가 NAT와 IGW 사이 같은 행에 있어 clean 후보가 없다. 후보 0개 |
| | slide-no-title | 2 → 2 | 같음 | 같음 |
| `qa/t4-three-az-writer` | document | 5 → 5 | (1, db.2), (1, ep.2), (2, db.2), (2, db.3), (2, ep.3) | trunk `orders.* -> db.1`. follower 1·2가 다른 AZ의 Endpoint·reader 행을 지난다. clean 후보가 없다. 후보 0개 |
| | slide | 5 → 5 | 같음 | 같음 |
| | slide-no-title | 6 → 5 | 위 5개 | (0, ep.1)이 없어졌다. 후보 선택이 아니라 이후 단계(verdict로 고르는 feedback round)가 orders.1 선을 UVHV로 돌렸다. 나머지 5개는 위와 같은 이유로 남는다 |
| `qa/t1-privatelink` | slide | 2 → 2 | (12, s3a), (12, s3) | 손으로 둔 선(`shape: VHV, from_side, to_side, bend_y`). 다시 routing하지 않는다. `hard placement edge:12 … keeps R-flow F6` 경고가 나온다 |
| | slide-no-title | 2 → 2 | 같음 | 같음 |
| `qa/t3-ssm-trunk` | slide | 1 → 1 | (4, ssm) | trunk follower가 줄기에 붙으며 자기 끝 Session Manager의 이름 위를 지난다. follower는 skip 대상이 아니다(ticket 02 trunk 풀기) |
| | slide-no-title | 1 → 1 | 같음 | 같음 |

**bad 태그 사례 합계 30 → 29**다. 기존 이동만으로는 거의 줄지 않는다. 원인은 둘이다.
- router의 routing alternative는 *clean* 후보만 담는다. crossing이 남는 선에는 처음부터 clean 후보가 없다.
- trunk follower와 손으로 둔 edge는 skip 대상이 아니다.

남은 29건은 trunk 25건(dns 4, nat 4, three-az 15, ssm 2)과 손으로 둔 선 4건(privatelink)이다. ticket 02의 두 이동(trunk 풀기, 통로 넓히기)이 trunk 25건의 대상이다. 손으로 둔 4건은 `try:` 값으로만 안내한다.

## 의도한 새 보고

main에도 있던 crossing을 F6이 새로 보고하는 run이다. 모두 main 기준에서 같은 선의 LINE OVER ICON/TEXT check 문제가 이미 있었다. 이 run들은 태그가 없다.

| Case | Mode | F6 (edge, node) | 내용 |
|---|---|---|---|
| `bench/latest2-pipeline` | slide, slide-no-title | (24, sm) | trunk 선이 자기 끝 Secrets Manager의 이름을 지난다 |
| `trunk/merge-vfan` | document, slide, slide-no-title | (7, nat.2) | S3 → EC2 선이 NAT icon을 지난다 |
| `rt/sgw-ret` | slide-no-title | (8, gwlbe.1) | EC2 → Users 선이 GWLBe icon을 지난다 |
| `trunk/v-fork` | document, slide, slide-no-title | (9, rtfw) | TGW → ENI fork가 Firewall RT의 이름 줄을 지난다 |
| bad 태그 5개 사례 | 위 표 | | |

F6 전체는 **39 → 38**(20 run)이다. 기준 json 대비 runner의 "worse 20"은 모두 이 tier-0 증가 때문이다. 재판정 기준 대비로는 worse가 1건이다(아래).

## 최종 corpus

278 entries, 793 runs(새 사례 6개 18 runs 포함). drawn 777 / rejected 16, 태그 불일치 **0**.

재판정 기준 대비 결과: **better 3 / same 771 / worse 1 / uncompared 18 / unjudged 0**. 바뀐 draft는 4개다. 재실행 draft는 첫 실행과 byte-identical이었다(결정성).

| 항목 | 재판정 기준 | 최종 | 증감 |
|---|---:|---:|---:|
| R-flow (F6 포함, 기존 runs) | 85 | 84 | -1 |
| 그 밖의 규칙 | | | 0 |
| Check 문제 전체 | 371 | 371 | +0 |
| LINE OVER ICON | 32 | 31 | -1 |
| LINE OVER TEXT | 65 | 66 | +1 |
| TEXT AT BORDER | 1 | 2 | +1 |
| TEXT OVERLAP | 27 | 26 | -1 |

새 사례(18 runs)의 위반은 0이고, R-fit(three-az-writer-clear의 slide 두 mode)만 있다.

### 바뀐 draft

| Case | Mode | 판정 | Verdict 전 → 후 | 이유 |
|---|---|---|---|---|
| `rt/gw-ret` | slide | better | shape miss 3→2, shortfall 2.351→2.082pt, 면적 874734→834086 | main 최종 draft에는 crossing이 없다. 다만 선택 중 default draft에 F6 (8, gwlbe.1)·(9, gwlbe.2)가 있었다. 그래서 첫 이동이 `skip edges[2]=1`에서 `skip edges[8]=1; diagonal pairs …`로 바뀌었고, crossing 없는 더 나은 그림을 고른다 |
| `rt/gw-ret` | slide-no-title | better | shape miss 3→2, shortfall 1.433→1.132pt | 위와 같다 |
| `qa/t4-three-az-writer` | slide-no-title | better(tier-0 10→9) | shortfall 0.634→2.552pt, shape miss 0→1 | F6 (0, ep.1)을 없앤 feedback round를 tier-0 감소로 받아들였다. 글자 9.37→7.45pt 축소도 tier-0 엄격 감소라서 gate가 허용한다 |
| `trunk/v-fork` | slide | **worse** | shortfall 3.935→4.349pt, shape miss 1→2, 면적 2143665→1781496 | 아래 참고 |

### 의도하지 않은 변화 (미해결 2건)

1. **`trunk/v-fork` slide 악화.**
   - 고르는 후보는 main과 같다(`note place=pane`).
   - 그런데 그 승자에 main에도 있던 F6 (9, rtfw)가 붙는다. 그래서 step 2의 "rule-clean 승자만 gentle text scale을 시도한다"(`render_readable`의 `gentle` 조건, step2 spec 58행)가 더는 적용되지 않는다.
   - main의 14px 확대가 빠지고 12px로 남는다. tier-0는 같고 글자·shape miss만 나빠진다.
   - 고치는 길은 둘이다. (a) gentle 조건을 "tier-0 위반이 없다"에서 "보유 그림보다 tier-0가 늘지 않는다"로 바꾼다. (b) ticket 02가 이 crossing을 없애기를 기다린다.
   - 선택 코드 변경이 필요해 이 ticket 범위 밖이다. 판단을 요청한다.
2. **`qa/t4-three-az-writer` slide-no-title의 새 F5 identity.**
   - 같은 label 'PostgreSQL :5432'(edge:1)의 F5가 (edge:1, edge:2)에서 (edge:1, edge:0)으로 바뀌었다. orders.1 선이 UVHV로 돌아 그 label 옆을 지나기 때문이다.
   - 엔진 gate는 tier-0 합계가 10→9로 줄어서 허용한다. 하지만 "새 tier-0 identity 0" 기준으로는 1건이다.
   - 같은 변화로 slide 글자가 8pt 하한 아래(7.45pt)로 내려간다. ticket 10의 multiregion-dr 예외와 같은 종류(tier-0 엄격 감소로 축소 허용)다.

## 시간

| 항목 | 기준 601099d | 최종 |
|---|---:|---:|
| Corpus wall (s) | 113.60 | 114.55 |
| 합계 (s) | 653.42 | 658.67 |
| 최악 run (s) | 17.817 | 18.161 (`qa/t1-multiregion-dr` slide-no-title) |

- run 최대 비율은 `sides/t2` slide-no-title의 **1.647×**(0.017→0.028초)다.
- 0.5초 이상 run 중 최대는 `bench/latest2-pipeline` slide의 1.447×(4.786→6.924초)다.
- 3×·30초 초과는 0이다.

## 테스트

- `tests/test_rules.py` `LineOverNode` 7개:
  - 다른 노드 icon(표시 이름, `try:`)
  - 다른 노드의 이름과 sub 줄
  - 자기 끝 icon에 붙는 곳에서만 닿음(ATTACH_DEPTH 안은 통과, 가운데까지는 위반)
  - 자기 끝 icon을 붙는 곳 밖에서 관통
  - 자기 끝의 이름 위
  - group 제목·CIDR·edge label·badge는 세지 않음
  - `points`/`bend_x` 선의 `try:` 값
- `tests/test_unfixable_warnings.py`: ssm-trunk slide(F6, `edges[2] bend_x: `)와 nat-route-table slide(F6, `rt.1: dy: `) 두 사례를 추가했다.
- 전체 pytest(`uv run --with pyyaml --with pytest --with cairosvg --with python-pptx --with lxml python -m pytest -q`): **899 passed, 1 xfailed, 2581 subtests passed**, 243.30초(`final/pytest.log`). `tests/test_examples.py`(예제 golden·결정성)와 `tests/fixtures/examples-91062e1/`에 고정한 모듈 테스트를 포함한다. golden은 바꾸지 않았다.

## 재현

worktree 루트에서:

```bash
uv run --with pyyaml python tests/run_corpus.py --rule-checker scripts/rules.py:corpus -q -j 6 \
  --baseline ~/.cache/skill-design/baseline/main-601099d.json \
  --baseline-drafts ~/.cache/skill-design/baseline/main-601099d-drafts \
  --keep ~/.cache/skill-design/improve/line-cross/t01/final/drafts \
  --out ~/.cache/skill-design/improve/line-cross/t01/final/corpus.json
uv run --with pyyaml python ~/.cache/skill-design/improve/line-cross/t01/rejudge.py \
  ~/.cache/skill-design/baseline/main-601099d.json ~/.cache/skill-design/baseline/main-601099d-drafts \
  ~/.cache/skill-design/improve/line-cross/t01/final/corpus.json ~/.cache/skill-design/improve/line-cross/t01/final/drafts \
  ~/.cache/skill-design/improve/line-cross/t01/main-601099d-rejudged-f6.json
```

## 증거 파일

`~/.cache/skill-design/improve/line-cross/t01/`:
- `final/`: `corpus.json`, `corpus.log`, `drafts/`, `rejudged-compare.txt`, `times.txt`, `pytest.log`
- `run1/`: 같은 코드의 첫 실행. draft는 final과 같다
- `main-601099d-rejudged-f6.json`: F6으로 재판정한 기준
- `baseline-f6.txt`: 기준 draft의 F6 목록과 attach 깊이 분포
- `judge_drafts.py`, `rejudge.py`, `times.py`, `trace*.py`, `nof6.py`: 측정·추적 스크립트

## 남은 것

- ticket 02: trunk 풀기와 통로 넓히기로 위 29건을 줄인다.
- 위 미해결 2건에 대한 판단(gentle text scale 조건, three-az-writer의 F5 identity 교체).
- `rt/gw-ret`의 노트 본문 위 LINE OVER TEXT는 노드 이름이 아니라서 F6 대상이 아니다. check로만 남는다.
