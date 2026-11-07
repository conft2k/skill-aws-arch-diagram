# Ticket 02 validation

브랜치: `t02-decisions`. Baseline: `main-36c7ea3.json` 및 `main-36c7ea3-drafts`.

아래 초기 검증은 `0cf2ab0` 시점이다. 최신 API와 재검증은 끝의 리뷰 차단 수정에 기록한다.

완료 조건:

- [x] Corpus 760 runs의 **744 Draft 전부 byte-identical, 0 changed**. 별도로 실행한 examples도 **21 Draft, 0 changed**. 누락·추가 Draft 및 결과 필드 변경 모두 0 (`comparison.json`, `examples-comparison.json`).
- [x] Slide의 두 번째 decision set이 더 큰 effective text size를 선택: **9.342561pt → 10.037175pt** (`scripts/layout.py:175`, `tests/test_layout_main.py:193`).
- [x] NFW의 open diagonal pairs **2개**에서 default axis와 x/y cost, skippable connectors **8개**에서 routing alternatives **102개** 노출 (`scripts/layout_solve.py:93`, `scripts/layout.py:110`, `scripts/layout_route.py:109`).
- [x] 같은 Spec·decision set으로 두 번 만든 Draft가 byte-identical; examples **21개**도 두 실행이 동일 (`tests/test_layout_main.py:150`, `decisions-smoke.json`, `examples.log`).
- [x] **687 tests + 2539 subtests PASS**, examples **21 all PASS**. Diagram별 Baseline 대비 최대 **1.556×**, 최대 **10.358 s**; Corpus wall **126.04 → 327.65 s (2.600×)**. 3×·30 s 초과 Diagram 0 (`comparison.json`).

Corpus의 Check problems는 **389 → 389**, tier-0 Violations는 **201 → 201**,
R-fit Violations는 **298 → 298**, tag 불일치는 **0 → 0**이다. 새 문제는 없다.
공유 Baseline은 `-j 5`, 이번 실행은 지시대로 `-j 2`다. 위 wall ratio는 실제
측정값이며, summed runtime은 **616.69 → 654.21 s (1.061×)**다.

Layout decisions는 `scripts/layout_solve.py:79`의 immutable `Decisions`로 전달한다.
`diag=None`은 기존 prior, 명시적 set은 x로 분리할 open diagonal pairs를 뜻하며
나머지는 y로 분리한다. Overlay의 header는 `beside` / `above`, routing은 Edge
instance별 skip, Note는 place로 지정한다. Spec의 hard placements는 유지한다.
`Geometry.diag_pairs`는 기본 축과 x/y growth cost를 제공한다. `Build.diag_pairs`는
Note 전후 solve의 open pairs를 합치고, `Build.routing_alternatives`는 다음 clean
routing alternatives의 skip·shape·points를 제공한다. Trunk follower는 제외한다.

테스트를 먼저 작성하여 신규 5개가 `Decisions` 부재와 기존 boolean 호출 때문에
실패하는 것을 확인했다(red). 구현 후 해당 테스트와 기존 slide 테스트 2개가
통과했다(green). 이어서 두 축의 Draft, 실제 connector 변경, 부모 Group이 없는
Overlay를 검증하는 테스트 3개를 추가했고 마지막 경우의 실패를 수정했다.
최종 pytest: **687 passed, 2539 subtests passed, 97.25 s**.
Examples: **21 all PASS, 0 FAIL, 0 SKIP**; 별도 Baseline 비교도 **21 Draft, 0 changed**.

NFW document의 open diagonal pairs는 2개이며 default axis는 모두 x다.
x/y cost는 각각 0/0 px, 0/30 px다. Skippable connectors 8개에서 routing alternatives
102개를 제공한다. 동일 Spec·decision set의 두 Draft는 byte-identical이다.
기존 stacked-between prior를 억제하는 slide regression에서 effective text size는
**9.342561pt → 10.037175pt**로 증가하며 두 번째 decision set이 선택된다.

검증 명령은 팀장이 지정한 offline 의존성을 사용했다. Examples 내부 export의
`uv`에도 offline이 적용되도록 `UV_OFFLINE=1`을 상속했다. Corpus는 Python 3.15의
기본 `forkserver`가 sandbox의 socket bind 제한에 막혀, runner 파일 수정 없이
`multiprocessing.set_start_method("fork")`와 `runpy.run_path`로 실행했다.
Corpus의 `--rule-checker scripts/rules.py:corpus`, `-q`, `-j 2`는 그대로 유지했다.

재현 명령:

```bash
export TMPDIR="$HOME/.cache/codex-t02-decisions-tmp"
mkdir -p "$TMPDIR"
export UV_OFFLINE=1
uv run --offline --no-project --with pyyaml --with python-pptx --with cairosvg --with pytest pytest -q tests -p no:cacheprovider
uv run --offline --no-project --with pyyaml --with python-pptx --with cairosvg python3 tests/test_examples.py --keep "$HOME/.cache/skill-design/t02-decisions/examples"
uv run --offline --no-project --with pyyaml --with cairosvg python3 -c 'import multiprocessing, runpy; multiprocessing.set_start_method("fork"); runpy.run_path("tests/run_corpus.py", run_name="__main__")' --rule-checker scripts/rules.py:corpus --keep "$HOME/.cache/skill-design/t02-decisions/drafts" --out "$HOME/.cache/skill-design/t02-decisions/corpus.json" -q -j 2
```

결과 경로:

- `~/.cache/skill-design/t02-decisions/corpus.json`
- `~/.cache/skill-design/t02-decisions/comparison.json`
- `~/.cache/skill-design/t02-decisions/decisions-smoke.json`
- `~/.cache/skill-design/t02-decisions/examples-comparison.json`
- `~/.cache/skill-design/t02-decisions/examples.log`

이미지 보기 도구로 직접 확인한 PNG:

- `~/.cache/skill-design/t02-decisions/examples/nfw-reference-architecture/out/nfw-reference-architecture.png`
- `~/.cache/skill-design/t02-decisions/examples/slides_nfw-reference-architecture/out/nfw-reference-architecture.png`

두 PNG에서 Flow, 화살표의 끝, step badges 및 Note를 확인했다.

Worktree의 기본 index와 `COMMIT_EDITMSG`가 read-only여서 별도 index 및
`commit-tree`로 커밋하고 `t02-decisions`의 ref만 갱신한다. **index 동기화 필요**.

## 리뷰 차단 수정

`scripts/layout.py:159`의 `collect_alternatives=False`가 기본값이다. 기본 build,
Feedback round, Text scale은 경로 대안을 위한 추가 후보 평가를 하지 않는다.
이웃을 만들 때 `collect_alternatives=True`로 요청하면 목록을 제공한다.
`scripts/layout_route.py:2683`에서 현재 선과 좌표가 같은 대안과 중복 대안을 제거한다.
Draft와 같은 2자리 좌표를 비교하며, 각 대안의 원래 skip index는 유지한다.

테스트를 먼저 고쳐 4 FAIL을 확인했다(red). 기본 build의 후보 생성은 15회였고
직접 routing은 11회였다. 수정 후 추가 평가 없이 둘 다 11회이며 관련 10개 테스트가
통과했다(green). NFW의 대안 목록은 요청 시 **7 connectors, 53 alternatives**이며,
기본값에서는 빈 목록이다. 수집을 켜고 끈 Draft는 byte-identical이다.

동일 uv 환경, `-j 1`, main `d99e074`와 수정 브랜치를 워밍업 각 1회 후
교차 3회 실행한 중앙값이다. 시간 측정 중 다른 검증을 병행하지 않았다.

| Case · Mode | main | 수정 브랜치 | 비율 |
|---|---:|---:|---:|
| trunk/merge-v3az · slide | 1.064 s | 1.147 s | 1.078× |
| rt/ce-three · slide | 2.490 s | 2.684 s | 1.078× |
| flowcol/r2-float-two-wide · slide | 0.747 s | 0.790 s | 1.058× |

세 Case 모두 **1.1× 이내**다. 시간 측정의 main·브랜치 Draft **12쌍 모두 동일**하다.
전체 재검증은 **689 tests + 2539 subtests PASS (92.24 s)**, examples **21 all PASS**다.
Corpus **760 runs, 744/744 Draft byte-identical**, 별도 examples **21/21 Draft
byte-identical**이다. Check problems **389 → 389**, tier-0 Violations **201 → 201**,
tag 불일치 **0 → 0**, 비교한 결과 필드 변경은 0이다. 전체 Corpus wall은
**126.04 → 312.65 s (2.481×)**, summed runtime은 **624.12 s**다. Diagram별
Baseline 대비 최대 **1.348×**, 최대 시간 **10.707 s**로 기존 3×·30 s 제한도 충족한다.

리뷰 수정 결과: `~/.cache/skill-design/t02-decisions/review-fix/`의
`timing.json`, `alternatives.json`, `corpus.json`, `comparison.json`,
`examples-comparison.json`, `examples.log`, `pytest.log`.
