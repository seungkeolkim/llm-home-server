# Pi Coding Agent 운영 안내

Windows Native의 독립 Pi Desktop/CLI 환경입니다. 작업 branch는 `feature/pi-local-coding-agent`이며, 기본 모델은 사용자가 전환한 **Strata QFN IQ3_XXS**입니다. 기존 Infernix, Strata, LibreChat 설정과 모델 실행 인자는 변경하지 않습니다.

최신 버전·OS·출처·설치 범위는 [설치 계획과 패키지 검증](INSTALLATION_PLAN.md), 실제 결과와 제약은 [검증 보고서](VERIFICATION.md)를 확인하세요.

현재 Android 원격 연결은 [Paseo](../Paseo/README.md)를 사용합니다. Remote Pi 전용 Extension·Relay와 이전 pi Remote Android APK는 사용자 요청으로 정리했습니다. Pi CLI·gateway·billion-context 등 Paseo가 사용하는 기반 구성은 유지합니다.

## 시작·종료

관리 화면 `http://127.0.0.1:8788/`의 **Pi Coding Agent** 카드에서 **Pi 켜기 / Pi 끄기**를 누릅니다. LibreChat 및 LLM 서버 버튼과 독립적입니다. Pi를 끄면 Pi Desktop, 등록된 CLI 및 Pi gateway만 종료하고 세션은 보존합니다. 진행 중인 Pi 작업은 중단되므로 작업 완료 후 끄는 것이 좋습니다.

PowerShell에서도 제어할 수 있습니다.

```powershell
.\run-pi-coding-agent.ps1 status
.\run-pi-coding-agent.ps1 start
.\run-pi-coding-agent.ps1 stop
.\run-pi-coding-agent.ps1 cli
.\run-pi-coding-agent.ps1 cli -- --continue
```

재시작은 `stop` 후 `start`입니다. Desktop 창을 닫으면 tray에 남을 수 있으므로 완전 종료에는 Pi 끄기를 사용합니다. CLI만 먼저 실행한 상태에서 `start`하면 진행 중 요청이 없을 때 Desktop 실행으로 전환합니다. 관리 서버 reload는 Pi나 LLM을 자동 기동·종료하지 않습니다.

Desktop은 자체 내장 Pi 1.0.2 대신 **standalone 1.5.2**를 선택하도록 준비했습니다. Settings → Runtime에서 Active 1.5.2와 격리된 Config directory를 확인할 수 있습니다. 전역 Pi 설치는 하지 않았습니다.

## 모델 선택

| Pi Provider | 실제 Model ID | Context |
|---|---|---|
| `strata-local` (기본) | `sc117-qwen3.8-flash-next-abliterated-iq3_xxs` | 262144 |
| `infernix-local` | `infernix-orcarouter-qwen3.8-flash-next-nvfp4` | 262144 |

기존 관리 화면의 LLM 서버에서 원하는 Engine/model을 먼저 켜고, Desktop 모델 선택 또는 CLI `/model`에서 대응하는 Pi Provider를 선택합니다. 두 Provider를 등록한 것이 두 LLM을 동시에 Load한다는 뜻은 아닙니다. Pi는 모델을 자동 교체하거나 시작하지 않습니다. 다른 모델이 실행 중이면 해당 요청은 실패하며 사용자에게 기존 LLM 제어에서 확인하도록 안내합니다.

Pi가 사용하는 주소는 `http://127.0.0.1:8490/strata/v1` 및 `/infernix/v1`입니다. Gateway는 기존 `127.0.0.1:8488/v1`로만 전달합니다. 기존 API key는 launcher가 기존 local 설정에서 읽어 child 환경으로 전달합니다. 새 Provider 파일은 `${PI_STRATA_API_KEY}` / `${PI_INFERNIX_API_KEY}` 참조만 저장합니다. Key를 인자로 전달하거나 출력할 필요가 없습니다.

## 승인과 단일 Agent

- 기본 도구는 read/bash/edit/write이며 변경·Shell 실행은 로컬 approval Extension의 확인창을 거칩니다. powershell 도구를 별도로 활성화해도 확인 대상입니다.
- 기존 Desktop은 Extension UI, CLI는 interactive TUI로 승인합니다. Paseo는 별도의 자동승인 설정을 사용합니다. `--print`에서 변경 작업은 승인 UI가 없어 거절됩니다.
- Desktop worker 상한은 1입니다. Desktop/CLI의 입력은 공통 turn lock으로 직렬화하고, gateway는 동시 두 번째 LLM HTTP 요청을 upstream에 보내기 전에 429로 거절합니다.
- `billion-context`의 내장 delegation은 `pi.subagents: false`로 껐습니다. 별도 Subagent, Hermes, Browser Extension이나 추가 MCP 서버를 설치하지 않았습니다.
- 이 구성은 OS sandbox가 아닙니다. 승인한 Shell 명령은 현재 Windows 계정 권한으로 실행됩니다.

