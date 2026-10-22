# PolyStrata + Qwen3.6 실행

2026-10-22 `migration/polystrata`에서 기존 Strata + Qwen Flash-Next를 유지하고 PolyStrata + Qwen3.6을 추가했습니다.
공식 source는 `external_repo/PolyStrata`의 clean clone이며 실행·설치 산출물을 넣지 않습니다.

## 실행 설정

| 항목 | 설정 |
|---|---|
| Model | Unsloth Qwen3.6-35B-A3B-MTP-GGUF `UD-Q4_K_M` |
| API model ID | `qwen3.6-35b-a3b-ud-q4_k_m` |
| Profile | `polystrata-qwen36-q4km` |
| Engine | 공식 `v0.1.45-poly.2` Windows CUDA 13 prebuilt `strata-poly.exe` |
| API | `0.0.0.0:8488`, 기존 Strata·LibreChat과 같은 API key |
| Context | 153,600 tokens (150 Ki tokens) |
| KV | `q8_0`, `--kv-whole`로 최대 context를 Load 시 미리 할당 |
| Vision | Qwen3.6 `mmproj-F16.gguf`, CPU 8 threads, 최대 300 image tokens |
| VRAM reserve | 8,192 MiB. Process 사용량의 hard limit이 아님 |
| CPU experts | 8 threads, adaptive GPU expert cache |
| Conversation parking | Host cache 0 MiB |
| Sampling | 일반 thinking 공식값: temperature 1.0, top_p 0.95, top_k 20, min_p 0.0, presence_penalty 1.5, repetition_penalty 1.0 |
| Thinking loop | `reasoning_loop_recovery: "stop"`. 반복 감지 시 생성을 중단 |
| Tail skip | Upstream setup과 같은 `6`. CPU에 있는 낮은 순위 experts 일부를 생략하는 근사 최적화 |

KV는 GPU에 있고 active KV의 CPU streaming은 없습니다. Q8_0 KV의 150K 본체는 약 1.71 GiB이며 alignment·workspace는 별도입니다.
`--kv-whole`은 긴 대화에서 KV 증가로 expert cache가 뒤늦게 줄어드는 것을 피하고 최대 context의 메모리 비용을 Load 시 드러냅니다.
정확도와 속도 비교 검증은 하지 않았습니다. Tail skip을 끄려면 local 설정의 `--tail-skip`을 `0`으로 바꾸고 명시적으로 재기동합니다.
Vision 300-token 제한은 간단한 이미지용이며 세밀한 grounding·고해상도 이미지 정확도는 별도 검증이 필요합니다.

