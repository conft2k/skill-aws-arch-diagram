# Ticket 10: 사용자 승인 예외 — tier-0 감소가 있는 축소만 허용

2026-11-08, 코드 작성 세션. 사용자 승인 규칙과 최종 단일 전체 실행으로 **통과**했다. clean 7eb2d55 대비 **4 better / 756 same / 0 worse**, R-flow **46 ≤ 48**, 36c7ea3 대비 새 tier-0 identity **0**, 모든 run **≤3×·≤30s**다. 독립 리뷰는 별도 세션에서 한다. 공유 Git이 read-only여서 사용자 승인대로 worktree 안의 별도 index/준비 커밋과 bundle로 전달한다.

## 최종 결정과 코드

보유 그림의 effective text size가 목표 미만일 때, 그 글자의 99% 미만으로 줄어드는 후속 그림은 **전체 tier-0 위반 개수가 엄격히 줄어야만** 교체할 수 있다. check 문제나 tier-0 cost 감소만으로는 축소를 허용하지 않는다. Feedback, header, fixed-answer, text-scale 및 후보 내부 단계가 같은 `preserves_text`/`admits`를 쓴다. 검사기가 실패하면 개수 감소를 증명할 수 없어 이런 축소를 거부한다.

새 identity gate는 그대로다: `(rule, code, frozenset(owners))`가 새로 생기면 전체 tier-0 개수가 엄격히 줄어야 한다. 후보 선택의 고정 한도도 그대로다: 후보 글자가 목표와 완료 기본 그림 ×90% 모두보다 작으면 거부한다. 목표는 slide 10pt, document 760px 열에서 11px다. Verdict의 7개 순서, rules.py의 규칙 및 threshold는 바꾸지 않았다.

기존 build/fix 캐시, 장애물/행·열 캐시, 수평·수직 교차 계산을 유지했다. 두 경계도 고쳤다.

- **보유 fixed SVG의 handoff:** `render_checked`가 명시적으로 넘긴 완료 그림이 같은 raw build의 이전 memoized fix 결과보다 우선한다. 캐시가 이미 보유한 SVG/수정 개수를 덮어쓰지 못하게 했다. namespace·정책·고정 글자 한도별 캐시는 유지한다.
- **체크 수정 replay의 시작 그림:** 완료 그림과 처음 raw 그림 모두 tier-0가 없고 raw의 check가 더 많을 때는 완료 그림을 incumbent로 사용한다. 미완성 raw를 글자 보존의 기준으로 삼지 않는다. 초기 tier-0가 있거나 raw check가 더 많지 않으면 기존 후보의 font retry를 유지한다. 이 경계로 pin-bottom의 두 글자 회귀를 없애면서 rtsub/TGW의 기존 font 후보도 유지했다.

## Red → green과 검증

`red.log`: 새 규칙의 tier-0 감소+1.1% 축소가 기존 코드에서 거부되어 **4 failed / 32 passed**였다. 동일 tier-0 개수에서 cost만 줄거나 check만 줄어드는 축소의 거부, 1% 경계, 목표 이상 예외, 후보 선택 90% 한도를 두 medium 및 후보 내부/외부에서 함께 검증한다.

`red-handoff.log`: 명시적인 보유 SVG를 캐시가 덮어쓰는 실패 1건. `red-pin.log`: pin-bottom 두 mode의 글자 축소 실패 2건. `red-font-retry.log`: 너무 넓게 적용한 incumbent 시작이 TGW document font retry를 막는 실패 1건. 모두 green으로 고쳤다.

최종 필수 검증은 각각 **한 번** 실행했다. 전체 pytest **872 passed, 1 xfailed, 2572 subtests passed / 209.10s**, 예제 **21 all PASS / 0 FAIL / 0 SKIP**. Xfail은 기존 gw-ret 불투명 배경 가림이다. `pytest.log`, `examples.log` 및 시작/종료 파일을 보존한다. 이후 구현 파일을 변경하지 않았다.

## Canvas area 회귀와 캐시

