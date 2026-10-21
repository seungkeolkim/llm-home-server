# 운영 의도와 관리 서버 구성 계획

작성 기준: 2026-10-21

이 문서는 사용자가 설명한 운영 의도와 현재 구조 검토에서 나온 제안을 정리합니다.
새 대화나 후속 구현에서 운영 목적과 환경 분리 원칙을 이어가기 위한 기준 문서입니다.
기본 관리 서버는 구현됐으며, 아래에서 현재 구현과 후속 제안을 구분합니다.

## 사용자의 운영 의도

- 최상위 main repo에 전체 채팅 시스템을 모니터링하고 관리하는 서버를 둡니다.
- 관리 서버는 상시 실행하며, 집 밖에서도 상태 조회와 제어가 가능해야 합니다.
- LibreChat과 Strata를 각각 ON/OFF하고, 두 서비스와 시스템 리소스 상태를 확인합니다.
- 같은 PC에서 ComfyUI 이미지·영상 생성과 Strata 채팅을 함께 운영합니다.
- 영상 생성은 96 GB RAM 환경에서도 메모리가 부족할 수 있으므로, 작업에 따라 모델을 Load/Unload하여 RAM·VRAM을 확보합니다.
- 각 시스템의 dependency, 설정, 데이터와 실행 산출물을 최대한 분리합니다.
- 관리 대상 서비스를 중지해도 관리 서버는 계속 사용할 수 있어야 합니다.

사용자가 말한 메모리의 mount/unmount는 이 문서에서 모델 Load/Unload와 서비스 기동·종료로 구체화합니다.
파일시스템 mount 작업과는 별개입니다.

## 확정한 실행 형태와 화면 방향

2026-10-21에 Docker Strata 검증을 폐기한 뒤 다음 방향으로 기본 관리 서버를 구현했습니다.

- LibreChat과 MongoDB는 Docker, Strata는 Windows host native로 실행합니다.
- 관리 서버도 Windows host native로 실행하며 현재 사용하는 동일 Windows 계정을 사용합니다.
- 초기에는 사용자가 수동으로 실행합니다. Windows Service, Task Scheduler 자동 기동, failover, watchdog과 자동 재시작은 구현하지 않습니다. 운영 중 필요해지면 추가합니다.
- 앞서 제안한 service 실행 환경에서의 성능 검증은 초기 범위에서 제외합니다.
- 주 사용 환경은 모바일입니다. 모바일과 데스크톱에 각각 맞는 화면 배치를 제공하고 기능·API·인증은 공유합니다.
- 모바일은 세로 방향의 리소스 요약과 서비스별 카드·큰 제어 버튼을 우선합니다. 데스크톱은 리소스와 여러 서비스 상태를 함께 볼 수 있는 배치를 제안합니다.
- 관리 서버 수동 기동·재기동 자체가 Strata나 LibreChat을 자동 기동하거나 중지시키지 않도록 합니다. 하위 서비스 ON/OFF는 명시적인 사용자 조작으로 수행합니다.
- 표시 이름은 **LLM Home Server**, 로컬 폴더와 GitHub 저장소 이름은 **llm-home-server**입니다. 현재 Strata 제어는 adapter로 분리했습니다.
- 관리 서버는 HTTP `0.0.0.0:8788`에 bind합니다. HTTPS는 사용하지 않습니다. 공유기 외부 **38788 → PC 8788** 포트포워딩은 사용자가 설정합니다.
- 계정·관리자 로그인 체계 없이 local 설정의 접속 문자열 하나를 확인하고 해당 브라우저 session을 허용합니다.
- 기본으로 backend·HTML·CSS·JS·설정 변경을 reload합니다. Reload는 자동 장애 복구와 별개입니다.

### 1차 구현 범위

아래 기능은 구현했으며 실제 검증 결과는 하단 구현 기록과 운영 안내에 기록합니다.

