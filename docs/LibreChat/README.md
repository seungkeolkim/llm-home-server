# LibreChat 실행 환경

LibreChat과 MongoDB만 Docker로 실행합니다. 모델 추론과 컨텍스트 요약은 관리 화면에서 선택한 Windows Strata 또는 PolyStrata를 사용하며,
Web Search와 페이지 본문 추출은 API key 없이 Keenable을 호출합니다.
Meilisearch, RAG API, PostgreSQL, Redis 및 별도 Admin Panel은 설치하지 않습니다.

## 준비 및 실행

Docker Desktop의 Linux container engine과 `8488`에서 실행 중인 LLM profile이 필요합니다.
관리 화면에서 실행한 model을 LibreChat에서도 선택합니다. Strata QFN, PolyStrata Qwen3.6 Unsloth·Hauhau의 목록은 정적으로 고정합니다. Context는 Strata QFN 262,144 tokens, PolyStrata Qwen3.6 두 profile 153,600 tokens입니다.
Title은 `current_model`, summarization은 현재 대화 model을 사용합니다. [PolyStrata 연결·실측 문서](../PolyStrata/README.md)를 참고하세요.
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
요약도 현재 대화에서 선택한 LLM을 사용하며 최대 4,096 output tokens, 최근 2 turns 및 4,000 tokens 보존을 설정했습니다.
요약은 손실 압축이지만 원본 대화 기록은 MongoDB에 유지됩니다.
현재 Engine context와 LibreChat `maxContextTokens`는 Strata QFN 262,144 tokens, PolyStrata Qwen3.6 두 profile 153,600 tokens입니다. Strata QFN의 153,600과 초기 구성의 163,840은 이전 값입니다.
LibreChat은 여기에서 여유 공간을 빼므로 UI의 실제 context budget은 더 작습니다.

## 모델 선택과 실행 profile

Endpoint 이름 `Strata`는 기존 대화와 연결을 보존하기 위한 공통 식별자입니다. PolyStrata도 같은 `STRATA_BASE_URL`과 API key를 사용합니다.

| LibreChat 선택 | 관리 profile | 요청 model ID |
|---|---|---|
| Strata · Qwen Flash-Next | `strata-qwen-flash-next` | `sc117-qwen3.8-flash-next-abliterated-iq3_xxs` |
| PolyStrata · Qwen3.6 MoE | `polystrata-qwen36-q4km` | `qwen3.6-35b-a3b-ud-q4_k_m` |
| PolyStrata · Qwen3.6 Hauhau | `polystrata-qwen36-hauhau-q4km` | `qwen3.6-35b-a3b-hauhau-ttq-q4_k_m` |

관리 화면에서 기존 LLM을 끄고 새 profile을 켠 뒤 LibreChat의 model을 맞춥니다.
LibreChat에서 선택만 바꾸면 LLM이 교체되는 것이 아닙니다. 두 Engine 모두 실행 model과 다른 ID의 요청을 생성 전에 HTTP 400으로 거부합니다.
LibreChat에는 provider 오류가 표시되며 현재 model의 대체 답변은 생성하지 않습니다.
저장된 메시지의 model label은 요청 시 선택한 값이므로 실제 Engine 상태 확인은 관리 화면 또는 `GET /v1/models`로 합니다.

세 실행 설정의 `reasoning_loop_recovery: "stop"`은 thinking 반복 감지 시 생성을 중단합니다.
API 종료 사유는 `length`이며, LibreChat에는 Qwen Code와 같은 전용 loop 감지 알림이 없습니다.
Thinking에도 output token 예산이 사용됩니다. Loop 검사는 모든 반복을 잡거나 답변 완성을 보장하지 않습니다.
PolyStrata 두 profile은 공식 일반 thinking sampling을 설정하지만 LibreChat에서 직접 지정한 sampling 값이 우선합니다.

고정 model을 추가하면 관리 catalog, Engine local 설정, LibreChat YAML의 model 목록·tokenConfig·modelSpecs를 함께 맞춥니다.
Template을 바꾸어도 기존 local YAML에는 자동 반영되지 않습니다. YAML만 수정한 뒤에는 LibreChat container만 재시작합니다.

