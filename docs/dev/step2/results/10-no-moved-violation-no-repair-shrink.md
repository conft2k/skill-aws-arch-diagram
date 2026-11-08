# Ticket 10: 수정 1회 — 후속 글자 보존과 실행 시간

2026-11-08, 코드 작성 세션. **미완료**: 리뷰 차단 2건의 코드와 시간 조건은 해결했지만, 단일 전체 corpus의 R-flow가 **51 > 50**이고 clean 대비 12건이 worse다. 공유 Git 메타데이터도 read-only여서 실제 `t10-gate` 브랜치 반영은 차단되어 있다. 독립 리뷰는 별도 세션에서 한다.

## 결정과 구현

Identity는 `(rule, code, frozenset(owners))`다. 새 tier-0 identity가 있으면 전체 tier-0 개수가 엄격히 줄어야 한다. 좌표·owner 순서는 identity가 아니며, 활성 탐색 그룹 밖의 규칙도 검사한다. Verdict 순서는 그대로다.

`RuleGuard.preserves_text`와 `admits`는 후보 안의 feedback, header, fixed-answer, text-scale에도 보유 그림의 1% 보존 규칙을 적용한다. `candidate_build=True`에 대한 예외를 제거했다. 완료 후보를 기본 그림과 비교하는 선택에는 기존 `min(완료 기본 그림 × 90%, 목표)` 한도를 유지한다. 목표는 slide 10pt, document 760px 열에서 11px다. 역사적 완료 기본 그림은 fallback으로 먼저 구성하며 이 미완료 구성의 단계는 보유 완료 그림 교체가 아니다.

팀장 결정 3에 맞게 완료 조건을 고쳤다. 36c7ea3 대비 후보 선택에서 90% 한도 안으로 생긴 축소는 허용하되, 후보 내부를 포함한 후속 단계의 1% 초과 축소는 0이어야 한다. 남은 2건의 실제 도입 단계와 최종 SVG hash를 아래에 기록한다.

글자 gate를 통과하지 못한 중간 B2의 header 재시도를 생략한다. 체크는 통과하지만 F5가 남을 때는 기존 shape-miss의 공간 요구로 한 번 그린 독립 spacing 후보를 비교한다. 같은 12/16 예산의 한 슬롯을 쓰며, 후보의 후속 단계에는 1% 규칙을 적용한다. 이 선택으로 multiregion document의 기존 흐름 승자를 유지한다.

## 테스트 먼저 red → green

- 기존 최초 작성의 DNS slide/slide-no-title, multiregion slide CLI red 근거는 이전 커밋과 `~/.cache/skill-design/t10-gate/red.log`에 보존된다.
- 이번 `red.log`: 후보 내부 document/slide에서 1.1% 축소가 허용되어 **2 failed / 10 passed**. `red-privatelink.log`: 실제 CLI에서 더 이른 6.398→6.279pt feedback 위반을 포착했다. 리뷰의 6.296→5.920pt와 같은 예외 경로다.
- `red-build-cache.log`, `red-fixed-cache.log`, `red-note-cache.log`는 같은 실효 결정/보존 정책에서 중복 계산을 재현한다. `red-cache.log`는 같은 선분의 장애물 검사를 반복하는 것을 재현한다.
- 최종 필수 전체 pytest **840 passed, 1 xfailed, 2572 subtests passed / 195.21s**. 예제 **21 all PASS, 0 FAIL, 0 SKIP**. Xfail은 기존 gw-ret 불투명 배경 가림이다. 두 필수 검증은 각각 한 번 실행했고 그 뒤 구현 파일을 바꾸지 않았다.

## 프로파일과 성능 변경

먼저 xnt, engine2-egress, multiregion slide를 cProfile로 측정했다. 아래 누적 시간에는 프로파일 자체의 비용이 들어 있으며 Q1 판정에는 아래의 전체 corpus 시간을 사용한다.

| 사례 slide | profile 전체(s) | build 호출 | 다른 SVG | 주요 비용 |
|---|---:|---:|---:|---|
| ports/xnt | 30.269 | 22 | 13 | route.draw 18.836s, fixed-answer 5.696s |
| bench/engine2-egress | 13.985 | 15 | 7 | build 9.628s, route.draw 8.231s |
| qa/t1-multiregion-dr | 73.442 | 28 | 24 | route.draw 54.499s, label 배치 37.499s |

