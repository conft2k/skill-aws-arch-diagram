# Ticket 07: R-twin·R-label 선택 검증

기준은 main `6e3fb7a`의 `~/.cache/skill-design/baseline/main-6e3fb7a.json`과 `main-6e3fb7a-drafts/`이다(엔진은 시작점 91062e1과 같다). 기준과 최종 실행 모두 `-j 6`이다. 최종 전체 corpus는 한 번 실행했고, 실행 동안 pytest·렌더를 겹치지 않았다. 독립 리뷰(Codex)는 이 문서 뒤에 별도로 한다.

## 완료 조건

- [x] Verdict의 tier-0 부분이 모든 tier-0 규칙을 센다. `scripts/layout.py`의 `RULE_GROUPS`가 세 그룹(R-border·R-flow / R-rt / R-twin·R-label)을 두고, `SELECTION_RULES`는 그 합집합이다. 규칙 predicate·threshold·메시지 코드는 바꾸지 않았다.
- [x] Corpus 악화 **0**, 이전 그룹(R-border·R-flow·R-rt) 증가 0, check 문제 **379→373**. 이 그룹의 bad 태그 사례 합계는 **2→0**이다. 태그는 아래 표대로 bad에서 good으로 옮겼다.
- [x] Ticket 04 시간 제한 통과: run 최대 비율 **2.317×**(twin/ce-a document 0.618→1.432초), 최악 run **17.83초**, corpus wall **110.19→111.86초(1.015×)**. 3× 초과 0, 30초 초과 0.
- [x] 기존 gate 유지: 새 tier-0 identity gate, ticket 10의 글자 축소 gate, canvas clipping 우선. 6e3fb7a와 36c7ea3 대비 새 tier-0 identity run은 모두 **0건**이다.

## 구현

- **R-label:** 기존 edge 이웃이 그대로 적용된다. L1 위반이면 그 edge의, L2 위반이면 badge edge 각각의 다음 routing alternative를 건너뛴다.
- **R-twin:** `twin_copy`는 한 twin의 결정을 다른 twin에 복사한다. 순서는 먼저 이름이 나온 twin에서 다른 쪽으로, 그다음 반대 방향이다. 복사하는 결정은 세 가지다.
  - 대각선 쌍의 축
  - overlay 제목 위치
  - 대응하는 edge의 skip
  - 대응 관계는 `layout_solve.twin_maps`가 정한다. 이 함수는 `twin_sets`의 상자·노드·overlay 순서를 쓰며, twin_classes와 같은 정의다. `xy` 노드, `header:` overlay, 고정 경로는 바꾸지 않는다.
- **Header 텍스트 충돌:** `header_flips`는 overlay 제목을 beside에서 above로, 또는 그 반대로 뒤집는다. spec에 `header:`가 없는 overlay만 대상이다. 다음 중 하나가 그 overlay를 owner로 이름 대면 충돌로 본다.
  - 보유 그림의 check 문제: TEXT NEAR ICON, TEXT OVERLAP, LINE IN HEADER, LINE OVER TEXT, LINE NEAR TEXT
  - R-border 위반
  - 이 이동은 그룹 3을 켰을 때만 만든다. Summary는 `overlay <id> header <place>`로 이 결정을 보여 준다.
- **이전 그룹 승자 보존:** R-rt에만 있던 보존을 일반화했다. default에 그룹 k(k ≥ 1)의 위반이 있으면, 먼저 그 앞 그룹들로 탐색한 승자를 incumbent로 잡는다. 모든 탐색은 같은 12/16 예산을 나눠 쓴다. spec의 "Enabling rules by group"에 그룹 3을 추가했다.
- **Red → green:** `tests/test_select.py`에 5개 테스트를 더했다.
  - 모든 tier-0 규칙 count/cost
  - bedrock-dx slide의 L1 제거와 결정성
  - twin/three slide의 overlay header 뒤집기
  - `header:` 고정 overlay를 뒤집지 않음
  - 그룹 3을 켜도 이전 그룹 수가 늘지 않음
  - main 91062e1 사본에서 4 failed / 1 passed(`red.log`)였다. 통과한 1개는 고정 overlay 보호 테스트로, 원래 main에서도 통과한다. 이 브랜치에서는 5 passed(`green.log`)다.

## 최종 corpus

268 entries, 763 runs(새 사례 3 runs 포함). drawn 747 / rejected 16, 태그 불일치 **0**.

| 항목 | 기준 6e3fb7a | 최종 | 증감 |
|---|---:|---:|---:|
| R-border | 17 | 15 | -2 |
| R-flow | 46 | 46 | +0 |
| R-rt | 90 | 90 | +0 |
| R-twin | 6 | 6 | +0 |
| R-label | 2 | 0 | -2 |
| R-fit | 298 | 298 | +0 |
| Check 문제 전체 | 379 | 373 | -6 |
| LINE IN HEADER | 15 | 13 | -2 |
| LINE OVER TEXT | 67 | 65 | -2 |
| SERVICE AS TEXT | 12 | 10 | -2 |

