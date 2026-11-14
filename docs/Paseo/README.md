# Paseo 운영 안내

구축일: 2026-11-14 KST. Branch: `feature/pi-local-coding-agent`.
Windows Native Paseo CLI·Desktop **0.15.4**, Pi **1.5.2**, Strata QFN IQ3_XXS **Context 262144 / Parallel 1**입니다.
Android 앱 설치와 서버 연결은 사용자가 확인했습니다. 모바일 개별 작업·재접속 검증은 아래 범위를 따릅니다.

## 실행과 종료

- 바탕화면 **Paseo 켜기**는 전용 daemon과 Desktop을 시작합니다.
- **Paseo 끄기**는 Paseo daemon·Desktop·자식 Pi와 진행 중 Paseo 작업을 종료합니다. LLM·LibreChat·기존 Pi·Caddy·Relay는 유지합니다.
- 기존 Home Server Pi 버튼은 기존 Pi Desktop·gateway를 제어합니다. Paseo 카드는 추가하지 않았습니다.
- 모델은 기존 Home Server에서 켭니다. Paseo 기동으로 모델을 Load하거나 교체하지 않습니다.

다음 명령은 어느 위치에서든 일반 PowerShell·CMD에서 실행할 수 있으며 관리자 권한은 필요하지 않습니다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\azzib\Desktop\workspace_local\llm-home-server\run-paseo.ps1" desktop
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\azzib\Desktop\workspace_local\llm-home-server\run-paseo.ps1" status
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\azzib\Desktop\workspace_local\llm-home-server\run-paseo.ps1" pair
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\azzib\Desktop\workspace_local\llm-home-server\run-paseo.ps1" stop
```

`start`는 Desktop 없이 daemon만 시작합니다. Desktop에는 `127.0.0.1:6767` Host를 연결하고 현재 repo를 Workspace로 열었습니다. 기존 Pi를 끄면 공유 gateway도 꺼져 Paseo의 모델 호출이 실패할 수 있습니다. 이 경우 Paseo를 껐다 켜면 gateway를 headless로 준비합니다. 두 제어를 서로 대체하지 않습니다.

## Android 연결

1. Paseo와 Strata 실행 상태를 확인하고 위 `pair` 명령으로 Pairing Link를 출력합니다. 같은 Link는 `data/Paseo/home/pairing-link.txt`에 저장합니다.
2. Android Paseo의 **페어링 링크 붙여넣기 / Paste pairing link**에 `https://app.paseo.sh/#offer=...` 전체를 넣습니다. Remote Pi의 `remotepi://pair`와 다른 형식입니다.
3. 공식 offer에 자체 Relay `azzi-home.duckdns.org:38789`, TLS, daemon public key와 protected security mode가 포함됩니다. `app.paseo.sh`는 링크 형식이고 실제 연결은 자체 Relay로 갑니다.
4. Host의 프로젝트·Workspace에서 Pi 모델로 작업합니다. 기존 Pi Desktop의 실행 중 프로세스에 attach하는 방식이 아니라 Paseo가 별도 Native Pi session을 관리합니다. Session import/resume은 별도 작업이며 같은 JSONL을 두 프로세스에서 동시에 열지 않습니다.
5. Android **설정 → 채팅 → 추론 항상 펼치기 ON / 채팅 표시: 전체**를 선택합니다. 기기별 설정이며 Windows Desktop에는 적용했습니다.
6. 모바일 네트워크에서 Thinking·승인·중단·재접속과 AdGuard 병행을 확인합니다. VPN은 필요하지 않습니다.

Pairing Link·daemon key·credential은 공개하거나 Git에 넣지 않습니다. TLS 검증을 끄지 않습니다. 자동 Reasoning Loop 감지·중단은 없으며 사용자가 Thinking을 보고 중단합니다.

## 포트와 Docker

**추가 공유기 Port Forwarding은 필요하지 않습니다.**