프로파일 자료: `.t10-fix/*.prof`, `*.profile.txt`, `*.builds.json`. 같은 실효 skip·note 결정을 정규화하고 자동으로 선택된 axis/note 결정을 캐시에 등록한다. note를 명시적으로 고정한 캐시 사본에는 명시 결정을 유지한다. 탐색의 일반 build도 공유 캐시를 사용한다. fixed-answer는 checker namespace, 보호 정책, 규칙 그룹, 고정 글자 한도가 같은 경우에만 결과를 공유한다.

선분의 정적인 장애물 검사와 같은 행/열의 장애물 목록을 draw 내부에서 캐시한다. 동적인 포트·배지·이미 그린 선의 배치 검사는 캐시하지 않는다. 수평/수직 교차 검사는 기존 경계 접촉·역방향·길이 0 semantics를 유지하는 직접 계산으로 바꿨다. **390,625개 입력에서 기존 Liang–Barsky와 결과가 동일**했다(`segment-equivalence.log`).

프로파일 사례의 xnt 두 모드, engine2-egress slide, multiregion slide는 clean SVG와 바이트 동일하다. engine2-egress slide-no-title의 변경은 gate 수정 결과이며, 최적화 전후 SVG가 동일하다. 추가 회귀 대표 4건(merge-v3az, r2-pin-bottom, tgw document, three-b)은 최적화 기능을 끈 직접 CLI에서도 전체 실행 SVG와 같았다(`no-optim.log`). 캐시 최적화로 설명할 수 있는 회귀로 처리하지 않는다.

## 단일 전체 실행과 두 기준

전체 corpus는 **-j 6 한 번**, pytest·예제·프로파일·PNG 렌더와 겹치지 않게 실행했다. 부분 결과를 합치지 않았다. 원본은 `.t10-fix/corpus.json`이며 수정하지 않았다. Python 3.15 forkserver의 sandbox 소켓 제한 때문에 `run_corpus_fork.py`가 fork를 지정한 뒤 원본 `tests/run_corpus.py`를 실행했다.

필수 명령은 사용자 지정 uv 의존성과 offline 옵션을 사용했다. 중첩 uv에도 `UV_OFFLINE=1`을 적용했다. cache와 공유 Git 경로가 read-only여서 UV cache와 TMPDIR을 worktree의 `.t10-fix/uv-cache`, `.t10-fix/tmp`로 대체했다. `/tmp`는 사용하지 않았다. TMPDIR은 마무리 시 제거한다.

실행: `2026-11-08T01:12:09Z` → `2026-11-08T01:14:07Z`. 267 entries, 760 runs, drawn 744 / rejected 16, failures 0, tag mismatch 0. 원본 SHA-256 `820c91546c81a758460271732121c2baeb539262640ef338174e1c2068f7f7dd`.

`audit.py`는 렌더 없이 두 기준 및 팀장의 clean 전체 결과와 비교한다. 글자는 양쪽 SVG에서 full precision으로 재계산하고 규칙 비용은 baseline의 기록 정밀도를 따른다. 결과는 `audit.json`, `compare-3946906.json`, `compare-36c7ea3.json`, `compare-clean.json`이다.