gw-ret/rtsub의 area 악화는 최종 글자 값만 보면 규칙과 무관해 보였지만, 중간 그림의 글자 축소를 막아 header/feedback 승자를 잃은 결과였다. 동일 최적화에서 tier-0 감소 예외를 적용하면 원래 area와 SVG를 회복한다. 최적화를 끈 직접 CLI에서도 clean SVG와 동일함을 확인했다(`no-optim.log`).

실제 trace에서 gw-ret는 header repair의 **tier-0 2→0** 및 feedback **1→0**, rtsub는 feedback **1→0**에 해당하는 축소를 허용한다. 코드의 캐시 키를 느슨하게 만들어 area를 맞추지 않았다. 실제 SVG viewBox area를 검사하는 회귀 테스트를 두 mode씩 추가했다.

| Run | 303b12a area | clean 및 최종 area | 최종 글자 |
|---|---:|---:|---:|
| gw-ret S/N | 886030 | 874734 | 7.648725 / 8.566572pt |
| rtsub S/N | 725532 | 710700 | 9.718447pt |

## 단일 전체 corpus

Python 3.15, offline uv 의존성은 사용자 지정대로 사용했다. 중첩 uv에도 `UV_OFFLINE=1`을 적용했다. cache 경로가 read-only여서 TMPDIR은 `.t10-exception/tmp`, uv cache는 기존 worktree의 `.t10-fix/uv-cache`를 사용했다. `/tmp`는 사용하지 않았으며 TMPDIR은 마무리 시 삭제한다.

`run_corpus_fork.py`는 sandbox의 forkserver 소켓 제한 때문에 fork를 지정하고 원본 `tests/run_corpus.py`를 그대로 실행한다. `--rule-checker scripts/rules.py:corpus --baseline clean/corpus.json --baseline-drafts clean/drafts --keep .t10-exception/drafts --out .t10-exception/corpus.json -q -j 6`으로 **전체 한 번** 실행했다. pytest·예제·프로파일·PNG 렌더와 겹치지 않았고 부분 결과를 합치지 않았다.

원본 실행 `2026-11-08T02:26:50Z` → `2026-11-08T02:28:42Z`: 267 entries, 760 runs, drawn 744 / rejected 16, failures 0. 원본 SHA-256 `0ddc6324474abaabc634da2757318d85db2d684066af11b1331e510fb042c742`.

원본에는 multiregion 두 slide의 과거 bad R-flow tag 불일치 2건이 남는다. 이제 두 그림 모두 R-flow 0이므로 MANIFEST를 good R-flow로 고쳤다. 같은 저장 결과를 렌더 없이 재판정한 `tag-rejudgement.json`은 **0건**이다. 원본 JSON은 수정하지 않았고 재실행하지 않았다.

`audit.py`는 양쪽 SVG에서 full precision 글자 크기를 재계산하여 clean·3946906·36c7ea3를 비교한다. `compare-*.json`, `audit.json`은 파생 감사 자료이며 원본 전체 실행은 하나다.

| 항목 | 36c7ea3 | 3946906 | clean | 최종 |
|---|---:|---:|---:|---:|
| R-border | 17 | 17 | 17 | 17 |
| R-flow | 82 | 46 | 48 | 46 |
| R-rt | 94 | 90 | 90 | 90 |
| R-twin | 6 | 6 | 6 | 6 |
| R-label | 2 | 2 | 2 | 2 |
| R-fit | 298 | 298 | 298 | 298 |
| Check 전체 | 389 | 378 | 381 | 379 |
| BADGE NEAR ICON | 6 | 6 | 6 | 6 |
| LINE HUGS BORDER | 2 | 2 | 2 | 2 |
| LINE IN HEADER | 15 | 15 | 15 | 15 |
| LINE LEAVES BOX | 1 | 1 | 0 | 0 |
| LINE NEAR TEXT | 5 | 5 | 5 | 5 |
| LINE OFF CANVAS | 1 | 1 | 1 | 1 |
| LINE ON LINE | 15 | 8 | 10 | 8 |
| LINE OVER ICON | 32 | 32 | 32 | 32 |
| LINE OVER TEXT | 67 | 65 | 67 | 67 |
| SERVICE AS TEXT | 12 | 12 | 12 | 12 |
| SLIDE TOO SMALL | 184 | 184 | 184 | 184 |
| TEXT AT BORDER | 1 | 1 | 1 | 1 |
| TEXT NEAR ICON | 21 | 19 | 19 | 19 |
| TEXT OVERLAP | 27 | 27 | 27 | 27 |
| Wall(s) | 126.04 | 168.67 | 174.25 | 110.19 |
| 합계(s) | 616.69 | 977.31 | 1010.74 | 631.98 |
| 최악 run(s) | 10.67 | 19.484 | 28.219 | 17.181 |