| 기능 | 현재 구현 |
|---|---|
| 접속 허용 | 접속 문자열 확인, 서명된 HttpOnly session cookie, 현재 브라우저 잠그기 |
| 서비스 조회 | Strata, LibreChat, MongoDB의 실행·준비·생성 중·전환 중·오류 상태 구분 |
| 서비스 제어 | 기존 runner를 통한 Strata ON/OFF, Compose를 통한 LibreChat·MongoDB stack ON/OFF |
| 리소스 조회 | Windows RAM 사용·여유량, GPU VRAM 사용·여유량, CPU·GPU 사용률과 GPU 온도 |
| 제어 진행 상황 | 버튼 중복 실행 방지, 기동·종료 진행 표시, 진행 중 생성이 있을 때 종료 확인 |
| 운영 정보 | 최근 제어 결과·오류, 제한된 로그 조회와 LibreChat·Strata 화면 바로가기 |
| ComfyUI | 8188에 직접 연결해 실행·대기 queue 조회, 모델·cache unload 요청. Queue 취소·삭제·interrupt는 제공하지 않음 |
| Comfy Home Server | 8388은 바로가기만 제공하며 코드·설정·실행 상태를 변경하지 않음 |

현재 LLM ON/OFF는 Strata 전체 서비스의 start/stop입니다. 별도 LLM 모델 Load/Unload, 모델 선택과 영상·채팅 모드 전환은 후속 범위입니다.
다른 serving engine을 지원할 때 adapter를 추가하며 현재는 Strata adapter만 구현했습니다.

## 현재 구조와 유지할 원칙

| 위치 | 현재 역할과 유지할 원칙 |
|---|---|
| `external_repo/Strata`, `external_repo/LibreChat` | 독립된 공식 source clone입니다. 자체 수정, dependency 설치, 실행 산출물을 추가하지 않습니다. |
| `.venv/Strata`, `requirements/Strata` | Strata 전용 Python·CUDA runtime과 dependency 정의를 분리합니다. |
| `config/<시스템 이름>/` | 시스템별 template과 Git에서 제외하는 local 설정을 관리합니다. |
| `scripts/<시스템 이름>/` | 준비·실행·운영 스크립트를 관리합니다. |
| `docs/<시스템 이름>/` | 시스템별 운영·복구 문서를 관리합니다. |
| `data/LibreChat/` | 업로드, 애플리케이션 상태와 백업을 보존합니다. 2026-10-21에 기존 runtime에서 분리했습니다. |
| `runtime/<시스템 이름>/` | 로그, 실행 상태와 진단 결과를 관리합니다. 실행 중인 프로세스의 상태 기록을 일괄 삭제하지 않습니다. |
| `C:\Strata-data` | 기존 대용량 모델, Pack, Engine, component를 재사용합니다. 폴더 통일만을 위해 이동하거나 복제하지 않습니다. |

현재의 `config/<시스템 이름>`, `scripts/<시스템 이름>` 방식은 유지할 수 있습니다.
모든 시스템을 새로운 `services/` 아래로 전면 재배치할 필요는 없습니다.
기존 절대 경로와 runner의 경로 계산을 확인한 뒤 필요한 범위만 변경합니다.

## 개선 제안과 강도

강도 5는 관리 서버의 안정적인 운영을 위해 우선 반영할 사항입니다.
강도 4는 구현 시 권장하며, 강도 2~3은 필요에 따라 함께 정리할 수 있습니다.
이 표는 구조 검토에서 나온 제안이며, 각 항목의 실제 구현 완료를 뜻하지 않습니다.

| 강도 | 제안 | 이유와 적용 방향 |
|---|---|---|
| 5/5 | 관리 서버의 실행 환경 독립 | 별도 `.venv/ManagementServer`에서 Windows native로 수동 실행합니다. Strata나 Docker를 중지해도 관리 서버의 실행은 유지합니다. |
| 5/5 | 보존 데이터와 `runtime/` 분리 | 업로드, 영속 상태, local secret을 임시 파일·로그와 구분하여 정리 작업과 백업의 범위를 명확히 합니다. |
| 5/5 | 서비스 상태와 모델 상태 분리 | Service ON/OFF만으로는 RAM·VRAM 확보와 모델 재로딩 여부를 표현하기 어렵습니다. |
| 4/5 | 기존 runner와 API를 제어 adapter로 연결 | Strata의 공식 runtime 소유 관계와 상태 확인 기능을 재사용합니다. LibreChat 앱 중지와 전체 stack 중지를 구분합니다. |
| 4/5 | 환경 준비와 일상적인 기동 분리 | ON/OFF가 dependency 설치, 다운로드, 설정 재생성을 수행하지 않도록 합니다. |
| 3/5 | 재사용할 검증 코드를 `runtime/` 밖으로 이동 | `verify-integration.py`, `verify-firewall-regression.ps1` 같은 코드는 추적 가능한 위치에 두고 결과만 `runtime/`에 저장합니다. |
| 3/5 | 최상위 Strata 설치 스크립트 본체 정리 | 실제 구현은 `scripts/Strata/`에 두고, 필요하면 기존 최상위 명령은 얇은 launcher로 유지합니다. |
| 2/5 | Compose 정의를 `deployment/LibreChat/`으로 분리 | 배포 정의와 앱 설정을 구분할 수 있습니다. 현재 `config/LibreChat/compose.yaml`을 유지해도 되므로 우선순위는 낮습니다. |