| 항목 | 36c7ea3 | 3946906 | clean | 이번 단일 전체 |
|---|---:|---:|---:|---:|
| R-border | 17 | 17 | 17 | 17 |
| R-flow | 82 | 46 | 48 | 51 |
| R-rt | 94 | 90 | 90 | 90 |
| R-twin | 6 | 6 | 6 | 6 |
| R-label | 2 | 2 | 2 | 2 |
| R-fit | 298 | 298 | 298 | 298 |
| Check 전체 | 389 | 378 | 381 | 381 |
| BADGE NEAR ICON | 6 | 6 | 6 | 6 |
| LINE HUGS BORDER | 2 | 2 | 2 | 2 |
| LINE IN HEADER | 15 | 15 | 15 | 15 |
| LINE NEAR TEXT | 5 | 5 | 5 | 5 |
| LINE OFF CANVAS | 1 | 1 | 1 | 1 |
| LINE ON LINE | 15 | 8 | 10 | 10 |
| LINE OVER ICON | 32 | 32 | 32 | 32 |
| LINE OVER TEXT | 67 | 65 | 67 | 67 |
| SERVICE AS TEXT | 12 | 12 | 12 | 12 |
| SLIDE TOO SMALL | 184 | 184 | 184 | 184 |
| TEXT AT BORDER | 1 | 1 | 1 | 1 |
| TEXT NEAR ICON | 21 | 19 | 19 | 19 |
| TEXT OVERLAP | 27 | 27 | 27 | 27 |
| Wall(s) | 126.04 | 168.67 | 174.25 | 117.03 |
| 합계(s) | 616.69 | 977.31 | 1010.74 | 667.76 |
| 최악 run(s) | 10.67 | 19.484 | 28.219 | 15.053 |

| 기준 | better | same | worse | 바뀐 SVG | 최대 run 비율 | 3×/30s 초과 |
|---|---:|---:|---:|---:|---:|---:|
| 36c7ea3 | 80 | 680 | 0 | 80 | 2.779× | 0/0 |
| 3946906 | 23 | 725 | 12 | 35 | 1.688× | 0/0 |
| clean | 3 | 745 | 12 | 15 | 1.667× | 0/0 |

760개 전체(거부 16개 포함)의 최대 시간 비율도 **2.779×**다. 모든 run이 3× 및 30s 한도 안이다. multiregion slide **15.054s ≤ 25s** 목표도 통과한다.

| 시간 문제 사례 | 36c7ea3(s) | clean(s) | 이번(s) | 36 비율 |
|---|---:|---:|---:|---:|
| ports/xnt.layout.yaml slide | 2.367 | 9.535 | 4.950 | 2.091× |
| ports/xnt.layout.yaml slide-no-title | 2.349 | 9.714 | 4.944 | 2.105× |
| bench/engine2-egress.layout.yaml slide | 1.387 | 4.619 | 2.239 | 1.614× |
| bench/engine2-egress.layout.yaml slide-no-title | 1.347 | 4.558 | 3.743 | 2.779× |
| qa/t1-multiregion-dr.layout.yaml slide | 9.730 | 28.219 | 15.053 | 1.547× |

## 3946906 대비 모든 변경 35건

D=document, S=slide, N=slide-no-title. 아래에 SVG가 바뀐 run을 모두 기재한다. 시간만 바뀐 run은 앞의 성능 표로 판정한다.

