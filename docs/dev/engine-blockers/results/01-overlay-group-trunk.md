# Ticket 01: overlay group 끝의 trunk와 선 옵션

기준은 main `c3aa9ef`의 `~/.cache/skill-design/baseline/main-c3aa9ef.json`과 `main-c3aa9ef-drafts/`다(`-j 6`). 독립 리뷰(Codex 코드 리뷰, PNG 판정)는 이 문서 뒤에 별도로 한다.

증거: `~/.cache/skill-design/improve/eb/eb01/`
- corpus: `eb01.json`, `corpus.log`, `eb01-drafts/`
- 재현 before/after: `before/{to,from}-{document,slide,slide-no-title}.{draft.svg,png}`, `after/` 같은 이름. before는 HEAD(2f66c6f) 코드로 같은 spec을 그린 것이다.

## 완료 조건

- [x] 재현 두 개가 corpus에 있다(`qa/ov-trunk-to-group`, `qa/ov-trunk-from-group`). 세 mode 모두 줄기 하나가 group의 한 점(가운데)에서 만나고, Layout OK, rules.py 위반 0(`good: R-flow, R-label, R-border`).
- [x] trunk를 만들 수 없는 사례가 경고를 내고 corpus가 `match`로 확인한다(`qa/ov-trunk-straight`: `shape: H`). 접힌 HVH 경고도 같다(`qa/hvh-level`).
- [x] 기존 단일 overlay 선(`lanes/*`, `bench/*pipeline` `proxy -> aurora`, `sides/ov3` `mon -> asg`)을 포함해 corpus 전체 draft가 byte-identical이다.
- [x] `references/layout_spec.md` edges 절에 group 끝의 trunk와 offset을 적었다.
- [x] corpus vs main-c3aa9ef: **better 0 / same 804 / worse 0, uncompared 12(새 사례 4개 × 3 mode), 바뀐 draft 0**, check problem delta +0, 위반 delta 전부 +0, 태그 불일치 0, failures 0. 전체 테스트 **962 passed, 1 xfailed**.
- [ ] Codex review, Codex PNG 판정: 이 문서 뒤.

## 무엇을 바꿨나 (`scripts/layout_route.py`)

- **group으로 모이는 trunk의 shape** (`_group_trunk`): trunk 선의 공유 끝이 group이고, 그 group의 범위가 다른 끝들의 행을 덮어 instance가 각자 H가 되면(`task.* -> aurora`), 모든 instance를 HVH로 바꾼다(열을 덮으면 VHV). 그러면 기존 trunk 표시가 merge / fork로 묶는다.
- **한 점에서 만남** (`_Topo.pin`, `_Edge.port`): 공유 group 끝은 상대 끝의 좌표 대신 group의 행 / 열 중심(overlay는 box 중심)에서 만난다. lead와 follower가 같은 port를 받아 follower가 lead의 꺾임점에서 끝난다(merge) / 시작한다(fork). 모든 `_port` 호출(ends, steps, detours, `_group_ports`)이 `x.port`를 거친다.
- **overlay 끝의 offset**: overlay 끝의 `from_offset` / `to_offset`은 overlay 중심에서 잰다(`to_offset: 0` = 중심). 처음에는 모든 group 끝에 적용했지만, nfw 예제 slide가 나빠졌다(아래). 그래서 일반 box group 끝은 예전 기준(마주 보면 상대 끝 좌표, 아니면 중심)을 유지한다.
- **detour 순위**: 공유 group 끝 trunk에서는 U 우회 후보를 unclean 후보와 같은 순위에 둔다. 우회하면 trunk가 갈라져 각자 선이 되기 때문이다. 자기 shape이 border에 붙어 unclean이어도 먼저 그려지고, layout.py feedback이 간격을 넓혀 다음 round에 깨끗해진다(mirror 사례: 전에는 UVHV 두 개로 그려졌다).
- **경고 두 가지**:
  - `trunk: true not drawn, each instance keeps its own line — <why>`: 공유 끝이 group인 trunk가 만들어지지 않을 때 낸다. `shape: H|V` 강제, 다른 끝이 group 양쪽에 있거나 열을 공유함, from_side / to_side 불일치, instance shape가 서로 다름 같은 이유를 group id와 함께 밝힌다. 예전에는 아무 경고 없이 넘어갔다.
  - `refusing the requested shape: HVH, drawn H — its ends are level (y = …)`: 강제한 HVH / VHV가 같은 높이의 두 port 사이에서 직선으로 접힐 때 낸다. layout.py feedback의 `drew X instead of` 정규식에 걸리지 않게 썼다. 걸리면 간격을 넓히지만, 같은 높이의 두 끝에는 아무 간격도 leg를 주지 못한다.

## 의도한 변경 draft

없다. 기존 corpus draft는 모두 byte-identical이다. 새 사례 4개(12 run)만 추가됐다.

## 중간에 버린 것

- group 끝 전체에 "offset은 중심에서" 규칙을 적용한 첫 시도: corpus가 `docs/examples/specs/nfw-reference-architecture` [slide] 1건을 worse로 판정했다.
  - 판정 근거: R-fit shortfall 1.89 → 2.04, canvas 1422×721 → 1725×1414, note 6줄 경고, VPC B 선이 TGW 왼쪽에서 VPC B 오른쪽 면으로 들어감.
  - 원인: `vpca <-> tgw`의 `from_offset: -60`. selection 중간 geometry에서 tgw.cx가 VPC A box 폭 안에 들어왔다. 예전 규칙은 tgw.cx − 60, 새 규칙은 colc − 60이어서 선택 경로가 달라졌다. 최종 geometry에서는 두 규칙이 같은 점을 준다.
  - 처리: overlay 끝에만 적용하도록 좁혔다. 이 판단이 ticket 문구("offset on a group end is measured from the group's centre")보다 좁으므로 리뷰에서 확인을 받는다.

## 백로그 후보 (이 ticket 범위 밖)

- AZ 안 첫 subnet 열을 덮는 overlay(`over: [task.*]`, task가 첫 열)는 세로 테두리가 AZ 2 제목을 지난다(LINE OVER TEXT, 이 변경 전에도 같다). mirror 사례는 템플릿처럼 ALB subnet 열을 앞에 두어 피했다.