| 비교 기준 | better | same | worse | 바뀐 SVG | 최대 run 비율 | 3× / 30s 초과 |
|---|---:|---:|---:|---:|---:|---:|
| 36c7ea3 | 92 | 668 | 0 | 92 | 2.757× | 0/0 |
| 3946906 | 28 | 730 | 2 | 30 | 1.481× | 0/0 |
| clean | 4 | 756 | 0 | 4 | 1.611× | 0/0 |

거부 16건을 포함한 **모든 760 run**의 36 대비 최대 비율도 **2.757×**다. 모두 ≤3× 및 ≤30s. multiregion slide **17.037s**, slide-no-title **17.181s**, 전체 최악 17.181s로 25s 목표도 통과했다.

## 바뀐 run — clean 대비 4건

| Run | 판정 | 글자 전→후 | 이유 |
|---|---|---:|---|
| bench/engine2-egress.layout.yaml · slide-no-title | better | 6.660793→6.750000pt | 같은 tier-0/check에서 다른 font/note 승자 선택; font 확대 및 shape miss 제거 |
| bench/engine2-pipeline.layout.yaml · document | better | 4.117381→4.147340px | 같은 tier-0/check에서 Verdict-selected feedback/font 후보 개선; effective text 증가 |
| qa/t1-multiregion-dr.layout.yaml · slide | better | 3.661823→3.495586pt | 보호된 feedback에서 tier-0 6→2; F2와 LINE ON LINE 제거를 위해 축소 허용 |
| qa/t1-multiregion-dr.layout.yaml · slide-no-title | better | 3.661823→3.495586pt | 보호된 feedback에서 tier-0 6→2; F2와 LINE ON LINE 제거를 위해 축소 허용 |

clean 대비 worse run은 **0건**, 목록은 없다. 303b12a의 기존 회귀 12건은 모두 해소했다. 시간 최적화 코드는 유지했다.

## 바뀐 run — 3946906 대비 30건

