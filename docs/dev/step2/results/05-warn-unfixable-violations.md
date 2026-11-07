# Ticket 05: 남은 위반의 spec 수정 안내

기준: `main 511fd73`, `~/.cache/skill-design/baseline/main-511fd73.json`과
`main-511fd73-drafts/`. 변경은 보고 메시지와 문서에 한정한다.

## 완료 조건과 근거

- [x] 남은 enabled-rule 위반마다 owner와 기존 spec-fix 힌트를 경고한다.
  전체 corpus의 **360건 모두 경고가 있으며 누락 0건**이다
  (R-flow 45, R-border 17, R-fit 298). 실제 corpus에서 힌트가 없는 위반은
  없고, 그런 owner의 설명은 CLI 테스트로 확인했다.
  최종 draft의 rule 결과와 check problem을 재사용한다. F5는 label/badge에
  맞는 `label_at`/`step_at` 안내를 붙이고, 적용 가능한 owner 힌트가 없으면
  `no spec hint: the existing spec-fix hints do not apply to these owners`라고
  설명한다. R-fit은 항상 안내하며, 비활성 rule에는 이 경고를 추가하지 않는다.
- [x] 검증되지 않은 수정은 `spec hint (not a guarantee)`로 명시한다.
  최소 3개 수정의 성공을 주장하는 대신 티켓의 비보장 안내 조건을 택했다.
  실제 corpus 6개를 CLI로 그려 경고·owner·힌트·반복 draft 동일성을 확인했다:
  `ports/u3` document(F3), `sides/xy3` document(F4),
  `qa/t2-alb-trunk-header` slide(B2),
  `qa/t3-dns-trunk` slide(F1), `qa/t3-cache-label` slide(F5),
  `qa/t4-order-14steps` slide(F1/F5).
- [x] 남은 R-border/R-flow bad 태그 10개 모두 사유 주석이 있다.
  주석이 없던 QA 4개에만 사유를 추가했다. MANIFEST의 YAML 파싱 결과는
  기준과 같으며 태그·spec·mode 데이터는 그대로다.
- [x] 전체 corpus **760 runs, same 760 / better 0 / worse 0**.
  그린 draft **744개 모두 byte-identical, changed drafts 0**.
  기대 결과 실패·태그 불일치·경고 누락 모두 0이다 (`audit.json`).

## 테스트

- Red: 경고 테스트 **9 failed, 1 passed**, 구현 전에 실행했다.
- Green: 집중 검증 **25 passed, 2 subtests passed**.
- 최종 경고 테스트 **10 passed**. 다음 티켓의 R-rt 활성화와 독립적으로
  비활성 rule 필터를 검증하도록 테스트의 enabled 그룹을 고정했다.
- 전체 pytest **772 passed, 2542 subtests passed**, 153.20 s.
- Examples: **21 all PASS, 0 FAIL, 0 SKIP**.
  첫 실행은 21개 모두 layout/check/구조 비교를 통과했지만 내부 export의
  `uv`가 PyPI에 접속해 실패했다. 자식 프로세스에도 offline 설정이 전해지도록
  `UV_OFFLINE=1`을 지정해 재실행했고 export까지 통과했다.
  테스트 러너 코드는 바꾸지 않았다.

## Corpus 전후

| 항목 | 기준 | 변경 후 |
|---|---:|---:|
| Check problem | 377 | 377 |
| R-flow | 45 | 45 |
| R-border | 17 | 17 |
| R-fit | 298 | 298 |
| R-rt | 90 | 90 |
| R-twin | 6 | 6 |
| R-label | 2 | 2 |

전체 실행은 **495.46 s wall**, 기준 대비 summed 시간은 **1.030×**다.
기준은 `-j 6`, 이번 실행은 요청된 `-j 2`이고 테스트와 겹쳤으므로
wall 비율 **2.996×**는 같은 병렬도의 성능 비교가 아니다.
후보 생성·verdict·spec 배치·golden은 변경하지 않았다.

## 결과 파일과 PNG

결과 디렉터리: `~/.cache/skill-design/t05-warn/`.
`corpus.json`, `audit.json`, `corpus.log`, `drafts/`,
`red.log`, `green.log`, `warnings-final.log`, `tests.log`, `examples.log`와
최초 export의 환경 실패 로그 `examples-network-failure.log`를 보관한다.
기본 multiprocessing `forkserver`는 샌드박스의 소켓 생성 제한 때문에
실행 시작 전에 실패했다. 실제 전체 실행은 다음과 같이 시작 방식만 `fork`로
지정하며 요청된 `-j 2`를 유지한다:

```bash
uv run --offline --no-project --with pyyaml --with cairosvg python3 -c \
  'import multiprocessing, runpy; multiprocessing.set_start_method("fork"); runpy.run_path("tests/run_corpus.py", run_name="__main__")' \
  --rule-checker scripts/rules.py:corpus \
  --keep "$HOME/.cache/skill-design/t05-warn/drafts" \
  --out "$HOME/.cache/skill-design/t05-warn/corpus.json" \
  --baseline "$HOME/.cache/skill-design/baseline/main-511fd73.json" \
  --baseline-drafts "$HOME/.cache/skill-design/baseline/main-511fd73-drafts" -q -j 2
```

이미지 보기 도구로 직접 확인한 PNG:

- `visuals/ports-u3.document.png`: A의 아래 두 경로가 bend 근처에서 교차하는
  기존 F3가 남으며 경고는 두 edge의 spec 항목을 안내한다.
- `visuals/qa-t3-cache-label.slide.png`: Async replication 라벨이 SQL 흐름과
  맞닿는 기존 F5가 남으며 경고는 해당 라벨의 spec 항목을 안내한다.
- `visuals/qa-t2-alb-trunk-header.slide.png`: ALB의 아래 trunk가 AZ2 App subnet
  제목을 통과하는 기존 B2가 남는다. 경고는 routing과 subnet 크기 힌트를 안내한다.

기존 위반은 이 메시지 전용 티켓에서 유지한다. 힌트의 효과는 spec을 수정한 뒤
다시 그려 확인해야 한다. 기본 index는 `index.lock` 생성이 read-only로 막혀
별도 index를 사용한다. **index 동기화 필요**.