| Run | Verdict | 글자 전→후 | 이유 |
|---|---|---:|---|
| bench/engine2-egress.layout.yaml · slide-no-title | better | 6.661→6.750pt | 1% gate 후 다른 font/note 후보 선택; 같은 규칙/check에서 6.661→6.750pt |
| bench/engine3-pipeline.layout.yaml · slide | better | 4.733→5.008pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| bench/engine3-pipeline.layout.yaml · slide-no-title | better | 5.301→5.609pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/eng-egress-tgw.layout.yaml · slide | better | 5.844→6.056pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/eng-egress-tgw.layout.yaml · slide-no-title | better | 5.904→6.269pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| rt/ce-three.layout.yaml · document | better | 5.078→5.281px | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| rt/right.layout.yaml · document | better | 7.164→7.893px | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/merge-v3az.layout.yaml · slide | worse | 8.949→8.757pt | 후보 내부 9.604→8.949pt 축소 거부로 기존 승자 탈락; clean 대비 F3 재발, 미해결 |
| trunk/merge-v3az-top.layout.yaml · slide | worse | 8.949→8.757pt | 후보 내부 9.604→8.949pt 축소 거부로 기존 승자 탈락; clean 대비 F3 재발, 미해결 |
| flowcol/r2-pin-bottom.layout.yaml · slide | worse | 8.182→7.554pt | 강화한 후보 내부 gate로 replay 승자 탈락; 완료 기본 그림의 더 작은 글자로 복귀, 회귀 |
| flowcol/r2-pin-bottom.layout.yaml · slide-no-title | worse | 9.646→8.460pt | 강화한 후보 내부 gate로 replay 승자 탈락; 완료 기본 그림의 더 작은 글자로 복귀, 회귀 |
| twin/sub.layout.yaml · slide | better | 9.703→9.703pt | 규칙/check/글자 유지; canvas area 감소 |
| twin/sub.layout.yaml · slide-no-title | better | 9.703→9.703pt | 규칙/check/글자 유지; canvas area 감소 |
| ports/xnt.layout.yaml · slide | better | 5.649→5.743pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| ports/xnt.layout.yaml · slide-no-title | better | 5.904→6.432pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| rt/rtsub.layout.yaml · slide | worse | 9.718→9.718pt | 규칙/check/글자는 같지만 선택된 geometry의 canvas area가 커져 terminal Verdict 악화 |
| rt/rtsub.layout.yaml · slide-no-title | worse | 9.718→9.718pt | 규칙/check/글자는 같지만 선택된 geometry의 canvas area가 커져 terminal Verdict 악화 |
| rt/three.layout.yaml · slide | better | 7.626→8.268pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/ce-tgw.layout.yaml · slide | better | 5.844→6.056pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/ce-tgw.layout.yaml · slide-no-title | better | 5.904→6.269pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-fork.layout.yaml · slide | better | 5.651→6.065pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-stem.layout.yaml · slide | better | 5.844→6.056pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-stem.layout.yaml · slide-no-title | better | 5.904→6.269pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-three.layout.yaml · document | better | 5.164→5.474px | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-three.layout.yaml · slide | better | 4.927→5.100pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-three.layout.yaml · slide-no-title | better | 5.518→5.712pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/x-fork-b.layout.yaml · slide | better | 5.649→5.969pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/x-fork-b.layout.yaml · slide-no-title | better | 5.904→6.269pt | 안전한 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| qa/t3-nat-route-table.layout.yaml · document | better | 12.000→12.000px | 안전하게 완료한 경로의 비교; LINE LEAVES BOX 제거 |
| qa/t1-privatelink.layout.yaml · slide | worse | 5.920→6.398pt | 후보 내부의 1% 초과 feedback 거부; 6.398pt 및 기존 F5 복귀 |
| qa/t1-multiregion-dr.layout.yaml · slide | worse | 3.496→3.662pt | 후속 축소 거부; 3.662pt와 기존 F2 보존 |
| qa/t1-multiregion-dr.layout.yaml · slide-no-title | worse | 3.496→3.662pt | 후속 축소 거부; 3.662pt와 기존 F2 보존 |
| qa/t3-hybrid-dns.layout.yaml · slide | worse | 5.651→6.264pt | 새 F3 및 후속 축소 거부; 기존 VGW의 F3/F5와 6.264pt 보존 |
| qa/t3-hybrid-dns.layout.yaml · slide-no-title | worse | 5.651→6.264pt | 새 F3 및 후속 축소 거부; 기존 VGW의 F3/F5와 6.264pt 보존 |
| ../../docs/examples/specs/tgw-reference-architecture.layout.yaml · document | worse | 7.735→6.867px | 강화한 후보 내부 gate로 replay 승자 탈락; 완료 기본 그림의 더 작은 글자로 복귀, 회귀 |

## 팀장 clean 대비 모든 변경 15건

D=document, S=slide, N=slide-no-title. 아래에 SVG가 바뀐 run을 모두 기재한다. 시간만 바뀐 run은 앞의 성능 표로 판정한다.