| Run | 판정 | 글자 전→후 | 이유 |
|---|---|---:|---|
| bench/engine2-egress.layout.yaml · slide-no-title | better | 6.661→6.750pt | 같은 tier-0/check에서 다른 font/note 승자 선택; font 확대 및 shape miss 제거 |
| bench/engine2-pipeline.layout.yaml · document | better | 4.117→4.147px | 같은 tier-0/check에서 Verdict-selected feedback/font 후보 개선; effective text 증가 |
| bench/engine3-pipeline.layout.yaml · slide | better | 4.733→5.008pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| bench/engine3-pipeline.layout.yaml · slide-no-title | better | 5.301→5.609pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/eng-egress-tgw.layout.yaml · slide | better | 5.844→6.056pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/eng-egress-tgw.layout.yaml · slide-no-title | better | 5.904→6.269pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| rt/ce-three.layout.yaml · document | better | 5.078→5.281px | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| rt/right.layout.yaml · document | better | 7.164→7.893px | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/merge-v3az.layout.yaml · slide | better | 8.949→9.034pt | tier-0 감소를 동반한 후보 feedback 허용; F3 제거 후 안전한 font 확대 |
| trunk/merge-v3az-top.layout.yaml · slide | better | 8.949→9.034pt | tier-0 감소를 동반한 후보 feedback 허용; F3 제거 후 안전한 font 확대 |
| ports/xnt.layout.yaml · slide | better | 5.649→5.743pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| ports/xnt.layout.yaml · slide-no-title | better | 5.904→6.432pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| rt/gw-ret.layout.yaml · slide | better | 7.649→7.649pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| rt/gw-ret.layout.yaml · slide-no-title | better | 8.567→8.567pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| rt/three.layout.yaml · slide | better | 7.626→8.268pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| rt/three-b.layout.yaml · slide | better | 8.424→9.076pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| rt/three-b.layout.yaml · slide-no-title | better | 9.476→9.487pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/ce-tgw.layout.yaml · slide | better | 5.844→6.056pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/ce-tgw.layout.yaml · slide-no-title | better | 5.904→6.269pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-fork.layout.yaml · slide | better | 5.651→6.065pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-stem.layout.yaml · slide | better | 5.844→6.056pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-stem.layout.yaml · slide-no-title | better | 5.904→6.269pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-three.layout.yaml · document | better | 5.164→5.474px | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-three.layout.yaml · slide | better | 4.927→5.100pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/v-three.layout.yaml · slide-no-title | better | 5.518→5.712pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/x-fork-b.layout.yaml · slide | better | 5.649→5.969pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| trunk/x-fork-b.layout.yaml · slide-no-title | better | 5.904→6.269pt | 새 tier-0 없는 후보의 두 번 이내 작은 uniform font 확대; 규칙/check 보존 |
| qa/t3-nat-route-table.layout.yaml · document | better | 12.000→12.000px | 안전한 경로 완료; LINE LEAVES BOX 제거 |
| qa/t3-hybrid-dns.layout.yaml · slide | worse | 5.651→6.264pt | AZ1 새 접점/축소 거부; 기존 VGW F3/F5 및 6.264pt 보존 |
| qa/t3-hybrid-dns.layout.yaml · slide-no-title | worse | 5.651→6.264pt | AZ1 새 접점/축소 거부; 기존 VGW F3/F5 및 6.264pt 보존 |

3946906 대비 worse 두 run은 DNS slide/slide-no-title이다. 새 AZ1 접점을 없애고 더 큰 기존 그림으로 돌아온 티켓의 의도된 변경이며, clean 대비는 same다. 그 PNG를 아래처럼 직접 확인했다.

## 36c7ea3 대비 identity·목표 미만 축소

새 tier-0 identity run: **0건** — 목록 없음. 목표 미만 축소는 아래 **5건**이다. 직접 CLI 추적은 전체 결과에 합치지 않았으며, 최종 SVG hash가 전체 실행 draft와 같은 것만 증거로 사용했다.

| Run | 이전→최종 | 보존율 | 도입 단계 | tier-0 전→후 |
|---|---:|---:|---|---:|
| bench/v2-3-egress.layout.yaml · document | 7.502056→7.294055px | 97.23% | 후보 선택 | 4→4 |
| qa/t1-privatelink.layout.yaml · slide | 6.398104→5.919915pt | 92.53% | 후보 내부 feedback | 6→5 |
| qa/t1-multiregion-dr.layout.yaml · document | 2.972621→2.839352px | 95.52% | 후보 선택 | 5→4 |
| qa/t1-multiregion-dr.layout.yaml · slide | 3.661823→3.495586pt | 95.46% | 보유 기본 그림 feedback | 6→2 |
| qa/t1-multiregion-dr.layout.yaml · slide-no-title | 3.661823→3.495586pt | 95.46% | 보유 기본 그림 feedback | 6→2 |

Bench/v2-3-egress와 multiregion document는 독립 후보 선택의 고정 90% 한도로 허용한다. Privatelink는 후보 replay feedback에서 6.398104→5.919915pt 및 **6→5 감소**를 확인했고, 이후 winner repair는 크기를 그대로 유지한다. Multiregion 두 slide는 보유 기본 그림 feedback의 **6→2 감소**로 허용한다.

`shrink-stages.json`에 각 최종 hash와 `trace/*.json` 경로를 기록했다. 후보 선택 후 동일 크기의 경로 수정으로 hash가 바뀌는 경우도, 도입 직후 크기와 최종 winner repair의 크기 및 최종 hash를 함께 확인한다. 추적한 모든 보호된 후속 호출의 1% 초과 축소는 tier-0 감소를 동반했다. 위반 호출 **0건**이며 rule matrix와 공통 gate가 모든 뒤 단계를 적용한다.

