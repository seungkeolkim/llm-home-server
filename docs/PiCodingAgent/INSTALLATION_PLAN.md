# Pi Coding Agent 설치 계획

검증일: 2026-11-13. 작업 branch: `feature/pi-local-coding-agent`.

## 검증한 배포

| 구성 | 현재 최신 버전 | Windows Native 및 출처 |
|---|---|---|
| Pi | `@earendil-works/pi-coding-agent@1.5.2` | [공식 repo](https://github.com/earendil-works/pi), Node >=22.19.0, Windows x64/ARM64 release. 이전 `badlogic/pi-mono`가 이전한 공식 프로젝트이며 `@mariozechner` 패키지의 마지막 버전 0.73.1은 최신이 아닙니다. |
| pi Desktop / Remote | 0.7.7 | [서드파티 repo 및 release](https://github.com/justhil/pi-app/releases/tag/v0.7.7). Windows x64 Portable/Setup EXE와 Android 9+ arm64 APK. 동일 프로젝트의 Desktop/Android 구성입니다. Desktop 내장 Pi는 1.0.2이므로 외부 Pi 1.5.2 선택 및 호환성을 별도 검증합니다. |
| pi-web-access | 0.47.0 | [maintainer repo](https://github.com/nicobailon/pi-web-access). Node >=22.19.0. Keyless Exa MCP 및 DuckDuckGo 제공. 실제 fetch tool 이름은 `fetch_content`이며 `web_fetch`가 아닙니다. |
| billion-context | 0.1.213 | [maintainer repo](https://github.com/ranxianglei/billion-context). Node >=20, Windows 관련 지원/제약 문서 제공. Pi Native Extension 제공. 내장 Subagent는 `pi.subagents: false`로 비활성화합니다. `billion-context-pi` 0.1.83은 별도 구형 패키지로 중복 설치하지 않습니다. |
| agent-browser | 0.43.0 | [공식 repo](https://github.com/vercel-labs/agent-browser). Node >=22, Windows x64 Native binary. `agent-browser install`이 전용 Chrome for Testing을 설치합니다. |

조회한 registry metadata와 pinned README는 ignored `data/PiCodingAgent/research/`에 보관합니다. 설치 가능 여부와 실제 정상 동작 여부를 구분하며, 실행 검증 결과는 후속 README/검증 보고서에 기록합니다.

## 설치와 보존 범위

1. 현재 branch에서 새 feature branch를 만들며 기존 미추적 파일을 보존합니다.
2. npm dependency는 `data/PiCodingAgent/npm/`, Desktop Portable과 APK는 `data/PiCodingAgent/downloads/`, Portable 추출·세션·Desktop profile은 `runtime/PiCodingAgent/`에 분리합니다. 전역 설치, 전역 PATH 수정, WSL, Docker, 방화벽 변경은 수행하지 않습니다.
3. `config/PiCodingAgent/`에 공개 template과 ignored local 설정을 분리합니다. 기존 Infernix/Strata API key는 launcher가 기존 설정에서 읽어 child process 환경으로 전달하며 Git, 문서, command line에 넣지 않습니다.
4. Infernix NVFP4 및 Strata IQ3_XXS Provider를 별도로 등록합니다. 둘 다 262144 Context이며 현재 8488에서 실제 제공되는 Model ID를 확인합니다. Pi start/stop은 model start/stop 및 교체를 수행하지 않습니다.
5. `billion-context`를 Native Extension으로 사용하고 내장 delegation 및 자동 업데이트를 차단합니다. 기본 Compaction은 Extension의 취소 hook과 함께 검증하여 중복 압축을 방지합니다. 기본 reserve 24576 / recent 32768은 Pi fallback 정책이며 Extension 자체 압축 정책과 동일한 옵션이라고 표시하지 않습니다.
6. Web Search는 Exa/DuckDuckGo로 제한하고 summary/curator의 추가 LLM 호출과 브라우저 자동 실행을 차단합니다. Search query는 선택한 서비스에 전송되고 fetch는 PC가 대상 URL을 요청합니다. 무료 endpoint의 고정 Rate Limit이나 SLA는 보장되지 않습니다.
7. agent-browser용 Skill과 전용 브라우저를 설치하고 로컬 예제로 DOM, 클릭, 입력, Screenshot, Console과 종료를 검증합니다. 추가 Browser Extension/MCP는 설치하지 않습니다.
8. 관리 서버에 Pi 전용 상태 및 start/stop을 추가합니다. 관리 서버 reload가 Pi를 자동 시작/종료하지 않으며 LibreChat/LLM 제어와 독립적입니다. 소유 PID와 생성 시각을 확인한 프로세스만 종료합니다.
9. Desktop/CLI의 단일 Agent 실행 정책을 검증합니다. 휴대폰이 없으면 Android pairing/복구/첨부 등은 실제 기기 미검증으로 남기고 확인 절차를 제공합니다. Mobile은 기본 disabled이며 외부 포트 공개나 VPN 설치는 수행하지 않습니다.

## 변경 예정 파일

- 신규: `requirements/PiCodingAgent/`, `scripts/PiCodingAgent/`, `config/PiCodingAgent/`, `docs/PiCodingAgent/`, `tests/PiCodingAgent/`, `run-pi-coding-agent.ps1`.
- 관리 통합: `management_server/`의 Pi adapter, monitoring, worker, operation allowlist 및 `web/ManagementServer/` 서비스 카드.
- 운영 문서: `docs/ManagementServer/OPERATING_PLAN.md`.
- 실행 산출물: ignored `data/PiCodingAgent/`, `runtime/PiCodingAgent/`, `config/PiCodingAgent/*.local.json`.
- 기존 Infernix/Strata/LibreChat 설정은 수정하지 않습니다. 변경 전 hash는 `data/PiCodingAgent/backups/protected-configuration-hashes.json`에 기록합니다.

설치·테스트·사용 안내·Rollback은 실제 결과에 맞춰 작성합니다. 모델 서버와 다른 서비스의 기존 상태는 유지합니다.
