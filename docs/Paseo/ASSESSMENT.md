# Paseo 도입 검토

검토일: 2026-11-14 KST. 현재 운영 환경은 Windows Native Pi 1.5.2, Strata QFN IQ3_XXS, Context 262144와 Single Agent 정책입니다.

## 판정

Paseo는 실시간 Thinking과 Android Native UI를 제공하는 **조건부 도입 가능 후보**입니다. 공식 Pi Adapter, Custom Relay 및 Self-hosted Relay가 있어 현재 요구에 필요한 연결 경로를 구성할 수 있습니다. 기존 Pi Desktop의 실행 중 프로세스를 그대로 원격 조작하는 방식은 아니며, 추가 LLM 호출과 동시 실행을 막는 구성이 필요합니다.

이 문서는 **도입 전 검토 기록**입니다. 이후 같은 날 사용자 요청으로 Native daemon·Windows Desktop·자체 Relay를 구축하고 실제 QFN Thinking·승인·취소·Relay 재접속을 확인했습니다. 현재 위치·제어·포트는 [운영 안내](README.md), 실제 범위는 [검증 기록](VERIFICATION.md)을 우선합니다. 아래 미실시 표기는 검토 당시의 상태이며 Android 실기기 연결은 여전히 후속 확인 항목입니다.

## 고정한 조사 대상

| 항목 | 확인 결과 |
|---|---|
| Paseo stable | `v0.15.4`, 2026-11-10 UTC Release |
| Source commit | `1c00b365c9e0b74c1580eba33d905d693125ae21` |
| Windows | 공식 x64·ARM64 Setup EXE 배포 |
| Android | 공식 `paseo-v0.15.4-android.apk`, 381117177 bytes |
| Android GitHub asset digest | `b482d0260bb5bdaef88627a9a93db9f805ae285ee7c3de92d816223b8343d820` (metadata 확인, APK 다운로드·서명 검사는 미실시) |
| 공식 Relay | `getpaseo/paseo-relay`, Elixir/Erlang, Docker 제공 |
| Relay 조사 commit | `5f4b7636af41a85ef20200c0b7e99dd1ea2ee1f2` |
| 조회한 Relay image | `ghcr.io/getpaseo/paseo-relay:latest` |
| 조회 시 image digest | `sha256:9d5c65d4bd2c42a85a5c8ab329f801a7db41dc4c153ca7bfba6c0857b3cdad0d` (manifest 조회만 수행, 운영 배치 안 함) |

Paseo source는 `data/Paseo/research/source/`, Relay source는 `data/Paseo/research/relay-source/`에 clean clone으로 두었습니다. 두 경로에 dependency나 자체 수정을 추가하지 않았습니다.

## 기능과 현재 환경 적합성

