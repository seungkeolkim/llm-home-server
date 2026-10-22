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

현재 LLM ON/OFF는 선택한 Strata 또는 PolyStrata profile의 전체 서비스 start/stop입니다. 별도 model·KV unload/offload와 영상·채팅 모드 전환은 후속 범위입니다.
2026-10-22에 고정 catalog와 Engine·model 선택 UI, PolyStrata Qwen3.6 adapter를 구현했습니다.
Engine·model 선택 기동의 확정 방향과 단계는 아래 「LLM Engine·model 선택 기동 설계」를 따릅니다.
리소스 카드는 CPU → RAM → GPU → VRAM 순서의 동일한 크기로 표시합니다.
RAM·VRAM의 주요 수치는 `사용량 / 전체 용량 GiB`이며 사용률과 함께 보여줍니다.
넓은 화면은 네 열, 좁은 화면은 두 열로 배치합니다.

## LLM Engine·model 선택 기동 설계

2026-10-22에 확정한 설계이며, 같은 날 기존 Strata 유지와 PolyStrata + Qwen3.6 추가까지 구현했습니다. 상세 설정·검증·제한은 [PolyStrata 실행 문서](../PolyStrata/README.md)를 따릅니다. PolyStrata + QFN은 후속 범위입니다.
이 결정은 앞서 검토한 「Flash-Next까지 PolyStrata로 일원화」를 대체합니다. Strata를 폐기하거나 즉시 PolyStrata로 전환하지 않고 두 실행 체계를 함께 지원합니다.

### 사용자 확정 사항

- 기존 Strata와 현재 Flash-Next 실행 경로를 유지합니다.
- 먼저 PolyStrata와 Qwen3.6 MoE 실행 조합만 추가합니다.
- 그다음 Flash-Next도 PolyStrata로 실행할 수 있게 추가합니다. 이때 기존 Strata의 Flash-Next 조합도 남깁니다.
- LLM Home Server의 기존 「LLM 서버 켜기」를 누르면 어떤 Engine으로 어떤 model을 실행할지 먼저 선택하고, 선택한 조합으로 기동하도록 바꿉니다.
- 새로운 Engine이나 특정 model에 특화된 Engine이 추가될 수 있음을 전제로 설계합니다. Strata·PolyStrata 두 종류나 특정 model 이름에 UI·일반 제어 흐름을 고정하지 않습니다.
- LibreChat의 사용 가능 model 목록과 model별 context는 미리 고정해서 관리합니다. 초기 지원 model은 모두 약 150K context를 기준으로 사용하며, 기동할 때 실제 Engine을 조회해 LibreChat 설정을 동적으로 바꾸는 방식은 사용하지 않습니다.
- 초기에는 LLM 하나만 실행합니다. 다른 조합을 사용하려면 현재 LLM을 끈 뒤 새 조합을 선택해 켭니다. 실행 중 자동 교체·자동 drain·실패 시 이전 model 자동 복구는 초기 구현에 포함하지 않습니다.
- 실행 profile, 요청 시점의 설정 revision과 실제 실행 instance를 구분해 관리합니다. 준비와 기동을 분리하고, adapter의 공통 제어 계약과 profile별 리소스 예산을 둡니다.

### 단계별 지원 조합

| 단계 | UI에서 선택할 Engine | Model | 의미 |
|---|---|---|---|
| 현재 유지 | Strata | Qwen3.8-Flash-Next (QFN) | 현재 사용 중인 기존 실행 경로와 설정을 보존합니다. |
| 1차 추가 | PolyStrata | Qwen3.6-35B-A3B MoE | Unsloth `UD-Q4_K_M` 및 HauhauCS Aggressive TTQ Q4_K_M을 별도 profile로 지원합니다. 2026-10-22 Hauhau에 MTP sidecar·CPU Vision을 연결하고 LibreChat 검증 후 전환했습니다. |
| 2차 추가 | PolyStrata | Qwen3.8-Flash-Next (QFN) | 기존 Strata 조합과 나란히 남기는 후속 조합입니다. |