| 경로 | 역할·공개 범위 |
|---|---|
| 외부 TCP 38789 → Windows TCP 8789 → Caddy 443 | 기존 Android 접속 규칙 |
| 외부 TCP 443 → Windows TCP 443 → Caddy 443 | 기존 TLS-ALPN-01 발급·갱신 규칙 |
| `wss://azzi-home.duckdns.org:38789/ws` | Caddy → Paseo Relay WebSocket |
| `https://azzi-home.duckdns.org:38789/paseo-health` | Paseo health: `{"status":"ok"}` |
| `/`, `/health` 등 이전 Remote Pi 경로 | Remote Pi 정리 후 404 |
| Paseo Relay TCP 4000 | Docker internal network만, host publish 없음 |
| `127.0.0.1:6767` | Native Paseo daemon, loopback만 |
| `127.0.0.1:8490` | 기존 Pi gateway 유지 |

기존 billion-context 보조 listener도 loopback에서만 동작하며 외부 공개하지 않습니다.

Relay Compose는 `config/Paseo/compose.yaml`, Caddy 설정과 Compose는 `config/RemotePi/Caddyfile`·`config/RemotePi/compose.yaml`입니다. Remote Pi 전용 Relay는 제거했고, 기존 이름의 Caddy·network·production 인증서 volume은 Paseo가 사용하므로 그대로 유지합니다. `llm-home-server-paseo`는 internal network `llm-home-server-remote-pi_relay-internal`을 사용합니다. 최초 배치는 Caddy를 먼저 시작해 network를 준비한 뒤 Paseo Relay를 시작합니다.

```powershell
.\scripts\Paseo\manage-proxy.ps1 start
docker compose -f "C:\Users\azzib\Desktop\workspace_local\llm-home-server\config\Paseo\compose.yaml" up -d
docker compose -f "C:\Users\azzib\Desktop\workspace_local\llm-home-server\config\Paseo\compose.yaml" ps
```

Relay image는 `ghcr.io/getpaseo/paseo-relay@sha256:9d5c65d4bd2c42a85a5c8ab329f801a7db41dc4c153ca7bfba6c0857b3cdad0d`로 고정했습니다. `restart: unless-stopped`, 로그 회전·HTTP healthcheck를 적용하며 개발 디렉터리를 mount하지 않습니다. Relay와 Caddy는 Paseo 실행 여부와 독립적입니다.

TLS 인증서·자동 갱신은 기존 Caddy 정책을 유지합니다. 새 인증서 발급이나 갱신 정책 변경은 없습니다. DuckDNS 공인 IPv4 변경은 기존 수동 갱신 절차를 따릅니다. DDNS 자동 Task·버튼은 추가하지 않았습니다.

Caddy 상태·검증·설정 reload는 `scripts/Paseo/manage-proxy.ps1 status|validate|reload`로 수행합니다. Firewall 준비 helper는 `scripts/Paseo/enable-https-firewall.ps1`, 수동 DDNS helper는 `scripts/Paseo/update-duckdns.ps1`로 옮겼습니다. 기존 Firewall rule 이름 `LlmHomeServerRemotePiHttpsInbound`는 공유 포트 규칙의 중복 생성을 피하도록 유지합니다. Token은 여전히 미설정이며 자동 갱신 Task를 추가하지 않았습니다.

## 위치와 재준비

| 위치 | 내용 |
|---|---|
| `requirements/Paseo/package*.json` | CLI dependency와 lock |
| `data/Paseo/npm/` | 격리 npm runtime, 전역 설치 없음 |
| `data/Paseo/desktop/0.15.4/Paseo.exe` | 공식 Windows x64 ZIP 배포 |
| `data/Paseo/downloads/desktop-release.json` | 공식 asset·SHA256 검증 기록 |
| `config/Paseo/paseo.local.json` | loopback port·Relay endpoint·Desktop 경로 |
| `data/Paseo/home/config.json` | `PASEO_HOME`, daemon·Provider 설정 |
| `data/Paseo/home/` | key·credential·Host·Workspace 상태 |
| `runtime/Paseo/desktop-profile/` | 별도 Electron profile·표시 설정 |
| `runtime/Paseo/agent/` | 별도 Pi settings·models·AGENTS |
| `data/Paseo/pi-sessions/`, `data/Paseo/context/` | Pi session·압축 저장소 |
| `runtime/Paseo/daemon-output.log` | daemon·Provider 로그 |
| `runtime/Paseo/service-state.json` | 소유 PID·생성 시각 |
| `runtime/Paseo/verification/` | 격리 fixture와 검증 기록 |

