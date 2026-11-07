# Ticket 06: 목표 글자 크기 이상인 후보의 예외

기준은 main `511fd73`의 `main-511fd73.json` + `main-511fd73-drafts/`다. 직전 구현은 `1cc30fe`(무조건 90% 한도)이며 main의 티켓 05 `af80829`를 포함한다. 이번 전체 corpus는 기준과 같은 **-j 6으로 1회** 실행했다. 이 작성자의 테스트·예제·렌더는 corpus 종료 후 실행했다.

## 완료 조건

- [x] 테스트를 먼저 썼다. 목표 이상인 큰 축소를 세 규칙 그룹·두 mode에서 허용하는 테스트와 shared-lane 재현이 기존 코드에서 **7 failed / 6 passed**였다. gw-ret 가림은 **1 strict xfail**로 재현했다 (`red.log`). 수정 후 선택 테스트는 **35 passed / 1 xfailed**다 (`select-green.log`). 기존 nd-single 기본 그림 보존·반복 결정성 테스트도 계속 통과했다.
- [x] `scripts/layout.py:227`의 공통 admission check를 `actual >= min(default × 0.9, target)`으로 수정했다. 목표는 기존 `drawn_text`가 돌려주는 slide **10pt**, document **760px 열의 11px**다. 모든 그룹과 후속 단계가 같은 검사와 고정된 default reference를 공유한다.
- [x] `docs/dev/step2/spec.md:66` Search·`:67` Verdict와 `GLOSSARY.md:118` Candidate의 문장을 같은 조건으로 고쳤다. 검사기의 정의·verdict tuple·메시지 코드는 바꾸지 않았다.
- [x] pytest 전체 **799 passed, 1 xfailed, 2542 subtests passed**, 181.79초. Xfail은 아래 가림 백로그이며 고친 것으로 처리하지 않았다. 예제 **21 all PASS / 0 FAIL / 0 SKIP**다. Golden 변경은 없다.
- [x] shared-lane은 04 승자를 되찾았고 nd-single은 계속 차단된다. gw-ret은 목표 미만이라 승자를 되찾지 못하며, 가림을 놓치는 원인을 조사해 백로그에 기록했다. 가림 검사나 배치 코드는 수정하지 않았다.

## 주요 재현 결과

- `qa/t4-shared-lane` slide: **18.237→15.607pt**, R-flow F5 **1→0**(직전→현재). 15.607pt ≥ 10pt이므로 큰 축소도 허용된다. 현재 Draft는 main-511fd73의 04 승자와 같은 결과이며 good 태그를 복원했다.
- `rt/nd-single` document: **7.927→7.927px**, RT2 **1→1**. 이전 RT2 제거 후보 5.805px는 목표 11px 아래이며 기본 그림 대비 26.8% 작으므로 계속 차단된다.
- `rt/gw-ret` document: **7.482→7.482px**, check **3→3**. 04 승자는 6.633px로 목표 11px 아래이고 기본 그림 대비 11.35% 작으므로 예외 대상이 아니다. 노트 배경 가림은 남는다.
- `qa/t1-privatelink` slide-no-title: **7.166→7.166pt**, tier-0 **4→4**. 04 승자는 5.920pt로 목표 10pt 아래이고 기본 그림 대비 17.39% 작아 계속 차단된다.

아래 순서는 **기준(04) / 직전 무조건 90% 한도 / 이번 목표 예외**다. 글자 단위는 document px, slide pt이며 모두 effective text size다.