## 관리 서버의 책임과 경계

관리 서버는 상태 조회, 정해진 서비스의 기동·종료, 모델 Load/Unload, 작업 모드 전환을 담당합니다.
초기에는 하나의 작은 애플리케이션으로 구성하고, 내부 역할에 따라 제어 adapter와 리소스 조회 코드를 분리합니다.
복잡한 plugin 체계나 여러 관리용 microservice를 먼저 도입하지 않습니다.

- 관리 서버의 실행 환경과 수명은 Strata의 `.venv` 및 LibreChat container와 분리합니다.
- 초기에는 수동 실행하며 자동 기동·자동 복구는 도입하지 않습니다. 구체적인 실행·종료 명령과 로그 위치를 제공합니다.
- 기동·종료는 기존 공식 runtime과 Docker Compose를 사용합니다. PID나 포트만 보고 임의의 프로세스를 종료하지 않습니다.
- 진행 중인 전환 작업을 표시하고, 중복 실행이나 서로 충돌하는 기동·종료 요청을 제어합니다.
- 사용자가 의도한 OFF와 비정상 종료를 구분합니다. 영상 생성 때문에 중지한 Strata를 무조건 자동 재기동하지 않습니다.
- 리소스 상태 확인에는 생성 요청을 사용하지 않습니다. 상태 조회 때문에 모델이 다시 Load되지 않아야 합니다.
- ComfyUI는 기존 환경에 연결하는 adapter를 둡니다. 이 repo로 source나 dependency를 옮기는 것은 현재 범위에 포함하지 않습니다.
- 외부 접근을 위한 인증과 서비스별 허용 동작을 둡니다. 임의 shell 명령 실행 기능을 관리 API로 제공하지 않습니다.
- 방화벽 등 최초 관리자 권한 설정과 일상적인 서버 실행 권한을 구분합니다.

## Service ON/OFF와 모델 Load/Unload

### Strata

현재 source의 `docs/DETAILS.md`에는 `POST /load`, `POST /unload`가 설명되어 있습니다.
Unload는 engine과 vision encoder 프로세스를 종료하며, API 서버를 유지할 수 있습니다.
기본 동작에서는 다음 생성 요청이 모델을 다시 Load하므로 Unload만으로 영상 생성 중 재로딩을 막을 수는 없습니다.
OS file cache 등으로 인해 Unload 직후 모든 메모리 지표가 같은 폭으로 내려가는 것은 아닙니다.

초기 영상 생성 모드는 진행 중인 채팅을 기다린 뒤 Strata 서비스 자체를 중지하는 방식이 단순합니다.
API 서버를 유지하는 구성이 필요해지면 새 생성 요청을 차단하는 정책과 함께 모델 Unload를 사용합니다.
자동 재로딩 정책은 구현 당시 사용 중인 Strata 버전과 설정을 다시 확인합니다.

### LibreChat과 MongoDB

현재 `scripts/LibreChat/run-librechat.ps1 stop`은 LibreChat과 MongoDB를 함께 중지합니다.
관리 화면에서는 LibreChat 앱만 중지하는 동작과 전체 stack을 중지하는 동작의 차이를 명확히 해야 합니다.
모델 메모리를 확보하는 목적에서는 Strata 제어가 우선입니다.

### ComfyUI

