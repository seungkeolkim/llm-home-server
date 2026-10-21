# LLM Home Server 운영 안내

현재 Windows 계정으로 수동 실행하는 관리 서버입니다. 관리 화면과 browser tab 이름은 **LLM Home Server**, repo 이름은 `llm-home-server`입니다.
Windows Service, Task Scheduler, 자동 재시작과 failover는 사용하지 않습니다.

로컬 repo 경로는 `C:\Users\azzib\Desktop\workspace_local\llm-home-server`입니다. IDE와 터미널도 이 경로에서 다시 엽니다.
LibreChat의 Compose project 이름은 `llm-home-server-librechat`입니다. 기존 MongoDB와 이미지 데이터를 새 이름의 volume으로 이전해 보존했습니다.

## 준비와 기동

먼저 `config/ManagementServer/management.local.json.template`을 같은 폴더의 `management.local.json`으로 복사합니다.
`CHANGE_ME_` 안내가 있는 `access_string`과 `session_secret`을 실제 값으로 바꿉니다.
`session_secret`은 32자 이상 무작위 값이며, 기존 파일이 있으면 해당 값을 보존합니다.
전체 설정 복사 명령과 secret 생성 방법은 [프로젝트 README](../../README.md)에 있습니다.

```powershell
.\scripts\ManagementServer\prepare-environment.ps1
.\run-management-server.ps1
```

별도 `.venv/ManagementServer`를 사용합니다. 준비 시 복사한 설정의 필수 값을 검증하며 local 설정을 덮어쓰지 않습니다.
주소는 `http://127.0.0.1:8788`, bind는 `0.0.0.0:8788`입니다. HTTPS는 사용하지 않습니다.
관리 서버를 실행한 터미널을 유지하며 Ctrl+C로 종료합니다. 관리 서버 기동·종료가 다른 서비스를 자동 기동·종료시키지는 않습니다.

기본으로 `management_server/`, `web/ManagementServer/`, `config/ManagementServer/`의 코드·화면·설정 변경을 reload합니다.
열린 관리 화면도 다음 상태 조회에서 HTML·CSS·JS revision 변경을 감지하면 새로고침합니다.
`run-management-server.ps1 -NoReload`로 reload를 끌 수 있습니다. Reload는 개발 편의 기능이며 장애 자동 복구가 아닙니다.

## 접속과 외부 네트워크

- 계정·회원가입·관리자 권한 체계를 만들지 않고 접속 문자열 하나만 확인합니다.
- 문자열이 맞으면 서명한 HttpOnly / SameSite=Strict cookie로 해당 브라우저를 허용합니다. 기본 유효 기간은 7일입니다.
- Session secret은 local 설정에 보존하므로 코드 reload 후에도 세션을 유지합니다. `잠그기`는 현재 브라우저의 cookie를 제거합니다.
- 제어 요청은 같은 출처와 session별 CSRF token을 확인합니다.
- 접속 문자열과 signing secret은 `config/ManagementServer/management.local.json`에 있으며 Git에서 제외합니다. 화면·상태 API·로그에 노출하지 않습니다.
- LAN에서는 `http://<PC LAN IP>:8788`, 외부에서는 포트포워딩한 주소로 접속합니다.

필요한 Windows 방화벽 규칙은 관리자 CMD 또는 PowerShell에서 다음 명령으로 적용합니다.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ManagementServer\allow-network-access.ps1
```

공유기에서는 사용자 선택에 따라 **외부 TCP 38788 → PC의 8788**로 포트포워딩합니다.
외부 접속 주소는 `http://azzi-home.iptime.org:38788`입니다. 포트포워딩은 사용자가 설정합니다.
화면 바로가기는 현재 접속 hostname을 유지하며 local·외부 port 매핑은 local 설정의 `links`, `external_links`에서 수정합니다.
현재 Comfy Home Server의 외부 port는 사용자 제공 주소에 맞춰 38388로 설정합니다.

## 기능과 제어 경계

| 대상 | 동작 |
|---|---|
| Windows | 물리 RAM 사용·여유량과 CPU 사용률 조회 |
| GPU | NVIDIA GPU VRAM 사용·여유량, 사용률·온도·전력 조회 |
| LLM | 현재 Strata adapter의 상태·모델명 조회와 공식 managed runtime start/stop |
| LibreChat | Docker Compose stack의 상태 조회, LibreChat·MongoDB 함께 start/stop |
| ComfyUI 8188 | 실행·대기 queue 조회와 모델·execution cache unload 요청 |
| Comfy Home Server 8388 | 바로가기만 제공. 이 서버의 코드·설정·프로세스는 관리하지 않음 |

ComfyUI는 최신 `/api/jobs` 목록을 우선 조회하고 구버전은 GET `/queue`로 조회합니다.
Queue 취소·삭제·순서 변경, `/interrupt`, 작업 제출 API는 관리 서버에 구현하지 않습니다.
메모리 해제는 POST `/free`에 `unload_models=true`, `free_memory=true`를 함께 보냅니다.
HTTP 성공은 **요청 접수**입니다. 작업 중이면 처리 후 반영되며, queue가 남으면 다음 작업에서 모델이 다시 로드될 수 있습니다.
실제 RAM·VRAM 수치를 보고 결과를 확인합니다.

LLM의 ON/OFF는 현재 serving engine인 Strata의 전체 서비스 기동·종료입니다.
현재 모델은 기존 Strata 설정을 그대로 사용합니다. 여러 모델 선택이나 다른 engine adapter는 아직 구현하지 않았습니다.
다른 engine은 `create_llm_adapter()` 경계에 adapter를 추가할 수 있으며 화면·일반 제어 API는 `llm`이라는 이름을 사용합니다.
LLM 시작이 ComfyUI queue를 취소하거나 메모리를 자동 해제하지는 않습니다.

## 작업 이력과 reload

- 상태는 연결한 브라우저 수와 무관하게 약 3초마다 한 번 수집합니다.
- 제어는 고정된 동작만 받으며 동시에 하나만 접수합니다.
- 제어 worker는 API server와 독립 실행하므로 browser를 닫거나 API를 reload해도 이미 접수한 동작은 이어집니다.
- 완료·실패·접수 결과는 `data/ManagementServer/operations.sqlite3`에 보관합니다.
- Worker가 비정상 종료되면 상태를 실패로 기록하며 자동 재실행하지 않습니다.
- Worker 로그는 `runtime/ManagementServer/operations/`에 보관합니다. 화면에서는 최근 12 KB만 조회합니다.
- LLM·LibreChat 비밀키와 사용자 데이터는 기존 서비스 설정·데이터 위치에 보존합니다.

## 검증

```powershell
.\.venv\ManagementServer\Scripts\python.exe -m pip install -r requirements/ManagementServer/test.txt
.\.venv\ManagementServer\Scripts\python.exe -m pytest tests/ManagementServer -q
```

운영 의도와 구현 범위는 [운영 계획](OPERATING_PLAN.md)에서 이어갑니다.
