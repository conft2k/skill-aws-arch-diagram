# Ticket 06 review fix: 실제 글자 크기 10% 축소 한도

이 문서는 목표 이상인 글자의 예외를 도입하기 전 기록이다.
최신 결과와 gw-ret 가림 조사는 [목표 크기 예외 검증](06-target-size-exception.md)에 있다.

main `af80829`(티켓 05) 위로 `git rebase main`을 먼저 수행했다. 충돌은 없었고 기존 06 커밋은 `93df8a5`가 됐다. 기본 worktree git 메타데이터가 읽기 전용이라 작업 파일은 같은 worktree에 두고 임시 git-dir/공유 common-dir로 실제 rebase했다. 티켓 05의 `spec_fix`·unresolved 경고와 메시지 코드는 유지했다.

기준은 요청한 main `511fd73`의 `~/.cache/skill-design/baseline/main-511fd73.json`과 `main-511fd73-drafts/`다. 이번 수정의 전체 corpus는 **1회**, 기준과 같은 **-j 6**으로 실행했다. Corpus 동안 이 작성자의 pytest·예제·렌더는 겹치지 않았다.

## 수정과 완료 조건

- [x] 실제 재현을 먼저 테스트했다. nd-single과 benchmark 문서 3건, 세 활성 규칙 그룹의 10% 초과 경계가 기존 코드에서 **7 failed / 3 passed**였다 (`red.log`). 정확히 90%는 허용하고 89.9%는 거부하는 테스트다. 구현 후 선택 테스트 **22 passed**였다 (`select-green.log`).
- [x] 모든 규칙 그룹에 같은 90% 하한을 적용한다. `scripts/layout.py:86`, `:227`, `:1755`: 기존 `drawn_text`의 effective text size를 최초 완성된 default에서 재고 하한을 고정한다. 후보·이전 그룹 탐색·후속 feedback/header/fixed-answer/text-scale 검사가 같은 하한을 공유하므로 여러 번 조금씩 작아져도 총 10%를 넘을 수 없다.
- [x] `docs/dev/step2/spec.md:66` Search, `:67` Verdict와 `GLOSSARY.md:118` Candidate에 이 admission limit를 반영했다. 기존 verdict tuple의 순서는 유지했다.
- [x] pytest 전체 **786 passed, 2542 subtests passed**, 179.05초. 티켓 05의 경고 테스트도 포함한다. 예제 **21 all PASS / 0 FAIL / 0 SKIP**이다. Golden은 바꾸지 않았다.
- [x] 전체 corpus의 (a) 기존 06 변경 10건, (b) 04 승자의 되돌림 수·목록·이유, (c) 규칙/check/시간 전후를 아래에 기록했다. 글자 하한 위반 0, 관련 없는 worse 0, 새 clipping 0이다.

## 글자 회귀 재현의 전후

| Document Case | 기준(04) px | 리뷰 전(06) px | 수정 후 px | 기본 그림 대비 유지율 |
|---|---:|---:|---:|---:|
| `bench/engine1-egress.layout.yaml` | 7.529 | 5.494 | 7.529 | 100.88% |
| `bench/v2-2-egress.layout.yaml` | 7.400 | 5.302 | 7.400 | 100.00% |
| `bench/v2-3-egress.layout.yaml` | 7.502 | 5.343 | 7.294 | 97.23% |
| `rt/nd-single.layout.yaml` | 7.927 | 5.805 | 7.927 | 100.00% |

nd-single은 기본 그림으로 돌아가 RT2가 다시 1건 남는다. 기존 RT2 제거 테스트는 새 정책에 맞춰 기본 Draft 보존·반복 결정성·RT2 잔존을 검증하도록 바꿨고 document bad 태그도 복원했다. Benchmark 문서에서는 engine1/v2-2가 기준으로 돌아가고 v2-3은 기준 대비 글자 크기 **−2.77%**인 다른 후보를 선택했다.

완성된 Draft **744개**의 기본 그림과 최종 effective text size를 모두 저장해 검사했다. 최소 유지율은 **90.214%**, 90% 하한 미달은 **0건**이다. 원자료는 `default-text/*.json`이고 geometry/판정은 정규 corpus 실행기의 결과다.

## (a) 06 변경 10건 중 남은 것

**다른 허용 후보로 남음 3건, 기준으로 복귀 7건, 리뷰 전과 byte-identical한 변경 0건**이다. 남은 3건은 모두 `bench/v2-3-egress`의 document / slide / slide-no-title이며 여전히 기준 대비 better다. 다음 표는 모든 10건을 나열한다.