현재 설치된 ComfyUI의 `/free`는 처리할 flag를 queue에 넣습니다.
HTTP 성공은 요청 수락을 의미하므로, 관리 서버는 작업 상태와 실제 RAM·VRAM을 확인한 뒤 해제 결과를 표시해야 합니다.
영상 생성 중 다른 시스템을 다시 Load하는 동작도 충돌하지 않도록 제어합니다.

### 영상 생성 모드 전환의 제안 흐름

1. 새로운 채팅 생성이 모델을 다시 Load하지 않도록 제어합니다.
2. 진행 중인 채팅 작업의 종료를 기다립니다. 대기 중에는 진행 상태를 표시합니다.
3. Strata 모델을 Unload하거나 서비스를 중지합니다.
4. 프로세스 상태와 실제 사용 가능한 RAM·VRAM을 확인합니다.
5. 확인한 상태를 화면에 표시합니다. 작업별 필요 메모리를 정의하지 않았다면 단순 해제 성공만으로 영상 생성 가능을 보장하지 않습니다.

채팅 모드 복귀 시에도 진행 중인 ComfyUI 작업을 확인합니다.
진행 중인 작업을 강제로 중단할지 여부는 별도 정책으로 다루며, 기본 전환 동작에 묵시적으로 포함하지 않습니다.

## 모니터링할 상태

| 대상 | 필요한 상태와 지표 |
|---|---|
| 관리 서버 | 정상 여부, 진행 중인 제어 작업, 최근 오류 |
| LibreChat·MongoDB | 각각의 실행 상태, health, 최근 오류 |
| Strata | 서비스 중지, 모델 Unload, Loading, 사용 가능, 생성 중, 오류 |
| ComfyUI | 연결 상태, 실행 중인 작업과 queue, 메모리 해제 진행 상태 |
| Windows | 사용 가능한 물리 RAM, Commit 사용량, 주요 프로세스 Working Set과 Private memory |
| GPU | VRAM 전체·사용·여유량, 지원되는 범위의 프로세스 정보 |
| Docker·WSL | container 상태·메모리, WSL의 실제 메모리 사용량 |

Working Set과 Private memory는 의미가 다르므로 더해서 메모리 사용량으로 표시하지 않습니다.
WSL의 메모리 상한과 실제 사용량도 구분합니다.
다른 Docker 서비스까지 종료하는 `wsl --shutdown`을 일반적인 메모리 해제 동작으로 사용하지 않습니다.

## 데이터 보존과 백업 경계

- `data/<시스템 이름>/`: 업로드와 재기동 후에도 보존해야 하는 애플리케이션 상태를 둡니다.
- `runtime/<시스템 이름>/`: 로그, process identity, 임시 파일, 검증 결과를 둡니다. 실행 중인 프로세스가 사용하는 기록은 무조건 삭제하지 않습니다.
- `config/<시스템 이름>/`: 추적하는 template과 Git에서 제외하는 local 설정·secret을 구분합니다.
- 관리자 초기화 정보는 임시 진단 결과와 분리합니다. 실제 계정 정보의 기준은 MongoDB이며, 초기화 파일 편집만으로 DB의 비밀번호가 바뀌지는 않습니다.
- MongoDB와 LibreChat 이미지의 Docker named volume은 유지할 수 있습니다. Windows 폴더 구조를 맞추기 위해 bind mount로 바꾸지 않습니다.
- 백업 대상에는 DB, 사용자 업로드, 필요한 이미지 volume, local 설정과 암호화 key를 포함합니다.
- Git에서 제외하는 것과 삭제 가능한 것은 서로 다른 기준입니다. 새 `data/` 경로와 local secret의 Git 제외 규칙도 함께 확인해야 합니다.
- 데이터 경로 변경은 실제 파일과 mount 위치를 확인하고 서비스를 안전하게 멈춘 뒤 수행합니다. 단순 폴더 정리로 데이터를 삭제하거나 초기화하지 않습니다.

## 목표 구조 예시

아래는 제안 구조입니다. 현재 폴더가 모두 존재하거나 이동이 완료되었다는 뜻은 아닙니다.
관리 서버 내부 폴더는 실제 기능 규모에 따라 필요한 시점에 나눕니다.