최종 목표는 **Strata + QFN / PolyStrata + QFN / PolyStrata + Qwen3.6 MoE**의 세 조합입니다. 최종이라는 표현은 이번 작업의 목표를 뜻하며, 이후 Engine·model 추가를 제한하지 않습니다.

이 문서에서 UI의 Engine 선택은 사용자가 구분하는 Strata·PolyStrata 실행 체계입니다. 내부 executable·backend는 별도로 구분합니다. 예를 들어 PolyStrata에서 QFN은 `strata`, Qwen3.6은 `strata-poly` executable을 사용할 수 있으므로, UI의 Engine 이름과 executable 이름을 같은 식별자로 취급하지 않습니다.

### UI 동작

1. 사용자가 「LLM 서버 켜기」를 누르면 Engine과 model을 고르는 단계를 엽니다.
2. 선택한 Engine에서 실행 가능한 model 조합을 보여줍니다. 아직 준비되지 않은 조합을 실행 가능한 항목처럼 표시하지 않습니다.
3. 사용자가 선택을 확정했을 때 그 조합의 기동 요청을 보냅니다. 선택 화면을 열거나 취소하는 것만으로 서비스를 기동하거나 model을 Load하지 않습니다.
4. 상태 카드에는 실제 실행 중인 Engine과 model을 표시합니다. 「끄기」는 실제 실행 중인 조합을 종료하는 동작과 연결합니다.

Modal·별도 선택 화면·단일 조합 목록 등 구체적인 표시 형태와 기본 선택값·선택 기억 방식은 후속 UI 구현에서 정합니다. 초기 구현에서는 기동 중이거나 실행 중인 LLM이 있으면 다른 조합을 추가 기동하지 않습니다. 먼저 현재 LLM을 명시적으로 종료하고 종료 상태를 확인한 뒤 새 기동을 요청합니다. 기동 실패 시 다른 model을 자동 Load하거나 이전 profile로 자동 복구하지 않습니다.

### LibreChat의 고정 model 목록과 context

- 지원할 model과 model별 context를 정적으로 등록합니다. 초기 목표는 모두 약 150K이며 정확한 token 수는 실제 profile 정의 시 LibreChat과 Engine 양쪽에 같은 값으로 반영합니다. 앞서 작성한 32K 검토 초안은 이번 목표값이 아닙니다.
- model 목록과 context를 현재 실행 중인 Engine의 응답으로 자동 변경하지 않습니다. 지원 조합이 추가되거나 model별 context 정책이 바뀔 때 고정 설정을 명시적으로 갱신합니다.
- LibreChat의 model 목록뿐 아니라 token/context 설정, 제목 생성과 요약에 쓰는 model 참조도 등록한 고정 model 목록 안에서 정의합니다. model별 context를 다르게 잡아야 할 경우에도 고정 설정에서 관리합니다.
- LibreChat에 model이 등록돼 있다는 사실과 해당 model이 현재 실행 중이라는 사실을 구분합니다. 미실행 조합으로 요청이 들어왔다는 이유로 관리 화면의 명시적 조작 없이 다른 Engine·model을 자동 기동하거나 교체하지 않습니다.

### 실행 profile과 제어 대상 고정

- 선택·기동의 내부 단위는 Engine, model과 실행 설정을 묶은 profile입니다. Model weights의 quantization, KV 형식, context, Vision 위치와 메모리 예산이 profile에 속합니다. 초기 UI는 준비된 profile 선택을 제공하며 모든 Engine option의 자유 편집 기능부터 만들지 않습니다.
- 표시 예시는 `PolyStrata · Qwen3.6 · Q4_K_M · KV Q8_0 · 약 150K · CPU Vision`입니다. 이는 표시 구성의 예시이며 아직 확정하지 않은 KV 등 실행 설정을 이 문장만으로 확정하지 않습니다.
- 기동 접수 시 profile 식별자와 설정 revision을 제어 작업에 고정합니다. Worker 실행 시점의 최신 선택값을 다시 읽어 다른 조합을 켜지 않습니다. 설정이 바뀌었다면 대상 변경을 묵인하지 않고 해당 요청의 불일치를 처리합니다.
- 종료는 다음 기동을 위해 선택해 둔 profile이 아니라 실제 실행 instance를 대상으로 합니다. 소유 process와 시작 시각, 실행 profile의 관계를 보존해 관리 서버 reload 이후에도 대상을 식별합니다.
- 실제 실행 대상 Engine·model·profile과 revision을 제어 이력에 남깁니다. 설정 revision이나 이력에 API key 같은 secret을 노출하지 않습니다.

