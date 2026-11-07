# B2 check_layout 구현 검증

기준: main `88872ab`, 브랜치: `b2-check`, 2026-11-07. 공식 AWS 아이콘 캐시만 사용했다.

## 판정과 feedback

`check_layout.header_bands()`가 그룹 자신의 아이콘·제목·CIDR을 묶는다. `header_band()`는 왼쪽/위쪽 경계부터 marks의 오른쪽/아래쪽 끝까지의 상자이고, `segment_in_header()`는 기존 B2의 0.5px 경계 허용 및 뒤에 그린 mask를 적용한다. `lines_in_headers()`는 연결선 owner와 그룹마다 한 번 보고한다. `rules.border_rules()`와 check_layout이 이 공개 도우미를 함께 쓴다. LINE IN HEADER 메시지는 그룹, badge/title/CIDR 구간, band 좌표, 오른쪽/아래로 옮길 px를 포함한다. 기존 `line_hugs()`는 바꾸지 않았다.

기존 feedback으로 선택한 draft에 B2가 남을 때만 최대 5회를 더 시도한다. 첫 회는 해당 edge의 머리띠를 라우터 장애물로 지정하여 기존 bend/대체 경로를 다시 찾는다. 남는 문제는 기존 detour room과 같은 `Requirement(axis, group wall, contained end node, current distance + required shift)`로 공간을 연다. 세로 구간은 머리띠 오른쪽, 가로 구간은 머리띠 아래로 보내는 일반 제약이다. 후보는 자동 수정 이후 다른 check 코드별 수 및 (rule, code)별 위반 수가 증가하거나, 기존 ≥10pt 슬라이드가 <10pt가 되면 버린다. 기존에 최종 B2가 없었던 run은 기존 SVG를 그대로 보존한다.

## Corpus 전후

| check 코드 | main | branch |
|---|---:|---:|
| BADGE NEAR ICON | 6 | 6 |
| LINE HUGS BORDER | 0 | 0 |
| LINE IN HEADER | 미보고 (같은 판정으로 63) | 6 |
| LINE NEAR TEXT | 6 | 6 |
| LINE OFF CANVAS | 1 | 1 |
| LINE ON LINE | 5 | 5 |
| LINE OVER ICON | 4 | 4 |
| LINE OVER TEXT | 36 | 36 |
| OFF CANVAS | 46 | 46 |
| SERVICE AS TEXT | 12 | 12 |
| SLIDE TOO SMALL | 174 | 174 |
| TEXT NEAR ICON | 21 | 21 |
| TEXT OVERLAP | 17 | 17 |

표에 없는 check 코드는 모두 0→0이다. SLIDE TOO SMALL을 포함한 기존 코드 총합은 328→328이며, 새 LINE IN HEADER 6건은 기존 B2를 새 검사 코드로 노출한 것이다.

| 규칙/세부 코드 | main | branch |
|---|---:|---:|
| R-border B1 | 0 | 0 |
| R-border B2 | 63 | 6 |
| R-fit FIT | 174 | 174 |
| R-flow F1 | 5 | 5 |
| R-flow F3 | 12 | 12 |
| R-flow F4 | 8 | 8 |
| R-flow F5 | 5 | 5 |
| R-label L1 | 2 | 2 |
| R-rt RT1 | 67 | 67 |
| R-rt RT2 | 1 | 1 |
| R-rt RT4 | 26 | 26 |
| R-twin 전체 | 0 | 0 |

| 항목 | main | branch |
|---|---:|---:|
| 슬라이드 최소 pt 전체 최솟값 (기존 불량 입력 포함) | 3.62 | 3.62 |
| 슬라이드 <10pt run | 174 | 174 |
| 새로 <10pt가 된 run | — | 0 |
| t7-xyref slide 최소 pt | 11.84 | 11.84 |
| corpus | 246 항목 / 706 run | 246 항목 / 706 run |
| drawn / rejected / failures | 690 / 16 / 0 | 690 / 16 / 0 |
| 실행 시간 (초) | 35.42 | 47.34 |