```text
llm-home-server/
  management_server/
    api/
    service_control/
    resource_monitoring/
    operation_workflows/
  web/ManagementServer/
  config/{ManagementServer,Strata,LibreChat}/
  scripts/{ManagementServer,Strata,LibreChat}/
  requirements/{ManagementServer,Strata}/
  .venv/{ManagementServer,Strata}/
  data/{ManagementServer,LibreChat}/
  runtime/{ManagementServer,Strata,LibreChat}/
  docs/{ManagementServer,Strata,LibreChat}/
  external_repo/{Strata,LibreChat}/
```

`{...}`는 시스템별 디렉터리를 줄여 표현한 것으로 실제 폴더 이름이 아닙니다.
MongoDB named volume과 기존 `C:\Strata-data`는 이 tree 밖에서 별도로 관리합니다.

## 제안하는 진행 순서

- [x] 보존 데이터, local secret, 실행 산출물의 경계와 백업 범위를 정리합니다.
- [x] 관리 서버의 독립 실행 환경과 수동 실행 명령을 구성합니다.
- [x] 현재 runner와 Compose를 연결하여 상태 조회 및 ON/OFF를 제공합니다.
- [x] RAM·VRAM과 작업 상태 모니터링을 제공합니다.
- [ ] 모델 Load/Unload와 영상·채팅 모드 전환을 연결합니다.
- [ ] 실제 원격 사용에서 상태 표시, 중복 제어, 진행 중 작업 처리와 복구를 검증합니다.
- [ ] 관련 구현과 구조 정리가 끝나면 사용자와 `AGENTS.md`의 이 문서 참조 유지 여부를 검토합니다.

작업을 진행할 때 완료된 항목과 최종 선택한 운영 방식을 이 문서에 반영합니다.
`AGENTS.md` 참조 제거 여부는 작업 완료 후 검토하며, 문서 작성만으로 완료 처리하거나 참조를 제거하지 않습니다.

## 구현 기록: runtime 경계 정리

2026-10-21에 첫 단계의 파일 경계 정리를 적용했습니다.

- LibreChat의 uploads와 application 상태는 `data/LibreChat/`으로, 관리자 초기화 정보는 `config/LibreChat/`으로 이전했습니다.
- 검증 코드는 `scripts/LibreChat/`과 `tests/LibreChat/`으로 분리하고, 검증 결과는 `runtime/LibreChat/diagnostics/`에 둡니다.
- Strata의 vision 검증 결과는 `runtime/Strata/diagnostics/`으로 옮겼습니다. managed runtime·working·로그와 실제 실행 환경은 유지했습니다.
- Compose mount, 준비·실행 스크립트와 Git 제외 규칙을 함께 갱신했습니다.
- 준비 시 이전 경로 잔존을 확인하고, 기동 시 이전 데이터 폴더 잔존 또는 필수 보존 경로 누락을 거부하도록 확인을 추가했습니다.
- 이전 전 DB·파일·local 설정을 백업하고, 파일 hash와 DB document hash로 보존을 확인했습니다.
- LibreChat 재기동 후 health·로그인·실제 Strata 채팅과 저장 경계 테스트를 통과했습니다.
- MongoDB named volume, 기존 계정과 채팅, Strata 프로세스는 유지했습니다.

별도 LLM 모델 Load/Unload와 작업 모드 전환은 후속 작업입니다.

## 구현 기록: 기본 관리 서버

- 관리 서버 전용 환경·설정·화면·worker·제어 이력을 시스템별 폴더에 분리했습니다.
- Comfy Home Server의 스타일을 참고해 모바일 세로 배치와 데스크톱 배치를 구현했습니다. 해당 repo의 코드는 수정하지 않았습니다.
- LLM 제어는 현재 Strata의 공식 managed runtime을 재사용합니다.
- ComfyUI 8188의 queue 조회와 `/free`의 두 flag를 연결했으며 접수와 실제 메모리 반환을 구분해 표시합니다.
- SQLite와 별도 worker로 중복 제어를 막고 API reload 중에도 제어가 이어지도록 했습니다. Worker 장애 자동 재시작은 하지 않습니다.
- Session·CSRF·허용한 제어 경계·Comfy queue·메모리 해제 payload·Windows reload 상태 조회 테스트를 통과했습니다.
- 관리 서버에서 실제 LLM OFF/ON, 기동 중 API reload와 session 유지, LibreChat 기동 명령, Comfy unload 접수를 검증했습니다.
- 새 repo 경로에서 native Strata와 LibreChat을 복구하고 실제 LibreChat 대화를 검증했습니다.
- 상세 명령과 데이터 위치는 [관리 서버 운영 안내](README.md)에 있습니다.

