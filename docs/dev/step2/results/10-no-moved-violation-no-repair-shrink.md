# Ticket 10: 옮긴 위반과 목표 미만 글자의 추가 축소를 개선으로 보지 않기

작성: 2026-11-08 KST. 브랜치 `t10-gate`. 코드 작성 결과이며 독립 리뷰는 별도 세션에서 진행한다.

## 구현과 red → green

`RuleGuard.admits`가 기존 Verdict 앞에서 교체를 판정한다. Identity는
`(rule, code, frozenset(owners))`이며 좌표·메시지·owner 순서를 포함하지 않는다.
탐색에 아직 켜지 않은 R-twin/R-label도 포함한 전체 tier-0에서 새 identity가
생기면 개수가 엄격히 줄어야 한다. Feedback, header, fixed-answer, text-scale,
탐색 후보 및 단계 결과를 보유 그림에 채택하는 비교가 이 판정을 공유한다.
Verdict의 순서와 검사기의 규칙·threshold는 바꾸지 않았다.

보유 그림이 목표 미만이면 후속 단계는 effective text size의 1%를 넘는 축소를
거부한다. 후보 탐색은 기존의 `min(완료 기본 그림 × 90%, 목표)` 한도를 유지한다.
목표는 slide 10pt, document 760px 열의 11px다.

단계 경계도 명시했다. 기존 완료 기본 그림은 fallback과 고정 크기 기준으로 먼저
구성한다. Original spec의 guarded replay는 탐색 후보를 구성하므로 기존 90% 한도를
쓴다. 이 과정의 rule 비교에도 identity gate를 적용한다. 완료 그림을 보유한 뒤의
repair에는 1% 한도까지 적용한다. 이 구별로 multiregion document의 후보 승자를
유지하고 slide의 후속 축소는 막는다.

처음 쓴 CLI 재현 3건(DNS slide/slide-no-title, multiregion slide)은 모두 red였다.
DNS는 새 `F3 edge:4/edge:7`, multiregion은 3.50pt가 실패 근거다.
Feedback 두 경로, header, fixed-answer, text-scale의 moved-identity 테스트도 red였다.
Owner 순서·좌표 변경은 같은 identity이며, 새 identity도 전체 개수가 줄면 허용함을
검증했다. 1% 경계 및 기존 후보 한도는 두 medium에서 따로 검증한다.

회귀를 보존하기 위한 두 수정도 포함했다.

- `t7-xyref`: B1을 B2로 옮긴 미완성 후보는 채택하지 않는다. 후보 구성 중 그
  B2를 header repair로 실제 제거한 결과를 다시 gate로 판정한다. 채택한 header
  제약과 회피 영역은 다음 feedback에도 유지한다. 현재 main의 SVG와 바이트 동일하다.
- `ports/xnt`: 새 규칙 위반 없는 후보는 아직 text-scale 시도를 하지 않았다.
  Feedback이 그대로 둔 이런 후보는 기존 두 번 예산 안에서 canvas font 1단위씩
  확대한다. Feedback geometry를 유지하며 매번 같은 gate와 Verdict를 통과해야 한다.
  이미 시도한 완료 그림에는 반복하지 않는다. 새 CLI 회귀도 red 뒤 green이다.

기존 note wrapping 테스트는 완료 기본 그림의 byte 동일성을 확인하도록 경계를
정리했다. 강제로 모든 note를 unwrapped로 만드는 mock은 미완성 후보의 check도
바꾸므로 새 gate 이후 탐색 결과까지 동일하다는 가정은 성립하지 않는다.
실제 CLI 결과는 전체 corpus 및 예제 golden 비교로 별도 검증한다.
Multiregion의 slide 두 모드에는 기존 F2가 남으므로 해당 mode의 bad tag를 명시했다.
Document의 R-flow 통과는 CLI 회귀로 계속 검사한다.

## 검증 및 실행

필수 pytest: **824 passed, 1 xfailed, 2544 subtests passed**, 245.96초.
Xfail은 기존의 뒤에 그린 불투명 배경에 의한 `gw-ret` 가림이며 해결한 것으로
처리하지 않았다. 예제: **21 all PASS / 0 FAIL / 0 SKIP**. Golden 변경은 없다.

