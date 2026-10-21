# LibreChat 실행 환경

LibreChat과 MongoDB만 Docker로 실행합니다. 모델 추론과 컨텍스트 요약은 기존 Windows Strata를 사용하며,
Web Search와 페이지 본문 추출은 API key 없이 Keenable을 호출합니다.
Meilisearch, RAG API, PostgreSQL, Redis 및 별도 Admin Panel은 설치하지 않습니다.

## 준비 및 실행

Docker Desktop의 Linux container engine과 실행 중인 Strata가 필요합니다.
명령은 이 repository root에서 실행합니다.
먼저 아래 template을 파일명 끝의 `.template`만 제거한 이름으로 복사합니다.

- `config/LibreChat/.env.local.template` → `.env.local`
- `config/LibreChat/librechat.local.yaml.template` → `librechat.local.yaml`
- `config/LibreChat/admin-credentials.local.json.template` → `admin-credentials.local.json`

`.env.local`의 `DOMAIN_CLIENT`·`DOMAIN_SERVER`, `STRATA_API_KEY`, `CREDS_KEY`·`CREDS_IV`, `JWT_SECRET`·`JWT_REFRESH_SECRET`을 반드시 입력합니다.
Strata API key는 `config/Strata/strata.local.json`의 값과 같아야 합니다.
관리자 JSON의 `email`과 `password`도 반드시 바꿉니다.
값의 형식과 생성 명령, 기존 파일을 보존하는 복사 명령은 [프로젝트 README](../../README.md)에 있습니다.

```powershell
.\scripts\LibreChat\prepare-environment.ps1 -PublicUrl 'http://<공인 IP 또는 DDNS>:8588'
.\scripts\LibreChat\run-librechat.ps1 validate
.\scripts\LibreChat\run-librechat.ps1 start
.\scripts\LibreChat\run-librechat.ps1 create-admin
.\scripts\LibreChat\run-librechat.ps1 status
```

준비 스크립트는 `config/Strata/strata.local.json`에서 port, model name, API key 및 context window를 읽어 입력값을 확인하고 YAML placeholder를 확장합니다.
Strata endpoint는 container에서 `http://host.docker.internal:<Strata port>/v1`로 연결합니다.
API key는 Git에서 제외된 `config/LibreChat/.env.local`에만 저장합니다.
재준비 시 encryption/JWT secret과 최초 관리자 자격 증명을 보존하며 이미 확장한 YAML도 덮어쓰지 않습니다.
Strata 모델·port를 바꾼 경우 `.env.local`의 연결 주소·key와 YAML의 모델·context를 직접 맞춥니다.
`-Port`를 생략하면 기존 local port를 유지하며 최초 기본값은 8588입니다.

최초 관리자 login email과 password는 `config/LibreChat/admin-credentials.local.json`에 직접 입력합니다.
`create-admin`은 공식 `registerUser`를 이용하며 기존 administrator와 password를 유지합니다.
공개 회원가입, social login 및 email password reset은 비활성화되어 있습니다.

HTTP 주소를 사용하면 browser login과 대화가 TLS로 암호화되지 않습니다.
현재 HTTP 운영에 맞춰 Secure cookie를 끄며, HTTPS 주소를 구성하면 준비 스크립트가 다시 켭니다.

## Port와 외부 접속

기본 port mapping은 `0.0.0.0:8588 -> LibreChat container:3080`입니다.
공유기의 외부 8588을 이 PC의 내부 8588에 연결합니다. MongoDB 27017은 Docker 내부 전용이며 host에 publish하지 않습니다.
ComfyUI의 8188과 LibreChat의 8588은 분리하여 사용합니다.
runner는 다른 프로그램을 자동 종료하지 않습니다.

외부 port와 내부 host port를 다르게 운영할 수도 있습니다.

```powershell
.\scripts\LibreChat\prepare-environment.ps1 -PublicUrl 'http://<공인 IP>:8588' -Port 8288
.\scripts\LibreChat\run-librechat.ps1 start
```

이 경우 공유기 외부 8588의 내부 대상은 8288이어야 합니다.
`PublicUrl`은 외부에서 사용하는 실제 origin을 입력합니다.
Windows Firewall에서도 해당 host port 또는 Docker Desktop의 inbound 연결이 허용되어 있어야 합니다.
localhost 및 이 PC의 LAN 주소에서 연결되는 것만으로는 인터넷 inbound 검증을 대신할 수 없습니다.