### 준비 상태, adapter 계약과 리소스

- 다운로드 중, Engine 미설치, 파일 검증 실패, 기동 가능, Loading, 사용 가능 등의 상태를 구분합니다. 환경 준비 완료와 model이 실제 Load돼 생성 가능한 상태를 같은 의미로 쓰지 않습니다.
- 「켜기」는 준비된 조합을 기동하는 동작입니다. 선택이나 기동 요청만으로 dependency 설치·다운로드·설정 재생성을 묵시적으로 수행하지 않습니다.
- Adapter의 초기 공통 계약은 준비 상태 조회, start, status, stop과 로그 위치 제공을 중심으로 둡니다. Engine별 status API, process 제어, 로그 경로와 인증 차이는 adapter 안에서 처리합니다. 지원하지 않는 기능을 공통 기능처럼 제공하지 않습니다.
- Profile마다 RAM·VRAM의 예상 사용량, Load·생성 시 peak와 검증 여부를 관리합니다. 추정치와 실측값을 구분하고, 기동 직전 가용 리소스도 확인합니다. Reserve나 LLM용 8 GiB 예산은 실제 사용량의 hard limit으로 표시하지 않습니다.
- ComfyUI의 작업 취소·강제 unload를 LLM 기동에 묵시적으로 연결하지 않는 기존 운영 경계를 유지합니다.

### TODO: Engine 유지와 model·KV offload 분리

- 나중에 Engine 또는 serving process를 유지한 채 model weights와 KV를 GPU 밖으로 offload하거나 unload하는 제어가 필요할 수 있습니다.
- **현재는 TODO로만 기록하고 초기 구현 범위에 포함하지 않습니다.** 지금은 서비스 전체 켜기·끄기와 실행 profile 선택을 우선하며, 이 기능을 위한 UI·API·adapter 동작은 구현하지 않습니다.
- 실제 필요성이 생기면 Engine 유지의 의미, weights·KV 각각의 unload와 CPU RAM offload 차이, 대화 상태 보존, 재Load trigger와 자동 재Load 차단 정책을 구분해 설계합니다. 모든 Engine이 같은 기능을 지원한다고 가정하지 않습니다.

### 확장을 위한 설계 반영 방향

아래는 사용자 운영 의도를 구현에 반영할 방향이며, 구체적인 schema·API 계약은 구현 시 현재 코드와 함께 정합니다.

- Engine 정의, model 정의, 실행 가능한 조합의 설정을 분리합니다. 같은 QFN model이라도 Strata 실행 조합과 PolyStrata 실행 조합을 서로 구분합니다.
- 각 실행 조합은 식별 가능한 configuration/profile을 참조하고, Engine adapter가 해당 조합의 준비 상태·기동·조회·종료를 담당하게 합니다. LibreChat의 고정 model 목록을 실행 가능한 profile과 연결하는 mapping도 명시적으로 관리합니다.
- 공통 UI와 일반 제어 API는 선택 가능한 조합 목록을 사용하고, Engine별 CLI·process 제어 차이는 adapter 안에 둡니다. 새로운 Engine 때문에 화면과 일반 제어 흐름 전체를 다시 작성하지 않도록 합니다.
- 현재 실행 중인 조합과 사용자가 다음 기동을 위해 선택한 조합을 구분합니다. 제어 이력에도 실제 대상 Engine·model 조합을 식별할 수 있게 합니다.
- 화면 선택을 위해 임의 executable·shell command를 받지 않고, 서버에서 관리하는 실행 조합을 참조합니다. 복잡한 plugin framework나 별도 microservice를 먼저 만드는 것은 목표가 아닙니다.
- 기존 Strata 설정·API key·model 파일과 실행 경로를 유지하며 PolyStrata의 설정·dependency·runtime·스크립트는 별도 시스템 폴더에서 관리합니다. 공식 source clone 내부에는 자체 설정이나 설치 산출물을 추가하지 않습니다.