비교 결과: 760 runs **better 8 / same 752 / worse 0 / unjudged 0**. 새 사례 3 runs는 기준에 없어서 uncompared다. 바뀐 Draft 8개는 모두 better이다. 다른 check 코드의 증감은 모두 0이다.

## 이 그룹의 bad 태그 사례

기준에서 bad 태그가 붙은 R-label 사례는 하나다. R-twin bad 태그 사례는 없다.
- `qa/t1-multiregion-dr`의 TW 6건에는 태그가 없다. 이 위반은 선택 결정이 아니라 solve 제약에서 나온다. 엔진도 "other constraints keep them apart"라고 경고한다. 그래서 이번에도 그대로 남는다. twin copy 이동 2개를 평가했지만 초안은 같았다.

| Case | 태그 mode | 전 → 후 | 합계 전 → 후 | 판정과 이유 |
|---|---|---|---|---|
| `docs/examples/specs/bedrock-dx-reference-architecture.layout.yaml` | S / N | 1→0 / 1→0 | 2→0 | good: 선택이 edge:2의 다음 routing alternative를 고른다(`skip edges[2]=1; note place=pane`). 'DNS :53'이 자기 선의 수평 구간 위에 놓여 L1이 없어진다. document에는 원래 L1이 없다. MANIFEST를 `good: [R-flow, R-label]`로 고쳤다 |

**합계 2→0**.

## 새 corpus 사례: AZ 행 반전

`tests/corpus/qa/timing-mirrored-az-rows.layout.yaml`은 시간 측정용 그림을 줄인 최소 재현이다. 원본 spec은 노드 18, 엣지 16이고 축소본은 노드 4, 엣지 0이다. 원본 경로는 spec 머리 주석에 있다.
- 원본 그림에서 Inspection VPC의 두 AZ는 좌우가 아니라 **위아래로** 뒤집혀 있다. AZ 1은 Public 행이 위, Appliance 행이 아래이고 AZ 2는 그 반대다. 원본 spec의 rows `[a1, a2, main, b1, b2]`가 이렇게 배치하고, 엔진은 쓰인 대로 그린다.
- main 91062e1 사본에서 판정한 결과, **R-twin은 이 사례를 보고하지 않는다**. 세 mode 모두 violation이 0이다. 그래서 bad 태그 없이 `rules: [R-twin]`과 `# rules.py 미검출` 주석을 붙여 넣었다. 규칙은 다시 정의하지 않았다.
- 보고하지 않는 이유: `twin_classes`가 두 AZ를 twin으로 보지 않는다. 다음 두 조건이 모두 걸린다.
  - AZ 제목이 다르다(Availability Zone 1 / 2). `_shape`는 `TWIN_NAMED`(vpc, account, region, onprem, cloud)에 있는 타입의 root 제목만 무시하는데, az는 여기에 없다.
  - AZ 안의 행 순위가 다르다. Public이 AZ 1에서는 0번, AZ 2에서는 1번이다.
  - 변형 spec으로 확인했다. 제목만 같게 하거나 행 순서만 바로잡으면 twin이 아니고, 둘 다 바꿔야 twin이 된다.
- 덧붙여, 제목이 1/2로 다른 한 VPC 안의 두 AZ는 행 순서가 같아도 twin이 아니다. `references/layout_spec.md`의 "AZ 1 and AZ 2 of one VPC under one ASG do not [twin]"은 ASG가 없으면 twin이 된다고 읽히는데, 실제 동작은 다르다. 이번 범위 밖이므로 백로그로 남긴다.
- 선택은 이 그림을 바꾸지 않는다. 위반이 없으므로 default를 유지한다. PNG: `png/case/mirrored.png`.

## 바뀐 Draft와 이유

| Case | Mode | Tier-0 전→후 | Check 전→후 | 글자 전→후 | 이유 |
|---|---|---:|---:|---|---|
| `sides/ov3` | document | 0→0 | 1→1 | 14→14px | header flip `overlay asg header above`, canvas area 247104→225792 |
| `sides/ov3` | slide | 0→0 | 1→1 | 13.40→13.07pt | header flip `overlay asg header above`, area 169200→147492. 목표 10pt 이상이라 verdict를 따른다 |
| `sides/ov3` | slide-no-title | 0→0 | 1→1 | 15.01→14.64pt | 위와 같다 |
| `twin/three` | slide | 1→0 | 4→1 | 9.703→9.505pt | `overlay asg header beside`: ALB→EC2 선이 ASG 제목 band를 지나던 R-border B2가 없어진다. 같은 원인의 LINE IN HEADER, LINE OVER TEXT, SERVICE AS TEXT도 함께 없어진다. 축소율 2.0%는 후보 선택의 고정 90% 한도 안이고, tier-0도 줄었다 |
| `twin/three` | slide-no-title | 1→0 | 4→1 | 9.703→9.505pt | 위와 같다 |
| `twin/ce-a` | document | 0→0 | 1→1 | 4.733→5.069px | `overlay asga header above; note place=panel`: R-fit shortfall 6.267→5.931 |
| bedrock-dx | slide | 1→0 | 1→1 | 4.918→4.918pt | `skip edges[2]=1; note place=pane`: L1 제거, shape miss 0→1 |
| bedrock-dx | slide-no-title | 1→0 | 1→1 | 5.508→5.508pt | 위와 같다 |