| Run | Verdict | 글자 전→후 | 이유 |
|---|---|---:|---|
| bench/engine2-egress.layout.yaml · slide-no-title | better | 6.661→6.750pt | 1% gate 후 다른 font/note 후보 선택; 같은 규칙/check에서 6.661→6.750pt |
| trunk/merge-v3az.layout.yaml · slide | worse | 9.034→8.757pt | 후보 내부 9.604→8.949pt 축소 거부로 기존 승자 탈락; clean 대비 F3 재발, 미해결 |
| trunk/merge-v3az-top.layout.yaml · slide | worse | 9.034→8.757pt | 후보 내부 9.604→8.949pt 축소 거부로 기존 승자 탈락; clean 대비 F3 재발, 미해결 |
| flowcol/r2-pin-bottom.layout.yaml · slide | worse | 8.182→7.554pt | 강화한 후보 내부 gate로 replay 승자 탈락; 완료 기본 그림의 더 작은 글자로 복귀, 회귀 |
| flowcol/r2-pin-bottom.layout.yaml · slide-no-title | worse | 9.646→8.460pt | 강화한 후보 내부 gate로 replay 승자 탈락; 완료 기본 그림의 더 작은 글자로 복귀, 회귀 |
| twin/sub.layout.yaml · slide | better | 9.703→9.703pt | 규칙/check/글자 유지; canvas area 감소 |
| twin/sub.layout.yaml · slide-no-title | better | 9.703→9.703pt | 규칙/check/글자 유지; canvas area 감소 |
| rt/gw-ret.layout.yaml · slide | worse | 7.649→7.649pt | 규칙/check/글자는 같지만 선택된 geometry의 canvas area가 커져 terminal Verdict 악화 |
| rt/gw-ret.layout.yaml · slide-no-title | worse | 8.567→8.567pt | 규칙/check/글자는 같지만 선택된 geometry의 canvas area가 커져 terminal Verdict 악화 |
| rt/rtsub.layout.yaml · slide | worse | 9.718→9.718pt | 규칙/check/글자는 같지만 선택된 geometry의 canvas area가 커져 terminal Verdict 악화 |
| rt/rtsub.layout.yaml · slide-no-title | worse | 9.718→9.718pt | 규칙/check/글자는 같지만 선택된 geometry의 canvas area가 커져 terminal Verdict 악화 |
| rt/three-b.layout.yaml · slide | worse | 9.076→8.424pt | candidate replay/후속 확대의 기존 승자 탈락; clean 대비 글자 확대 이득 상실 |
| rt/three-b.layout.yaml · slide-no-title | worse | 9.487→9.476pt | candidate replay/후속 확대의 기존 승자 탈락; clean 대비 글자 확대 이득 상실 |
| qa/t1-privatelink.layout.yaml · slide | worse | 5.920→6.398pt | 후보 내부의 1% 초과 feedback 거부; 6.398pt 및 기존 F5 복귀 |
| ../../docs/examples/specs/tgw-reference-architecture.layout.yaml · document | worse | 7.735→6.867px | 강화한 후보 내부 gate로 replay 승자 탈락; 완료 기본 그림의 더 작은 글자로 복귀, 회귀 |

## 36c7ea3 identity·축소와 도입 단계

새 tier-0 identity run은 **0개**이며 목록은 없다. 목표 미만이면서 글자가 작아진 run은 아래 **2개**다. 둘 다 실제 완료 기본 그림과 비교한 후보 선택(`later=False`)에서 생겼다. 최종 winner repair의 hash와 전체 corpus SVG hash가 같고, 도입 후 추가 축소가 없다.

| Run | 36→이번 | 보존율 | 도입 단계·증거 |
|---|---:|---:|---|
| bench/v2-3-egress.layout.yaml · document | 7.502056→7.294055px | 97.23% | select_drawing 후보 비교, `later=False`; final SHA `e6e48fb46c741aa2ed6697f45b12cf9890d6c122f34c0bb810655457a2806e8c` |
| qa/t1-multiregion-dr.layout.yaml · document | 2.972621→2.839352px | 95.52% | select_drawing 후보 비교, `later=False`; final SHA `43d3af302e1fc7e28acb3b3386f73605a7fef40598d939c6ec5c0695a0771fc8` |

`phase-evidence.json` 및 각 `*.normal.stages.json`의 실제 CLI 호출 기록: 완료 기본 그림 → 후보 선택 → winner repair. 위 두 run과 privatelink의 보호된 `later=True` 호출에서 **1% 초과 축소를 허용한 호출은 0**이다. Privatelink는 이제 36c7ea3와 같은 6.398104pt여서 축소 목록에서 빠졌다. 내부 후보와 보유 그림 양쪽을 검사한 경계 테스트, feedback/header/fixed-answer/text-scale 회귀 및 공통 gate가 다른 보호 단계도 검증한다.

## PNG 직접 판정

