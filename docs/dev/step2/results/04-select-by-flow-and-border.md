# Ticket 04 validation

브랜치: `t04-select`. 기준: `main-cc17a2d.json`과 `main-cc17a2d-drafts/`.
시작 HEAD는 `4aab3b3`이며 기준과 Draft가 같다. 기준과 다른 multiregion DR
태그는 시작 worktree의 Mode별 태그를 사용했다.

## 완료 조건

- [x] Verdict 순서: tier-0 개수, 비용, Check problem, effective text shortfall,
  shape misses, canvas area. `scripts/rules.py:874`가 순서를 정의하며
  `scripts/layout.py:197`이 호출한다. 선택의 tier-0는 R-border와 R-flow만
  포함하고 R-fit은 항상 포함한다. Shortfall은 반올림하지 않는다.
- [x] 예산: 기본 Candidate와 Text scale tries를 제외한 이웃 Candidate가
  document 최대 12, slide 최대 16이다 (`scripts/layout.py:85`, `:1519`, `:1572`).
  CLI 테스트도 두 Mode의 요약에 표시된 예산을 확인한다 (`tests/test_select.py:43`, `:88`).
- [x] 결정성: 선택되는 Spec을 두 번 실행해 Draft와 선택 요약이 동일하다
  (`tests/test_select.py:43`). Examples 21개도 반복 실행이 byte-identical이다.
- [x] Corpus: 760 runs, worse 0, better 84, same 676. 기대 결과 불일치 0.
- [x] 시작 시점 R-border/R-flow bad-tagged Case 13개를 아래에 모두 기록했다.
  태그가 적용된 Mode의 해당 Rule Violation 합계는 42→27이다.
- [x] 고쳐진 태그는 이유를 기록했다. 세 Case는 모든 Mode가 통과하여 good으로,
  두 Case는 document만 통과하여 bad를 두 slide Mode에만 남겼다.
- [x] Check problem은 385→375이며, 증가한 Case·Mode는 0이다.
- [x] 바뀐 Draft 84개 모두 better Verdict이며 아래에 전부 기록했다.
- [ ] Runtime의 **동일 병렬도 조건**: 기준 JSON은 `jobs: 6`, 이번 실행은 요청대로
  `-j 4`이다. 제공된 기준 대비 수치 한도는 모두 통과했다: 최대 2.668×,
  최악 19.361 s, wall 2.149×. 그러나 같은 `-j 4` 기준의 측정은 없으므로
  병렬도까지 동일한 조건이라고 단정하지 않는다. 변경 엔진의 전체 Corpus는 1회다.
- [x] 태그는 증거로만 변경했다. Retag 전 불일치 9건을 같은 760-run 결과로
  재판정하여 0건을 확인했다. 엔진을 다시 실행하거나 시간 수치를 바꾸지 않았다.
- [x] CLI 요약은 Candidate index, 기본값과 다른 decisions, 제거한 Violation을
  표시하고 마지막 Rule Violation 집계 줄을 유지한다 (`tests/test_select.py:43`, `:88`).
- [x] 기본값이 이미 최선이면 Draft가 그대로다 (`tests/test_select.py:28`).
- [x] Hard placement를 유지하고 경고한다 (`tests/test_select.py:88`,
  `scripts/layout_route.py:115`, `scripts/layout.py:1460`).
- [x] Checker의 check/score 실패와 새 Draft에서의 늦은 실패 모두 기본값으로
  복귀하고 오류를 한 번 보고한다 (`tests/test_select.py:64`, `:102`).

## 구현

`scripts/layout.py:1398`에서 Violation을 `(tier, rule, owners, code, message)`로
정렬하고 이웃을 만든다. R-flow의 각 edge와 R-border의 edge는 다음 **서로 다른**
routing alternative를 선택한다. 현재 선·중복 선을 제외한 티켓 02의 대안을 사용하므로
같은 선의 raw skip index가 중간에 있어도 이웃을 놓치지 않는다.
R-fit은 모든 open diagonal pair를 x로 두거나 auto Note의 다른 place를 시도한다.
Spec이 고정한 placement는 이웃에 포함하지 않는다.

