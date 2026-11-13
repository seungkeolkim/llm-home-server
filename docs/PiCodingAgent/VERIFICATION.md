# Pi 설치·검증 기록

검증일: 2026-11-13, Windows Native. 기본 Provider는 사용자 요청에 따라 Strata IQ3_XXS입니다.

2026-11-14에 별도 Android Remote Pi 앱의 Self-hosted Relay 및 수동 코드 pairing을 구축했고 사용자가 정상 작동을 확인했습니다. 아래 `justhil/pi-app` Mobile 검증 항목과 구분하며, 추가 결과는 [Remote Pi 검증 기록](../RemotePi/VERIFICATION.md)을 따릅니다.

## 설치 결과

| 항목 | 설치·확인 결과 |
|---|---|
| 환경 | PowerShell 7.6.5 / Node 24.20.0 / npm 11.19.0 / Git 2.53.0.windows.1 |
| Pi | `@earendil-works/pi-coding-agent@1.5.2`, 실제 `--version` 확인 |
| Desktop/Remote | 0.7.7 Windows x64 Portable EXE / Android 9+ arm64 APK |
| Desktop SDK | 내장 1.0.2 대신 격리된 standalone 1.5.2 Active를 실제 UI에서 확인 |
| Web | `pi-web-access@0.47.0`, Exa Keyless 검색 및 readable 본문 fetch 성공 |
| Context | `billion-context@0.1.213`, Extension load error 0, 내장 delegation tool 없음 |
| Browser | `agent-browser@0.43.0`, 전용 Chrome 157.0.8103.78, Windows Native 실행 성공 |
| 기존 설정 보존 | 초기 hash 16개를 비교하여 Infernix/Strata/LibreChat 및 관리 local 설정의 변경 0개 |
| 자동화 검사 | Python 55 passed / Node control-history 6 passed / `git diff --check` 통과 |

공식 출처와 호환성 근거는 [설치 계획](INSTALLATION_PLAN.md)에 있습니다. npm registry 응답, pinned upstream README와 Release metadata는 `data/PiCodingAgent/research/`에 보관합니다.

## T01~T13

| ID | 결과 | 실제 확인과 범위 |
|---|---|---|
| T01 모델 연결 | 성공: Strata / Infernix 추론 미검증 | Strata Model ID `sc117-qwen3.8-flash-next-abliterated-iq3_xxs`, `/models` loaded·262144 확인. Pi Streaming `PI_STRATA_READY`, Desktop `PI_DESKTOP_READY`. Infernix는 사용자의 전환 전에 `/models`·supports_tools만 확인했으며 전환 중 요청 실패를 성공으로 계산하지 않았습니다. |
| T02 Coding Loop | 성공 | 실제 모델이 fixture를 read → edit → bash로 수정·실행했습니다. `return items.length - 1`을 `return items.length`로 바꾸고 node:test 1/1 통과. 승인 대상 밖 명령은 실행 전 거절했습니다. |
| T03 Tool Calling | 성공 | read, read, edit의 연속 3회 성공 및 bash 테스트 성공. 거절 후 재시도나 작은 Context의 불필요한 compress 거절은 별도 로그에 남깁니다. |
| T04 Web Search | 성공 | 검색 key·계정 로그인 없이 `web_search`, 실제 Provider Exa, query 1개·결과 5개. |
| T05 Web Fetch | 성공 | `fetch_content https://pi.dev`의 실제 readable 본문 5786 chars·71 lines를 가져왔습니다. tool의 실제 이름은 web_fetch가 아닙니다. |
| T06 Browser | 성공 | 로컬 HTTP 예제의 Snapshot → 입력 → 클릭 → Screenshot → Console `PI_BROWSER_READY`, errors 없음, close 성공. |
| T07 Context | 성공: 기능 검증 | 실제 compress가 1개 block을 만들고 약 4438 estimated tokens를 절약했습니다. 실제 요청 후 threshold Compaction hook은 `{cancel:true}`를 반환했습니다. 테스트 최근 보존량 128 및 수동 압축 허용을 사용했으며 운영 최근 32768·nudge/recommendation 제한과 구분합니다. 262K 장기 부하는 미검증입니다. |
| T08 Session | 성공 | Pi 프로세스 종료 후 같은 JSONL Session을 다시 열어 결정 코드·수정 파일을 복원했습니다. 압축 Session 재시작 후 `PI_CONTEXT_9427`, `count-items.cjs`, `return items.length`, `node:test passed 1/1`도 보존됐습니다. |
| T09 Android 복구 | 미검증 | APK 준비 및 서명 검증 완료. 실제 기기의 background·재접속 검증 필요. |
| T10 Mobile Coding | 미검증 | upstream의 Tool Call·승인 UI·Diff 경로는 확인했으나 실제 기기 작업 지시·복구는 확인하지 못했습니다. |
| T11 Mobile Attachment | 미검증 | Android Source에서 이미지와 일반 파일 업로드 경로를 확인했습니다. 실제 업로드·분석은 미검증이며 일반 문서 해석은 형식별 parser와 별개입니다. |
| T12 동시성 | 성공: 설정·차단 경계 | Desktop worker 1, Subagent package 미설치, 내장 delegation OFF. Gateway 테스트에서 첫 요청 실행 중 두 번째 요청은 429, upstream 수신은 1개, maximum_in_flight=1. 실제 upstream tool 목록에 acp_delegate/subagent 없음. 실제 Extension의 공통 turn lock도 offline input simulation에서 handled로 차단했습니다. |
| T13 접근 경계 | PC 범위 성공 / 원격 미검증 | Pi listener는 127.0.0.1:8490. 기존 backend key 검증과 고정 route/Model ID만 전달. 신규 방화벽·공인 port·47900 listener 없음. Mobile OFF. 기존 LLM API의 기존 bind 설정은 유지합니다. Android E2EE pairing/VPN 실제 연결은 미검증입니다. |

