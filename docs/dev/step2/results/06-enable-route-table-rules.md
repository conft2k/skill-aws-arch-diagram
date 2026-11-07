# Ticket 06: R-rt 선택 검증

기준은 main `511fd73`의 `main-511fd73.json`과 `main-511fd73-drafts/`이다. 기준과 최종 실행 모두 `-j 6`이다. 전체 corpus 실행 동안 이 작성자의 pytest·예제·렌더를 겹치지 않았다.

## 완료 조건

- [x] R-rt를 tier-0 count/cost에 포함한다. `scripts/layout.py:84`, `:210`이 기존 `rules.score(..., enabled_rules=...)`를 사용한다. 규칙 predicate·threshold·메시지 코드는 바꾸지 않았다.
- [x] Corpus 악화 0, R-border·R-flow·check 증가 0. R-rt bad 태그 사례 합계는 21→20이다. 각 사례와 good 변경 근거는 아래 표에 있다.
- [x] `rt/three-b`와 single 계열의 모든 mode에 대해 전후 verdict를 아래에 기록했다. 남은 RT1의 원인도 기록했다.
- [x] Ticket 04의 시간 제한을 통과했다. 최대 2.643×, 최악 22.986초, 전체 wall 1.097×이다. 3×·30초 초과는 모두 0이다.

## 구현과 red → green

- `scripts/layout.py:1400`: association이 있는 route table의 열린 대각선 쌍을 하나씩 뒤집는다. y→x를 먼저, x→y를 다음, 그 table의 모든 쌍을 뒤집는 후보를 마지막으로 만든다. 관련 없는 쌍의 축을 보존하고 `xy`로 고정한 table은 제외한다.
- `scripts/layout.py:1506`: default에 R-rt가 남으면 이전 R-border/R-flow 그룹의 승자를 먼저 확보한다. 두 탐색은 하나의 12/16개 후보 예산을 공유하며, 이후 결과는 이전 승자의 전체 verdict와 check 수를 보호한다. checker 실패 시 원래 완성된 default를 복원한다.
- `tests/test_select.py:133`: RT tier-0 count/cost, nd-single RT2 제거·결정성, 고정 xy 보존의 3개 테스트를 먼저 썼다. 기존 코드에서 3 failed (`red.log`), 구현 후 3 passed (`green.log`)였다.
- 최초 전체 실행은 `ports/xnt` slide 1건이 worse였다. 두 RT1을 없앤 기존 승자보다 작은 글자를 고르는 탐색 경로 문제였다. 회귀 테스트를 먼저 추가해 1 failed (`regression-red.log`)를 확인하고 위의 승자 보존을 구현했다. 선택 테스트 12개 모두 통과했다 (`select-green.log`). 실패 수정 때문에 전체 corpus를 한 번 재검증했고, 최초 결과는 `corpus.json`에 그대로 보존했다.
- `tests/corpus/MANIFEST.yaml:238`: nd-single의 document bad 태그를 `good: [R-rt]`로 변경했다. document에서 RT2가 1→0이고 두 slide mode는 원래부터 0이다.
- `docs/dev/step2/spec.md:68`: 이전 그룹의 승자와 후보 예산 공유를 문서화했다.

## 최종 corpus

| 항목 | 기준 | 최종 | 증감 |
|---|---:|---:|---:|
| R-border | 17 | 17 | +0 |
| R-flow | 45 | 45 | +0 |
| R-rt | 90 | 89 | -1 |
| R-twin | 6 | 6 | +0 |
| R-label | 2 | 2 | +0 |
| R-fit | 298 | 298 | +0 |
| Check problem 전체 | 377 | 377 | +0 |

760 runs: **better 10 / same 750 / worse 0 / unjudged 0**. 변경된 Draft 10개는 전부 better이다. Case·Mode별 check 증가, 새 clipping, 기대 결과 불일치, 태그 불일치는 모두 0이다. Check 코드별 증감도 전부 0이다. QA 15개 Case의 45 runs와 예제 56 runs는 기준 Draft와 byte-identical이다. Golden은 변경하지 않았다.

## 기준의 R-rt bad 태그 사례

아래 순서 D / S / N은 document / slide / slide-no-title이다. mode별 수는 그 Case의 R-rt 전체 위반 수다. 기준에서 태그가 있던 mode만 합산했다.

| Case | 태그 mode | 전 → 후 | 합계 전 → 후 | 판정과 이유 |
|---|---|---|---|---|
| `bench/latest2-egress.layout.yaml` | D / S / N | 2→2 / 2→2 / 2→2 | 6→6 | bad 유지: table의 열린 대각선 쌍이 없어서 고정된 행·열 관계를 바꿀 수 없다 |
| `bench/v2-1-egress.layout.yaml` | D / S / N | 2→2 / 2→2 / 2→2 | 6→6 | bad 유지: table의 열린 대각선 쌍이 없어서 고정된 행·열 관계를 바꿀 수 없다 |
| `rt/nfw-noatt.layout.yaml` | D / S / N | 2→2 / 3→3 / 3→3 | 8→8 | bad 유지: table의 열린 대각선 쌍이 없어서 고정된 행·열 관계를 바꿀 수 없다 |
| `rt/nd-single.layout.yaml` | D | 1→0 | 1→0 | good: rtsp를 x에서 분리해 자기 연결선의 RT2 reach 안에 둔다; S/N도 0 |