| Case | Mode | 상태 | 기준 글자 | 리뷰 전 글자 | 수정 후 글자 | 기준 대비 판정 |
|---|---|---|---:|---:|---:|---|
| `bench/engine1-egress.layout.yaml` | document | 기준으로 복귀 | 7.529 | 5.494 | 7.529 | same |
| `bench/engine1-egress.layout.yaml` | slide | 기준으로 복귀 | 6.658 | 5.895 | 6.658 | same |
| `bench/engine1-egress.layout.yaml` | slide-no-title | 기준으로 복귀 | 7.387 | 6.336 | 7.387 | same |
| `bench/latest3-egress.layout.yaml` | slide | 기준으로 복귀 | 6.509 | 5.895 | 6.509 | same |
| `bench/latest3-egress.layout.yaml` | slide-no-title | 기준으로 복귀 | 6.489 | 6.140 | 6.489 | same |
| `bench/v2-2-egress.layout.yaml` | document | 기준으로 복귀 | 7.400 | 5.302 | 7.400 | same |
| `bench/v2-3-egress.layout.yaml` | document | 다른 허용 후보 | 7.502 | 5.343 | 7.294 | better |
| `bench/v2-3-egress.layout.yaml` | slide | 다른 허용 후보 | 6.509 | 5.895 | 6.509 | better |
| `bench/v2-3-egress.layout.yaml` | slide-no-title | 다른 허용 후보 | 7.032 | 6.062 | 7.032 | better |
| `rt/nd-single.layout.yaml` | document | 기준으로 복귀 | 7.927 | 5.805 | 7.927 | same |

## (b) 04 승자 중 글자 한도로 되돌린 사례

**3 Cases / 3 Case·Mode runs**다. 기존 04 승자의 글자 크기가 최초 default의 90% 미만이었다는 근거로 분류했다. 아래 3건은 모두 기존 verdict 기준으로 worse이며 **전부 “글자 한도로 되돌림”**이다. 이 목록 밖의 worse는 0이다.

| Case / Mode | 기본 그림 글자 | 04 승자 글자 | 90% 하한 | 수정 후 글자 | 04 승자 유지율 | 이유 |
|---|---:|---:|---:|---:|---:|---|
| `qa/t1-privatelink.layout.yaml` / slide-no-title | 7.166 | 5.920 | 6.449 | 7.166 | 82.61% | 글자 한도로 되돌림 |
| `qa/t4-shared-lane.layout.yaml` / slide | 18.237 | 15.607 | 16.413 | 18.237 | 85.58% | 글자 한도로 되돌림 |
| `rt/gw-ret.layout.yaml` / document | 7.482 | 6.633 | 6.733 | 7.482 | 88.65% | 글자 한도로 되돌림 |

- `qa/t1-privatelink` slide-no-title: 04의 승자는 82.61%였다. 이번에는 같은 글자 크기를 보존하는 다른 후보(skip edge:2)를 고른다. Tier-0 count 3→4, check 7→7이고 R-flow가 1건 늘어난다.
- `qa/t4-shared-lane` slide: 04의 승자는 85.58%였다. 기본 그림을 유지하면서 DLQ 라벨의 F5가 다시 1건 남는다. 두 그림의 글자는 이미 10pt 이상이지만 사용자 결정은 목표 크기와 관계없이 동일한 상대 한도를 요구한다. document와 slide-no-title은 R-flow 0을 유지한다.
- `rt/gw-ret` document: 04의 승자는 88.65%였다. 기본 그림을 유지해 check 2→3이다. `SERVICE AS TEXT` +2, `LINE OVER TEXT` −1이며 새 clipping은 없다. 반환선은 Users까지 이어진다.

Verdict = `(clipping, tier-0 count, cost, check, text shortfall, shape misses, area)`. 표는 text shortfall을 소수 6자리로 표시한다.

| Case / Mode | 기준 verdict | 수정 후 verdict |
|---|---|---|
| `qa/t1-privatelink.layout.yaml` / slide-no-title | `(0, 3, 67, 7, 4.080085, 4, 1625764)` | `(0, 4, 71.8, 7, 2.834123, 4, 1297228)` |
| `qa/t4-shared-lane.layout.yaml` / slide | `(0, 0, 0, 0, 0, 1, 232512)` | `(0, 1, 9, 0, 0, 1, 171456)` |
| `rt/gw-ret.layout.yaml` / document | `(0, 0, 0, 2, 4.367273, 2, 1032625)` | `(0, 0, 0, 3, 3.518458, 2, 975200)` |

## (c) 규칙·check·시간

760 runs: **better 3 / same 754 / worse 3**, unjudged 0, 기대 결과 불일치 0이다. 단순 규칙 verdict 악화 3건은 위 사용자 지정 글자 한도에 따른 되돌림이며 새 한도를 어긴 선택은 없다.

| 항목 | 기준 | 수정 후 | 증감 |
|---|---:|---:|---:|
| R-border | 17 | 17 | +0 |
| R-flow | 45 | 47 | +2 |
| R-rt | 90 | 90 | +0 |
| R-twin | 6 | 6 | +0 |
| R-label | 2 | 2 | +0 |
| R-fit | 298 | 298 | +0 |
| Check problem | 377 | 378 | +1 |