## 구현 기록: repo 이름 이관 마무리

- LibreChat Compose project·container·network·named volume을 `llm-home-server-librechat` 이름으로 변경했습니다.
- MongoDB의 기존 anonymous configdb volume도 명시적인 `mongodb-configdb` named volume으로 이전했습니다.
- 서비스 중지 상태에서 volume 전체와 local 설정을 백업하고 파일 내용·Unix metadata를 비교했습니다. 재기동 전 DB 57개 collection의 document hash가 모두 일치했습니다.
- 기존 이름의 container·network·volume은 검증 후 제거했습니다. 백업은 `data/LibreChat/backups/compose-project-rename-20261021-205049/`에 보관합니다.
- 공식 LibreChat·MongoDB image 이름에는 이전 프로젝트명이 없으므로 기존 image를 유지했습니다.
- `.venv/Strata`와 `.venv/ManagementServer`의 activation script·CLI launcher·`pyvenv.cfg`를 새 repo 경로로 정리했습니다. Dependency와 실행 중인 native Strata·관리 서버는 유지했습니다.
- 이전 venv script는 `data/ManagementServer/backups/virtual-environment-paths-20261021-205009/`에 보관합니다.
- 두 venv의 activation·`pip.exe`·`pip check`, 관리 서버 테스트 6개, LibreChat 로그인·대화 목록·실제 Strata 채팅, 외부 관리 URL의 HTTP 200을 확인했습니다.
- 추가로 실행한 기존 storage-boundary PowerShell test는 Windows PowerShell 5.1의 UTF-8 해석과 native stderr 처리 문제로 완료하지 못했습니다. 이번 데이터 보존은 실제 volume 파일·metadata 및 DB document hash와 운영 로그인·채팅으로 별도 검증했습니다.

## 구현 기록: 복사해서 사용하는 설정 template

- 설정 template은 실제 파일명 뒤에 `.template`을 붙이는 방식으로 통일했습니다. JSON은 `*.json.template`, YAML은 `*.yaml.template`, 환경변수는 `.env.local.template`입니다.
- 관리 서버 접속 문자열·session secret, Strata API key, LibreChat 암호화·JWT key와 최초 관리자 정보는 사용자가 template을 복사한 실제 local 파일에 입력합니다.
- Template의 필수 입력은 `CHANGE_ME_` 안내로 표시하며 JSON에는 `이 부분을 바꾸세요`를, env에는 항목별 주석을 넣었습니다.
- 준비 스크립트는 누락된 local 파일이나 남은 안내 문자열을 거부하고 secret을 자동 생성·교체하지 않습니다. Strata 경로와 LibreChat YAML의 모델 placeholder만 준비 시 확장합니다.
- 기존 local 설정, API key, session secret과 LibreChat 계정·데이터는 그대로 유지합니다.
- Git에는 template을 포함하고 실제 local JSON·YAML·env 및 데이터·백업·runtime은 제외합니다.
- 필수 변경 항목, template 복사 명령과 무작위 key 생성 방법은 최상위 README에 정리했습니다.
- Python 테스트 12개와 Windows PowerShell 저장 경계 테스트를 통과했습니다. 이전에 확인한 PowerShell 인코딩·native stderr 처리 문제도 수정해 실제 스크립트로 검증했습니다.
- 운영 설정 5개 파일의 hash가 유지되며 관리 서버·LibreChat health와 외부 관리 URL의 HTTP 200을 확인했습니다.

## 관련 문서

- [프로젝트 소개와 실행 안내](../../README.md)
- [Strata 복구 및 검증 기록](../Strata/RESTORATION.md)
- [LibreChat 운영 안내](../LibreChat/README.md)
- [현재 clone의 Strata 상세 문서](../../external_repo/Strata/docs/DETAILS.md)