**합계 21→20**. `bench/latest2-egress`, `bench/v2-1-egress`는 RT1이 각각 두 table에 남는다. `rt/nfw-noatt`는 RT1 두 건과 slide modes의 RT4 한 건이 남는다. 관련 쌍이 없는 근거는 `remaining-pairs.json`에 있다. 위반 메시지 전문은 `corpus-final-audit.json:bad_tagged_cases`에 보존했다.

## three-b와 single 계열 verdict

Verdict = `(clipping, tier-0 count, cost, check, text shortfall, shape misses, area)`. 표의 text shortfall은 소수 6자리로 표시하며 JSON은 전체 정밀도를 유지한다.

| Case | Mode | R-rt 전→후 | 기준 verdict | 최종 verdict |
|---|---|---:|---|---|
| `rt/single.layout.yaml` | document | 0→0 | `(0, 0, 0, 0, 1.952381, 0, 1522584)` | `(0, 0, 0, 0, 1.952381, 0, 1522584)` |
| `rt/single.layout.yaml` | slide | 0→0 | `(0, 0, 0, 0, 0, 0, 592876)` | `(0, 0, 0, 0, 0, 0, 592876)` |
| `rt/single.layout.yaml` | slide-no-title | 0→0 | `(0, 0, 0, 0, 0, 0, 582232)` | `(0, 0, 0, 0, 0, 0, 582232)` |
| `rt/single-below.layout.yaml` | document | 0→0 | `(0, 0, 0, 0, 3.709832, 0, 989541)` | `(0, 0, 0, 0, 3.709832, 0, 989541)` |
| `rt/single-below.layout.yaml` | slide | 0→0 | `(0, 0, 0, 0, 0, 0, 592876)` | `(0, 0, 0, 0, 0, 0, 592876)` |
| `rt/single-below.layout.yaml` | slide-no-title | 0→0 | `(0, 0, 0, 0, 0, 0, 598808)` | `(0, 0, 0, 0, 0, 0, 598808)` |
| `rt/nd-single.layout.yaml` | document | 1→0 | `(0, 1, 129, 0, 3.073325, 0, 5533836)` | `(0, 0, 0, 0, 5.19478, 0, 1319640)` |
| `rt/nd-single.layout.yaml` | slide | 0→0 | `(0, 0, 0, 1, 2.26361, 0, 919266)` | `(0, 0, 0, 1, 2.26361, 0, 919266)` |
| `rt/nd-single.layout.yaml` | slide-no-title | 0→0 | `(0, 0, 0, 1, 1.580866, 0, 919266)` | `(0, 0, 0, 1, 1.580866, 0, 919266)` |
| `rt/three-b.layout.yaml` | document | 1→1 | `(0, 1, 1, 0, 4.011494, 0, 1229310)` | `(0, 1, 1, 0, 4.011494, 0, 1229310)` |
| `rt/three-b.layout.yaml` | slide | 1→1 | `(0, 1, 1, 1, 1.576355, 0, 1500170)` | `(0, 1, 1, 1, 1.576355, 0, 1500170)` |
| `rt/three-b.layout.yaml` | slide-no-title | 1→1 | `(0, 1, 1, 1, 0.524089, 0, 1090131)` | `(0, 1, 1, 1, 0.524089, 0, 1090131)` |

`rt/three-b`는 모든 mode에서 Firewall RT의 RT1이 남는다. 이 table에는 열린 대각선 쌍이 없다. Spoke RT의 쌍을 바꾸어도 Firewall RT와 두 ENI 선 사이의 bracket을 바꾸지 못한다. 명시적인 `VH` 연결과 고정된 track 배치를 그대로 지켰다. 새로운 쌍/track 이동을 만들거나 spec 배치를 바꾸는 작업은 이번 범위 밖이다. `rt/single`과 `rt/single-below`는 세 mode 모두 원래 R-rt가 0이고 그대로 유지됐다.

## 변경된 Draft와 이유