| Case | Mode | 글자 | R-flow | R-rt | Check |
|---|---|---|---|---|---|
| `rt/nd-single.layout.yaml` | document | 7.927 / 7.927 / 7.927 | 0 / 0 / 0 | 1 / 1 / 1 | 0 / 0 / 0 |
| `rt/nd-single.layout.yaml` | slide | 7.736 / 7.736 / 7.736 | 0 / 0 / 0 | 0 / 0 / 0 | 1 / 1 / 1 |
| `rt/nd-single.layout.yaml` | slide-no-title | 8.419 / 8.419 / 8.419 | 0 / 0 / 0 | 0 / 0 / 0 | 1 / 1 / 1 |
| `rt/gw-ret.layout.yaml` | document | 6.633 / 7.482 / 7.482 | 0 / 0 / 0 | 0 / 0 / 0 | 2 / 3 / 3 |
| `rt/gw-ret.layout.yaml` | slide | 7.649 / 7.649 / 7.649 | 0 / 0 / 0 | 0 / 0 / 0 | 6 / 6 / 6 |
| `rt/gw-ret.layout.yaml` | slide-no-title | 8.567 / 8.567 / 8.567 | 0 / 0 / 0 | 0 / 0 / 0 | 6 / 6 / 6 |
| `qa/t1-privatelink.layout.yaml` | document | 4.651 / 4.651 / 4.651 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `qa/t1-privatelink.layout.yaml` | slide | 5.920 / 5.920 / 5.920 | 2 / 2 / 2 | 0 / 0 / 0 | 7 / 7 / 7 |
| `qa/t1-privatelink.layout.yaml` | slide-no-title | 5.920 / 7.166 / 7.166 | 2 / 3 / 3 | 0 / 0 / 0 | 7 / 7 / 7 |
| `qa/t4-shared-lane.layout.yaml` | document | 12.000 / 12.000 / 12.000 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `qa/t4-shared-lane.layout.yaml` | slide | 15.607 / 18.237 / 15.607 | 0 / 1 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |
| `qa/t4-shared-lane.layout.yaml` | slide-no-title | 16.500 / 16.500 / 16.500 | 0 / 0 / 0 | 0 / 0 / 0 | 0 / 0 / 0 |

## Corpus 전후와 worse의 이유

760 runs: **better 3 / same 755 / worse 2 / unjudged 0**. 기대 결과·태그 불일치는 0이다. 직전 구현 대비 shared-lane slide만 회복됐고, 남은 worse는 다음 두 건이다. 두 건 모두 글자 한도로 되돌림이며 관련 없는 worse는 0이다.

| Worse Case | 이유 |
|---|---|
| `rt/gw-ret` document | 글자 한도로 되돌림: 04 글자 6.633px < 11px, 기본 그림의 88.65%; check 2→3. 가림 백로그는 아래에 있다 |
| `qa/t1-privatelink` slide-no-title | 글자 한도로 되돌림: 04 글자 5.920pt < 10pt, 기본 그림의 82.61%; tier-0 3→4, check 7→7 |

| 항목 | 기준 | 이번 | 증감 |
|---|---:|---:|---:|
| R-border | 17 | 17 | +0 |
| R-flow | 45 | 46 | +1 |
| R-rt | 90 | 90 | +0 |
| R-twin | 6 | 6 | +0 |
| R-label | 2 | 2 | +0 |
| R-fit | 298 | 298 | +0 |
| Check problem | 377 | 378 | +1 |

R-flow +1은 privatelink slide-no-title이다. Check +1은 gw-ret document의 `SERVICE AS TEXT` +2와 `LINE OVER TEXT` −1이다. 다른 check 코드 증감은 0이며 새 canvas clipping은 0이다. 단, canvas clipping이 0이라는 사실은 아래 불투명 배경 가림을 검사했다는 뜻이 아니다.

744개 완성 Draft에서 새 조건 위반 **0**을 확인했다. 목표 이상 예외를 실제 사용한 Case·Mode는 shared-lane slide **1건**이며 글자 15.607pt / 목표 10pt다 (`default-text/`, `audit.json:target_exception_cases`).

## gw-ret 가림이 verdict에서 다뤄지지 않는 이유