B2는 63→6(90.5% 감소). 다른 규칙 위반 수는 동일하다. 바뀐 run 중 8개는 글자가 작아졌고 2개는 커졌다. 8개 감소 중 4개는 원래 <10pt인 r2-float-two-wide/r2-pin-bottom 양 모드이고, 나머지 r2-float-two 및 merge-vfan 양 모드는 ≥10pt를 지킨다. merge-vfan slide은 11.17→10.29pt이다. 여백을 고정 증분으로 넓히지 않고 판정에 필요한 이동량만 요구한다.

## 바뀐 draft 57개와 분류

경로는 `tests/corpus/` 기준이며 확장자는 `.layout.yaml`. `slide + slide-no-title`은 별개 draft 두 개이다. 연결선만 변경 29개, 노드/그룹 기하도 변경 28개. 57개 모두 main에서 B2가 있던 run이고 document draft 및 나머지 입력은 byte-identical이다.

| 분류 | 입력 | 모드 |
|---|---|---|
| 기하+연결선 | flowcol/base | slide + slide-no-title |
| 기하+연결선 | flowcol/r2-float-two-wide | slide + slide-no-title |
| 기하+연결선 | flowcol/r2-float-two | slide + slide-no-title |
| 기하+연결선 | flowcol/r2-pin-bottom | slide + slide-no-title |
| 기하+연결선 | flowcol/r3-xy-560 | slide + slide-no-title |
| 기하+연결선 | flowcol/r6-flowrow-and-col | slide + slide-no-title |
| 기하+연결선 | flowcol/r7-center-end | slide + slide-no-title |
| 기하+연결선 | flowcol/r7-center-first | slide + slide-no-title |
| 기하+연결선 | flowcol/t1-pinned | slide + slide-no-title |
| 기하+연결선 | flowcol/t4-one-center | slide + slide-no-title |
| 기하+연결선 | flowcol/t5-toplevel | slide + slide-no-title |
| 기하+연결선 | flowcol/t7-xyref | slide + slide-no-title |
| 기하+연결선 | flowcol/t8-two-cols | slide + slide-no-title |
| 기하+연결선 | trunk/merge-vfan | slide + slide-no-title |
| 연결선만 | flowcol/r4-center-one | slide-no-title |
| 연결선만 | flowcol/r5-mid-bottom | slide + slide-no-title |
| 연결선만 | flowcol/r5-mid-center | slide + slide-no-title |
| 연결선만 | flowcol/r5-mid-top | slide + slide-no-title |
| 연결선만 | flowcol/r6-flowrow-bottom | slide + slide-no-title |
| 연결선만 | flowcol/r7-bottom-first | slide + slide-no-title |
| 연결선만 | flowcol/r7-top-end | slide + slide-no-title |
| 연결선만 | flowcol/r7-top-first | slide + slide-no-title |
| 연결선만 | flowcol/t2-cloud-overlap | slide + slide-no-title |
| 연결선만 | flowcol/t3-group-only-stack | slide + slide-no-title |
| 연결선만 | flowcol/t4-nocw | slide + slide-no-title |
| 연결선만 | flowcol/t4-one-bottom | slide + slide-no-title |
| 연결선만 | flowcol/t4-one-top | slide + slide-no-title |
| 연결선만 | flowcol/t6-overlay | slide + slide-no-title |
| 연결선만 | flowcol/t6b-overlay | slide + slide-no-title |

상세 owner·canvas·pt 전후: [changed-drafts.json](../../artifacts/b2/changed-drafts.json).

## 남은 B2 6건

- `flowcol/r3-xy-30`: slide, slide-no-title. 기존 그림 그대로. routing 후보가 머리띠를 피하면 App subnet 테두리에 붙는다. 머리띠 오른쪽의 공간을 요구하면 Region이 고정 좌표 KMS까지 넓어져 TEXT AT BORDER / LINE OVER ICON을 만든다. 보호 조건이 이 후보를 버린다. KMS 좌표 또는 regional service 배치까지 함께 풀어야 한다.
- `twin/sub`, `twin/three`: 각각 slide, slide-no-title. 기존 그림 그대로. 긴 ASG overlay 제목이 ALB→ea 경로를 막는다. 현재 라우터의 대체 후보로는 깨끗한 경로를 찾지 못했고, `header_room()`은 부모 체인의 포함 관계로 끝 노드를 찾으므로 `over:` 멤버십의 ASG에는 요구 제약을 만들지 못한다. skip 후보를 끝까지 시도하고 기존 B2를 보고한다. overlay 멤버십을 반영한 공간 제약 또는 추가 경로 탐색이 남았다.