`scripts/layout.py:1488`은 결정적 best-improvement hill-climb이다. 엄격히 더 좋은
Verdict만 유지하고 동점은 이전 Candidate를 유지한다. 규칙을 먼저 판정하여
tier-0가 더 나쁜 Candidate는 drawing check를 생략한다 (`:1557`).
Skip만 바꾸면 이미 푼 Geometry와 Note/raw elements를 재사용한다 (`:1433`).
대안 수집도 관련된 edge만 요청한다 (`scripts/layout_route.py:2425`).

기존의 완성된 기본 Draft를 비교에 남기고, 그 solve와 check 결과를 재사용하여
첫 렌더부터 feedback, fixed-answer repair, Text scale을 Verdict로 판정한다
(`scripts/layout.py:1218`, `:1346`, `:1498`). 따라서 미완성 round로 돌아가
Check problem을 늘리는 결과는 쓰지 않는다. 선택되지 않은 Rule도 전체 Verdict로
보호하며, Check problem 수가 증가한 결과는 쓰지 않는다.
선택된 Candidate의 뒤 단계도 Verdict로 비교한다.

후보 판정의 fixed-answer pass는 `Advisor.plan(auto_only=True)`를 사용한다.
자동 수리가 없는 수동 위치 제안의 trial을 생략하여 비용을 줄이고 마지막 CLI
보고에서는 기존 제안을 계산한다 (`scripts/check_layout.py:1650`, `:2593`).
SMALL TEXT 수리는 적용하고 수동 LINE ON LINE은 유지하는 테스트를 먼저 red로
확인했다 (`tests/test_check_layout.py:38`).

Step 3 삭제 검토 대상: `layout.build_at_size`의 기존 slide all-x retry는
R-fit 이웃이 같은 선택을 제공한다. 기본 Draft의 호환성을 위해 이번에는 유지한다.
R-rt 이웃 생성이나 티켓 05의 unfixable spec-change 경고는 추가하지 않았다.

## 검증

- Pytest: **757 passed, 2539 subtests passed**, 117.13 s.
- 최종 CLI 선택 테스트: **6 passed**, 2.00 s.
- Examples: **21 all PASS, 0 FAIL, 0 SKIP**. 생성, 반복 결정성, check, export,
  기존 Golden 구조 비교 모두 통과했다. Golden은 변경하지 않았다.
- CLI 테스트를 구현 전에 작성하여 요약·승리 후보·하드 경고·checker 실패의
  실패를 확인했다. 자동 수리 최적화 테스트도 구현 전에 red를 확인했다.
- 전체 Corpus는 다른 테스트·렌더와 겹치지 않게 `-j 4`로 1회 실행했다.
  Python 3.15의 forkserver socket bind가 sandbox에서 거절되어 runner 수정 없이
  `multiprocessing.set_start_method("fork")`로 실행했다.

재현 명령:

```bash
export TMPDIR="$HOME/.cache/codex-t04-select-tmp"
mkdir -p "$TMPDIR"
export UV_OFFLINE=1
uv run --offline --no-project --with pyyaml --with python-pptx --with cairosvg --with pytest pytest -q tests -p no:cacheprovider
uv run --offline --no-project --with pyyaml --with python-pptx --with cairosvg python3 tests/test_examples.py --keep "$HOME/.cache/skill-design/t04-select/examples"
uv run --offline --no-project --with pyyaml --with cairosvg python3 -c 'import multiprocessing, runpy; multiprocessing.set_start_method("fork"); runpy.run_path("tests/run_corpus.py", run_name="__main__")' --rule-checker scripts/rules.py:corpus --keep "$HOME/.cache/skill-design/t04-select/drafts" --out "$HOME/.cache/skill-design/t04-select/corpus.json" --baseline "$HOME/.cache/skill-design/baseline/main-cc17a2d.json" --baseline-drafts "$HOME/.cache/skill-design/baseline/main-cc17a2d-drafts" -q -j 4
```

