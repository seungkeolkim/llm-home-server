# Infernix Orcarouter NVFP4 운영 안내

2026-11-05에 사용자가 Infernix와 Orcarouter Qwen3.8-Flash-Next Uncensored NVFP4를 선택하고,
우선 백그라운드 다운로드를 시작했습니다. 이후 요청으로 Engine 설치와 LLM Home Server·LibreChat
실행 설정을 추가했습니다. 모델·PLE·DFlash2의 약 120.614 GiB 다운로드와 전체 16개 파일 검증이
2026-11-05 19:30 KST에 완료되었습니다. 같은 날 사용자가 관리 화면에서 Infernix를 기동했고,
LibreChat을 통한 실제 응답까지 확인했습니다.

## 실행 구성

| 항목 | 설정 |
|---|---|
| 관리 profile | `infernix-orcarouter-nvfp4` |
| 정확한 Model ID | `infernix-orcarouter-qwen3.8-flash-next-nvfp4` |
| Engine | 공식 Windows `windows-2026.11.01`, 단일 `infernix-serve.exe` |
| Model | Orcarouter Uncensored, NVFP4 experts / FP8 dense |
| Context / concurrency | 262144 / 1 |
| KV / speculative decode | INT8 / DFlash2, auto draft tokens, lm-head-draft |
| PLE | FP8, `ngram-residency=volume`로 SSD에서 필요한 row 읽기 |
| Expert RAM | `exclusive`, RAM 예산에 못 담는 expert는 SSD tier 사용 |
| 여유 공간 | RAM 8192 MiB / VRAM headroom 2048 MiB |
| Host context cache | 2048 MiB |
| Input / 반복 감지 | Text·이미지, Vision RAM offload (GPU encode) / native `reasoning-loop=conclude` |
| 공통 API | `0.0.0.0:8488`, 기존 LLM API key 공유 |

파일 크기의 합계는 RAM 사용량이 아닙니다. FP8 PLE 전체 약 48.83 GiB를 RAM에 올리지 않도록
volume residency를 명시했고 expert RAM은 native 자동 예산을 사용합니다. 48 GiB 가용 RAM과
12 GiB 가용 VRAM을 관리 서버의 최소 기동 조건으로 두지만, 이는 실측 사용량이나 기동 보장이 아닙니다.
VRAM headroom은 처음 8 GiB로 준비했으며, 사용자 요청에 따라 2026-11-05에 2 GiB로 변경하고
재기동했습니다. 이는 native 예산 설정이며 warmup·driver 등의 할당 이후 실제 GPU 여유를
항상 정확히 2 GiB로 보장하는 hard limit은 아닙니다.
실행 로그에서 처음 관측한 배분은 expert RAM 51.6 GiB, RAM prefix cache 2.0 GiB,
기타 RAM 3.7 GiB이며 expert 나머지는 SSD tier를 사용합니다. GPU KV는 초기 0.16 GiB에서
긴 Context에 따라 최대 3.28 GiB로 커지는 설정입니다. 이 수치는 2026-11-05 startup 기준이며
PC 전체 사용량과 구분합니다. 당시 VRAM expert cache는 199 frames였고 ComfyUI의 GPU 사용 이후
0 frames로 축소된 기록이 있습니다. 여유 RAM·VRAM이 늘면 native 자동 예산의 결과도 달라질 수 있습니다.
2 GiB headroom으로 재기동한 뒤에는 Expert cache 2530 frames (6.5 GiB), Prefill chunk 10624
tokens, Context 증가 시 최소 chunk 5248로 배분됐습니다. 직후 GPU 여유는 약 1354 MiB였습니다.
동일한 128K 입력 131051 tokens를 Prefill 약 46.86초, 2796.63 tok/s로 처리했고 첫 출력 수신 후
바로 취소했습니다. [2 GiB headroom 관측 기록](PREFILL_HEADROOM_2G_2026-11-05.md)을 참고하세요.

Vision은 `--vision --vision-offload on`으로 활성화했습니다. Orcarouter artifact에
Vision weights가 포함되어 있으므로 별도 mmproj 다운로드는 필요하지 않습니다.
Vision tower는 pinned system RAM에 상주하며 이미지 encoding 때 expert cache의 GPU 메모리를
일시적으로 빌립니다. 상시 Vision weights용 VRAM 할당을 피하는 설정이며 CPU-only 연산은 아닙니다.
현재 Infernix CLI는 CPU-only Vision backend를 제공하지 않습니다. 추가 pinned RAM과 이미지 encoding 중
임시 VRAM·media cache 사용량이 발생합니다. Infernix의 실제 이미지 입력은 아직 검증하지 않았습니다.

