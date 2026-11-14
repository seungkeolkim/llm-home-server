# Paseo 구축 검증

아래는 도입 시 검증 이력입니다. 이후 사용자 요청으로 Remote Pi 전용 구성을 정리했으며 기존 Remote Pi `/health`는 현재 404입니다. Paseo 보존·현재 검증은 [원격 지원 정리 기록](REMOTE_SUPPORT_CLEANUP.md)을 따릅니다.

2026-11-14 KST, Windows 11 Native, Paseo 0.15.4 + Pi 1.5.2 + Strata QFN IQ3_XXS에서 수행했습니다.

| 검증 | 결과·증거 |
|---|---|
| 공식 Desktop ZIP SHA256 | `43c91edf4c8b7004721344c00f7524ad01b764ca97020420ebd00dc8d25561c1`, GitHub asset digest 일치 |
| Native daemon·Desktop | CLI 0.15.4, loopback 6767 health 200, 공식 Windows ZIP 실행·Host 연결·첫 실행 안내 완료 |
| Thinking 표시 설정 | Windows UI에서 `추론 항상 펼치기` ON / `채팅 표시: 전체` 확인 |
| 모델 조회 | available Pi만, Strata QFN 모델 1개, Low 기본 Thinking 선택지 |
| 기존 Extension | billion-context·web-access·기존 승인 Extension을 로드하여 실제 Pi session 실행 |
| 실제 Native QFN 응답 | `17 × 23` → `391`, `native-agent.json` |
| 실제 Relay Thinking stream | `7 × 8` → `56`, reasoning delta 5개, `streaming.json` |
| 승인·거절 | 승인 전 파일 없음, Yes 후 테스트 파일 생성; No 후 두 번째 파일 없음, `approval.json` |
| Paseo 자동승인 | 사용자 요청으로 auto 적용 후 실제 Relay에서 write·edit·bash가 확인 질문·승인 응답 없이 완료, `automatic-approval.json` |
| 승인 정책 분리 | 4개 도구 자동승인·수동 승인/거절·설정 오류 manual fallback·Subagent 차단·기존 Pi 수동 승인 확인, LLM 없는 `approval-mode.json` |
| Metadata·중복 요청 차단 | 실제 Pi + 가짜 backend에서 모두 handled, LLM 요청 0, `policy.json` |
| 차단 후 turn 정리 | 다른 PID의 공통 lock이 있을 때 요청이 LLM 없이 idle로 완료, `blocked-turn.json` |
| 생성 중 취소 | 실제 reasoning 수신 후 cancel, Agent idle·gateway in_flight 0, `streaming.json` |
| Relay TLS·E2EE·재접속 | 공식 offer + Node transport로 `azzi-home.duckdns.org:38789` protected 연결·Agent 목록 조회 2회, `relay.json` |
| Relay·기존 Remote Pi | Paseo container healthy, `/paseo-health` 정상, 기존 `/health` OK·기존 container healthy |
| 종료 경계 | Native Paseo 종료 중 Relay·기존 Remote Pi 유지, 이후 Native Paseo 재기동 |
| 포트 | daemon loopback 6767, Relay expose 4000만, host publish·추가 Firewall·공유기 규칙 없음 |
| 설정·서비스 보존 | 보호 파일 8개 Hash 일치, Strata Parallel 1, 기존 Pi PID 17032·Strata PID 31180 유지·LibreChat/MongoDB healthy |
| 재준비·정적 검사 | helper 재실행 시 Paseo 설정 byte 불변, Python AST·Compose config·Git diff whitespace 통과 |
| Source 경계 | 공식 research clone 2개 clean, 자체 patch·dependency 설치 없음 |

원본 기록은 `runtime/Paseo/verification/` 아래이며 Git에서 제외합니다.

## 재사용 검증 도구

- `scripts/Paseo/verify_connection.mjs`: 실제 모델 조회·Math 응답·Timeline, 새 테스트 Agent 생성.
- `scripts/Paseo/verify_approval.mjs`: manual 모드에서 위 Agent의 fixture write 승인·거절. 최초 검사 뒤 같은 fixture 파일이 있으면 덮어쓰지 않고 중단합니다.
- `scripts/Paseo/verify_approval_mode.mjs`: LLM 없이 auto/manual·설정 오류·기존 Pi 승인·Subagent 차단 확인. 운영 설정을 바꾸지 않습니다.
- `scripts/Paseo/verify_automatic_approval.mjs`: auto 모드에서 새 fixture Agent의 실제 write·edit·bash 완료 확인. 승인 응답을 보내지 않습니다.
- `scripts/Paseo/verify_policy.py`: 실제 Pi + 가짜 backend의 Metadata·공통 lock 차단. 사용자 turn lock이 있으면 덮어쓰지 않고 실패합니다.
- `scripts/Paseo/verify_relay.mjs`: Pairing offer를 로컬에 기록하고 E2EE 연결·재접속, LLM 호출 없음.
- `scripts/Paseo/verify_streaming.mjs`: 테스트 Agent의 실제 Thinking·생성 중 취소.

실제 LLM 검사는 Strata가 켜져 있고 다른 Pi 작업이 없을 때 수행합니다. 파일 변경 범위는 `runtime/Paseo/verification/workspace/`입니다.

## 남은 확인과 한계

- Android 서버 연결은 사용자가 성공을 확인했습니다. Thinking·작업·취소·백그라운드 복귀·모바일 재접속·AdGuard 병행의 개별 검증은 남아 있습니다. 서버의 공인 DDNS·외부 port 검사와 실기기 검사를 구분합니다.
- billion-context 압축·복구, Browser, 첨부, Git worktree·PR·commit, 장시간·262K 부하는 Paseo 조합에서 새로 검증하지 않았습니다.
- 기존 Pi Desktop 실행 중 프로세스에 attach하지 않으며 동일 JSONL 동시 사용을 피해야 합니다. 자동 Reasoning Loop 감지는 없습니다.
- Desktop 첫 Host 연결과 표시 설정은 UI로 확인했습니다. 재기동 후 추가 UI 관측은 Windows automation helper의 `foreground window did not report a process id` 오류로 중단했습니다. 이후 process·health·모델·Relay streaming은 API로 확인했습니다.
- daemon process tree Working Set 합은 약 0.5–0.6 GiB였습니다. Desktop 제외이며 공유 page 중복 합산 가능성이 있어 실제 추가 physical RAM으로 단정하지 않습니다.
- TLS 갱신은 기존 Caddy 정책을 유지하며 미래 실제 갱신 시점의 결과는 아닙니다.