결과는 `~/.cache/skill-design/t04-select/`에 있다:
`corpus.json`, `audit.json`, `retag.json`, `pytest-green.log`, `select-green.log`,
`examples.log`, `red.log`, `auto-red.log`, `corpus-before-retag.log`.
`corpus.json`은 태그 갱신 전 불일치도 `tag_misses_before_retag`에 보존한다.

## PNG 직접 확인

`~/.cache/skill-design/t04-select/png/`의 아래 pair PNG를 이미지 보기 도구로
직접 확인했다. 왼쪽은 기준, 오른쪽은 변경 후다.

| PNG | 확인 |
|---|---|
| bedrock-dx-reference-architecture-slide-pair.png | Note가 아래의 긴 lines에서 왼쪽 pane으로 옮겨져 text shortfall이 줄었다. DX/VGW/endpoint/Bedrock Flow는 유지된다. 여전히 R-fit이 남는다. |
| bedrock-dx-reference-architecture-slide-no-title-pair.png | 같은 Flow와 Note 변화이며 untitled의 Effective text size도 개선된다. |
| nlb-reference-architecture-document-pair.png | IGW→NLB→ASG, NAT outbound와 두 AZ를 유지하면서 세로 면적을 줄였다. |
| tgw-reference-architecture-document-pair.png | VPN/TGW peering/VPC attachment와 RT Association을 유지한다. 글자 확대 때문에 아이콘이 상대적으로 작아지고 shape misses가 0→6이지만 Rule/Check problem은 0이다. |
| gwlb-reference-architecture-document-pair.png | Note를 아래 panel로 옮겨 글자가 커지고 IGW/GWLBe/GWLB/firewall Flow와 badges를 유지한다. |
| merge-v3az-document-pair.png | ALB fan의 bend 옆 crossing이 사라지고 각 EC2→CloudWatch Flow가 유지된다. |
| t9-tmpl-on-flowcol-document-pair.png | 겹치던 두 EC2→CloudWatch 선이 별도 lane을 사용한다. |
| t4-shared-lane-slide-pair.png | “5회 실패 후 이동”이 Queue→DLQ의 dashed line 가까이에 배치되어 SNS→Mail과 구별된다. |
| t1-privatelink-slide-pair.png | 일부 false junction/attribution은 줄었지만 기존 Check problem 7개, R-border와 R-flow가 남는다. Text shortfall도 악화된다. 전체 Verdict는 tier-0 6→3으로 개선되지만 전달용으로는 추가 수리가 필요하다. |

Native Bedrock/DX 예제 PNG도 직접 확인했다:
`~/.cache/skill-design/t04-select/examples/bedrock-dx-reference-architecture/out/bedrock-dx-reference-architecture.png`.
변경된 example Mode 5개 전부의 pair가 있으며 `png-pairs.json`에 경로를 기록했다.
이 확인은 작성자의 검증이며, 별도 Codex 리뷰나 Golden 교체는 하지 않았다.

## Corpus 비교

| 항목 | 기준 | 변경 후 |
|---|---:|---:|
| R-border Violation | 17 | 17 |
| R-flow Violation | 74 | 45 |
| R-rt Violation | 94 | 90 |
| R-twin Violation | 6 | 6 |
| R-label Violation | 2 | 2 |
| R-fit Violation | 298 | 298 |
| Check problem | 385 | 375 |
| 시간 중앙값 (s, 744 Draft) | 0.1975 | 0.184 |
| 시간 최악 (s, 744 Draft) | 17.145 | 19.361 |
| 시간 합계 (s, 744 Draft) | 655.919 | 956.023 |
| 시간 합계 (s, 760 runs) | 655.99 | 956.1 |
| Corpus wall (s) | 112.71 | 242.24 |
| better / same / worse | — | 84 / 676 / 0 |
| 바뀐 Draft | — | 84 / 744 |