## Context 정책

`billion-context@0.1.213` Native Extension 하나가 Context를 관리합니다. 현재 버전은 기본 inline 방식으로 Pi 프로세스 안에서 동작합니다.

- 모델 Context: 262144. Pi 최대 출력: 16384.
- Extension: `compress.modelContextLimit=262144`, `maxContextLimit="75%"`, `emergencyThresholdPercent="90%"`, `preserveRecentTokens=32768`.
- `requireNudge=true`, `requireRecommendation=true`로 유효한 압축 안내·추천 범위 안에서만 모델의 압축을 허용합니다. 작은 작업 직후의 불필요한 압축 시도와 잘못된 ref는 거절됩니다.
- Pi fallback: 기본 Auto Compaction 설정은 enabled, reserve 24576, recent 32768입니다. Extension이 실제로 이 세션의 요청을 처리했다는 근거가 있으면 threshold/overflow Compaction을 취소합니다. Extension이 동작하지 않으면 Pi의 기본 Compaction을 유지하는 upstream 설계입니다.
- 수동 `/compact`는 upstream에서 별도로 취급합니다. 일상 작업에서는 Extension의 `compress`, `/acp` 도구를 사용하고 기본 설정을 임의로 토글하지 않습니다.
- Pi Session JSONL과 Extension의 compression state를 함께 보존해야 합니다. Native 세션 기록만 옮기는 것으로 압축 상태까지 복원된다고 가정하지 않습니다.
- Pi cache warming, Extension cache keepalive, 자동 업데이트와 advisory 강제 업데이트를 끕니다.

운영 32K 최근 보존 설정으로 짧은 대화가 압축되지 않는 것은 정상입니다. 압축 검증에서는 별도 테스트 설정의 최근 보존량을 128로 줄여 작은 실제 대화에 압축 블록을 생성했습니다. **262K 장기 부하 검증은 수행하지 않았습니다.**

## Search와 Browser

`web_search`는 Exa MCP의 Keyless 경로를 우선하고 DuckDuckGo를 fallback으로 사용합니다. `workflow=none`이므로 Curator와 요약용 추가 모델 호출을 기본 실행하지 않습니다. 본문 도구의 실제 이름은 **`fetch_content`**입니다. 기본 `readable` 모드는 PC에서 본문을 추출하며 필요하면 `raw`를 사용할 수 있습니다. 로그인 쿠키, 유료 Provider 및 원격 hosted fetch fallback은 사용하지 않습니다.