```powershell
docker compose --env-file config/LibreChat/.env.local -f config/LibreChat/compose.yaml restart librechat
```

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
python -I -B .\scripts\LibreChat\verify-integration.py --mode chat --model sc117-qwen3.8-flash-next-abliterated-iq3_xxs
# Hauhau 실행 중에는 아래 model ID를 지정합니다.
python -I -B .\scripts\LibreChat\verify-integration.py --mode chat --model qwen3.6-35b-a3b-hauhau-ttq-q4_k_m
.\tests\LibreChat\verify-storage-boundaries.ps1
```

`login`은 관리자 로그인과 대화 목록 접근을 확인합니다.
`chat`은 실제 검증 대화를 만들며, `--mode search`는 외부 검색을 포함하는 검증 대화를 만듭니다. 실행 중인 profile에 해당하는 명령 하나만 사용합니다.
`--model`을 생략하면 Strata local 설정의 QFN ID를 사용하므로 PolyStrata 검증에서는 반드시 지정합니다.
검증 응답은 `runtime/LibreChat/diagnostics`에 저장합니다.
저장 경계 테스트는 같은 diagnostics 아래에 실제 secret을 사용하지 않는 임시 workspace를 만듭니다.
방화벽 fixture는 `tests/LibreChat/verify-firewall-regression.ps1 -Scenario <시나리오>`로 실행합니다.
`new_native`, `existing_native`는 종료 코드 0, `access_denied`, `bad_verification`은 종료 코드 1이 정상입니다.

## 검증 기록

2026-10-22 세 profile의 실제 채팅 및 Hauhau의 MTP·CPU Vision을 검증했습니다.
Strata request 정책 적용 후 LibreChat에서 QFN 정상 응답과 미실행 PolyStrata 선택 시 `status: 400` error content 저장을 확인했습니다.
`verification-chat.json`은 최근 검증 때 덮어쓰는 파일입니다. Hauhau 기록은 `verification-hauhau-chat.json`, model 불일치는 `verification-strata-model-mismatch.json`에 별도 보존했습니다.

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

## 미해결 장애: 답변 streaming 중 LibreChat 종료

기록일: 2026-10-22. 아래 시각은 별도 표기가 없으면 한국 시간(KST)입니다.
상태: 원인 분석 완료, 수정 미적용. 기록 당시 Strata는 가동 중이며 조사 과정에서 중지하거나 재시작하지 않았습니다.

### 증상과 발생 순서

사용자는 think 과정이 끝난 뒤 최종 답변이 작성되는 도중 화면에서 사라지는 현상이 다시 발생했다고 보고했습니다.

| 시각 | 확인한 내용 |
|---|---|
| 2026-10-22 00:47:45 | 해당 사용자 메시지를 LibreChat이 접수하고 MongoDB에 저장했습니다. |
| 2026-10-22 00:51:07 | `undici`에서 `AssertionError: assert(!this.paused)`가 발생하고 LibreChat process가 종료됐습니다. |
| 2026-10-22 00:51:08 | Docker의 `unless-stopped` 정책으로 LibreChat container가 다시 시작됐습니다. |

### 확인한 근거

- 오류 로그: `runtime/LibreChat/logs/error-2026-10-21.log`의 40번째 줄. 로그 timestamp는 `2026-10-21T15:51:07.027Z`(UTC)입니다.
- 해당 request ID: `9bf2ca80-5f70-4d0f-841a-3fc9188e6ccc`, 요청 경로: `POST /api/agents`.
- Stack: `Parser.finish` (`/app/node_modules/undici/lib/dispatcher/client-h1.js:374`) → `Socket.onHttpSocketEnd` (같은 파일의 959번째 줄).
- Docker events에 같은 시각의 `die`와 1초 뒤 `start`가 있으며, 조사 시 `RestartCount=1`, `OOMKilled=false`였습니다.
- MongoDB에 사용자 메시지 `89cce95e-74bc-4476-adaa-bcfa2b430e76`은 존재하지만, 이를 `parentMessageId`로 갖는 assistant 답변은 0개였습니다. 대화 본문은 이 문서에 기록하지 않습니다.
- 동일 stack의 오류가 2026-10-21 21:29:31, 21:50:03, 21:54:38에도 기록돼 있습니다.
- 조사 시 실행 환경: LibreChat `v0.8.8`, Node.js `v24.16.0`, 설치된 npm package `undici 7.30.0`. Node 내장 `undici`는 `7.25.0`이지만 이번 stack은 `/app/node_modules/undici/`를 가리킵니다.
- 운영 image digest: `sha256:ff73f3e16986f70dc95680b96b60fccca38dcef2843cff3b9748e3688d0ef4c8`.

### 원인과 판단의 한계

설치된 `undici` 코드는 HTTP parser가 paused 상태일 때 socket 종료 경로에서 `Parser.finish()`를 호출하고,
그 안의 `assert(!this.paused)`로 예외를 발생시킵니다. LibreChat의 `uncaughtException` handler는
이 오류에 대해 `process.exit(1)`로 종료합니다.

이는 응답 body의 backpressure로 parser가 일시 정지한 상태에서 상대가 연결을 닫으면 발생하는
[Undici issue #5360](https://github.com/nodejs/undici/issues/5360)의 조건 및 stack과 일치합니다.
Strata의 `serve/server.py`는 응답에 `Connection: close`를 보내며 SSE에도 이 경로를 사용합니다.
이 연결 종료 방식이 해당 bug의 발생 조건에 노출됩니다.
다만 이번 요청에서 backpressure가 발생한 세부 원인과 순간적인 buffer 상태는 기존 로그만으로 확정하지 못했습니다.

화면에 표시하던 streaming 답변이 최종 저장되기 전에 LibreChat이 종료됐고,
재연결 시 저장된 대화만 표시되면서 답변이 사라진 흐름으로 판단합니다.
사용자 메시지 저장, assistant 답변 부재 및 process 종료는 확인했지만,
당시 브라우저의 SSE event나 원본 응답 전체를 확보한 것은 아닙니다.

### 후속 수정 방향과 운영 경계

[Upstream PR #5474](https://github.com/nodejs/undici/pull/5474)는 paused parser를 재개하고 남은 데이터를 처리한 뒤
socket 종료를 완료하도록 수정합니다. 후속 작업에서는 이 수정이 포함된 LibreChat image 또는 호환되는 dependency 구성을
확인해야 하며, image tag나 Node 버전만으로 적용 여부를 판단하지 않습니다.
현재 설치된 package에는 문제가 발생하는 assertion 경로가 남아 있음을 직접 확인했습니다.

이번 조사는 로그·실행 코드·container 상태·MongoDB 조회만 수행했습니다.
LLM 및 LibreChat을 수동으로 중지·재시작하지 않았으며 source, 운영 설정, dependency와 대화 데이터를 변경하지 않았습니다.
위의 LibreChat 재시작은 장애 발생 당시 Docker가 자동으로 수행한 동작입니다.