최대 시간 비율은 `ports/xnt · slide`의 2.668× (2.583→6.891 s), 최악 시간은
`qa/t1-multiregion-dr · slide`의 19.361 s (기준 17.145 s)다. 3× 초과와
30 s 초과는 모두 0이다. 전체 wall은 112.71→242.24 s (2.149×), summed runtime은
655.99→956.10 s (1.457×)다. 기준 `-j 6` / 변경 `-j 4` 차이는 위의 미확인 조건에 남겼다.

R-border는 17건 그대로이고 R-flow는 74→45다. R-rt의 94→90은 배치·경로 변경의
부수 결과다. R-rt를 tier-0 선택 그룹에 넣거나 그 Rule의 이웃을 만들지는 않았다.

## 시작 시점 bad-tagged Case 전체

D=document, S=slide, U=slide-no-title. 숫자는 해당 Rule의 Violation 수이며
`—`는 시작 태그가 적용되지 않은 Mode다. 태그 갱신 전에 저장한 집합으로 비교한다.

| Case | Rule | D | S | U |
|---|---|---:|---:|---:|
| trunk/merge-v3az | R-flow | 1→0 | 1→1 | 1→1 |
| trunk/merge-v3az-top | R-flow | 1→0 | 1→1 | 1→1 |
| flowcol/t9-tmpl-on-flowcol | R-flow | 1→0 | 1→0 | 1→0 |
| ports/u3 | R-flow | 1→1 | 1→1 | 1→1 |
| lanes/a | R-flow | — | 1→1 | 1→1 |
| sides/xy3 | R-flow | 1→1 | 1→1 | 1→1 |
| ports/g1 | R-flow | — | 1→1 | 1→1 |
| qa/t3-cache-label | R-flow | — | 2→1 | 2→1 |
| qa/t1-multiregion-dr | R-flow | 3→0 | — | — |
| qa/t4-shared-lane | R-flow | 1→0 | 1→0 | 1→0 |
| qa/t3-hybrid-dns | R-flow | 1→1 | 2→1 | 2→1 |
| qa/t4-order-14steps | R-flow | — | 3→3 | 3→3 |
| qa/t2-alb-trunk-header | R-border | — | 1→1 | 1→1 |

**해당 태그·Mode 합계: 42→27.** 일부 Violation이 줄어도 Rule이 남는 Case는 bad를 유지한다.

태그 변경 근거:

- `flowcol/t9-tmpl-on-flowcol`: D/S/U F1 1→0; good R-flow (`MANIFEST.yaml:401`).
- `qa/t1-multiregion-dr`: D의 F3/F5 3→0, S/U 0 유지; good R-flow (`MANIFEST.yaml:1097`). R-twin과 R-fit은 남는다.
- `qa/t4-shared-lane`: D/S/U F5 1→0; good R-flow (`MANIFEST.yaml:1104`).
- `trunk/merge-v3az`와 `merge-v3az-top`: D의 F3 1→0, S/U 1 유지; bad를 S/U에만 남김 (`MANIFEST.yaml:249`, `:254`).

## 바뀐 Draft 전체

모두 `better`다. 아래 tuple은 `(tier-0 개수, 비용, Check problem 수, text shortfall, shape misses, 면적)`이다.
가독성을 위해 여기의 소수는 6자리 유효숫자로 표시하며 원래 정밀도는 `corpus.json`에 있다.

