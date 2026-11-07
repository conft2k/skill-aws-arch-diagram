# 개발 백로그

2026-11-07에 멈춘 지점과 남은 일입니다. 다시 시작할 때 이 문서와
[`rules-design.md`](rules-design.md)를 먼저 읽습니다.

## 지금 상태

- **회귀 corpus:** `tests/corpus/`(MANIFEST.yaml) + `tests/run_corpus.py`가 변경 판정의 기준입니다.
  - 실행: `python3 tests/run_corpus.py --rule-checker scripts/rules.py:corpus --keep <dir> --out <json> -q -j 6`
  - 결과: 246개 항목, 706회 실행. spec 형식 오류 16건만 거부되고, 이전에 거부되던 모순 제약 케이스 4개도 이제 그려집니다.
- **규칙 검사기 1단계:** `scripts/rules.py`는 보고 전용이라 엔진 draft를 바꾸지 않습니다.
  - 규칙: R-flow, R-rt, R-twin, R-label, R-fit, R-border
  - corpus의 `good`/`bad` 태그로 검사기 판정을 검증합니다.
- **사용자가 정한 기준:** 그림을 보고 정한 기준은 `rules-design.md` §6에 있습니다.
  - RT1 엄격: 허브의 모든 선이 연관된 RT만 허브 옆이어도 통과
  - RT2: 연관 선이 하나인 RT는 그 선에서 2S + sibling_gap 안
  - F5·L1의 직접 배치 면제와 모서리 판정
  - R-border를 tier 0으로
- **리뷰:** 코드 리뷰는 Codex CLI(`codex exec`)가 맡고, 코드는 Claude Code가 씁니다.

## 남은 일 (순서대로)

1. **2단계: 엔진이 규칙 판정으로 후보를 고르기.**
   - 설계는 `rules-design.md` §3, 완료 기준은 §4 Step 2에 있습니다.
   - 아래 문제를 이 단계에서 다룹니다.
     - `rt/three-b`: RT1 위반입니다. nfw처럼 ENI 선이 RT를 감싸게 유도해야 합니다.
     - `rt/single`류의 RT 배치: 보류한 브랜치 `f-rtlone`(fe033ee)이 노린 개선입니다. Codex 판정은 조건부였습니다(gm4가 나빠지고, 긴 라벨에서 9.66pt).
     - `flowcol/r2-float-two-wide`: 폭을 줄이면 팬아웃 교차가 1개에서 2개로 늘어납니다(R-flow F3).
     - `merge-v3az`(제목 없는 슬라이드): 10pt를 지키는 대가로 선 2개가 UHVH로 그려집니다.
2. **3단계: 경우별 휴리스틱 제거.**
   - 대상은 `rules-design.md` §3 끝의 Removable later 목록입니다.
   - 휴리스틱 하나당 커밋 하나로 지우고, 지울 때마다 corpus 판정과 검사 건수가 같거나 좋아야 합니다.
3. **R-border B2를 check_layout에도 넣기.**
   - B2는 선이 그룹 머리띠(아이콘·제목·CIDR 줄)를 지나는 경우입니다.
   - 지금은 rules.py만 보고합니다. corpus 슬라이드 59건(주로 x=308에서 App subnet 아이콘과 제목 사이)은 check_layout에 넣어야 엔진이 고칩니다.
   - 이 중 11건은 실제 글자 크기 판정으로 요청한 HVH 선이 그려지면서 생겼습니다(r5-mid-*, r6-flowrow-bottom, r7-*, t2-cloud-overlap, t4-*, merge-vfan). 같은 케이스의 다른 모드에 원래 있던 유형입니다.
4. **저장소 전체 Codex 재리뷰(`CODE_REVIEW-2.md`).**
   - 첫 리뷰의 R1~R7은 모두 고쳤습니다.
   - 레이아웃 엔진 바깥 부분(export, PPTX, 아이콘, spec 로더, 문서)은 지금 바로 리뷰할 수 있습니다.

## 알려진 문제 (막는 문제 아님)

- **svg2pptx / export**
  - `stroke-width="1e-320"`인 점선은 overflow가 나고 출력이 일부만 남습니다.
  - polyline만 있는 슬라이드는 그룹 크기가 0으로 기록됩니다.
  - viewBox에 NaN이 들어가도 그대로 받습니다.
  - render_pptx 미리보기 파일이 입력 덱의 하드 링크이면 덱을 덮어씁니다.
  - 쓰는 도중 I/O가 실패하면 그 파일은 일부만 써진 채 남습니다(평범한 `open()`과 같은 동작).
- **rules.py**
  - owner map을 `collect()`의 `own`과 따로 만듭니다.
  - 0.5px 허용값이 두 곳에 정의돼 있습니다.
  - check_layout의 비공개 함수 `_head_at`을 씁니다.
  - `for:`가 없는 RT는 판정하지 않습니다.
  - 설계 문서 L2의 "once each"에 `step_each` 예외를 적어야 합니다.
  - F5의 여유 4px 경계 사례가 있습니다(engine3/latest3-pipeline).
- **overlay 분할**
  - 상자를 나눌지 미리 시험하는 계산 때문에 로드가 느려집니다(20개 분할 시 약 1.5초).
  - 나뉜 상자에서 header 경고가 두 번 나올 수 있습니다.
- **xy 완화**
  - r3-xy-30 문서 모드에서 KMS를 Cloud 위 바깥에 두어 약 94px의 빈 띠가 생깁니다.
  - 빈 트랙 규칙 때문에 `on:` 노드가 있는 슬라이드가 16px 넓어집니다.
- **거부 메시지:** 원인을 짚는 힌트가 부족합니다.
  - overlay 멤버가 VPC 안과 밖에 나뉜 경우
  - "테두리에 걸치려면 `in:`을 빼라"
- **문서:** `layout_spec.md`의 hub 설명이 동작과 다릅니다. 선이 닿지 않는 박스는 오류가 아니라 hub None입니다.