위반 수의 R-flow +2는 PrivateLink와 shared-lane에서 각각 +1이다. R-rt count 감소는 글자 한도를 적용하면서 없어졌다. 다른 규칙의 위반 수는 그대로다. 전체 check +1은 gw-ret document에만 있으며 나머지 Case·Mode의 check 수는 증가하지 않는다.

| Check 코드 | 증감 |
|---|---:|
| LINE OVER TEXT | -1 |
| SERVICE AS TEXT | +2 |

나머지 check 코드 증감은 모두 0이다. 새 clipping은 0이다.

| 시간 항목 | 기준 | 수정 후 |
|---|---:|---:|
| Draft 중앙값 (s) | 0.1845 | 0.186 |
| 최악 (s) | 19.55 | 19.31 |
| 시간 합계 (s) | 957.93 | 972.65 |
| Corpus wall (s) | 165.39 | 167.75 |

최대 per-run 비율 **1.667×** (`sides/vbottom` slide, 0.015→0.025초), 최악 **19.310초**, 전체 wall **1.014×**, 시간 합계 **1.015×**다. 3× 및 30초 초과는 모두 0이다.

## 태그·남은 문제·이미지

Raw corpus의 태그 불일치는 shared-lane slide 1건이었다. 저장된 F5 owner `edge:3`의 근거로 good 태그를 mode별 bad 태그로 바꿨다. 저장된 같은 760 runs를 새 manifest로 재판정해 **불일치 0**을 확인했다 (`tag-rejudgement.json`). Raw `corpus.json`은 편집하지 않았다. nd-single document도 새 글자 한도로 RT2를 남기므로 bad로 복원했다.

남은 문제는 nd-single의 RT2, 기존 three-b의 RT1, 위 되돌림에서 복원된 R-flow 2건과 check 1건이다. 티켓 05의 unresolved/spec hint 경고는 계속 이를 설명한다. 새 정책이 적용된 뒤 06의 원래 “악화 0·bad 위반 합계 감소” gate는 위에서 이유를 입증한 글자 한도 되돌림에 대해 사용자 결정으로 대체된다.

아래 PNG 7개를 embed·렌더하고 이미지 보기 도구로 직접 확인했다. 리뷰 전보다 문서 본문이 커졌다. shared-lane의 라벨 모호성과 PrivateLink의 추가 R-flow는 남는다. 반환선 잘림은 새로 생기지 않았다.

- `/home/ec2-user/.cache/skill-design/t06-rt/text-limit/png/rt-nd-single-document-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/text-limit/png/bench-engine1-egress-document-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/text-limit/png/bench-v2-2-egress-document-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/text-limit/png/bench-v2-3-egress-document-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/text-limit/png/qa-t1-privatelink-slide-no-title-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/text-limit/png/qa-t4-shared-lane-slide-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/text-limit/png/rt-gw-ret-document-pair.png`

## 증거와 재현

`~/.cache/skill-design/t06-rt/text-limit/`:

- `corpus.json`, `audit.json`, `corpus.log`, `default-text/`
- `red.log`, `select-green.log`, `pytest.log`, `examples.log`
- `tag-rejudgement.json`, `png-pairs.json`, `png/`, `corpus-drafts/`
- `run_corpus_with_text_evidence.py`, `audit.py`: 기본 글자 크기와 rejected 후보의 근거를 수집/분류한 실행·검증 스크립트

Python 기본 forkserver의 Unix socket이 sandbox에서 금지되어 기존 corpus 실행기를 `fork`로 실행했다. evidence wrapper는 결과를 바꾸지 않고 `select_drawing`과 `accepts_text`를 관찰하며 각 최종 Draft가 90% 하한을 지키는지 assert한다. 동일한 corpus 실행기의 판정·baseline 비교 결과를 그대로 저장했다.

```bash
export TMPDIR="$HOME/.cache/codex-t06-rt-tmp"
mkdir -p "$TMPDIR"
uv run --offline --no-project --with pyyaml --with cairosvg python3 \
  "$HOME/.cache/skill-design/t06-rt/text-limit/run_corpus_with_text_evidence.py" \
  --rule-checker scripts/rules.py:corpus -q -j 6 \
  --baseline "$HOME/.cache/skill-design/baseline/main-511fd73.json" \
  --baseline-drafts "$HOME/.cache/skill-design/baseline/main-511fd73-drafts" \
  --keep "$HOME/.cache/skill-design/t06-rt/text-limit/corpus-drafts" \
  --out "$HOME/.cache/skill-design/t06-rt/text-limit/corpus.json"
```

기본 git 메타데이터/index가 읽기 전용이라 임시 git-dir에서 같은 `t06-rt` 브랜치에 직접 커밋한다. 커밋 후 그 index 기준 `git diff HEAD --stat` 빈 출력을 확인한다. **index 동기화 필요**.