## 관리 버튼과 화면

실제 인증·CSRF가 적용된 관리 API에서 `pi/stop`, `pi/start`가 모두 succeeded였습니다. 전후 Strata listener PID **31180**이 유지됐고 LibreChat 상태도 동일했습니다. 마지막 상태는 Pi gateway와 Desktop 실행 중입니다.

브라우저 1440px와 390px에서 Pi 카드와 독립 버튼을 확인했습니다. 실행 중에는 Pi 켜기가 disabled, Pi 끄기가 enabled이며 두 폭에서 horizontal overflow가 없었습니다. 증거는 `runtime/PiCodingAgent/verification/management-1440.png`, `management-390.png`, `management-pi-card.png`에 있습니다.

## 배포 무결성

공식 [0.7.7 Release](https://github.com/justhil/pi-app/releases/tag/v0.7.7)의 `SHA256SUMS.txt`와 GitHub asset digest를 대조했습니다.

| 파일 | SHA-256 |
|---|---|
| Windows Portable EXE | `fd975f15fa2ea167410b40f5519a01b5cd31338981b3193b6275bfe3fc92724d` |
| Android APK | `65d02aecb8c61bc5eca4432aa23770309abc0045bfc74ed96b24ce08b9267cf4` |
| APK signer certificate | `0294b033efecedbbb543a9a8dbb21ee603a9cbddb082b738b76d1198709a0b06` |

APK v2의 전체 content digest, signer certificate와 public key 일치, RSA SHA256 서명 `Verified OK`를 기존 Git OpenSSL로 검증했습니다. Certificate subject는 `O=pi-app, CN=pi Remote`, 유효기간은 2026-10-06~2054-02-21입니다. 이는 공식 APK와의 일치 및 서명 무결성 검사이며 Android 기기 설치 검사를 대신하지 않습니다. Windows EXE는 Authenticode NotSigned입니다.

## 설치 명령과 백업

처음에는 다음과 같이 격리 설치한 뒤 생성한 package-lock을 `requirements/PiCodingAgent/`에 고정했습니다.

```powershell
git switch -c feature/pi-local-coding-agent
New-Item -ItemType Directory -Path data/PiCodingAgent/npm -Force
Copy-Item requirements/PiCodingAgent/package.json data/PiCodingAgent/npm/package.json
npm install --prefix data/PiCodingAgent/npm --ignore-scripts --no-audit --no-fund
.\scripts\PiCodingAgent\prepare-environment.ps1
.\scripts\PiCodingAgent\download-desktop.ps1
```

재설치 helper는 현재 `npm ci`를 사용하며 기존 local 설정은 보존합니다. 최초 Browser 설치에서 upstream 기본 user cache 경로를 확인한 뒤, 이번에 설치한 Chrome 폴더만 경로를 검증하여 Pi runtime으로 옮겼습니다. 이후 wrapper는 child의 USERPROFILE과 socket 경로를 Pi runtime으로 한정하며 `install`에서 같은 binary를 재사용하는 것을 확인했습니다. 전역 USERPROFILE/PATH는 바꾸지 않습니다.

기존 설정의 변경 전 hash는 `data/PiCodingAgent/backups/protected-configuration-hashes.json`, 재생성한 Pi 설정 백업은 같은 폴더의 시각별 하위 폴더에 있습니다. 기존 Infernix 설정을 복사하거나 비밀값을 새 Provider JSON에 기록하지 않았습니다. 작성한 source와 Pi 설정·검증 로그에 기존 secret이 그대로 포함되는지 검사하여 일치 0개를 확인했습니다.

## 주요 증거

- `runtime/PiCodingAgent/npm-install.log`, `prepare-environment.log`: 설치 기록.
- `verification/coding-summary.json`, `coding-loop.jsonl`, `session-resume.jsonl`: 실제 Tool Calling·승인·Session.
- `verification/web/summary.json`: Search Provider와 readable fetch 결과.
- `verification/context/summary.json`: 압축 block 및 재시작 후 기억 보존. 테스트용 Context 설정도 같은 폴더에 있습니다.
- `verification/extension-summary.json`: Extension load error 0, 도구 목록, 기본 Compaction 취소.
- `verification/browser-summary.json`, `browser.png`: DOM·입력·클릭·Console·Screenshot.
- `verification/control-summary.json`, `management-ui-summary.json`: 독립 ON/OFF와 반응형 화면.
- `verification/apk/signature-summary.json`: APK 서명 검증.

Model과 Extension의 응답은 비결정적입니다. 승인 거절과 압축 보호 규칙이 정상 동작한 기록을 실제 코드 실행 실패와 혼동하지 않으며, 요청한 기능의 합격 기준과 거절된 시도를 구분해 보고합니다.