Source clone은 `external_repo/Infernix/`에 두며 수정하지 않습니다. 현재 clone HEAD
`0e1c221d5c6d2a87366e387c9e71b1cf7d24be43`와 설치된 release의 source 버전은 구분합니다.
실제 설치 증거는 executable 옆 `BUILD.json`의 release·archive SHA-256·interface_verified입니다.
Release tag의 source commit `8e71f5fdeb2e020b1f440bc56d0c74c2f1258990`에서도 Orcarouter recipe C,
`nvfp4_mul` loader, 사용한 model·metrics API 필드를 확인했습니다. 이 source 확인은 실제 모델 Load 검증과 구분합니다.
Build toolchain이나 Python serving dependency를 별도로 설치하지 않고 release에 포함된 DLL을 사용합니다.
시스템 CUDA Toolkit·PATH·driver는 변경하지 않습니다.

## 준비와 명시적 기동

Repo root의 PowerShell에서 실행합니다. 관리 서버 Python 환경과 기존 Strata 공통 API key 설정이 필요합니다.

```powershell
# 공식 release 검증·설치, 최초 local 설정 생성, --help 옵션 호환성 확인
.\scripts\Infernix\prepare-environment.ps1
# LibreChat template·local YAML에 모델 등록, local은 백업하고 Container는 유지
.\.venv\ManagementServer\Scripts\python.exe -B scripts/Infernix/configure_librechat.py
.\scripts\LibreChat\prepare-environment.ps1 -ValidateOnly
.\run-infernix.ps1 status
```

준비 helper는 기존 `config/Infernix/orcarouter-nvfp4.local.json`을 덮어쓰지 않습니다.
최초 생성 때 경로를 확장하고 기존 Strata API key를 복사합니다. 실제 key는 Git에서 제외한 local JSON과
`runtime/Infernix/working/orcarouter.server.local.toml`에만 기록하며 process command line에는 넣지 않습니다.
`-ConfigurationOnly`는 release 다운로드·검증 없이 local 설정만 준비합니다.

다운로드 완료 후 관리 화면의 **LLM 켜기 → Infernix · Orcarouter NVFP4**로 기동하거나 아래 CLI를 사용합니다.
CLI도 관리 서버와 동일한 control lock·revision·instance 기록을 사용하므로 별도 서버가 중복 실행되지 않습니다.

```powershell
# 모델 metadata와 CUDA context로 리소스 배분 계획만 생성; weight Load·listener 없음
.\run-infernix.ps1 plan
.\run-infernix.ps1 start
.\run-infernix.ps1 status
.\run-infernix.ps1 stop
```

`plan`은 GPU를 전혀 사용하지 않는 검사가 아닙니다. 결과는 `runtime/Infernix/plan.json`에 저장합니다.
관리 서버의 켜기·끄기는 전체 serving process의 시작·종료이며 개별 model unload가 아닙니다.
`stop`은 해당 Infernix instance만 대상으로 하고 다른 Engine의 실행을 종료하지 않습니다.
자동 기동·완료 알림·watchdog·자동 model 전환 launcher는 사용하지 않습니다.

준비 상태는 다운로드의 `completed` 기록과 모든 대용량 파일의 크기·pinned hash receipt,
설치 release·Chat template을 함께 확인합니다. 상태 조회마다 120 GiB를 다시 hashing하지는 않습니다.
기동 readiness는 소유 listener의 `/health`, 인증된 `/v1/models`, `/metrics?format=json`의
Engine·Model ID·Context·instance로 확인하며 생성 요청을 보내지 않습니다.
서버 로그는 `runtime/Infernix/logs/server.log`입니다.

LibreChat에서는 **Infernix · Orcarouter NVFP4**를 선택합니다. 기존 공통 endpoint 이름 `Strata`와
`STRATA_BASE_URL`·`STRATA_API_KEY`를 유지합니다. 모델 이름만 선택해도 Engine이 전환되지는 않으며,
미실행 Model ID 요청은 Infernix가 HTTP 404로 거부합니다. Native server의 별도 Web UI는 제공하지 않습니다.
YAML 파일 등록 후 실행 중인 LibreChat에 반영하려면 해당 Container 재시작이 필요합니다.
2026-11-05에 LibreChat 앱 Container만 재시작하고, 인증된 `/api/config`·`/api/models`의 모델 등록과
실제 대화의 `INFERNIX_LIBRECHAT_READY` 응답을 확인했습니다. 기존 MongoDB와 Infernix는 유지했습니다.
증거는 `runtime/LibreChat/diagnostics/verification-infernix-chat.json`에 있습니다.