### 현재 준비 상태와 남은 작업

- `external_repo/PolyStrata` clone과 Qwen3.6 `UD-Q4_K_M` 다운로드를 완료했습니다. 2026-10-22 14:05 KST에 최종 파일 크기 22,663,387,424 bytes와 downloader의 `completed`·SHA-256 검증 통과 기록을 확인했습니다. Engine 설치·tokenizer·mmproj 준비와 model Load는 별도 미완료 상태입니다.
- 기존 Q4_K_XL·Q6·Q8 config template은 앞서 작성한 Strata용 검토 초안입니다. 이번 PolyStrata + Qwen3.6 Q4_K_M의 확정 실행 설정으로 사용하지 않습니다. Context 목표는 약 150K로 정했으며 정확한 token 수·KV·메모리 예산 등의 실제 실행 설정은 후속으로 확정합니다.
- 고정 catalog `config/ManagementServer/llm-profiles.json`, 선택 UI, profile·revision·instance를 고정하는 제어 이력과 PolyStrata 실행 경로를 구현했습니다. 두 Engine은 `8488`을 공유하며 한 개만 기동합니다.
- 현재 작업 branch는 `migration/polystrata`입니다. Branch 이름과 별개로 구현 목표는 기존 Strata 유지와 PolyStrata 추가 지원입니다.
- 이후 사용자가 개발·LibreChat 연결·실제 VRAM 측정을 요청하고 VRAM을 비웠으므로 기동·생성 검증까지 수행했습니다. 앞선 기동 금지와 config 작성 보류는 이번 요청으로 해제됐습니다. ComfyUI의 process·queue·model은 조작하지 않았습니다.

### 2026-10-22 구현·검증 결과

- 초기 context를 두 profile과 LibreChat 모두 **153,600 tokens**로 고정했습니다. 기존 Strata의 163,840 설정도 이 값으로 맞췄습니다.
- PolyStrata는 UD-Q4_K_M, KV Q8_0, 최대 KV 선할당, CPU Vision, reserve 8,192 MiB입니다. 설치·tokenizer 생성은 기동과 분리했습니다.
- 기존 Strata와 PolyStrata 각각 관리 API start/stop·readiness·실제 생성이 통과했고 LibreChat 로그인·대화 생성도 각각 통과했습니다. 관리 화면에서 선택 후 취소하면 기동하지 않는 것을 확인했습니다.
- Qwen3.6은 CPU Vision 이미지 색상 식별과 3,624-token 요청을 추가 검증했습니다. GPU 전체 peak 8.40 GiB, baseline 대비 증가 약 7.07 GiB, OS 가용 RAM 감소 약 23.78 GiB였습니다. 150K 전체 prefill·heavy Comfy 동시 작업의 실측은 아닙니다.
- 기존 Strata는 native ownership RPC·API identity·launch attestation을 재사용합니다. 보호된 process의 command line을 조회하지 않고 owner·instance 조건을 붙여 종료합니다.
- PolyStrata는 다른 model ID를 요청하면 거부합니다. 기존 Strata 생성 API에는 다른 model ID에도 현재 model로 답하는 upstream 동작이 남아 있으므로 LibreChat에서 실제 실행 model을 선택해야 합니다. 자동 Engine 전환은 하지 않습니다.

## 현재 구조와 유지할 원칙

| 위치 | 현재 역할과 유지할 원칙 |
|---|---|
| `external_repo/Strata`, `external_repo/PolyStrata`, `external_repo/LibreChat` | 독립된 공식 source clone입니다. 자체 수정, dependency 설치, 실행 산출물을 추가하지 않습니다. |
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
- [x] 기존 Strata + QFN을 유지하면서 Engine·model 선택 기동 UI와 PolyStrata + Qwen3.6 MoE 조합을 추가합니다.
- [ ] PolyStrata + QFN을 추가해 세 조합을 지원합니다. 이후 Engine·model을 추가할 수 있는 구조를 유지합니다.
- [ ] TODO: 실제 필요성이 생기면 Engine 유지 상태의 model·KV unload/offload와 영상·채팅 모드 전환을 별도로 설계합니다. 초기 선택 기동 구현에는 포함하지 않습니다.
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