모든 임시 파일은 `TMPDIR=$HOME/.cache/codex-t10-gate-tmp`에 두었다.
Python 3.15를 사용했다. 예제의 하위 uv에도 `UV_OFFLINE=1`을 적용했다.
전체 corpus는 **-j 6으로 1회** 실행하고, 테스트·예제·PNG export와 겹치지 않았다.
Python 3.15 forkserver의 sandbox 소켓 제한을 피하기 위해
`~/.cache/skill-design/t10-gate/run_corpus_fork.py`가 multiprocessing 시작 방법을
fork로 정한 뒤 원본 `tests/run_corpus.py`를 그대로 실행한다.
부분 재현은 전체 실행 전에 사용했다.

최종 결과 및 재현 도구는 `/home/ec2-user/.cache/skill-design/t10-gate/`에 보존한다.
`corpus.json`은 runner의 원본이며 수정하지 않는다. `audit.py`는 이 결과와 두
기준의 draft를 읽어 `compare-3946906.json`, `compare-36c7ea3.json`, `audit.json`을
만들고 추가로 렌더하지 않는다. 글자 크기는 양쪽 SVG에서 full precision으로
재계산한다. Rule 비용은 baseline의 소수점 2자리 기록 정밀도를 따른다.


## 최종 corpus와 완료 조건

전체 1회 결과는 `corpus.json`: 760 runs, R-flow 54, check 384, better 21 / same 731 / worse 8이었다. 추가 회귀 4건을 red로 고정하고 F5 후보 구성을 완료 보유 그림에서 시작하게 했으며, F1을 F2로 옮긴 후보는 채택하지 않고 같은 예산 안에서 다음 경로 한 번을 완성한 뒤 비교했다. Effective text 정보도 재사용한다.

그 뒤 두 기준 중 하나라도 check/violation이 있거나 처음 전체 실행에서 바뀐 entry 143개, **429 runs**를 -j 6으로 부분 재검증했다. 나머지 **331개 clean run은 최초 전체 결과를 유지**한다. `final-assembled.json`은 이 두 원본을 명시적으로 합친 자료이며 새 전체 실행으로 표시하지 않는다. `corpus.json`과 `recheck.json`은 수정하지 않았다.

최종 합산: **R-flow 48, check 381, 태그 재판정 불일치 0**. 두 merge-v3az의 slide는 F3가 없어져 해당 bad tag를 slide-no-title에만 남겼다. 마지막 수정 후 새 회귀와 document 승자 테스트 **5 passed**. 전체 pytest/예제의 최종 코드 재실행은 시간 제한 때문에 남는다.

| 항목 | 36c7ea3 | 3946906 | 최종 합산 |
|---|---:|---:|---:|
| R-border | 17 | 17 | 17 |
| R-flow | 82 | 46 | 48 |
| R-rt | 94 | 90 | 90 |
| R-twin | 6 | 6 | 6 |
| R-label | 2 | 2 | 2 |
| R-fit | 298 | 298 | 298 |
| Check 전체 | 389 | 378 | 381 |
| BADGE NEAR ICON | 6 | 6 | 6 |
| LINE HUGS BORDER | 2 | 2 | 2 |
| LINE IN HEADER | 15 | 15 | 15 |
| LINE LEAVES BOX | 1 | 1 | 0 |
| LINE NEAR TEXT | 5 | 5 | 5 |
| LINE OFF CANVAS | 1 | 1 | 1 |
| LINE ON LINE | 15 | 8 | 10 |
| LINE OVER ICON | 32 | 32 | 32 |
| LINE OVER TEXT | 67 | 65 | 67 |
| SERVICE AS TEXT | 12 | 12 | 12 |
| SLIDE TOO SMALL | 184 | 184 | 184 |
| TEXT AT BORDER | 1 | 1 | 1 |
| TEXT NEAR ICON | 21 | 19 | 19 |
| TEXT OVERLAP | 27 | 27 | 27 |

| 비교 | better | same | worse |
|---|---:|---:|---:|
| 3946906 | 26 | 730 | 4 |
| 36c7ea3 | 91 | 669 | 0 |

시간: 최초 전체 실행 **171.29s wall, 994.0s 합계, 최악 22.523s**, 현재 main 대비 wall 1.016×. 최종 합산의 시간은 부분 재검증과 원본 clean run의 혼합이며 전체 wall 측정으로 해석하지 않는다.

