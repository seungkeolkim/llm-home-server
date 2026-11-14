# Android Remote Pi 운영 안내

2026-11-14에 별도 Paseo Relay를 추가하여 Caddy `/ws`·`/paseo-health` 경로를 공유합니다. 기존 Remote Pi `/`·`/health` 경로와 container는 유지합니다. Paseo의 별도 Compose·Native daemon·Android 연결은 [Paseo 운영 안내](../Paseo/README.md)를 따릅니다.

확인일: 2026-11-14 KST (구축 시작 11-13). Branch: `feature/pi-local-coding-agent`. **Self-hosted HTTPS/WSS Relay와 Windows Native Pi 연결은 정상이며 Android 수동 코드 pairing 성공을 사용자가 확인했습니다.**

## 현재 상태

- 공식 Self-hosted Relay는 Docker에서 실행 중이며 `/health`는 `OK`입니다. Relay의 host port는 publish하지 않았습니다.
- Caddy는 별도 container로 실행하며 `azzi-home.duckdns.org`의 Staging 및 Production TLS-ALPN-01 발급이 모두 성공했습니다. 외부 443에서 CA의 검증 요청이 Caddy에 도달했습니다.
- `https://azzi-home.duckdns.org:38789/health`는 인증서 chain·hostname 검증을 유지한 Windows curl 및 Node.js에서 HTTP 200 `OK`입니다. 공식 transport로 WSS Ed25519 인증과 연결 해제 후 재접속도 성공했습니다.
- 두 container 모두 `restart: unless-stopped`입니다. Pi만 종료했을 때 container ID·시작 시각이 유지됐고 HTTPS 응답도 정상인 것을 확인했습니다. Pi는 다시 시작했습니다.
- Caddy 재시작 후에도 같은 Production 인증서 fingerprint가 유지됐습니다. 인증서 유효기간은 2026-11-13 13:52:19 UTC ~ 2027-02-11 13:52:18 UTC입니다. 자동 인증서 관리·background maintenance·ACME renewal 정보 수신을 확인했으며 실제 미래 갱신 시점은 아직 도래하지 않았습니다.
- Extension `remote-pi@0.7.0`은 별도 npm runtime에 설치했고 Windows Native Pi `1.5.2` 및 기존 Extension들과의 load 오류는 0개였습니다. 기존 Pi의 자동 discovery 경로에 additive loader를 추가했습니다. 실제 기존 Desktop 세션에서 `/remote-pi`로 연결했고 Pi 재시작 후 같은 identity·room의 재연결도 Relay 로그에서 확인했습니다. Android는 QR 대신 공식 `remotepi://pair` 코드를 수동 입력했으며 사용자가 정상 작동을 확인했습니다. 모바일 재접속·원격 작업 승인 등 세부 시나리오는 별도 검증 항목으로 남깁니다.
- 기존 Infernix·Strata·Pi 설정 및 Pi npm manifest/lockfile 8개는 사전 SHA256과 일치합니다. 현재 LLM은 Strata이며 Infernix로 전환하지 않았습니다.
- 사용자가 DuckDNS의 A record를 현재 공인 IPv4 `14.7.75.149`로 직접 등록했습니다. 기존 ipTIME DDNS는 다른 서비스에서 그대로 사용합니다. DuckDNS Token은 설정하지 않았고 자동 갱신 Task도 등록하지 않았습니다.

## 경로

| 역할 | 경로 |
|---|---|
| Compose | `config/RemotePi/compose.yaml` |
| Caddy 설정 | `config/RemotePi/Caddyfile` |
| DDNS·ACME 환경 | `config/RemotePi/.env.local` (Git 제외) |
| Extension 추가 설정 | `config/RemotePi/remote-pi.local.json` (Git 제외) |
| Extension policy wrapper | `scripts/RemotePi/remote-pi-extension.ts` |
| Native loader 설치 | `scripts/RemotePi/install-native-extension.ps1` |
| QR 표시 호환 helper | `scripts/RemotePi/pairing-artifacts.mjs` |
| 현재 pairing QR | `runtime/RemotePi/pairing/pairing-qr-code.png` (일시 파일, 외부 공개 안 함) |
| 격리 dependency | `data/RemotePi/npm/node_modules/remote-pi` |
| 고정 dependency 목록 | `requirements/RemotePi/package.json`, `package-lock.json` |
| 공식 Android APK | `data/RemotePi/downloads/RemotePi-1.2.0.apk` |
| 검증 로그 | `runtime/RemotePi/verification/` |
| 관리자 방화벽 결과 | `runtime/RemotePi/firewall-result.json` |

Relay DB는 `llm-home-server-remote-pi_relay-data` named volume에 저장합니다. Caddy 인증서 volume은 `llm-home-server-remote-pi-caddy-staging`과 `llm-home-server-remote-pi-caddy-production`으로 분리합니다. Caddy `/config`도 별도 named volume입니다. Container에 개발 디렉터리를 mount하지 않으며 Caddyfile 한 개만 read-only로 mount합니다.