| 요구 | 확인한 근거와 한계 |
|---|---|
| Thinking 실시간 표시 | Pi Adapter가 `thinking_delta`를 `timeline.item.type = reasoning`으로 전달합니다. 앱에는 `Always expand reasoning`과 `Chat display: Full` 설정이 있습니다. 실제 QFN → Paseo Android streaming은 미검증입니다. |
| 작업 중단·방향 수정 | Pi RPC의 `abort`, `steer`, `clear_queue`를 호출하는 경로가 있습니다. 실제 Strata 생성 중 abort와 backend 자원 반환은 추가 검증이 필요합니다. |
| 기존 승인 Extension | `ctx.ui.confirm`의 RPC `extension_ui_request`를 Yes/No question으로 변환하며 응답을 `extension_ui_response.confirmed`로 돌려줍니다. 현재 Pi 1.5.2의 승인·거절 RPC 왕복은 별도 fixture에서 실제 통과했습니다. Paseo UI를 포함한 왕복 검사는 아닙니다. |
| Windows Native | 공식 Windows 배포와 Windows Pi CLI launch test가 있습니다. WSL을 필수로 요구하지 않습니다. 현재 PC에서 Paseo daemon 기동은 미실시입니다. |
| 로컬 Strata·Infernix | Pi executable override와 provider별 환경변수 주입이 가능합니다. 기존 모델 서버를 변경할 필요는 없으며, 기존 Pi gateway 및 launcher의 API key·BILI·Browser 환경을 전달해야 합니다. |
| Context·기존 Extension | Pi CLI를 `--mode rpc`로 실행하므로 기존 Pi resource 경로를 지정할 수 있습니다. billion-context 압축·복구 및 web/browser tool 공존은 실제 검증 전입니다. |
| 기존 Session | Pi JSONL import/resume 및 `--session` 실행 경로가 있습니다. 실행 중인 Desktop worker에 attach하는 방식은 아닙니다. 같은 Session을 두 프로세스가 동시에 쓰지 않도록 해야 합니다. |
| VPN 없는 Android | Self-hosted Relay에 daemon과 Android가 각각 WebSocket으로 연결할 수 있습니다. Android VPN slot을 사용할 필요가 없는 구조입니다. 실제 AdGuard 병행 사용은 기기 검증 항목입니다. |
| Custom hostname·38789 | 앱이 pairing offer의 `relay.endpoint`와 `useTls`를 사용합니다. 공식 shared parser에서 `azzi-home.duckdns.org:38789` 입력을 실제 통과시켰습니다. Android 실기기 연결은 미검증입니다. |
| Relay privacy | 공식 문서상 Relay payload는 E2EE입니다. 자체 Relay를 사용할 수 있으며 Public Relay를 필수로 사용하지 않습니다. |
| Thinking Loop 자동 감지 | Pi Adapter에서 reasoning 반복을 판별해 자동 중단하는 기능은 확인하지 못했습니다. Thinking을 읽고 중단할 수 있는 것과 자동 감지는 구분합니다. |

## 제안하는 외부 연결 구조

현재 외부 TCP 38789 → Windows TCP 8789와 Caddy 인증서를 재사용하는 구성이 가능합니다. Paseo Relay의 WebSocket endpoint는 `/ws`, 기존 Remote Pi는 `/`이므로 Caddy에서 경로를 구분할 수 있습니다. 아래는 source에 근거한 배치 제안이며 적용하지 않았습니다.

```text
Android Paseo
  → wss://azzi-home.duckdns.org:38789/ws
  → 기존 Caddy (Windows host 8789)
  → 별도 Paseo Relay container:4000 (host port publish 없음)
  ← Windows Native Paseo daemon
  → 격리된 Pi CLI 1.5.2 --mode rpc
  → 기존 Pi gateway
  → 기존 Strata
```

Paseo 설정의 Relay endpoint 형식은 `hostname:port`입니다. `daemon.relay.endpoint`와 `publicEndpoint`를 명시하고 `useTls: true`, `publicUseTls: true`를 명시해야 합니다. Custom endpoint는 기본 공식 Relay와 달리 TLS를 자동으로 선택한다고 가정하면 안 됩니다. Pairing link가 이 hostname·port·TLS 정보를 Android에 전달합니다.

Paseo Relay에는 기존 Remote Pi Relay와 다른 image·protocol을 사용합니다. 기존 Relay를 그대로 Paseo backend로 사용할 수는 없습니다. Caddy의 `/ws` 분기, 새 container/network와 내부 health probe가 추가로 필요합니다. 인증서 갱신용 외부 443 경로와 기존 Remote Pi root 경로는 보존하는 설계입니다.

## 바로 전환하지 않는 이유