## PNG 직접 판정

이번 전체 실행 SVG에서 `png/{clean,36c7ea3,3946906,after}/`를 export했다. 다음 pair PNG를 이미지 보기 도구로 직접 확인했다.

- `qa__t3-hybrid-dns.layout.yaml.slide.{clean,36c7ea3,3946906}-pair.png`와 `slide-no-title.clean-pair.png`: clean 그림을 그대로 유지한다. main 3946906의 AZ1 Inbound ENI 앞 새 접점은 없고, 36과 같은 VGW 옆 기존 F3/F5는 남는다. 두 mode **6.264407pt**, 새 identity 없음. 작은 글자와 기존 UDP/TCP :53 귀속은 전달 차단 백로그다.
- `qa__t1-multiregion-dr.layout.yaml.slide.{clean,36c7ea3,3946906}-pair.png`: clean의 DNS 제어선/앱 선 collinear gap을 없앴다. 복제선과 badge는 SQL/NLB 요청선에서 분리된 상태를 유지한다. **3.661823→3.495586pt** 축소는 tier-0 **6→2** 및 F2/LINE ON LINE 제거로 허용된다. 흐름은 개선됐지만 실제 slide 글자는 여전히 너무 작아 R-fit 전달 차단은 남는다.
- `trunk__merge-v3az.layout.yaml.slide.clean-pair.png`, `trunk__merge-v3az-top.layout.yaml.slide.clean-pair.png`: clean의 세 ALB 분기선을 유지하고 두 그림 모두 **F3 0**, **9.033877pt**다. 303b에서 복귀한 접점 회귀를 없앴다.
- `qa__t1-privatelink.layout.yaml.slide.clean-pair.png`: clean과 같은 **5.919915pt**, R-border B1 및 R-flow F1/F3가 남고 F5는 없다. 후보 내부 tier-0 감소가 확인되어 축소를 허용했다. 엔드포인트를 관통하는 기존 경로 및 작은 글자는 여전히 전달 백로그다.

## 완료 조건

- [x] 새 규칙 red→green: count 감소 허용, cost/check 감소만 있는 축소 거부. 후보 내부/외부, 두 medium 및 1% 경계.
- [x] 새 identity gate와 후보 선택 90% 고정 한도 유지.
- [x] clean 대비 worse **0**, R-flow **46≤48**; shared-lane 두 mode와 multiregion document R-flow 0 유지.
- [x] 36 대비 새 tier-0 identity **0**, 모든 run ≤3×·≤30s; 축소 5건의 실제 도입 단계·개수 감소·최종 hash 증거.
- [x] DNS 두 mode ≥6.26pt 및 새 identity 없음, merge 두 slide F3 없음; privatelink 상태·이유·PNG 기록.
- [x] build/fix·장애물·교차 최적화 유지; canvas area 네 회귀 해소; 보유 fixed SVG handoff 캐시 문제도 테스트로 수정.
- [x] 전체 pytest·예제·corpus 각각 1회; corpus -j 6 단독 실행 및 단일 원본 사용, 부분 실행 합치지 않음.
- [x] spec·GLOSSARY·티켓·증거 문서 갱신, 개선에 맞춰 mri bad tag를 good으로 정정.
- [x] 사용자 승인 fallback: 공유 Git read-only 시 별도 index의 준비 커밋과 bundle로 전달. 준비 HEAD와 작업 트리 tracked diff가 비어 있음을 확인한다. 공유 HEAD는 아직 303b12a라 실제 HEAD diff는 반영 전까지 남는다. **index 동기화 필요**.

남은 구현 차단은 없다. 기존 DNS F3/F5, PrivateLink B1/F1/F3 및 엔드포인트 관통, 큰 문서 spec을 slide로 변환할 때의 작은 글자, 기존 gw-ret 가림 xfail은 백로그다. 공유 브랜치 적용은 팀장이 bundle을 반영한다.