Remote Pi upstream은 일부 상태에 `REMOTE_PI_HOME`을 지원하지만 identity·paired devices는 Windows Credential Manager와 `%USERPROFILE%\.pi\remote`를 사용합니다. 기존 Pi의 `runtime/PiCodingAgent/agent/settings.json` 및 `models.json`은 그대로 보존합니다.

## 제어

Repository root에서 실행합니다. Script 내부 경로는 `$PSScriptRoot`를 기준으로 계산하므로 script 자체를 절대경로로 지정하면 다른 현재 폴더에서도 실행할 수 있습니다.

```powershell
.\scripts\RemotePi\manage-relay.ps1 status
.\scripts\RemotePi\manage-relay.ps1 validate
.\scripts\RemotePi\manage-relay.ps1 logs
```

`start`로 두 container를 시작합니다. 현재 `.env.local`은 DuckDNS hostname과 Production ACME를 사용합니다. `stop`은 Remote Pi project만 중지하고 데이터를 삭제하지 않습니다. Pi의 ON/OFF는 기존 Home Server 또는 `run-pi-coding-agent.ps1`을 사용하며 이 Compose project를 제어하지 않습니다.

관리자 CMD에서 방화벽 script를 실행할 때는 다음 명령을 사용합니다. 실제로 TCP 443·8789 허용 rule 생성이 성공했습니다.

```bat
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\azzib\Desktop\workspace_local\llm-home-server\scripts\RemotePi\enable-https-firewall.ps1"
```

## ipTIME hostname의 TLS 차단과 해결

실제 오류:

```text
CAA record for iptime.org prevents issuance
```

조회된 `iptime.org`의 CAA는 `letsencrypt.org`를 허용하되 두 개의 지정 `accounturi`와 `validationmethods=dns-01`을 요구합니다. 자체 Caddy의 계정에는 발급 권한이 없습니다. CNAME으로 ipTIME hostname을 가리켜도 CAA lookup이 CNAME을 따라가므로 해결책으로 사용하지 않습니다.

해결 방법은 `azzi-home.duckdns.org`의 A record를 서버 공인 IP로 직접 등록하는 것이었습니다. CNAME은 사용하지 않았습니다. 이 hostname에서 Staging·Production 발급과 정상 trust 검증 HTTPS/WSS가 성공했습니다. 인증서 검증을 끄는 설정은 사용하지 않습니다.

## Android 연결 절차

다음 절차의 Custom Relay 설정과 수동 코드 pairing은 사용자 기기에서 정상 작동을 확인했습니다. 원격 세션 작업·승인 및 모바일 재접속의 세부 검증은 별도로 수행합니다.