| Case · Mode | 기준 Verdict → 변경 Verdict |
|---|---|
| bench/engine1-egress.layout.yaml · document | (4, 476.5, 0, 3.53682, 0, 1.00302e+07) → (4, 476.5, 0, 3.47111, 0, 1.0197e+07) |
| bench/engine1-egress.layout.yaml · slide-no-title | (4, 408.46, 1, 2.9399, 0, 6.59253e+06) → (4, 381.94, 1, 2.61277, 0, 6.24982e+06) |
| bench/engine2-egress.layout.yaml · slide | (2, 2, 1, 4.93433, 0, 1.57555e+06) → (2, 2, 1, 3.86997, 1, 3.76456e+06) |
| bench/engine2-egress.layout.yaml · slide-no-title | (2, 2, 1, 4.32645, 0, 1.57555e+06) → (2, 2, 1, 3.33921, 1, 3.58002e+06) |
| bench/latest1-egress.layout.yaml · slide | (2, 2, 1, 4.85714, 0, 1.6254e+06) → (2, 2, 1, 4.17647, 0, 1.72883e+06) |
| bench/latest1-egress.layout.yaml · slide-no-title | (2, 2, 1, 4.24, 0, 1.6254e+06) → (2, 2, 1, 4.17647, 0, 1.72883e+06) |
| bench/latest2-egress.layout.yaml · slide | (2, 2, 1, 3.9301, 0, 3.76109e+06) → (2, 2, 1, 3.86997, 1, 3.72419e+06) |
| bench/latest3-egress.layout.yaml · slide | (4, 543.8, 1, 3.57391, 0, 9.31464e+06) → (4, 522.34, 1, 3.49101, 1, 9.19601e+06) |
| bench/v2-2-egress.layout.yaml · slide | (4, 219.78, 1, 4.97207, 0, 1.56589e+06) → (4, 203.78, 1, 4.1048, 1, 1.64697e+06) |
| bench/v2-2-egress.layout.yaml · slide-no-title | (4, 219.78, 1, 4.36872, 0, 1.56589e+06) → (4, 203.78, 1, 3.83315, 1, 1.64697e+06) |
| bench/engine3-pipeline.layout.yaml · document | (1, 3.43, 0, 6.44456, 0, 2.72072e+06) → (0, 0, 0, 6.44456, 1, 2.72072e+06) |
| bench/engine3-pipeline.layout.yaml · slide | (1, 8, 1, 5.26731, 0, 2.08118e+06) → (0, 0, 1, 5.26731, 1, 2.08118e+06) |
| bench/engine3-pipeline.layout.yaml · slide-no-title | (1, 8, 1, 4.69939, 0, 2.08118e+06) → (0, 0, 1, 4.69939, 1, 2.08118e+06) |
| bench/latest3-pipeline.layout.yaml · slide | (1, 2, 1, 5.00463, 0, 1.7977e+06) → (0, 0, 1, 4.96738, 1, 1.81015e+06) |
| bench/latest3-pipeline.layout.yaml · slide-no-title | (1, 2, 1, 4.40518, 0, 1.7977e+06) → (0, 0, 1, 4.36347, 1, 1.81015e+06) |
| trunk/eng-egress-tgw.layout.yaml · slide | (0, 0, 1, 4.93433, 0, 1.62245e+06) → (0, 0, 1, 4.15584, 0, 1.73527e+06) |
| trunk/eng-egress-tgw.layout.yaml · slide-no-title | (0, 0, 1, 4.32645, 0, 1.62245e+06) → (0, 0, 1, 4.09585, 0, 1.73527e+06) |
| slide-fit/nfw-slide.layout.yaml · slide | (0, 0, 1, 0.105437, 0, 678626) → (0, 0, 1, 0.105437, 0, 677412) |
| slide-fit/nfw-slide.layout.yaml · slide-no-title | (0, 0, 1, 0.105437, 0, 678626) → (0, 0, 1, 0.105437, 0, 677412) |
| slide-fit/nfw-t.layout.yaml · slide | (0, 0, 1, 0.117647, 0, 611490) → (0, 0, 1, 0.117647, 0, 603636) |
| slide-fit/nfw-t.layout.yaml · slide-no-title | (0, 0, 1, 0.117647, 0, 611490) → (0, 0, 1, 0.117647, 0, 603636) |
| rt/ce-three.layout.yaml · document | (0, 0, 0, 6.73832, 0, 3.20572e+06) → (0, 0, 0, 5.92205, 0, 3.01369e+06) |
| rt/right.layout.yaml · document | (0, 0, 0, 4.94824, 0, 934340) → (0, 0, 0, 3.83582, 0, 987848) |
| rt/wide-a.layout.yaml · slide | (0, 0, 1, 0.0972795, 0, 679280) → (0, 0, 1, 0.0972795, 0, 678067) |
| rt/wide-a.layout.yaml · slide-no-title | (0, 0, 1, 0.0972795, 0, 679280) → (0, 0, 1, 0.0972795, 0, 678067) |
| trunk/merge-v3az.layout.yaml · document | (1, 1, 0, 0, 0, 825804) → (0, 0, 0, 0, 0, 825804) |
| trunk/merge-v3az.layout.yaml · slide | (1, 1, 1, 1.24324, 2, 652125) → (1, 1, 1, 1.05114, 2, 422400) |
| trunk/merge-v3az-top.layout.yaml · document | (1, 1, 0, 0, 0, 825804) → (0, 0, 0, 0, 0, 825804) |
| trunk/merge-v3az-top.layout.yaml · slide | (1, 1, 1, 1.24324, 2, 666925) → (1, 1, 1, 1.05114, 2, 422400) |
| flowcol/r2-pin-bottom.layout.yaml · slide | (0, 0, 1, 2.44604, 2, 518748) → (0, 0, 1, 1.81818, 2, 478940) |
| flowcol/r2-pin-bottom.layout.yaml · slide-no-title | (0, 0, 1, 1.53957, 2, 518748) → (0, 0, 1, 0.561798, 2, 510237) |
| flowcol/t7-xyref.layout.yaml · slide | (0, 0, 2, 0, 0, 333564) → (0, 0, 1, 0, 0, 363660) |
| flowcol/t7-xyref.layout.yaml · slide-no-title | (0, 0, 2, 0, 0, 333564) → (0, 0, 1, 0, 0, 363660) |
| flowcol/t9-tmpl-on-flowcol.layout.yaml · document | (1, 288, 1, 0, 0, 665532) → (0, 0, 0, 0, 0, 665532) |
| flowcol/t9-tmpl-on-flowcol.layout.yaml · slide | (1, 258, 2, 2.22222, 0, 430920) → (0, 0, 1, 2.22222, 1, 430920) |
| flowcol/t9-tmpl-on-flowcol.layout.yaml · slide-no-title | (1, 258, 2, 1.28889, 0, 430920) → (0, 0, 1, 1.28889, 1, 430920) |
| twin/sub.layout.yaml · slide | (1, 1, 4, 0.297254, 0, 726706) → (1, 1, 4, 0.297254, 0, 714326) |
| twin/sub.layout.yaml · slide-no-title | (1, 1, 4, 0.297254, 0, 726706) → (1, 1, 4, 0.297254, 0, 714326) |
| twin/three.layout.yaml · slide | (1, 1, 4, 0.297254, 0, 724230) → (1, 1, 4, 0.297254, 0, 711850) |
| twin/three.layout.yaml · slide-no-title | (1, 1, 4, 0.297254, 0, 724230) → (1, 1, 4, 0.297254, 0, 711850) |
| ports/xnt.layout.yaml · slide | (3, 14, 2, 4.85714, 3, 1.5309e+06) → (0, 0, 1, 4.35146, 1, 1.79537e+06) |
| ports/xnt.layout.yaml · slide-no-title | (3, 14, 2, 4.24, 3, 1.5309e+06) → (0, 0, 1, 4.09585, 1, 1.79537e+06) |
| twin/v-firstonly.layout.yaml · document | (0, 0, 0, 0.219858, 0, 467838) → (0, 0, 0, 0.219858, 0, 458532) |
| rt/gw-ret.layout.yaml · document | (0, 0, 3, 3.51846, 2, 975200) → (0, 0, 2, 4.36727, 2, 1.03262e+06) |
| rt/gw-ret.layout.yaml · slide | (0, 0, 6, 2.35127, 3, 886030) → (0, 0, 5, 2.68293, 3, 1.03837e+06) |
| rt/gw-ret.layout.yaml · slide-no-title | (0, 0, 6, 1.43343, 3, 886030) → (0, 0, 5, 2.1194, 3, 1.03837e+06) |
| rt/hub.layout.yaml · slide | (0, 0, 1, 0.25, 0, 704704) → (0, 0, 1, 0.25, 0, 691152) |
| rt/hub.layout.yaml · slide-no-title | (0, 0, 1, 0.25, 0, 704704) → (0, 0, 1, 0.25, 0, 691152) |
| rt/rtcol.layout.yaml · slide | (0, 0, 1, 0.1, 0, 610400) → (0, 0, 1, 0.1, 0, 602560) |
| rt/rtcol.layout.yaml · slide-no-title | (0, 0, 1, 0.1, 0, 610400) → (0, 0, 1, 0.1, 0, 602560) |
| rt/rtsub.layout.yaml · slide | (0, 0, 1, 0.281553, 0, 725532) → (0, 0, 1, 0.281553, 0, 710700) |
| rt/rtsub.layout.yaml · slide-no-title | (0, 0, 1, 0.281553, 0, 725532) → (0, 0, 1, 0.281553, 0, 710700) |
| rt/three.layout.yaml · slide | (0, 0, 1, 2.43697, 0, 798252) → (0, 0, 1, 2.37414, 0, 1.00617e+06) |
| trunk/ce-tgw.layout.yaml · slide | (0, 0, 1, 4.93433, 0, 1.62245e+06) → (0, 0, 1, 4.15584, 0, 1.73527e+06) |
| trunk/ce-tgw.layout.yaml · slide-no-title | (0, 0, 1, 4.32645, 0, 1.62245e+06) → (0, 0, 1, 4.09585, 0, 1.73527e+06) |
| trunk/v-fork.layout.yaml · document | (0, 0, 3, 6.18479, 0, 2.34856e+06) → (0, 0, 3, 6.10204, 1, 2.27909e+06) |
| trunk/v-fork.layout.yaml · slide | (0, 0, 4, 5.00924, 0, 1.78963e+06) → (0, 0, 4, 4.34862, 2, 1.7815e+06) |
| trunk/v-fork.layout.yaml · slide-no-title | (0, 0, 4, 4.41035, 0, 1.78963e+06) → (0, 0, 4, 4.24, 2, 1.6863e+06) |
| trunk/v-stem.layout.yaml · slide | (0, 0, 1, 4.93433, 0, 1.62245e+06) → (0, 0, 1, 4.15584, 0, 1.73527e+06) |
| trunk/v-stem.layout.yaml · slide-no-title | (0, 0, 1, 4.32645, 0, 1.62245e+06) → (0, 0, 1, 4.09585, 0, 1.73527e+06) |
| trunk/v-three.layout.yaml · document | (0, 0, 0, 6.67773, 0, 2.63328e+06) → (0, 0, 0, 5.83579, 0, 2.52185e+06) |
| trunk/v-three.layout.yaml · slide | (0, 0, 1, 5.63813, 0, 1.88424e+06) → (0, 0, 1, 5.07299, 0, 2.05829e+06) |
| trunk/v-three.layout.yaml · slide-no-title | (0, 0, 1, 5.1147, 0, 1.88424e+06) → (0, 0, 1, 4.48175, 0, 2.05829e+06) |
| trunk/x-fork-b.layout.yaml · slide | (0, 0, 1, 5.08197, 0, 1.67116e+06) → (0, 0, 1, 4.35146, 0, 1.79537e+06) |
| trunk/x-fork-b.layout.yaml · slide-no-title | (0, 0, 1, 4.4918, 0, 1.67116e+06) → (0, 0, 1, 4.09585, 0, 1.79537e+06) |
| rt/withsn.layout.yaml · slide | (0, 0, 1, 0.117647, 0, 611490) → (0, 0, 1, 0.117647, 0, 603636) |
| rt/withsn.layout.yaml · slide-no-title | (0, 0, 1, 0.117647, 0, 611490) → (0, 0, 1, 0.117647, 0, 603636) |
| qa/t3-dns-trunk.layout.yaml · document | (1, 5.55, 0, 0, 0, 451792) → (0, 0, 0, 0, 1, 451792) |
| qa/t1-privatelink.layout.yaml · slide | (6, 79.8, 7, 3.6019, 4, 1.29723e+06) → (3, 67, 7, 4.08009, 4, 1.62576e+06) |
| qa/t1-privatelink.layout.yaml · slide-no-title | (6, 79.8, 7, 2.83412, 4, 1.29723e+06) → (3, 67, 7, 4.08009, 4, 1.62576e+06) |
| qa/t3-cache-label.layout.yaml · slide | (2, 10.6, 0, 0, 1, 297600) → (1, 5, 0, 0, 1, 312960) |
| qa/t3-cache-label.layout.yaml · slide-no-title | (2, 10.6, 0, 0, 1, 297600) → (1, 5, 0, 0, 1, 312960) |
| qa/t1-multiregion-dr.layout.yaml · document | (5, 29, 0, 8.02738, 2, 3.2214e+06) → (2, 14, 0, 8.16065, 2, 3.47538e+06) |
| qa/t4-shared-lane.layout.yaml · document | (1, 5, 0, 0, 1, 235248) → (0, 0, 0, 0, 1, 286704) |
| qa/t4-shared-lane.layout.yaml · slide | (1, 9, 0, 0, 1, 171456) → (0, 0, 0, 0, 1, 232512) |
| qa/t4-shared-lane.layout.yaml · slide-no-title | (1, 9, 0, 0, 1, 171456) → (0, 0, 0, 0, 1, 232512) |
| qa/t3-hybrid-dns.layout.yaml · slide | (2, 4.2, 1, 4.34862, 3, 1.77365e+06) → (1, 1, 1, 4.34862, 4, 1.6834e+06) |
| qa/t3-hybrid-dns.layout.yaml · slide-no-title | (2, 4.2, 1, 4.34862, 3, 1.77365e+06) → (1, 1, 1, 4.34862, 4, 1.6834e+06) |
| qa/t2-alb-trunk-header.layout.yaml · document | (0, 0, 0, 2.11977, 0, 667550) → (0, 0, 0, 0.308324, 0, 646574) |
| ../../docs/examples/specs/bedrock-dx-reference-architecture.layout.yaml · slide | (1, 1, 1, 5.64516, 0, 1.76204e+06) → (1, 1, 1, 5.08197, 0, 1.56026e+06) |
| ../../docs/examples/specs/bedrock-dx-reference-architecture.layout.yaml · slide-no-title | (1, 1, 1, 5.12258, 0, 1.76204e+06) → (1, 1, 1, 4.4918, 0, 1.56026e+06) |
| ../../docs/examples/specs/nlb-reference-architecture.layout.yaml · document | (0, 0, 0, 0.307359, 0, 779856) → (0, 0, 0, 0.307359, 0, 766920) |
| ../../docs/examples/specs/tgw-reference-architecture.layout.yaml · document | (0, 0, 0, 4.13253, 0, 788832) → (0, 0, 0, 3.26463, 6, 2.86929e+06) |
| ../../docs/examples/specs/slides/gwlb-reference-architecture.layout.yaml · document | (0, 0, 0, 0.866667, 1, 1.69568e+06) → (0, 0, 0, 0.183168, 1, 1.97475e+06) |

## Git metadata

기본 index의 `index.lock` 생성이 read-only file system으로 거절됐다.
별도 `GIT_INDEX_FILE`과 `commit-tree`로 `t04-select`에 직접 커밋한다.
기본 **index 동기화 필요**. 임시 디렉터리는 결과·로그·PNG를 보존한 뒤 삭제한다.