재준비는 Paseo를 종료한 뒤 `scripts/Paseo/prepare-environment.ps1`로 수행합니다. 이미 존재하는 Paseo 설정을 보존합니다. 기존 Pi 설정이 바뀌더라도 자동 덮어 복사하지 않습니다. 바로가기는 `scripts/Paseo/create-shortcuts.ps1`로 다시 만듭니다.

## 기존 환경 보존과 실행 정책

- 기존 Infernix·Strata·Pi 설정과 npm dependency는 수정하지 않았으며 보호 파일 8개 Hash가 일치합니다.
- 기존 Provider 환경·Extension을 읽어 사용하고 Session·BILI state를 분리합니다. Remote Pi 자동 loader는 복사하지 않아 기존 room·identity를 중복 사용하지 않습니다.
- 사용자 요청으로 **Paseo는 자동승인**을 사용합니다. `config/Paseo/paseo.local.json`의 `"approval_mode": "auto"`가 `bash`·`powershell`·`write`·`edit`의 확인을 생략합니다. `"manual"`로 바꾸면 Yes/No 질문이 다시 표시됩니다. 설정은 도구 호출 때마다 읽으므로 모드 변경에 daemon 재기동은 필요하지 않습니다. 누락·오류·알 수 없는 값은 manual로 처리합니다.
- Paseo의 승인 로직은 `scripts/Paseo/pi-policy-extension.ts`에 있으며 기존 Pi 승인 Extension은 Paseo 설정에서만 제외했습니다. 기존 Pi의 원래 승인 파일·설정은 그대로입니다. Subagent 차단과 공통 turn lock도 유지합니다. Remote Pi 전용 loader는 정리했습니다.
- 기존 `runtime/PiCodingAgent/agent-turn.lock`을 공유하여 Pi·Paseo Agent turn을 직렬화하며 gateway single-request guard도 유지합니다.
- MCP Agent orchestration 주입과 Voice·Dictation·Web UI는 끕니다. `pluginsEnabled: false`여도 공식 built-in usage/provider plugin 프로세스는 로드됩니다. 이를 모든 plugin 프로세스 차단으로 해석하지 않습니다. 실제 available Provider는 Pi만 반환됐습니다.
- 자동 제목·branch·commit·PR Metadata용 `--no-session` Pi 입력은 LLM 전에 차단합니다. 필요한 이름은 수동 지정합니다. 실제 RPC probe의 LLM 요청은 0회였습니다.
- Pi 1.5.2의 `prompt.data.disposition = handled`에 Paseo가 인식하는 `agentInvoked: false`를 추가합니다. 원래 필드·정상 응답은 보존하고 공식 source를 수정하지 않습니다.
- Paseo 전용 Thinking 기본값은 Low, 선택지는 Off/Low/Medium/High입니다. 기존 Pi Thinking 설정은 유지합니다.

## 검증과 복구

실제 결과는 [검증 기록](VERIFICATION.md), 도입 전 근거는 [기능 검토](ASSESSMENT.md)를 따릅니다.

문제 시 `run-paseo.ps1 stop`으로 Native Paseo만 종료합니다. Relay까지 중지하려면 Paseo Compose의 `stop`을 사용합니다. Caddy 설정 복구는 현재 Paseo 경로를 기준으로 수행하며, 초기 백업 `data/Paseo/backups/initial/Caddyfile`은 제거된 Remote Pi Relay를 참조하므로 그대로 적용하지 않습니다. Production 인증서 volume·network·Caddy는 보존합니다.

Remote Pi 제거 범위와 공유 구성 보존 검증은 [원격 지원 정리 기록](REMOTE_SUPPORT_CLEANUP.md)에 정리합니다.

공식 근거: [v0.15.4 Release](https://github.com/getpaseo/paseo/releases/tag/v0.15.4), [Self-hosted Relay](https://github.com/getpaseo/paseo-relay), [Custom providers](https://paseo.sh/docs/custom-providers).