| Case | Mode | Tier-0 count/cost 전 → 후 | Text shortfall 전 → 후 | 이유 |
|---|---|---|---|---|
| `bench/engine1-egress.layout.yaml` | document | 4/476.50 → 4/167.49 | 3.471106 → 5.506024 | RT1/RT4 개수는 유지, RT4 거리 cost 감소 |
| `bench/engine1-egress.layout.yaml` | slide | 4/454.09 → 4/183.27 | 3.341554 → 4.104803 | RT1/RT4 개수는 유지, RT4 거리 cost 감소 |
| `bench/engine1-egress.layout.yaml` | slide-no-title | 4/381.94 → 4/183.27 | 2.612766 → 3.664000 | RT1/RT4 개수는 유지, RT4 거리 cost 감소 |
| `bench/latest3-egress.layout.yaml` | slide | 4/522.34 → 4/181.33 | 3.491009 → 4.104803 | RT1/RT4 개수는 유지, RT4 거리 cost 감소 |
| `bench/latest3-egress.layout.yaml` | slide-no-title | 4/297.24 → 4/181.33 | 3.510730 → 3.860465 | RT1/RT4 개수는 유지, RT4 거리 cost 감소 |
| `bench/v2-2-egress.layout.yaml` | document | 4/596.62 → 4/176.35 | 3.600000 → 5.697674 | RT1/RT4 개수는 유지, RT4 거리 cost 감소 |
| `bench/v2-3-egress.layout.yaml` | document | 4/676.35 → 4/209.23 | 3.497944 → 5.657293 | RT1/RT4 개수는 유지, RT4 거리 cost 감소 |
| `bench/v2-3-egress.layout.yaml` | slide | 4/647.43 → 4/227.03 | 3.491009 → 4.104803 | RT1/RT4 개수는 유지, RT4 거리 cost 감소 |
| `bench/v2-3-egress.layout.yaml` | slide-no-title | 4/556.59 → 4/227.03 | 2.968497 → 3.937671 | RT1/RT4 개수는 유지, RT4 거리 cost 감소 |
| `rt/nd-single.layout.yaml` | document | 1/129.00 → 0/0.00 | 3.073325 → 5.194780 | RT2 제거 |

9개 benchmark 변경은 새 R-rt cost 비교가 feedback/text-scale 라운드를 고르는 결과다. 위반 개수는 줄지 않았으므로 고친 Case로 태그를 바꾸지 않았다. 작은 글자를 고르는 tradeoff가 있으며, `rt/nd-single` document의 유효 글자 크기도 **7.93→5.81px**다. Tier-0 count/cost가 R-fit보다 먼저라는 verdict 결정에 따른 better이며 R-fit 위반 수는 298로 유지된다. 이 한계를 이미지와 함께 검토할 수 있게 보존했다.

## 시간

| 항목 | 기준 | 최종 |
|---|---:|---:|
| Draft 시간 중앙값 (s) | 0.1845 | 0.1885 |
| 시간 최악 (s) | 19.55 | 22.986 |
| 시간 합계 (s) | 957.93 | 1054.55 |
| Corpus wall (s) | 165.39 | 181.42 |

최대 비율은 `xy/refuse` slide-no-title **0.014→0.037초 (2.643×)**다. 전체 wall은 **165.39→181.42초 (1.097×)**, 합계 비율은 **1.101×**다.

기본 Python forkserver가 sandbox에서 Unix socket을 만들지 못해 실행 전 실패했다. 실행기나 엔진을 바꾸지 않고 `multiprocessing.set_start_method("fork")` wrapper로 동일한 `-j 6` worker 수를 사용했다. 재현 명령:

```bash
export TMPDIR="$HOME/.cache/codex-t06-rt-tmp"
mkdir -p "$TMPDIR"
uv run --offline --no-project --with pyyaml --with cairosvg python3 -c 'import multiprocessing, runpy; multiprocessing.set_start_method("fork"); runpy.run_path("tests/run_corpus.py", run_name="__main__")' \
  --rule-checker scripts/rules.py:corpus -q -j 6 \
  --baseline "$HOME/.cache/skill-design/baseline/main-511fd73.json" \
  --baseline-drafts "$HOME/.cache/skill-design/baseline/main-511fd73-drafts" \
  --keep "$HOME/.cache/skill-design/t06-rt/corpus-final-drafts" \
  --out "$HOME/.cache/skill-design/t06-rt/corpus-final.json"
```

## 테스트와 직접 확인한 PNG

- 전체 pytest: **766 passed, 2542 subtests passed**, 144.29초 (`pytest.log`).
- 예제: **21 all PASS, 0 FAIL, 0 SKIP** (`examples.log`). 결정성·check·export·structure 검증을 모두 통과했다.

`~/.cache/skill-design/t06-rt/`에 모든 증거를 보존했다:

- `corpus-final.json`, `corpus-final-audit.json`, `corpus-final.log`
- `red.log`, `green.log`, `regression-red.log`, `select-green.log`, `pytest.log`, `examples.log`
- `remaining-pairs.json`, `png-pairs.json`, `corpus-final-drafts/`

아래 PNG 여섯 개는 공식 아이콘을 embed한 후 렌더하고 이미지 보기 도구로 직접 확인했다. 왼쪽 기준, 오른쪽 최종이다. 선과 끝점의 흐름에 새로운 blocking defect는 보이지 않았다. three-b의 기존 bracket 위반과 작은 글자 한계는 위에 기록한 대로 남는다.

- `/home/ec2-user/.cache/skill-design/t06-rt/png/nd-single-document-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/png/three-b-slide-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/png/single-document-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/png/engine1-egress-document-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/png/v2-3-egress-document-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/png/xnt-slide-pair.png`

기본 index가 읽기 전용이어서 별도 index, `commit-tree`,
공유 git-dir의 `update-ref`로 `t06-rt`에 직접 커밋한다. **index 동기화 필요**.
커밋 후 `git diff HEAD --stat`이 비어 있는지 최종 응답에 기록한다.
