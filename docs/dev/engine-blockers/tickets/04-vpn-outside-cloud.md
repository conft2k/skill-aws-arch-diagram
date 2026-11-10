# 04: Site-to-Site VPN outside the AWS Cloud in the DX templates and the docs

**What to build:** The house rule (user decision 2026-11-10): AWS Site-to-Site VPN is an AWS service built for an external connection, so the diagram draws it outside the AWS Cloud box, as an exception to "regional resources go in the Region" — as `docs/examples/specs/tgw-reference-architecture.layout.yaml` does with `service/AWS-Site-to-Site-VPN`. Stage 5 (commit 9b9ddc2) moved the DX templates' VPN into the Region as `resource/Amazon-VPC_VPN-Connection` and rewrote the docs to match; this ticket puts both back to outside the Cloud and states the reason. The rest of 9b9ddc2 (private subnets kept, the document/slide split, "연결:/전파:" captions, account nesting) stays.

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `templates/dx-vpn-tgw.layout.yaml` and `templates/dx-vpn-tgw-slide.layout.yaml` draw `service/AWS-Site-to-Site-VPN` outside the AWS Cloud between the Internet and the TGW, keep "VPN attachment" readable on the VPN → TGW line or caption, and still pass every rule in the modes they list (tests/test_templates.py).
- [ ] references/diagram_guide.md, references/layout_spec.md, SKILL.md and the template header comments say: VPN outside the Cloud, with the reason; no doc says "VPN connection in the Region"; the "Older examples" sentence is gone.
- [ ] GLOSSARY or the guide records the exception once, so reviewers and judges can cite it.
- [ ] Corpus vs main-c3aa9ef: only the two DX templates change; tests green; Codex review 0 blocking; Codex PNG judge on both templates (told the convention) not worse and 0 misread blocking.