1. **별도 Pi 프로세스와 실행 환경**: Paseo는 Pi CLI를 새로 실행합니다. 현재 `run-pi-coding-agent.ps1`가 주입하는 Provider key, BILI state, Browser 경로와 공통 turn lock을 보존하는 launcher가 필요합니다. 현재 agent directory의 Remote Pi additive loader까지 그대로 자동 load하면 기존 Relay 연결의 identity·room·cwd 소유권과 충돌할 수 있으므로, Paseo에 적용할 resource 목록을 분리해야 합니다. 기존 운영 설정을 편집해서 해결하지 않습니다.
2. **Single Agent와 추가 LLM 호출**: Paseo의 기본 MCP 주입에는 Agent 생성·조정 기능이 포함됩니다. `daemon.mcp.enabled: false`와 `injectIntoAgents: false`로 비활성화하는 설정이 있습니다. 여러 Workspace의 실제 Agent turn도 기존 공통 잠금·gateway로 제한해야 합니다.
3. **자동 Metadata 생성**: 제목·branch·commit·PR 문구를 별도 LLM 호출로 생성합니다. 기본 Automatic은 활성 Provider의 작은 모델 및 현재 모델을 후보로 삼습니다. `providers: []`는 OFF가 아니라 Automatic입니다. v0.15.4의 공개 Metadata schema에는 전체 `enabled: false` 옵션이 없습니다. Pi만 활성화하고 Manual로 로컬 모델을 고정해도 추가 호출 자체가 없어지는 것은 아닙니다. 원치 않는 호출 차단·직렬화 및 수동 naming 경로의 동작을 확인해야 합니다.
4. **현재 서비스 제어와 분리**: 기존 Home Server의 Pi OFF/ON은 현재 Desktop/CLI/gateway 소유 프로세스를 제어합니다. Paseo daemon과 자식 Pi도 올바른 소유권·상태·중단 경계에 연결하는 운영 작업이 필요합니다. 현재 버튼만으로 새 구성 전체가 제어된다고 가정하지 않습니다.

## 수행한 검증과 남은 검증

- 공식 Release, pinned source, npm 배포 및 Relay image manifest를 확인했습니다.
- 설치된 Pi 1.5.2를 격리된 agent directory와 가짜 backend로 실행했습니다. `get_state`, `ctx.ui.confirm` → RPC 응답의 거절·승인 왕복이 통과했고 LLM 요청은 0개였습니다.
- Source의 shared `normalizeHostPort`를 직접 실행하여 `azzi-home.duckdns.org:38789` 보존을 확인했습니다.
- 결과: `runtime/Paseo/verification/rpc-compatibility.json`, probe: 같은 폴더의 `review-rpc-compatibility.py`. 기존 서비스·Session·Provider를 probe에 연결하지 않았습니다.
- 미실시: Paseo daemon 실제 기동, Self-hosted Relay의 Android pairing·재접속, QFN Thinking 표시, 승인 후 실제 tool 실행·거절, 생성 중 중단, billion-context 압축·복구, 동시 작업 및 Metadata 호출 차단, RAM 측정.

권장 순서는 기존 Remote Pi를 유지한 상태에서 별도 Paseo runtime과 fixture project를 준비하고, 위 미검증 항목을 확인한 뒤 주 사용 UI 전환을 결정하는 것입니다. 모델 교체나 Infernix 설정 변경은 필요하지 않습니다.

## 공식 근거

- [Paseo v0.15.4 Release](https://github.com/getpaseo/paseo/releases/tag/v0.15.4)
- [Pi Adapter](https://github.com/getpaseo/paseo/blob/v0.15.4/packages/server/src/server/agent/providers/pi/agent.ts)
- [Pi CLI launch](https://github.com/getpaseo/paseo/blob/v0.15.4/packages/server/src/server/agent/providers/pi/runtime.ts)
- [Android를 포함한 client의 Relay 설정](https://github.com/getpaseo/paseo/blob/v0.15.4/packages/app/src/types/host-connection.ts)
- [Thinking 표시 설정](https://github.com/getpaseo/paseo/blob/v0.15.4/packages/app/src/i18n/resources/en.ts)
- [Custom providers](https://paseo.sh/docs/custom-providers)
- [Metadata generation](https://paseo.sh/docs/metadata-generation)
- [v0.15.4 설정 schema](https://github.com/getpaseo/paseo/blob/v0.15.4/packages/server/src/server/persisted-config.ts)
- [공식 Self-hosted Relay](https://github.com/getpaseo/paseo-relay/tree/5f4b7636af41a85ef20200c0b7e99dd1ea2ee1f2)