이 PC는 WSL `mirrored` networking과 Hyper-V firewall을 사용합니다.
관리자 CMD에서 다음 명령으로 Windows와 WSL에 TCP 8588만 허용할 수 있습니다.
전체 WSL inbound 정책이나 다른 service의 규칙은 바꾸지 않습니다.

```powershell
.\scripts\LibreChat\allow-network-access.cmd
```

관리자 PowerShell에서는 `.\scripts\LibreChat\allow-network-access.ps1`을 직접 실행해도 됩니다.
Windows 규칙은 `StrataLibreChatTcp8588`, WSL 고유 규칙은 `StrataLibreChatWslTcp8588`로 이름을 분리합니다.
Hyper-V 조회에서 보이는 `HostFirewallLocal` 항목은 Windows 규칙의 반영이므로 Hyper-V 고유 규칙으로 수정하지 않습니다.
스크립트는 실제 두 규칙의 port, action, direction 및 WSL VM creator를 확인한 뒤 성공을 출력합니다.
오류 시 성공을 출력하지 않고 exit code 1을 반환합니다.

참고: [Microsoft WSL networking 안내](https://learn.microsoft.com/windows/wsl/networking#mirrored-mode-networking).
2026-10-21 현재 process는 관리자 권한이 없어 규칙 추가가 Access denied로 거부되었습니다.
localhost:8588의 health, Web UI, login 및 Strata 채팅은 통과했으며,
이 PC에서 LAN 주소 192.168.0.8:8588로 보낸 요청은 timeout되었습니다.
공유기 포트포워딩은 사용자가 나중에 변경할 예정이므로 실제 인터넷 inbound는 아직 검증하지 않았습니다.

## Web Search와 컨텍스트 자동 압축

채팅 입력창의 Web Search를 켜면 Strata 모델이 Keenable 검색 Tool을 사용할 수 있습니다.
Search Provider와 Scraper는 모두 Keenable이며 Reranker는 사용하지 않습니다.
결과는 최대 5개로 제한합니다. 검색어와 조회 URL이 Keenable에 전송되므로 민감한 대화에서는 기능을 꺼 주세요.
Keenable 공개 endpoint는 공인 IP별 1,000 requests/hour, 최대 10 requests/second를 허용하며 검색과 Fetch가 제한을 공유합니다.
정책과 현재 한도는 [Keenable Rate limits](https://docs.keenable.ai/rate-limits)에서 확인합니다.

`summarization.enabled: true`이며 LibreChat이 계산한 context budget의 80%에서 오래된 메시지를 요약합니다.
요약도 같은 Strata 모델을 사용하며 최대 4,096 output tokens, 최근 2 turns 및 4,000 tokens 보존을 설정했습니다.
요약은 손실 압축이지만 원본 대화 기록은 MongoDB에 유지됩니다.
Strata 자체의 context window는 현재 local config에서 읽으며 최초 구성 시 163,840 tokens입니다.
LibreChat은 여기에서 여유 공간을 빼므로 UI의 실제 context budget은 더 작습니다.

## 저장 위치 및 운영 명령

| 위치 | 내용 |
|---|---|
| `external_repo/LibreChat/` | 공식 source clone, 수정 및 설치 산출물 없음 |
| `config/LibreChat/compose.yaml` | 최소 두 service 및 persistent volume 정의 |
| `config/LibreChat/librechat.local.yaml.template` | Strata, Web Search, 자동 요약 복사용 template |
| `config/LibreChat/.env.local.template` | 접속 origin, API key·암호화 key·JWT secret 입력용 template |
| `config/LibreChat/admin-credentials.local.json.template` | 최초 관리자 email·password 입력용 template |
| `config/LibreChat/librechat.local.yaml` | 복사 후 Strata placeholder를 확장한 운영 설정, Git 제외 |
| `config/LibreChat/.env.local` | API key, encryption/JWT secret, 접속 origin, Git 제외 |
| `config/LibreChat/admin-credentials.local.json` | 최초 관리자 초기화 정보, Git 제외. 실제 계정의 기준은 MongoDB |
| `data/LibreChat/uploads/` | 사용자 업로드, `/app/uploads`에 mount, Git 제외 |
| `data/LibreChat/application/` | 애플리케이션 상태, `/app/data`에 mount, Git 제외 |
| `data/LibreChat/backups/` | 이전 전 백업과 보존할 설정 사본, Git 제외 |
| `runtime/LibreChat/logs/` | 애플리케이션 로그, `/app/logs`에 mount, Git 제외 |
| `runtime/LibreChat/diagnostics/` | 검증 응답, 이전 manifest와 검증 결과, Git 제외 |
| `scripts/LibreChat/verify-integration.py` | Python 표준 라이브러리 기반 로그인·채팅·검색 검증 코드 |
| `tests/LibreChat/` | 데이터 경계 검증과 실제 방화벽을 변경하지 않는 regression fixture |
| `llm-home-server-librechat_mongodb-data` | MongoDB Docker named volume |
| `llm-home-server-librechat_mongodb-configdb` | MongoDB configdb Docker named volume |
| `llm-home-server-librechat_librechat-images` | LibreChat image asset Docker named volume |

```powershell
.\scripts\LibreChat\run-librechat.ps1 status
.\scripts\LibreChat\run-librechat.ps1 logs
.\scripts\LibreChat\run-librechat.ps1 stop
.\scripts\LibreChat\run-librechat.ps1 start
```

`stop`은 두 container만 정지하고 volume은 유지합니다. Docker Desktop이 실행되면 `unless-stopped` 정책이 적용됩니다.
`docker compose down -v`는 대화 데이터 volume까지 지우므로 사용하지 않습니다.
백업에는 MongoDB 데이터, 이미지 asset volume, `data/LibreChat/uploads`, `data/LibreChat/application`,
local YAML과 `.env.local`의 encryption key가 함께 필요합니다. 관리자 초기화 정보도 별도로 보호합니다.
`data/`가 Git에서 제외된다는 사실은 백업을 대신하지 않습니다.
설정 변경 후에는 `start`로 변경한 env를 반영하고, YAML만 편집한 경우에는 해당 container를 재기동합니다.

LibreChat image는 검증한 digest로 고정합니다.
`registry.librechat.ai/librechat-ai/librechat-dev@sha256:ff73f3e16986f70dc95680b96b60fccca38dcef2843cff3b9748e3688d0ef4c8`
실행한 package version은 `v0.8.8`이며 MongoDB image는 `mongo:8.0.20`입니다.
`external_repo/LibreChat`의 `git pull`만으로 운영 image가 바뀌지는 않습니다.
업데이트는 image digest와 config schema의 호환성을 확인한 뒤 별도로 진행합니다.

### 저장 위치 이전

2026-10-21에 `runtime/LibreChat/uploads`와 `runtime/LibreChat/data`를 각각
`data/LibreChat/uploads`와 `data/LibreChat/application`으로 이전했습니다.
관리자 초기화 정보는 `config/LibreChat/admin-credentials.local.json`으로 옮겼습니다.
MongoDB와 이미지 asset의 named volume 및 Compose project 이름은 유지했습니다.

이전 구조가 남아 있는 다른 checkout에서는 먼저 LibreChat 앱을 중지하고, DB와 파일·설정을 백업합니다.
기존 파일과 새 대상 경로의 충돌 여부를 확인한 뒤 위 경로로 이전하고, 파일 hash를 비교합니다.
`compose.yaml`과 스크립트도 함께 갱신한 후 `start`로 container를 재생성합니다.
단순 `docker restart`는 변경한 bind mount를 반영하지 않습니다.
DB는 기존 volume을 계속 사용하며, volume 삭제나 관리자 재생성은 이전 절차에 포함하지 않습니다.

준비 스크립트는 이전 경로가 남아 있으면 실패하고, `start`는 보존 데이터 경로 누락 또는 이전 데이터 폴더 잔존 시 실패합니다.
빈 디렉터리가 자동으로 mount되어 기존 업로드가 사라진 것처럼 보이는 기동을 방지하기 위한 확인입니다.
이전 실패 시 앱을 중지하고 백업과 원래 경로·mount 정의를 함께 복구한 뒤 기동합니다.
백업에는 실제 데이터와 secret이 포함되므로 공개하거나 Git에 추가하지 않습니다.

### Compose project 이름 이전

2026-10-21에 Compose project를 `llm-home-server-librechat`으로 변경했습니다.
Container는 `llm-home-server-librechat-librechat-1`, `llm-home-server-librechat-mongodb-1`,
network는 `llm-home-server-librechat_default`입니다.
Image는 기존 공식 LibreChat digest와 `mongo:8.0.20`을 그대로 사용합니다. Image 이름에는 이전 프로젝트명이 없습니다.

LibreChat과 MongoDB를 중지한 상태에서 기존 volume을 tar로 백업하고 새 이름의 volume으로 복사했습니다.
MongoDB의 `/data/configdb`도 기존 anonymous volume에서 `llm-home-server-librechat_mongodb-configdb`로 이전했습니다.
파일 내용·권한·소유자·수정 시각과 DB 전체 collection의 document hash를 확인한 뒤 기존 container·network·volume을 제거했습니다.
업로드, local 설정, 관리자 계정과 Strata engine 설정은 보존했습니다.

백업은 `data/LibreChat/backups/compose-project-rename-20261021-205049/`에 있습니다.
각 volume의 tar, 파일 manifest, local 설정 사본과 `migration-state.json`을 함께 보관합니다.
`migration-state.json`에는 이전·이후 volume 이름, DB 비교 결과와 backup SHA-256이 있습니다.
다른 checkout에 기존 데이터가 있다면 Compose 이름만 바꾸어 기동하지 말고 먼저 중지·백업·volume 복사와 검증을 진행합니다.
복구할 때도 앱과 MongoDB를 중지하고 해당 백업의 volume mapping과 설정을 함께 확인합니다.

### 검증 명령

검증 스크립트는 Strata의 `.venv`나 별도 Python package에 의존하지 않습니다.
사용 가능한 Python 3로 실행하며, port와 public origin은 `.env.local`에서 읽습니다.

```powershell
python -I -B .\scripts\LibreChat\verify-integration.py --mode login
python -I -B .\scripts\LibreChat\verify-integration.py --mode chat
.\tests\LibreChat\verify-storage-boundaries.ps1
```

`login`은 관리자 로그인과 대화 목록 접근을 확인합니다.
`chat`은 실제 검증 대화를 만들며, `--mode search`는 외부 검색을 포함하는 검증 대화를 만듭니다.
검증 응답은 `runtime/LibreChat/diagnostics`에 저장합니다.
저장 경계 테스트는 같은 diagnostics 아래에 실제 secret을 사용하지 않는 임시 workspace를 만듭니다.
방화벽 fixture는 `tests/LibreChat/verify-firewall-regression.ps1 -Scenario <시나리오>`로 실행합니다.
`new_native`, `existing_native`는 종료 코드 0, `access_denied`, `bad_verification`은 종료 코드 1이 정상입니다.

## 검증 기록

2026-10-21 localhost 임시 port에서 다음을 확인했습니다.

- LibreChat과 MongoDB health check 정상.
- 관리자 login HTTP 200, 공개 회원가입 비활성화.
- LibreChat container에서 Strata `/v1/models` 인증 요청 HTTP 200.
- 실제 LibreChat chat route를 통해 `STRATA_LIBRECHAT_READY` 응답 수신.
- 모델이 Keenable `web_search`를 호출하고 Python asyncio 공식 문서의 본문과 URL을 반환.
- 검증 대화의 요청별 context를 4,096으로 낮춰 자동 압축 유도. summary 365 tokens가 생성되고 기억시킨 label과 port를 보존.
- 운영 context와 80% 자동 압축 설정은 그대로 유지. 검증 응답은 `runtime/LibreChat/diagnostics/verification-*.json`에 보관.
- 최종 운영 port를 8588로 변경하여 `0.0.0.0:8588 -> 3080` publish 확인.
- 8588의 Web UI, 관리자 login, 실제 Strata 채팅 재검증 통과. ComfyUI의 8188 응답 유지.

2026-10-21 저장 위치 분리 시에는 다음을 추가 확인했습니다.

- 이전 전 DB archive와 업로드·애플리케이션 상태·local 설정을 `data/LibreChat/backups/runtime-separation-20261021-143458`에 백업.
- 파일 이동 직후 SHA-256 일치 확인.
- 재기동 후 계정 3개, 대화 6개, 메시지 26개, 파일 기록 1개의 전체 document hash가 이전 전과 일치. 이후 채팅 검증으로 테스트 대화가 추가됨.
- 기존 named volume과 Strata의 host·child PID 및 instance identity 유지.
- 8588 Web UI와 health HTTP 200, 관리자 로그인·대화 목록·실제 Strata 채팅 통과.
- 재준비 시 데이터·secret 보존, 이전 경로 잔존 및 보존 경로 누락 시 기동 거부 검증 통과.
- 운영 방화벽 스크립트를 mock cmdlet로 실행한 4개 regression 시나리오 통과. 실제 방화벽은 변경하지 않음.

RAG API를 설치하지 않아 기동 시 RAG unavailable warning이 출력됩니다.
File Search와 Run Code는 꺼져 있으며 기본 채팅, Web Search 및 자동 압축에는 영향이 없습니다.