2026-10-22 thinking 반복 발생 후 [Qwen3.6 공식 일반 thinking sampling](https://huggingface.co/Qwen/Qwen3.6-35B-A3B#best-practices)을 local 설정과 template에 명시했습니다.
현재 `strata-poly` 경로는 server의 model-card sampling 자동 적용에서 제외되므로 `sampling`을 직접 지정합니다.
요청에서 전달한 sampling 값이 설정의 기본값보다 우선합니다. LibreChat에서 값을 지정하면 해당 값이 적용됩니다.
`reasoning_loop_recovery: "stop"`은 약 512 output tokens 간격으로 thinking의 반복 구절을 검사합니다.
감지 시 서버 로그에 사유를 기록하고 API는 `finish_reason: "length"`로 종료하므로 LibreChat의 전용 반복 감지 알림은 없습니다.
정상적인 반복을 오인하거나 표현이 다른 반복을 놓칠 수 있으며, loop 원인을 해결하거나 답변 완성을 보장하는 기능은 아닙니다.
Thinking 예산과 output 상한은 이번 변경에서 추가하지 않았습니다.

## 최초 준비와 평상시 제어

```powershell
# 기존 Qwen3.6 weights 다운로드가 완료된 뒤 한 번 수행합니다. Model은 Load하지 않습니다.
./scripts/PolyStrata/prepare-environment.ps1
```

- Dependency: `.venv/PolyStrata`, 고정 목록 `requirements/PolyStrata/requirements.lock.txt`.
- Engine: `C:/Strata-data/components/PolyStrata/v0.1.45-poly.2`.
- Weights·projector: `C:/Strata-data/models/qwen36-UD-Q4_K_M`.
- Tokenizer: `C:/Strata-data/packs/qwen36-ud-q4_k_m/tokenizer`.
- 실제 설정: `config/PolyStrata/qwen36.local.json` (Git 제외). Template의 API key는 준비 단계에서 기존 Strata key로 대체합니다. 기존 local 파일을 덮어쓰지 않습니다.
- Server·Engine 로그: `runtime/PolyStrata/logs/server.log`, `engine.log`.

준비 script는 고정 Engine archive와 projector의 SHA-256을 검증하고 tokenizer round-trip을 검사합니다.
Weights는 기존 downloader의 pinned revision·SHA-256 검증 완료 파일을 사용합니다. 준비 재실행 시 weights는 크기를 확인하며 22.7 GB 전체 hash를 다시 읽지 않습니다.
시스템 CUDA·전역 PATH·driver를 변경하지 않습니다.

관리 화면 `:8788`의 **LLM 켜기 → Engine·model 선택 → 선택한 LLM 켜기**로 기동합니다.
Strata와 PolyStrata는 같은 `8488`을 사용하므로 하나만 실행합니다. 다른 조합을 쓰려면 현재 LLM을 먼저 종료합니다.
선택을 취소하면 model을 Load하거나 요청 이력을 만들지 않습니다. 기동 동작에 설치·다운로드를 섞지 않습니다.

고정 catalog는 `config/ManagementServer/llm-profiles.json`이며 Engine·model·실행 profile을 구분합니다.
요청의 profile·configuration revision·instance ID를 SQLite 이력에 저장합니다.
Worker는 접수 후 설정이 바뀌면 기동을 거부합니다. 종료 시 PID·생성 시각·소유권을 확인하며 실제 instance만 종료합니다.
Strata는 보호된 process의 command line을 읽는 대신 native ownership RPC·attestation을 사용하고 owner·instance 조건을 붙여 종료합니다.
관리 서버 reload는 LLM을 재기동하지 않습니다. 타 process가 port를 쓰면 이를 종료하지 않고 제어를 거부합니다.

## LibreChat 연결

LibreChat의 기존 endpoint 식별자 `Strata`를 유지해 저장된 대화를 보존합니다.
UI에는 `Strata · Qwen Flash-Next`, `PolyStrata · Qwen3.6 MoE`, `PolyStrata · Qwen3.6 Hauhau` 고정 항목이 표시되며 context는 모두 153,600입니다.
Model 목록은 Engine 실행 여부에 따라 자동 변경하지 않습니다. 관리 화면에서 실제 실행한 model을 LibreChat에서도 선택합니다.
Title은 `current_model`, summarization은 model override를 생략해 현재 대화의 model을 사용합니다.

PolyStrata의 외부 `serve_profile.py`는 미실행 model 요청을 HTTP 400으로 거부하고 직접 Load·Unload·설정 변경 API를 막습니다.
기존 Strata의 생성 API는 다른 model ID에도 현재 model로 답하는 upstream 동작이 남아 있습니다. 자동 기동·전환은 하지 않습니다.
따라서 Strata 사용 시에도 LibreChat에서 실제 실행 model을 선택해야 합니다. 이 제한은 이번 Qwen3.6 추가 과정에서 새로 생긴 동작이 아닙니다.

```powershell
# 실제 생성 요청을 보내는 명시적 통합 검사입니다.
./.venv/Strata/Scripts/python.exe -B scripts/LibreChat/verify-integration.py --mode chat --model qwen3.6-35b-a3b-ud-q4_k_m
```

## RTX 5080 16 GB 실측

150K KV를 미리 할당하고 CPU Vision을 Load한 상태에서 2026-10-22 측정했습니다.

| 항목 | PolyStrata Qwen3.6 Q4_K_M |
|---|---:|
| 기동 전 GPU 전체 사용량 | 1,365 MiB / 1.33 GiB |
| Load 후 GPU 전체 사용량 | 8,448 MiB / 8.25 GiB |
| Load 증가분 | 7,083 MiB / 6.92 GiB |
| Load·이미지·3,624-token 요청 중 전체 peak | 8,602 MiB / 8.40 GiB |
| 기동 전 대비 peak 증가분 | 7,237 MiB / 7.07 GiB |
| Process tree working set 합 | 23.39 GiB |
| Process tree private commit 합 | 9.99 GiB |
| OS 가용 RAM 감소량 | 약 23.78 GiB |

Working set에는 mmap weights와 공유 page가 포함되므로 private commit과 합산하지 않습니다.
OS 가용 RAM 차이에는 다른 process·cache 변동도 섞입니다. GPU 수치는 전체 사용량이며 process별 전용 VRAM 계측이 아니라 baseline 차이입니다. Peak는 1초 간격 sampling에서 관측한 최대치입니다.
30 GiB RAM 여유를 기준으로 이번 관측에서는 약 6 GiB가 남습니다. Heavy Comfy 영상 작업과 동시에 재현한 실측은 아닙니다.
GPU free는 Load 후 약 7.35 GiB였습니다. Reserve 8 GiB가 고정 buffers까지 포함한 실제 free 8 GiB를 보장하지 않는 것을 확인했습니다.
150K KV allocation은 확인했지만 150K prompt 전체 prefill·장시간 대화의 성능·peak까지 검증한 결과는 아닙니다. 자동 summarization trigger까지 채우는 실측도 수행하지 않았습니다.

기존 Strata QFN도 150K·GPU KV 32K·INT8 설정으로 관리 API start/stop와 LibreChat 생성이 통과했습니다.
관측된 RAM 감소는 약 45.8 GiB로 두 profile의 RAM 요구량은 다릅니다.

증거는 Git 제외 경로에 있습니다.

- `runtime/ManagementServer/verification-polystrata-qwen36-q4km.json`: baseline·Load·생성·Vision·3,624-token 요청·process 메모리.
- `runtime/ManagementServer/verification-strata-qwen-flash-next.json`: 기존 Strata 기동·생성 검사.
- `runtime/LibreChat/diagnostics/verification-chat.json`: 마지막 LibreChat 검증 대화.

## HauhauCS Aggressive TTQ 실행

2026-10-22에 기존 Unsloth profile을 보존하고 Hauhau profile을 추가해 전환했습니다.

| 항목 | 설정 |
|---|---|
| 관리 profile | `polystrata-qwen36-hauhau-q4km` |
| API model ID | `qwen3.6-35b-a3b-hauhau-ttq-q4_k_m` |
| LibreChat 선택 | `PolyStrata · Qwen3.6 Hauhau` |
| 실제 설정 / 복사용 설정 | `config/PolyStrata/qwen36-hauhau.local.json` / 같은 이름의 `.template` |
| Weights | `C:/Strata-data/models/qwen36-HauhauCS-TTQ-Q4_K_M`의 HauhauCS Aggressive TTQ 4.90bpw Q4_K_M |
| MTP | 본체에 내장되어 있지 않아 같은 폴더의 `Qwen3.6-35B-A3B-MTP-ONLY-Q4_K_M-shared.gguf`를 `--draft-model`로 연결 |
| Vision | Hauhau 배포자의 `mmproj-Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-f16.gguf`, CPU |
| Tokenizer | Hauhau 본체에서 추출한 `C:/Strata-data/packs/qwen36-hauhau-ttq-q4_k_m/tokenizer` |
| 공통 정책 | 8488, context 153600, KV Q8_0 whole, reserve 8192 MiB, tail skip 6, 공식 일반 thinking sampling, loop 감지 시 stop |
| 로그 | `runtime/PolyStrata/logs/hauhau-server.log`, `hauhau-engine.log` |

다운로드 worker의 크기·SHA-256 검증이 완료된 세 파일로 준비합니다. 재준비는 기존 local 설정을 덮어쓰지 않습니다.

```powershell
./.venv/PolyStrata/Scripts/python.exe -B scripts/PolyStrata/prepare_hauhau_environment.py
```

기동은 관리 화면에서 Hauhau profile을 선택합니다. LibreChat에도 Hauhau를 선택해야 하며, 기존 Unsloth model ID를 요청하면 400으로 거부합니다.
제목과 summarization은 선택한 Hauhau model을 따릅니다. LibreChat 고정 model 목록 변경 후에는 LibreChat container만 재시작합니다.

검증 결과: tokenizer round-trip 16개 통과, 관리 API Load·텍스트 생성·CPU Vision 파란색 분석·미실행 model 거부 통과,
LibreChat 로그인·실제 채팅의 `STRATA_LIBRECHAT_READY` 응답 저장 통과. Profile 제어 관련 pytest 7개가 통과했습니다.
Load 시 GPU 전체 8462 MiB (baseline 1419 MiB), 검증 중 peak 8620 MiB, OS 가용 RAM 감소 약 22.58 GiB,
process tree working set 약 22.57 GiB를 관측했습니다. Working set과 RAM 감소량은 합산하지 않습니다.
이 수치는 짧은 생성·이미지·3624-token 요청 기준이며, 150K 전체 prefill이나 heavy Comfy 동시 작업의 보장값이 아닙니다.

증거: `runtime/ManagementServer/verification-polystrata-qwen36-hauhau-q4km.json`,
`runtime/LibreChat/diagnostics/verification-hauhau-chat.json`.

## 후속 범위

- PolyStrata + Qwen Flash-Next 추가.
- Engine을 유지한 model·KV unload/offload는 TODO만 유지합니다.
- 현재 Engine의 Load·Unload·자동 전환 기능을 관리 UI에 노출하지 않습니다.