## PNG 직접 확인

CairoSVG, 공식 AWS bundle 인라인, 1600px 폭으로 다음을 렌더하고 확인했다.

| 입력 | PNG | 직접 확인 |
|---|---|---|
| t7-xyref slide | [PNG](../../artifacts/b2/png/flowcol__t7-xyref.layout.yaml.slide.png) | 제목 오른쪽으로 ALB→AZ2 EC2 세로 구간 이동, 11.84pt 유지. 기존 KMS/Users 겹침 2개는 그대로 보고 |
| r5-mid-bottom slide | [PNG](../../artifacts/b2/png/flowcol__r5-mid-bottom.layout.yaml.slide.png) | EC2 오른쪽으로 진입, 직각·독립 포트·머리띠/테두리 여유, 12.21pt 유지 |
| t6-overlay slide | [PNG](../../artifacts/b2/png/flowcol__t6-overlay.layout.yaml.slide.png) | canvas 그대로 우회, 텍스트·아이콘 겹침 없음, 12.21pt 유지 |
| merge-vfan slide-no-title | [PNG](../../artifacts/b2/png/trunk__merge-vfan.layout.yaml.slide-no-title.png) | B2 제거, 11.53pt. 기존 S3→EC2/NAT LINE OVER ICON 1개는 유지 |
| r3-xy-30 slide | [PNG](../../artifacts/b2/png/flowcol__r3-xy-30.layout.yaml.slide.png) | 고정 KMS와 남은 App subnet B2 확인 |
| twin/sub slide | [PNG](../../artifacts/b2/png/twin__sub.layout.yaml.slide.png) | 긴 ASG 제목과 남은 B2 확인, 기존 9.3pt도 유지 |

완료한 수정 구간은 직각이고 새로운 선 겹침·테두리 붙음·텍스트/아이콘 충돌을 만들지 않았다. 기존 문제가 있는 전체 corpus 그림까지 사용자 규칙을 모두 충족했다고 주장하지 않는다.

## 검증과 재사용 자료

- pytest: 589 passed, 2090 subtests passed (최종 실행은 artifacts/b2/pytest.log).
- test_examples: 15 specs, 15 all PASS, 0 FAIL, 0 SKIP. yaml/orig/layout/check/export/struct 6항목씩 90개 PASS (SVG·PNG·PPTX export 및 반복 layout 포함) (artifacts/b2/examples.log).
- 결정성: branch를 두 번 실행하여 시간 필드 외 706 run 레코드 동일, 690 drawn SVG 모두 byte-identical. 두 번째 실행 38.64초.
- [main corpus JSON](../../artifacts/b2/main-corpus.json), [branch corpus JSON](../../artifacts/b2/branch-corpus.json), [branch repeat JSON](../../artifacts/b2/branch-repeat-corpus.json).
- main/branch SVG: artifacts/b2/main-drafts/, artifacts/b2/branch-drafts/. JSON과 PNG는 review 재사용을 위해 worktree에 남겼으며 커밋에는 코드·테스트·문서만 포함한다.

패키지는 `uv run --offline --no-project --with pyyaml --with python-pptx --with cairosvg` 및 pytest만 캐시에서 사용했다. main은 `git archive 88872ab`와 복사한 icons.json으로 한 번 실행했다. sandbox가 Python 3.15 기본 forkserver의 Unix socket 생성을 막아 corpus는 아래처럼 fork 시작 방법만 바꿨다. worker 수·runner·checker는 요청대로이다.

```bash
export TMPDIR=$HOME/.cache/codex-b2-tmp
uv run --offline --no-project --with pyyaml --with python-pptx --with cairosvg python3 -c 'import multiprocessing as mp, runpy; mp.set_start_method("fork"); runpy.run_path("tests/run_corpus.py", run_name="__main__")' --rule-checker scripts/rules.py:corpus --keep <dir> --out <json> -q -j 6
```