`.t10-fix/png/qa__t3-hybrid-dns.layout.yaml.slide.{36c7ea3,3946906}-pair.png`와 `.t10-fix/png/qa__t1-multiregion-dr.layout.yaml.slide.{36c7ea3,3946906}-pair.png` 네 장을 이미지 보기 도구로 직접 확인했다. 각 원본은 `png/{36c7ea3,3946906,after}/`에 있다. after는 이번 단일 전체 실행의 draft에서 export했다.

- DNS: AZ1 Inbound ENI 앞 새 접점 오독이 없어지고 VGW 옆 기존 접점으로 돌아왔다. **5.651→6.264pt**, 36c7ea3 크기를 보존한다. UDP/TCP :53의 기존 귀속 문제와 작은 CIDR/범례는 남아 전달 판정은 차단 유지다.
- Multiregion: 복제선과 badge를 SQL/NLB 요청선에서 분리한 개선을 유지한다. 기존 DNS 제어선/앱 요청선 F2는 남는다. **3.496→3.662pt**로 이전 크기를 보존하지만 실제 slide 글자가 너무 작아 전달 판정은 차단 유지다.

clean 대비 worse 12건의 `*.clean-pair.png`도 모두 직접 봤다. merge 두 그림의 ALB 분기선 접점과 글자 축소는 실제 회귀다. pin-bottom 두 모드는 구조는 읽히지만 글자가 작아졌다. three-b 두 모드는 요청/검사 흐름을 유지하나 확대 이득을 잃었다. gw-ret/rtsub 네 모드는 같은 흐름·글자를 유지하고 배치·여백이 달라진 canvas area 악화다. PrivateLink는 글자가 커졌지만 HTTPS 라벨 귀속 F5가 복귀했다. TGW document는 연결 의미를 유지하지만 최소 글자/범례 크기가 작아졌다. 이 회귀를 “다른 사례 악화 없음”으로 처리하지 않는다.

## 완료 조건

- [x] 기존 CLI 3건 red → green, 이번 후보 내부 경계/privatelink 및 캐시 red → green; 전체 pytest 840건 통과.
- [x] DNS 두 mode 새 identity 0 및 6.264pt; multiregion slide 3.661823pt 유지.
- [x] 3946906 및 36c7ea3의 규칙/check/판정/시간 표와 모든 변경 run; 수정 전 clean도 별도로 비교.
- [x] 36 대비 새 identity 0, 축소 2건의 목록·90% 한도·실제 선택 단계 및 hash 증거. 금지된 후속 축소 0.
- [ ] R-flow ≤50 및 기존 승자 보존: **51건**. shared-lane 두 slide 및 multiregion document는 R-flow 0을 유지하지만 merge 두 slide의 기존 승자를 잃었다.
- [x] 모든 760 run이 36 대비 ≤3×, ≤30s; 최악 15.054s, multiregion ≤25s 목표도 통과.
- [x] spec.md / GLOSSARY.md에 후보 내부까지 포함한 gate와 고정 후보 한도 명시.
- [x] 필수 전체 pytest·예제·corpus 각각 1회, corpus -j 6 단독 실행. 부분 재실행을 결과에 합치지 않음.
- [ ] 다른 corpus 사례 악화 없음: clean 대비 worse 12건을 위 표와 PNG 판정에 남김.
- [ ] 공유 브랜치 커밋: 현재 세션의 파일시스템 정책에서 공유 objects/refs가 read-only다. worktree 안에 별도 Git index/준비 저장소의 커밋과 bundle을 만들고, 공유 경로 쓰기가 열리면 반영해야 한다. **index 동기화 필요**. 실제 worktree HEAD는 아직 이전 커밋이라 HEAD diff가 남는다. 준비 커밋 기준의 tracked diff만 비어 있음을 확인한다.

추가 전체 검증 허용 및 cache/공유 Git 쓰기 권한 복구를 질문했으나 아직 응답이 없다. 선택지가 미리 표시되거나 시간이 지났다는 것을 승인으로 보지 않았다. 구현은 최초 단일 전체 실행 이후 고정했으며, 이후의 진단용 직접 CLI 실험을 최종 corpus에 합치거나 적용하지 않았다. R-flow/추가 회귀를 남은 문제로 보고한다.