`twin/three`의 두 slide는 tier-0가 우선이라는 verdict 결정에 따라 better다. 다만 R-fit shortfall이 0.297에서 0.495로 늘었다. bedrock-dx는 L1을 없애는 대신 shape miss가 하나 늘었다. 이것도 verdict 순서상 tier-0가 먼저다.

## PNG 직접 판정

기준과 최종 SVG를 공식 아이콘을 넣어 export했다. 아래 짝 그림(왼쪽 기준, 오른쪽 최종)은 이미지 보기 도구로 직접 확인했다. 새 차단 결함은 보이지 않았다.

- `png/twin__three_layout_yaml_slide-pair.png`: ASG 제목이 첫 member 행 옆으로 가서, ALB→AZ C EC2 선이 더 이상 제목을 지나지 않는다. 세 AZ는 똑같이 그려진다.
- `png/up__up__docs__examples__specs__bedrock-dx-reference-architecture_layout_yaml_slide-pair.png`: PC→사내 DNS 선이 왼쪽으로 돌아 DNS 위로 들어간다. 'DNS :53'은 그 수평 구간 위에 있어 자기 선으로 읽힌다. 우회가 조금 길어졌고, 작은 글자(R-fit)는 그대로다.
- `png/sides__ov3_layout_yaml_document-pair.png`, `png/sides__ov3_layout_yaml_slide-pair.png`: ASG 제목이 member 위로 가서 그림이 좁아진다. Monitor→ASG 흐름은 같다. AZ 2 제목을 지나는 기존 overlay 테두리(LINE OVER TEXT)는 남는다.
- `png/twin__ce-a_layout_yaml_document-pair.png`: 노트가 panel로 가고 글자가 커진다. 흐름과 RT 위치는 같다.

## 시간

| 항목 | 기준 6e3fb7a | 최종 |
|---|---:|---:|
| Corpus wall (s) | 110.19 | 111.86 |
| 합계 (s) | 631.98 | 641.50 |
| 최악 run (s) | 17.181 | 17.828 |

- 6e3fb7a 대비 run 최대 비율은 `twin/ce-a` document의 **2.317×**(0.618→1.432초)다. 다음은 `sides/ov3`의 세 mode로, 1.55–1.58×(0.08→0.13초)다.
- 36c7ea3 대비로도 최대는 2.751×(`bench/engine2-egress` slide-no-title, 이전 ticket의 값)이고, wall은 0.887×다.
- 3×·30초 초과는 두 기준 모두 0이다.

재현 명령(worktree 루트에서):

```bash
uv run --offline --no-project --with pyyaml --with cairosvg python3 tests/run_corpus.py \
  --rule-checker scripts/rules.py:corpus -q -j 6 \
  --baseline ~/.cache/skill-design/baseline/main-6e3fb7a.json \
  --baseline-drafts ~/.cache/skill-design/baseline/main-6e3fb7a-drafts \
  --keep ~/.cache/skill-design/improve/t07/drafts --out ~/.cache/skill-design/improve/t07/corpus.json
```

## 테스트

- 전체 pytest: **877 passed, 1 xfailed, 2573 subtests passed**, 238.64초 (`pytest.log`). `tests/test_examples.py`(예제 golden·결정성)가 포함된다. Xfail은 기존 gw-ret 노트 배경 가림이다. Golden은 바꾸지 않았다.

## 증거 파일

`~/.cache/skill-design/improve/t07/`:
- `corpus.json`, `corpus.log`, `corpus.start`, `corpus.end`, `drafts/`, `summary.txt`
- `red.log`, `green.log`, `pytest.log`
- `png/`
- `prelim/`: header flip summary 표기를 넣기 전의 예비 실행. Draft와 판정은 최종과 같다.

## 남은 것 (백로그)

- multiregion-dr의 TW 6건은 solve 제약에서 나온다. 결정을 복사해서는 없앨 수 없다.
- AZ 제목이 다른 두 AZ를 twin으로 보지 않는 동작과 layout_spec.md 문장이 맞지 않는다. 새 사례가 이것을 기록한다.
- corpus의 R-twin 위반 중 twin copy로 줄어든 것은 없다. 이동은 구현했고 평가도 했지만, 효과는 아직 corpus에서 보이지 않았다.