| 기준 | 기준 wall(s) | 최종 합산 최악(s) | 최대 draft 비율 | 3× 초과 |
|---|---:|---:|---:|---:|
| 3946906 | 168.67 | 27.989 | 2.000× | 0 |
| 36c7ea3 | 126.04 | 27.989 | 4.046× | 4 |

### 바뀐 run — 3946906 대비

| Case × mode | 판정 | 글자 전→후 | 이유 |
|---|---|---|---|
| bench/engine3-pipeline.layout.yaml · slide | better | 4.733→5.008pt | 규칙을 보존한 두 번의 작은 font 확대 |
| bench/engine3-pipeline.layout.yaml · slide-no-title | better | 5.301→5.609pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/eng-egress-tgw.layout.yaml · slide | better | 5.844→6.056pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/eng-egress-tgw.layout.yaml · slide-no-title | better | 5.904→6.269pt | 규칙을 보존한 두 번의 작은 font 확대 |
| rt/ce-three.layout.yaml · document | better | 5.078→5.281px | 규칙을 보존한 두 번의 작은 font 확대 |
| rt/right.layout.yaml · document | better | 7.164→7.893px | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/merge-v3az.layout.yaml · slide | better | 8.949→9.034pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/merge-v3az-top.layout.yaml · slide | better | 8.949→9.034pt | 규칙을 보존한 두 번의 작은 font 확대 |
| ports/xnt.layout.yaml · slide | better | 5.649→5.743pt | 규칙을 보존한 두 번의 작은 font 확대 |
| ports/xnt.layout.yaml · slide-no-title | better | 5.904→6.432pt | 규칙을 보존한 두 번의 작은 font 확대 |
| rt/gw-ret.layout.yaml · slide | better | 7.649→7.649pt | 중간 moved violation을 채택하지 않고 완료한 경로를 비교; 규칙/check/fit 개선 |
| rt/gw-ret.layout.yaml · slide-no-title | better | 8.567→8.567pt | 중간 moved violation을 채택하지 않고 완료한 경로를 비교; 규칙/check/fit 개선 |
| rt/three.layout.yaml · slide | better | 7.626→8.268pt | 규칙을 보존한 두 번의 작은 font 확대 |
| rt/three-b.layout.yaml · slide | better | 8.424→9.076pt | 규칙을 보존한 두 번의 작은 font 확대 |
| rt/three-b.layout.yaml · slide-no-title | better | 9.476→9.487pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/ce-tgw.layout.yaml · slide | better | 5.844→6.056pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/ce-tgw.layout.yaml · slide-no-title | better | 5.904→6.269pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/v-fork.layout.yaml · slide | better | 5.651→6.065pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/v-stem.layout.yaml · slide | better | 5.844→6.056pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/v-stem.layout.yaml · slide-no-title | better | 5.904→6.269pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/v-three.layout.yaml · document | better | 5.164→5.474px | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/v-three.layout.yaml · slide | better | 4.927→5.100pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/v-three.layout.yaml · slide-no-title | better | 5.518→5.712pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/x-fork-b.layout.yaml · slide | better | 5.649→5.969pt | 규칙을 보존한 두 번의 작은 font 확대 |
| trunk/x-fork-b.layout.yaml · slide-no-title | better | 5.904→6.269pt | 규칙을 보존한 두 번의 작은 font 확대 |
| qa/t3-nat-route-table.layout.yaml · document | better | 12.000→12.000px | 중간 moved violation을 채택하지 않고 완료한 경로를 비교; 규칙/check/fit 개선 |
| qa/t1-multiregion-dr.layout.yaml · slide | worse | 3.496→3.662pt | 목표 미만 후속 축소 거부; 기존 F2 보존 |
| qa/t1-multiregion-dr.layout.yaml · slide-no-title | worse | 3.496→3.662pt | 목표 미만 후속 축소 거부; 기존 F2 보존 |
| qa/t3-hybrid-dns.layout.yaml · slide | worse | 5.651→6.264pt | 새 F3 및 후속 축소를 거부; 기존 F3/F5 보존 |
| qa/t3-hybrid-dns.layout.yaml · slide-no-title | worse | 5.651→6.264pt | 새 F3 및 후속 축소를 거부; 기존 F3/F5 보존 |