1. **크기 한도:** 04 승자의 6.633px는 목표 11px와 기본 그림의 90%인 6.733px 모두 아래다. 그러므로 이번 예외로 04 승자를 선택할 수 없다.
2. **Paint order:** `edge:9:label`의 응답 baseline은 y=671이고 추정 text box는 `(351.8, 662, 375.8, 674)`다. 그 뒤에 노트 배경 `(x=16, y=668, w=1187, h=116)`이 opaque `#F8F9F9`로 그려져 글자의 일부를 가린다. 같은 `edge:9`의 `(687.6,680)→(40,680)` 반환선 구간은 배경에 완전히 가려진다.
3. **검사 범위:** `check_layout.collect`는 stroke 있는 rect를 테두리 segment로 수집하고 fill의 덮임을 따로 저장하지 않는다. 이 배경은 white mask 목록에도 없다. 현재 `LINE OVER TEXT` 1건은 노트 테두리 y=668이 응답 text box를 지나는 것을 보고한다. opaque fill이 나중에 앞선 글자·선의 일부를 가리는 check는 없다.
4. **Verdict:** F5/L1은 가리기 전 text box와 전체 논리 경로의 거리·방향을 판정한다. 응답 글자와 경로는 canvas 안에 있으므로 clipping count는 0이고 gw-ret의 tier-0도 0이다. 테두리 교차는 일반 check 수에만 포함된다. 실제 글자/경로 가림이 별도 lost-content 항목으로 판정되지 않는다.

이전 보고서의 “반환선이 Users까지 이어진다”는 서술을 정정한다. SVG 좌표의 연결을 rendered visibility로 판단한 것이 잘못이었다. 확대 PNG에서도 응답 글자 하단과 아래 수평 반환선의 가림을 확인했다.

사용자 지시대로 이 검사나 배치를 고치지 않았다. `docs/dev/backlog.md`의 “뒤에 그린 불투명 배경의 라벨 가림”에 라벨·연결선 가림 검사를 기록했다. `test_gw_ret_response_label_is_not_covered_by_note_background`는 assertion 실패만 허용하는 strict xfail로 보존해 다른 예외를 숨기지 않는다.

## 시간

| 항목 | 기준 | 이번 |
|---|---:|---:|
| Draft 중앙값 (s) | 0.1845 | 0.187 |
| 최악 (s) | 19.55 | 19.484 |
| 시간 합계 (s) | 957.93 | 977.31 |
| Corpus wall (s) | 165.39 | 168.67 |

최대 비율 **1.667×** (`sides/vbottom2` slide-no-title, 0.015→0.025초), 최악 **19.484초**, wall **1.020×**, 시간 합계 **1.020×**다. 3×·30초 초과는 0이다.

## PNG와 증거

`~/.cache/skill-design/t06-rt/target-exception/`에 `corpus.json`, `audit.json`, `case-progress.json`, `gw-ret-occlusion.json`, `default-text/`, `corpus-drafts/`, `red.log`, `select-green.log`, `pytest.log`, `examples.log`와 재현 스크립트를 보존했다. Corpus 실행기는 fork wrapper로 같은 -j 6을 사용하며 후보 결과를 바꾸지 않고 크기·목표를 관찰한다. Raw JSON은 편집하지 않았다.

아래 5개 PNG를 이미지 보기 도구로 직접 확인했다:

- `/home/ec2-user/.cache/skill-design/t06-rt/target-exception/png/qa-t4-shared-lane-slide-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/target-exception/png/rt-nd-single-document-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/target-exception/png/rt-gw-ret-document-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/target-exception/png/qa-t1-privatelink-slide-no-title-pair.png`
- `/home/ec2-user/.cache/skill-design/t06-rt/target-exception/png/gw-ret-label-occlusion-detail.png`

git 메타데이터/index가 읽기 전용이므로 임시 git-dir의 별도 index로 같은 t06-rt 브랜치에 직접 커밋한다. 그 index 기준 `git diff HEAD --stat`이 빈 출력인지 확인한다. **index 동기화 필요**.