검색 query는 Exa 또는 DuckDuckGo에 전달됩니다. URL fetch는 이 PC가 해당 웹사이트에 HTTP 요청을 보내므로 대상 사이트가 IP와 URL을 봅니다. Keyless는 비공개 전송을 뜻하지 않습니다. 검색 서비스의 [Exa 약관](https://exa.ai/terms)과 [DuckDuckGo 약관](https://duckduckgo.com/terms)을 따르며 무료 endpoint의 고정 quota/SLA는 확인되지 않았습니다. Extension은 DuckDuckGo 요청을 프로세스당 한 번에 하나, 최소 2초 간격으로 실행하고 bot check가 발생하면 5분부터 최대 1시간까지 backoff합니다. 별도 검색 API key나 계정 로그인은 필요하지 않습니다.

Browser는 `agent-browser-local` Skill을 사용합니다. Pi의 child PATH에 전용 wrapper가 있어 Git Bash에서 `agent-browser`를 실행하면 저장소의 Native binary와 전용 Chrome을 사용합니다. 브라우저 profile·socket·cache는 Pi runtime으로 격리합니다. 사용자의 기존 Chrome/Edge profile에는 연결하지 않습니다.

```powershell
node scripts/PiCodingAgent/browser_cli.mjs --session llm-home-pi open http://127.0.0.1:3000
node scripts/PiCodingAgent/browser_cli.mjs --session llm-home-pi snapshot -i
node scripts/PiCodingAgent/browser_cli.mjs --session llm-home-pi console
node scripts/PiCodingAgent/browser_cli.mjs --session llm-home-pi errors
node scripts/PiCodingAgent/browser_cli.mjs --session llm-home-pi close
```

페이지·검색 결과·파일 내용의 명령은 신뢰하지 않습니다. 로컬 개발 테스트 중심으로 사용하고 외부 사이트의 인증·결제·파괴적 조작은 자동 수행하지 않습니다.

## Android 연결

Paseo 앱의 Pairing Link와 자체 Relay를 사용합니다. [연결 절차](../Paseo/README.md#android-연결)를 따릅니다. 이전 pi Remote APK는 휴지통으로 옮겼으며 기본 다운로드 manifest와 설치 검증에서도 제외했습니다. Desktop Mobile port를 새로 열지 않습니다. 예전 APK 검증은 당시 [검증 보고서](VERIFICATION.md)의 이력입니다.

## 파일과 재설치

| 용도 | 경로 |
|---|---|
| 고정 dependency | `requirements/PiCodingAgent/package.json`, `package-lock.json` |
| Pi npm 설치 | `data/PiCodingAgent/npm/` |
| 배포 파일 | `data/PiCodingAgent/downloads/` |
| local 설정 | `config/PiCodingAgent/pi-coding-agent.local.json`, `billion-context.local.json` |
| 실제 Pi 설정·Session | `runtime/PiCodingAgent/agent/` |
| Context state | `runtime/PiCodingAgent/context/sessions/`, `runtime/PiCodingAgent/xdg/` |
| Desktop profile·Portable 추출 | `runtime/PiCodingAgent/desktop/`, `desktop-temp/` |
| Browser binary/profile | `runtime/PiCodingAgent/browser-home/` |
| 증거와 로그 | `runtime/PiCodingAgent/verification/`, `service.log`, `desktop.log` |
| 초기 설정 hash·Pi 설정 백업 | `data/PiCodingAgent/backups/` |

Python 제어 helper는 기존 `.venv/ManagementServer`의 httpx/psutil을 사용하고, Pi Agent 자체는 별도 npm 설치와 기존 Node에서 실행합니다. 전역 Python/Node dependency나 CUDA는 설치·변경하지 않았습니다.

재설치는 **Pi를 끈 후** 아래 명령으로 수행합니다. 기존 local 설정 파일은 보존하고, 재생성하는 Pi 설정은 `data/PiCodingAgent/backups/`에 백업합니다. Desktop SDK는 별도 설치한 dependency를 Junction으로 참조합니다.

```powershell
.\run-pi-coding-agent.ps1 stop
.\scripts\PiCodingAgent\prepare-environment.ps1
```

설치 중에는 `npm ci --ignore-scripts --no-audit --no-fund`를 사용합니다. 처음 설치 때 npm install로 생성한 lock을 고정했고 이후 ci에서 재사용합니다. 다운로드 스크립트는 pinned manifest의 SHA-256과 기존 파일을 대조하며 불일치 파일은 덮어쓰지 않습니다.

## 재검증

아래 검증은 **서로 순서대로** 수행합니다. `verify_controls.py`는 실제 Pi를 OFF/ON하고 마지막에 켜 둡니다. 다른 검증은 실제 Strata에 작은 순차 요청을 보냅니다.

```powershell
.\.venv\ManagementServer\Scripts\python.exe -X utf8 -B scripts/PiCodingAgent/verify_installation.py
.\.venv\ManagementServer\Scripts\python.exe -X utf8 -B scripts/PiCodingAgent/verify_coding_loop.py
.\.venv\ManagementServer\Scripts\python.exe -X utf8 -B scripts/PiCodingAgent/verify_web_context.py web
.\.venv\ManagementServer\Scripts\python.exe -X utf8 -B scripts/PiCodingAgent/verify_web_context.py context
.\.venv\ManagementServer\Scripts\python.exe -X utf8 -B scripts/PiCodingAgent/verify_browser.py
.\.venv\ManagementServer\Scripts\python.exe -X utf8 -B scripts/PiCodingAgent/verify_controls.py
.\.venv\ManagementServer\Scripts\python.exe -B -m pytest tests/ManagementServer tests/PiCodingAgent -q
node --test tests/ManagementServer/test_control_history.cjs
```

## Rollback

1. Pi 끄기 또는 `run-pi-coding-agent.ps1 stop`을 실행하고 8490 listener와 Pi Desktop이 종료됐는지 확인합니다. 열어 둔 전용 Browser session도 `browser_cli.mjs ... close`로 종료합니다.
2. 세션을 보존하려면 `runtime/PiCodingAgent/agent/`, `context/`, `xdg/`, `desktop/`과 `config/PiCodingAgent/`를 함께 별도 백업합니다. npm 설치와 Portable binary만 재설치해도 됩니다.
3. 이번 branch의 소스 변경을 제거하면 관리 화면에서 Pi 카드와 제어도 제거됩니다. 다른 사용자 변경이 있는 파일은 통째로 되돌리지 말고 Pi 관련 diff만 되돌립니다.
4. 더 이상 사용하지 않는 `data/PiCodingAgent/`와 `runtime/PiCodingAgent/`, Pi local 설정만 확인 후 제거합니다. Desktop SDK Junction의 대상인 다른 시스템을 지우지 않습니다. 이 안내는 삭제를 실행하지 않습니다.
5. 초기 기록의 기존 Infernix/Strata/LibreChat 설정 hash가 모두 동일하므로 기존 서비스 설정을 복원할 단계는 없습니다. 방화벽·포트포워딩·전역 PATH도 변경하지 않았습니다.