공식 `infernix-launcher`에는 Dashboard·설정·로그·채팅 Web UI가 있지만 Engine을 직접
기동·전환하는 구조입니다. 현재는 native `infernix-serve`를 사용하며 공식 Launcher는 실행하지 않습니다.
관리 화면의 기존 **엔진 화면 ↗** 바로가기는 원래 API port 8488로 유지했습니다.
Native 서버의 `/`는 404이므로 해당 주소에 Web UI가 표시되지는 않습니다.
사용자 요청으로 임시 추가했던 Home Server 모니터링 화면과 telemetry 확장은 제거했습니다.

## 다운로드 대상과 경로

| 대상 | 저장 위치 | 크기 |
|---|---|---:|
| Orcarouter Infernix 모델 3개 Shard | `data/Infernix/models/orcarouter-qwen3.8-flash-next-nvfp4/` | 약 71.06 GiB |
| 권장 NVIDIA FP8 PLE volume | `data/Infernix/components/ple-fp8/` | 약 48.83 GiB |
| DFlash2 drafter | `data/Infernix/components/dflash2/` | 약 0.72 GiB |

README, conversion report와 license도 함께 받으며 합계는 약 120.614 GiB입니다.
원본 Safetensors 대신 Infernix용 공개 변환본을 받습니다.
Hugging Face download cache에 전체 파일을 한 번 더 저장하지 않습니다.

정확한 repository, pinned revision, 파일 크기와 hash는
[다운로드 Manifest](../../config/Infernix/downloads/orcarouter-nvfp4.manifest.json)에 기록합니다.
모델·PLE·drafter는 각각 별도 repository에서 받습니다. NVIDIA repository에서는
선택한 PLE volume과 license만 받고 NVIDIA 모델 Shard는 받지 않습니다.

## 상태 확인과 재개

아래 명령은 repo root에서 실행합니다.

```powershell
Get-Content runtime/Infernix/downloads/orcarouter-nvfp4/status.json -Raw |
    ConvertFrom-Json |
    Select-Object state, progress_percent, received_bytes, expected_bytes,
        current_file, speed_mib_per_second, updated_at, detail
```

- Worker identity: `runtime/Infernix/downloads/orcarouter-nvfp4/worker.json`
- Stdout: `runtime/Infernix/downloads/orcarouter-nvfp4/download.stdout.log`
- Stderr: `runtime/Infernix/downloads/orcarouter-nvfp4/download.stderr.log`
- 최종 파일 옆의 `.part`는 이어받기용이며 완료로 취급하지 않습니다.
- `completed`는 전체 파일의 크기와 pinned hash가 검증된 상태입니다. 추론 준비 완료를 뜻하지 않습니다.
- 중복 worker는 Windows file lock으로 차단합니다. 종료·실패 후 같은 명령으로 재개합니다.

```powershell
python -u -B scripts/Infernix/download_orcarouter_nvfp4.py `
    --manifest config/Infernix/downloads/orcarouter-nvfp4.manifest.json
```

Worker는 Python standard library만 사용합니다. 전역 dependency를 설치하지 않습니다.
백그라운드 실행은 `Start-Process -WindowStyle Hidden`으로 시작하며 stdout·stderr를 위 경로로
redirect합니다. 큰 파일은 전송 중 SHA-256을 계산하고, 검증한 후에만 최종 이름으로 변경합니다.
기존 파일이나 부분 파일의 크기·hash가 다르면 보존하고 실패로 기록합니다.

## 검증 범위

2026-11-05: 공식 release archive 크기·SHA-256과 설치 executable `--help` 옵션 호환성,
관리 서버 테스트 52개, 기존 JavaScript 테스트 6개, LibreChat 설정 `-ValidateOnly`를 통과했습니다.
테스트는 다운로드 차단·파일/receipt 불일치·고정 identity·API 상태 정규화·native process 실행 계약과
기존 profile·이력 보존을 포함합니다. 실행 중 native API와 LibreChat 실제 텍스트 응답을 확인했습니다.
긴 Context·최대 KV·Vision 입력·ComfyUI 동시 부하의 성능 검증은 별도 항목입니다.

2026-11-05 후속: 이전 Strata의 보존 128K·8K 입력으로 제한 시간 120초의 Prefill 관측을
시도했으나, 두 요청 모두 KV 자원 부족의 HTTP 503으로 즉시 거부됐습니다.
상세 조건·응답·측정 한계는 [Prefill 진입 실패 관측](PREFILL_OBSERVATION_2026-11-05.md)을 따릅니다.
이후 Comfy GPU 메모리 반환과 headroom 2 GiB 변경·재기동 후 128K 요청은 HTTP 200으로
정상 처리됐습니다. 두 실행 조건을 구분합니다.