1. `https://azzi-home.duckdns.org:38789/health`의 `OK` 응답을 확인합니다. 443 포워딩은 인증서 자동 갱신을 위해 유지합니다.
2. 기존 Pi 설정 파일은 수정하지 않았습니다. 설치한 `runtime/PiCodingAgent/agent/extensions/remote-pi.ts`가 wrapper를 불러옵니다.
3. Pi는 Home Server로 재시작했습니다. Pi Desktop에서 기존 project/session을 엽니다. LLM과 LibreChat은 재시작하지 않습니다. Wrapper가 공식 `REMOTE_PI_RELAY`를 Self-hosted URL로 지정하며 public Relay를 사용하지 않습니다.
4. [공식 Android Release `app-v1.2.0`](https://github.com/jacobaraujo7/remote_pi/releases/tag/app-v1.2.0)의 `RemotePi.apk`를 설치합니다. `RemotePiCockpit`과 기존 `justhil/pi-app`의 Android 앱은 다른 배포입니다.
5. Android onboarding의 Custom Relay 또는 Settings에서 **`https://azzi-home.duckdns.org:38789`**를 입력합니다. 입력란은 `wss://`를 거부하고 내부에서 `wss://azzi-home.duckdns.org:38789`로 변환합니다. Default/Public Relay를 선택하지 않습니다.
6. 기존 Pi 세션에서 `/remote-pi`로 연결 상태를 확인하고 `/remote-pi pair --ttl 600`으로 유효기간 10분의 pairing 코드를 발급합니다. TTL을 지정하지 않으면 기본 token은 60초 후 만료됩니다. QR에는 Relay URL이 없으므로 앱의 Custom Relay 설정이 반드시 선행되어야 합니다.
7. 앱에서 QR를 스캔하거나 `runtime/RemotePi/pairing/pairing-code.txt`의 `remotepi://pair`로 시작하는 전체 코드를 수동 입력하고 Pi에 표시된 pairing 확인을 완료합니다. 해당 Pi room의 세션·메시지·도구 실행 및 승인 UI를 실기기로 확인합니다.
8. 모바일 연결 해제/재접속, Pi 종료 후 Relay/Caddy 유지와 Pi 재시작 후 같은 세션 재연결을 확인합니다.

현재 Pi Desktop 0.7.7은 공식 Extension의 `remote-pi:pair-code` custom message를 채팅에 표시하지 않습니다. Wrapper가 같은 공식 URI를 `qrcode@1.5.4`로 PNG에 표시하도록 보완했습니다. `/remote-pi pair --ttl 600`을 실행하면 `runtime/RemotePi/pairing/pairing-qr-code.png`와 `pairing-code.txt`가 생성됩니다. 이 파일을 PC에서 열어 앱으로 스캔하거나 앱의 수동 pairing 입력을 사용합니다. Git·Docker·Caddy에는 공개하지 않습니다.

파일은 Pi 프로세스가 실행 중이면 유효기간 후 삭제됩니다. Pi가 먼저 종료되더라도 원래 프로세스의 token은 유효하지 않습니다. 새 code를 생성한 뒤 오래된 timer가 새 파일을 삭제하지 않는 것을 테스트했습니다. QR 자체의 유효기간과 일회용 검증은 공식 Extension이 담당합니다.

브라우저에서 `https://azzi-home.duckdns.org:38789/`를 열면 `Connection header did not include 'upgrade'`라는 HTTP 400 응답이 나옵니다. `/`는 WebSocket 전용 endpoint이므로 일반 페이지 요청에는 Upgrade header가 없습니다. QR 만료나 인증서 오류를 뜻하지 않으며, 브라우저 상태 확인에는 `/health`를 사용하고 실제 연결에는 Remote Pi 앱을 사용합니다.

새 환경에서 loader는 `scripts/RemotePi/install-native-extension.ps1`로 다시 설치할 수 있습니다. Wrapper 코드를 바꾼 뒤에는 기존 Home Server로 Pi만 재시작하고 project/session을 다시 엽니다. Desktop의 `/reload`를 이 재시작 절차의 대체로 사용하지 않습니다.

공식 Extension의 Agent mesh 도구 `agent_send`, `agent_request`, `list_peers` 및 관련 skill의 resource 등록은 wrapper에서 생략합니다. 기존 Single Agent 정책과 기존 승인 Extension을 유지하며 Remote Pi supervisor·daemon·cron 설치는 실행하지 않습니다.

Relay는 TLS transport를 사용하지만 payload에 대한 E2EE를 제공하지 않습니다. Self-hosted Relay 운영자가 payload를 볼 수 있는 구조이며, 본 구성에서는 외부 public Relay를 사용하지 않습니다.

## 후속 계획: Home Server의 수동 DDNS 갱신 버튼

ipTIME DDNS가 IP를 바꾸는 것이 아니라 ISP의 공인 IPv4 변경을 공유기가 DDNS에 반영합니다. DuckDNS에도 Windows 서버의 공인 IPv4를 별도로 반영해야 합니다. 두 hostname 사이에 CNAME을 만들지 않습니다.

사용자는 자동 갱신 대신 나중에 LLM Home Server에 수동 trigger 버튼을 추가하기로 했습니다. 이번에는 UI·관리 API·자동 실행 Task를 추가하지 않습니다. 공인 IP 변경 후에는 현재처럼 DuckDNS 화면에서 새 IP를 수동 등록해야 합니다.

후속 버튼은 `azzi-home.iptime.org`와 `azzi-home.duckdns.org`의 A record를 조회하여 차이를 보여주고, 사용자의 명시적 클릭으로 DuckDNS의 A record를 숫자 IP로 갱신하는 방향입니다. ipTIME DDNS 자체는 변경하지 않으며 CNAME도 만들지 않습니다.

준비한 `scripts/RemotePi/update-duckdns.ps1`은 수동 `Configure`/`Update`/`Status`만 지원하도록 정리했습니다. 실행하거나 Token을 설정하지 않았습니다. 향후 Token을 사용하면 Windows DPAPI로 암호화하여 Git에서 제외된 local 설정에 저장합니다. Task 등록 코드는 포함하지 않습니다. 기존 관리 서버의 접속 인증을 사용하는 UI 통합은 후속 구현 범위입니다.

## 공식 근거

- [Remote Pi README](https://github.com/jacobaraujo7/remote_pi)
- [Relay README](https://github.com/jacobaraujo7/remote_pi/tree/main/relay)
- [Android Release source의 URL 처리](https://github.com/jacobaraujo7/remote_pi/blob/app-v1.2.0/app/lib/data/transport/relay_config.dart)
- [Let's Encrypt CAA](https://letsencrypt.org/docs/caa/)
- [Let's Encrypt IP certificates](https://letsencrypt.org/2026/01/15/6day-and-ip-general-availability)
- [DuckDNS API](https://www.duckdns.org/spec.jsp)
- [Caddy TLS issuer](https://caddyserver.com/docs/caddyfile/directives/tls)
