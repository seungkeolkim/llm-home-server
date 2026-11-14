# Remote Pi 검증 기록

이 문서는 제거 전 검증 이력입니다. 2026-11-14 사용자 요청으로 Remote Pi 전용 구성을 정리했으며 현재 상태는 [Paseo 정리 기록](../Paseo/REMOTE_SUPPORT_CLEANUP.md)을 따릅니다.

검증일: 2026-11-13~14 KST. DuckDNS로 변경하여 Production HTTPS/WSS Relay와 Native Pi 연결이 정상입니다. Android 수동 코드 pairing 성공은 사용자 확인이며, 세부 원격 동작 검증과 구분합니다.

| 검증 | 결과 |
|---|---|
| Android Custom Relay 비표준 port | 공식 `app-v1.2.0` source에서 `https://host:38789` 허용 및 WSS 변환 시 port 유지 확인 |
| 공식 APK checksum | `SHA256SUMS`와 일치, SHA256 `00576a4758c2a47cb8c500f048c9703873f909d9af03020de618c2bc447d6b30` |
| Windows Native Pi Extension | Pi 1.5.2, Node v24.20.0, Windows win32에서 공식 Extension 0.7.0 load 오류 0개 |
| 기존 Extension 공존 | `billion-context`, `pi-web-access`, 승인 Extension 동시 load 성공, LLM 요청 0건 |
| Single Agent wrapper | Agent mesh 3개 tool 노출 없음, `/remote-pi` command 등록 성공 |
| 기존 설정 보존 | Infernix·Strata·Pi 설정 및 Pi manifest/lockfile 8개 SHA256 일치 |
| Port/network 충돌 | 배치 전 host 443·8789 미사용, 독립 Compose project/network 사용 |
| Relay health | container 내부 및 Caddy container에서 `/health` → `OK` |
| Relay 공개 여부 | Host PortBindings 없음, `internal: true` network 한 개만 사용 |
| Caddy 경로 | host TCP 443·8789 → container TCP 443; Caddy → `relay:3000` |
| restart policy | 두 container 모두 `unless-stopped` |
| Windows Firewall | 관리자 실행 성공, `LlmHomeServerRemotePiHttpsInbound` inbound Allow TCP 443·8789 |
| 외부 443 도달 | 최초 timeout 이후 TLS-ALPN-01 challenge certificate 응답이 여러 CA 검증 요청에 제공됨 |
| 인증서 발급 | ipTIME CAA 제한 확인 후 DuckDNS에서 Staging·Production TLS-ALPN-01 발급 성공 |
| Production HTTPS/WSS | Windows curl·Node 기본 trust로 hostname/chain 검증 및 HTTP 200 OK, 공식 WSS transport Ed25519 인증 성공 |
| Relay 재접속 | 같은 임시 key로 연결 해제 후 재인증 성공. Agent/LLM 호출 없이 수행 |
| 자동 인증서 관리 | Caddy maintenance·ACME renewal 정보 확인, 재시작 후 같은 fingerprint 유지. 실제 미래 갱신 시점은 미도래 |
| 실제 Native Pi ↔ Relay | 기존 Desktop 세션의 `/remote-pi` 실행 및 Relay 인증 확인. Pi 재시작 후 같은 identity·room 재연결 확인 |
| Desktop QR 호환 | custom message 미표시 확인 후 같은 공식 pairing URI를 로컬 PNG로 출력. 유효기간·일회용 검증은 공식 Extension 유지 |
| QR 파일 만료 | PNG signature 확인, 잘못된 URI 거부, 오래된 timer의 새 QR 보호 및 현재 QR 만료 삭제 테스트 통과 |
| Android ↔ Relay pairing | Custom Relay와 공식 `remotepi://pair` 수동 코드 전달 후 사용자가 정상 작동 확인 (2026-11-14 KST) |
| Android 세션 제어·원격 승인·모바일 재접속 | 각 시나리오의 개별 검증은 미실시 |
| 브라우저 Relay root 응답 | 일반 GET `/`에서 사용자 첨부와 같은 Upgrade header 누락 HTTP 400 재현. `/health`는 200 OK, 정상 trust WSS 인증·재접속 성공 |
| Pi 종료 후 두 container 유지 | container ID·시작 시각 동일, 두 container healthy 및 HTTPS health OK. Pi 재시작 완료 |
| Parallel=1 | 기존 설정 변경 없음, 현재 Strata 설정 `parallel: 1`. Infernix는 현재 실행하지 않아 live 확인하지 않음 |
| DuckDNS 신규 hostname | 사용자 등록 및 A record `14.7.75.149` 일치 확인. AAAA 및 CAA 제한 없음 |
| DuckDNS updater | 자동 Task 미등록. 사용자 요청으로 Home Server 수동 버튼은 후속 계획에 기록하고 helper를 수동 실행 전용으로 정리 |

명령:

```powershell
node scripts/RemotePi/verify-extension.mjs
node scripts/RemotePi/verify-extension.mjs --wrapped
node scripts/RemotePi/verify-extension.mjs --installed-loader
node scripts/RemotePi/verify-relay.mjs
node --test tests/RemotePi/pairing-artifacts.test.mjs
.\scripts\RemotePi\manage-relay.ps1 validate
```

실행 결과는 `runtime/RemotePi/verification/extension-compatibility.json`, `caddy-staging.log`, `dns-caa.json`, `protected-hashes.json`, `container-layout.json`에 보관합니다. Raw 사전 container/network 및 설정 hash는 `data/RemotePi/backups/`에 있습니다.

2026-11-14 커밋 전 확인에서는 Management Server·Pi gateway의 Python 테스트 55개와 control history·pairing artifact의 Node 테스트 7개가 통과했습니다. PowerShell script 7개의 구문, staged JSON 9개와 `git diff --cached --check`가 정상입니다. 설치된 loader의 Extension load 오류는 0개이며 HTTPS health·WSS 인증 및 재접속을 재확인했습니다. Pi gateway/Desktop과 Relay/Caddy는 실행 중이며 보호 설정 8개의 SHA256이 유지됩니다. 실제 local 설정·runtime·첨부 파일을 커밋에서 제외했고 staged 파일의 기존 local 비밀값 일치는 0개였습니다. Python 테스트에는 기존 Starlette TestClient의 httpx 사용 deprecation warning 1개가 있습니다.