### 36c7ea3 identity·글자 감사

새 tier-0 identity run: **0개** — 목록 없음. 목표 미만이면서 글자가 작아진 run: **3개**.

| Case × mode | 전→후 | 근거 |
|---|---|---|
| bench/v2-3-egress.layout.yaml · document | 7.502056→7.294055px | 후보 단계, 기본 크기의 97.23% 유지; 기존 90% 결정에 따라 허용 |
| qa/t1-privatelink.layout.yaml · slide | 6.398104→5.919915pt | 후보 단계, 기본 크기의 92.53% 유지; 기존 90% 결정에 따라 허용 |
| qa/t1-multiregion-dr.layout.yaml · document | 2.972621→2.839352px | 후보 단계, 기본 크기의 95.52% 유지; 기존 90% 결정에 따라 허용 |

이 3건을 step 2와 무관하다고 주장하지 않는다. 모두 허용된 후보 단계의 축소이며, 특히 multiregion document 승자 유지가 티켓의 명시 조건이다. 금지한 후속 repair 축소와 구별한다. 잔여를 모두 “step 2와 무관”으로 설명하라는 완료 문구를 엄격히 적용하면 이 부분은 미완료다.

### PNG 직접 판정

`png/qa__t3-hybrid-dns.layout.yaml.slide.{36c7ea3,3946906}-pair.png`와 `png/qa__t1-multiregion-dr.layout.yaml.slide.{36c7ea3,3946906}-pair.png` 네 장을 이미지 보기 도구로 직접 확인했다. Before/after 원본은 `png/{36c7ea3,3946906,after}/`에 있다. PNG에 쓴 after SVG 두 장은 마지막 부분 재검증과 바이트 동일함을 확인했다.

- DNS: AZ1 Inbound ENI 앞 새 접점 오독을 없애고 VGW 옆 원래 접점으로 돌아왔다. UDP/TCP :53 라벨의 기존 귀속 문제는 남는다. **5.651→6.264pt**, 36c7ea3의 크기를 보존한다. CIDR/IP와 범례는 여전히 작고 F3/F5 때문에 전체 전달 판정은 차단 유지다.

- Multiregion: 복제선과 badge는 SQL/NLB 요청선에서 분리된 개선을 유지한다. DNS 제어선과 앱 요청선의 기존 F2는 남는다. **3.496→3.662pt**, 이전 크기를 보존하지만 실제 slide 크기에서 읽기에는 너무 작아 전달 판정은 차단 유지다.

### 완료 체크

- [x] CLI 3건 먼저 red 후 green: `red.log`, 전체 pytest와 마지막 CLI corpus의 크기/identity 기록

- [x] DNS 두 mode 6.264pt 및 새 identity 0, multiregion slide 3.661823pt

- [x] 두 기준의 rule/check/판정/시간과 변경 run: 위 표 및 final-audit.json

- [ ] 36c7ea3 잔여의 엄격한 “step 2와 무관” 조건: 허용된 후보 축소 3건은 관련 있으므로 명시적으로 남김

- [x] R-flow 48≤50, shared-lane 두 mode 및 multiregion document R-flow 0 유지

- [ ] 시간: 현재 main 기준 3×/30s 통과; 36c7ea3 기준 3× 초과 사례 및 최종 전체 wall 검증은 남음

- [x] spec.md와 GLOSSARY.md에 identity 및 후속 text gate 명시

- [ ] 마지막 경계/경로 수정 후 전체 pytest·예제 재실행: 시간 제한으로 미완료

남은 시간 3× 초과 목록(36c7ea3 기준):

- bench/engine2-egress.layout.yaml · slide: 1.387→4.628s, 3.337×
- bench/engine2-egress.layout.yaml · slide-no-title: 1.347→4.565s, 3.389×
- ports/xnt.layout.yaml · slide: 2.367→9.36s, 3.954×
- ports/xnt.layout.yaml · slide-no-title: 2.349→9.503s, 4.046×

기본 index가 read-only여서 별도 index와 commit-tree로 직접 t10-gate에 커밋한다. **index 동기화 필요**. 별도 index 기준 HEAD diff의 빈 출력을 확인한다.