## 구현 기록: 제어 요청 선기록과 중단 이력

- 사용자가 LLM start 중 시스템 freeze 후 전원 버튼으로 재부팅했다고 보고했습니다. 기존 stop timeout 기록과 별개의 현상이며, freeze의 원인은 이번 변경으로 확정하지 않습니다.
- 브라우저는 버튼 조작 확정 시 요청 ID·시각을 먼저 저장하고 화면에 표시합니다. 서버는 같은 ID의 접수 이력과 단계 로그를 디스크에 기록한 뒤 제어 worker를 실행합니다.
- 같은 요청의 상태를 접수·실행 중·최종 결과로 갱신하며, 응답을 받지 못한 브라우저 기록은 재접속 시 서버 이력과 대조합니다.
- 시스템 재부팅 또는 worker 종료로 완료되지 못한 요청은 `중단됨`으로 보존합니다. 당시 결과를 추정하거나 자동으로 다시 실행하지 않습니다.
- 기존 SQLite schema와 이력을 유지하며 외부 Strata source·설정·runtime dependency는 변경하지 않았습니다.
- 실제 LLM을 켜지 않고 임시 DB와 Mock으로 접수 선기록, 최종 상태 갱신, 재부팅 복구와 브라우저 기록 보존을 검증했습니다.

## 검토 기록: Qwen3.6 config 초안

- 2026-10-22에 Qwen3.6의 Q4·Q6·Q8별 CPU Vision config template과 8 GiB reserve를 목표로 하는 정적 VRAM 계산을 작성했습니다. Context 32K는 아직 사용자 선택 전인 초안의 가정입니다.
- ComfyUI 작업 중 Strata도 기동하지 말라는 사용자 지시에 따라 서비스 기동·모델 Load·생성 검증은 수행하지 않았습니다. 현재 Strata 설정과 관리 서버의 모델 연결도 유지했습니다.
- 이 작업은 모델 선택이나 Load/Unload 연동의 구현 완료를 뜻하지 않습니다. 실제 모델·tokenizer 준비, runner 연동, 실행 허용 후 메모리 실측은 후속 범위입니다.
- 계산과 성능 절충의 상세 내용은 [Qwen3.6 설정 초안](../Strata/QWEN36_CONFIGURATION.md)에 기록합니다.

## 준비 기록: Qwen3.6 Q4_K_M 다운로드

- 2026-10-22에 사용자가 Qwen3.6 `UD-Q4_K_M`을 선택하고 다운로드만 백그라운드로 진행하도록 요청했습니다. Model GGUF는 `C:/Strata-data/models/qwen36-UD-Q4_K_M/`에 저장합니다.
- 공식 PolyStrata Setup의 pinned revision·파일 크기·SHA-256을 사용하며, helper는 `scripts/PolyStrata/download_qwen36_ud_q4_k_m.py`, 진행 상태와 로그는 `runtime/PolyStrata/downloads/qwen36-UD-Q4_K_M/`에 둡니다. 사용자가 물을 때 상태를 확인하며 정기 조회나 알림은 설정하지 않았습니다.
- Strata·PolyStrata 기동, 모델 Load, runtime 설치와 기존 서비스 설정 변경은 하지 않았습니다. 이후 사용자는 기존 Strata를 유지하고 PolyStrata + Qwen3.6을 먼저 추가한 다음 PolyStrata + QFN을 추가하는 방향으로 확정했습니다. 상단 「LLM Engine·model 선택 기동 설계」를 따르며 전환은 아직 수행하지 않았습니다.

## 관련 문서

- [PolyStrata 추가 지원 handoff](POLYSTRATA_HANDOFF.md): context 압축 후 확정 사항·금지사항·Git 상태·다운로드 완료와 코드 경계를 이어가는 메모입니다.
- [프로젝트 소개와 실행 안내](../../README.md)
- [Strata 복구 및 검증 기록](../Strata/RESTORATION.md)
- [LibreChat 운영 안내](../LibreChat/README.md)
- [현재 clone의 Strata 상세 문서](../../external_repo/Strata/docs/DETAILS.md)
