# Ticket 04 canvas clipping review fix

기준: `main-cc17a2d.json`과 Draft 디렉터리. 전체 Corpus는 요청대로 `-j 6`으로
1회 실행했으며 기준도 `jobs: 6`이다. 다른 테스트·렌더와 겹치지 않았다.

## 수정과 재현

- [x] gw-ret slide / slide-no-title을 CLI 테스트로 먼저 고정했다
  (`tests/test_select.py:103`). 두 테스트 모두 기존 선택 결과의
  `(835.6,754)→(166,754)`가 1407×738 canvas 아래로 16px 잘려 red였다.
- [x] 변경 후 EC2.2→Users edge의 선이 실제 Draft에 있고 잘림 check가 0이다.
  두 Mode 모두 기존 그림(1255×706, 기존 check 6개)을 유지한다.
- [x] 실제 checker의 `LINE OFF CANVAS`, `OFF CANVAS`, `BADGE OFF CANVAS`를
  `scripts/check_layout.py:1098`에서 한 번 정의한다.
- [x] `scripts/rules.py:874`의 공통 Verdict는 잘림 개수를 첫 critical 항목으로
  둔다. 다른 Rule/check가 줄어도 새 잘림은 이길 수 없다.
- [x] 후보 선택과 feedback/header/fixed-answer/text-scale 비교가 같은 score를
  사용한다. Verdict의 named fields를 사용하여 추가된 항목 때문에 check 수나
  text shortfall 인덱스가 어긋나지 않게 했다 (`scripts/layout.py:1517`,
  `:1559`, `:1573`, `:1594`; `tests/run_corpus.py:468`).
- [x] 규칙만으로 미리 prune할 때, 이미 잘린 incumbent은 check에서 clipping을
  줄일 가능성을 남긴다. 잘리지 않은 incumbent은 기존 tier-0 prune을 유지한다.
- [x] `docs/dev/step2/spec.md`의 Verdict 결정과 `GLOSSARY.md`의 Verdict 정의에
  clipping의 critical 순서를 반영했다. Solution의 순서도 일치시켰다.

## 검증

- Pytest: **762 passed, 2542 subtests passed**, 123.50 s.
- 최종 재현·score 테스트: **5 passed, 3 subtests passed**, 8.84 s.
- Examples: **21 all PASS**, 0 FAIL, 0 SKIP. Golden은 변경하지 않았다.
- Corpus: **760 runs, better 82 / same 678 / worse 0**, 변경 Draft 82개 전부 better.
- 기대 결과 불일치 0, 태그 불일치 0, 새 clipping Case·코드 증가 0.
  Baseline의 기존 LINE OFF CANVAS 1건(rt/sgw-ret, slide-no-title)만 남으며 그 Draft는
  기준과 byte-identical이다. Check problem 수가 증가한 Case·Mode도 0이다.
- 최대 비율 **2.692×** (ports/xnt slide, 2.583→6.953 s), 최악 **19.550 s**.
  3×와 30 s를 넘는 Draft는 0이다. 동일 병렬도의 wall은 **1.467×**다.

| 항목 | 기준 | 수정 후 | 증감 |
|---|---:|---:|---:|
| R-border | 17 | 17 | 0 |
| R-flow | 74 | 45 | −29 |
| R-rt | 94 | 90 | −4 |
| R-twin | 6 | 6 | 0 |
| R-label | 2 | 2 | 0 |
| R-fit | 298 | 298 | 0 |
| Check problem 전체 | 385 | 377 | −8 |
| LINE OFF CANVAS | 1 | 1 | 0 (새 Case 0) |
| OFF CANVAS | 0 | 0 | 0 |
| BADGE OFF CANVAS | 0 | 0 | 0 |
| LINE OVER TEXT | 65 | 66 | +1 |
| TEXT NEAR ICON | 21 | 19 | −2 |
| SERVICE AS TEXT | 12 | 10 | −2 |
| LINE ON LINE | 13 | 8 | −5 |
| 시간 중앙값 (s, 744 Draft) | 0.1975 | 0.1845 | −0.013 |
| 시간 최악 (s) | 17.145 | 19.550 | +2.405 |
| 시간 합계 (s, 760 runs) | 655.990 | 957.930 | +301.940 |
| Corpus wall (s) | 112.710 | 165.390 | +52.680 |

나머지 check 코드의 증감은 모두 0이다. 새 잘림 판정은 Case·Mode·코드별로
기준보다 clipping check 수가 증가했는지 검사한다 (`audit.json:new_clipping=[]`).
기준과 현재 모두 새 Verdict 정의로 비교하므로 기준 파일의 구형 score 배열을
그대로 비교하지 않는다. 태그 재판정이나 결과 편집 없이 runner 결과가 그대로 통과했다.

## 결과 파일과 PNG

`~/.cache/skill-design/t04-select/clip-fix/`:
`corpus.json`, `audit.json`, `clip-corpus.log`, `clip-pytest.log`,
`clip-examples.log`, `clip-red.log`, `clip-repro-green.log`, `png-pairs.json`.

이미지 보기 도구로 직접 확인한 PNG:

- `png/gw-ret-slide-pair.png`
- `png/gw-ret-slide-no-title-pair.png`

왼쪽은 c3fa8e8의 잘린 선택 결과, 오른쪽은 수정 후다. 수정 후 반환선 전체가
캔버스 안에 표시되고 Users까지 연결된다. 기존의 다른 check 6개는 남는다.

기본 index와 worktree HEAD lock이 read-only여서 별도 index, `commit-tree`,
공유 git-dir의 `update-ref`로 직접 커밋한다. **index 동기화 필요**.
