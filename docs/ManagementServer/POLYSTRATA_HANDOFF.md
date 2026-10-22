# PolyStrata 추가 지원 handoff

> **2026-10-22 후속 갱신:** 사용자가 개발·LibreChat 연결·실제 기동·VRAM 측정을 명시적으로 요청해 초기 구현과 검증을 완료했습니다. 아래의 기동 금지·config 보류·미구현 기록은 그 요청 이전의 이력입니다. 현재 상태는 [운영 계획](OPERATING_PLAN.md)과 [PolyStrata 실행·실측 문서](../PolyStrata/README.md)를 우선합니다. Branch는 `migration/polystrata`이며 commit·push는 하지 않았습니다.

기록 시점: 2026-10-22 14:05 KST 이후.
Workspace: `C:/Users/azzib/Desktop/workspace_local/llm-home-server`

## 다음 대화에서 먼저 읽을 것

1. Repo의 `AGENTS.md`.
2. [운영 계획](OPERATING_PLAN.md)의 「LLM Engine·model 선택 기동 설계」. 이 문서가 확정 설계의 기준입니다.
3. 이 handoff의 금지사항, Git 상태와 다운로드 완료 기록.

이번 사용자 요청은 context 압축 전에 정보를 보존하는 것입니다. **설계 기록과 모델 다운로드까지만 수행했으며, 구현을 시작하라는 새로운 요청으로 해석하지 않습니다.**

## 반드시 유지할 사용자 지시

- 한국어·존댓말, 전문용어는 English. 함수별 docstring, PowerShell은 comment-based help. 역할을 알아볼 수 있는 이름과 가독성을 우선합니다.
- ComfyUI가 heavy 영상 작업 중이므로 **Strata·PolyStrata를 기동하거나 model을 Load하지 않습니다.** 생성 요청과 benchmark도 수행하지 않았습니다. 이후 사용자가 실행을 허용하기 전까지 유지합니다.
- 공식 source는 `external_repo/`의 독립 clone으로 유지합니다. 자체 설정·venv·dependency·로그·실행 산출물을 넣지 않습니다.
- 기존 Strata와 실행 설정·API key·model·Pack은 보존합니다. 시스템 CUDA Toolkit·전역 PATH·driver를 바꾸지 않습니다.
- 사용자는 처음에는 config 역산이 가능한지만 물었습니다. Agent가 먼저 만든 template은 당장 사용하지 않고 그대로 두었다가 나중에 수정하기로 했습니다. 추가 config 작성은 보류 중입니다.
- 정기 다운로드 조회나 알림은 요청하지 않았습니다. 사용자가 물으면 그때 상태를 확인합니다.
- Commit·push 요청은 없었으며 이번 대화에서 수행하지 않았습니다.

## 확정 설계

이전에 검토했던 「Strata를 PolyStrata로 완전 일원화」는 현재 방향이 아닙니다.

| 단계 | 실행 체계 | Model |
|---|---|---|
| 유지 | Strata | 기존 Qwen3.8-Flash-Next / SC117 IQ3_XXS |
| 1차 추가 | PolyStrata | Qwen3.6-35B-A3B MoE / Unsloth UD-Q4_K_M |
| 2차 추가 | PolyStrata | Qwen3.8-Flash-Next |

- 최종 세 조합을 유지하고 이후 새 Engine·특화 Engine·model을 추가할 수 있게 합니다.
- LLM Home Server의 「켜기」를 누르면 Engine·model 조합을 선택한 후 기동합니다. 선택 화면을 여는 것만으로 기동하지 않습니다.
- 초기에는 LLM 하나만 실행합니다. 다른 조합은 현재 LLM을 명시적으로 끈 뒤 선택해 켭니다. 자동 교체·drain·실패 시 이전 model 자동 복구는 하지 않습니다.
- 내부 선택 단위는 실행 profile입니다. Engine, model, weights quantization, KV, context, Vision과 메모리 예산을 묶되 공통 UI가 Engine별 CLI를 알지 않게 합니다.
- 기동 접수 시 profile ID·설정 revision을 고정합니다. Worker가 나중에 최신 선택값으로 대상을 바꾸지 않습니다. 종료는 실제 실행 instance를 대상으로 하며 process 소유 관계와 시작 시각을 식별해야 합니다.
- Adapter의 초기 계약은 준비 상태 조회·start·status·stop·로그 위치입니다. 지원하지 않는 기능을 공통 기능처럼 만들지 않습니다.
- 다운로드 중·Engine 미설치·파일 검증 실패·기동 가능·Loading·사용 가능을 구분하고, 환경 준비와 평상시 기동을 분리합니다.
- **LibreChat model 목록과 model별 context는 정적으로 고정**합니다. 모두 약 150K를 목표로 하며 정확한 token 수는 미확정입니다. 기동할 때 실제 Engine을 조회해서 LibreChat 설정을 동적으로 바꾸자는 제안은 사용자가 채택하지 않았습니다.
- LibreChat의 제목 생성·요약 model 참조와 context도 고정 목록 안에서 정의합니다. 미실행 model을 요청했다고 다른 조합을 자동 기동·교체하지 않습니다.
- Resource 예산과 실측 여부를 profile에 남기고 기동 직전 상태도 확인합니다. Reserve를 전체 사용량의 hard limit으로 취급하지 않습니다.
- **Engine/serving process를 유지한 채 model·KV만 unload/offload하는 기능은 TODO만 기록**했습니다. 현재 필요성을 느끼지 않으므로 초기 구현에 넣지 않습니다.
- UI의 Engine 항목 Strata·PolyStrata와 내부 executable 이름은 별개입니다. PolyStrata도 QFN에는 `strata`, Qwen3.6에는 `strata-poly`를 사용합니다.

## Git 상태와 보존할 변경사항

- Branch: **`migration/polystrata`**. 사용자가 branch 생성·전환을 요청하여 `main`에서 만들었습니다.
- 현재 HEAD: `956498b` (`Improve resource card layout and memory usage display`). 새 commit·push 없음.
- Branch를 만들기 전부터 다음 tracked 파일에 미commit 변경이 있었습니다. 이번 PolyStrata 구현으로 오인하거나 덮어쓰지 않습니다.
  - `docs/LibreChat/README.md`
  - `docs/ManagementServer/OPERATING_PLAN.md`
  - `docs/ManagementServer/README.md`
  - `management_server/application.py`, `operations.py`, `worker.py`
  - `tests/ManagementServer/test_management_server.py`
  - `web/ManagementServer/application.js`
- `tests/ManagementServer/test_control_history.cjs`도 이전 작업의 untracked 파일입니다.
- 이번 대화에서는 운영 계획과 관리 서버 README에 설계를 추가했습니다. 위 문서의 기존 변경을 보존해야 합니다.
- 추가된 untracked 파일은 Strata config 초안 3개, `docs/Strata/QWEN36_CONFIGURATION.md`, `QWEN36_MEMORY_ESTIMATES.json`, `scripts/PolyStrata/download_qwen36_ud_q4_k_m.py`와 이 handoff입니다.
- 실제 작업 전 `git status --short`를 다시 확인합니다. 외부 clone과 runtime·venv는 Git 제외 대상입니다.

## 외부 source

| Source | URL | 확인한 HEAD |
|---|---|---|
| Strata | https://github.com/Niko1221/Strata | `9ae93f7b1fe989d04a8e404d32cddaeeff10505f` |
| PolyStrata | https://github.com/VecSzn/PolyStrata | `4e14403c6b0259ac3b61eefd3209f40d71bbd993` |

- PolyStrata는 `external_repo/PolyStrata`에 full clone했습니다. Windows 긴 경로로 첫 checkout이 실패해 이 clone의 local Git config에만 `core.longpaths=true`를 설정하고 checkout을 완료했습니다.
- 조사 당시 외부 두 source는 수정하지 않았습니다. PolyStrata branch는 `main`이며 조사 당시 `origin/main`과 같았습니다. 이후 상태는 재확인합니다.

## Qwen3.6 Q4_K_M 다운로드 완료

- **2026-10-22 13:50:52 KST에 완료**, 14:05 KST에 상태 파일과 최종 파일 크기를 확인했습니다.
- 파일: `C:/Strata-data/models/qwen36-UD-Q4_K_M/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf`
- 크기: **22,663,387,424 bytes** (약 22.66 GB / 21.11 GiB).
- Repository: `unsloth/Qwen3.6-35B-A3B-MTP-GGUF`.
- Pinned revision: `5bc3e238d916f48a861bac2f8a1990a0e9b7e98d`.
- SHA-256: `0b21525e972670ed59e1812e170b27c26355381f0656ecc4e25617ece7dac58b`.
- Downloader가 전송 중 SHA-256을 계산하여 검증한 뒤 `.part`를 최종 파일로 변경했습니다. `status.json`은 `completed`, `100%`, `size and SHA-256 verified`입니다. 메모 시점에 대용량 파일 hash를 다시 읽지는 않았습니다.
- Worker PID는 `31756`이었고 완료 후 종료됐습니다. 이후 같은 PID가 재사용될 수 있으므로 PID만 보고 process를 판단하거나 종료하지 않습니다.
- 진행·완료 기록: `runtime/PolyStrata/downloads/qwen36-UD-Q4_K_M/status.json`, `stdout.log`, `stderr.log`.
- Downloader: `scripts/PolyStrata/download_qwen36_ud_q4_k_m.py`. 중복 worker 방지 lock, 부분 이어받기와 network retry가 있으며 설치·Load 기능은 없습니다. 완료 후 재실행할 이유가 없습니다.
- **Model GGUF만 다운로드했습니다.** PolyStrata Engine 설치, tokenizer 생성, Qwen3.6 전용 mmproj 다운로드, PolyStrata용 venv·runtime 준비는 아직 하지 않았습니다.

## 기술 조사에서 확인한 내용

- 기존 Strata의 Qwen3.6 전용 `src/qwen35/q36_engine.cu`는 전체 context의 FP32 KV를 GPU에 할당합니다. KV quantization과 `--kv-resident` streaming은 없습니다.
- PolyStrata의 Qwen3.6은 별도 `src/poly/` Engine입니다. 자주 쓰는 experts의 adaptive GPU cache, CPU expert 계산과 GPU 작업 병행, prefill의 quantized MMQ·staging, CUDA graphs와 speculative decoding을 사용합니다. F/N과 같은 전체 Engine은 아니지만 비슷한 CPU/GPU 분업 목적의 최적화가 있습니다.
- PolyStrata Qwen3.6도 **active KV의 CPU streaming/offload는 없습니다.** `Engine::cover()`가 GPU KV를 늘리면서 expert cache를 줄입니다. CUDA VMM의 물리 allocation은 DEVICE이며 CPU RAM offload가 아닙니다.
- KV 기본은 **FP16**, opt-in **`strata-poly --kv q8_0`** 지원. Q4 KV·K8V4·K/V별 형식 선택은 없습니다. Conversation parking의 host save/load는 active KV streaming이 아닙니다.
- KV는 대화 길이에 따라 GPU allocation이 증가합니다. `--kv-whole`을 쓰면 최대 context 전체를 Load 시 할당합니다. 성장 단위는 4,096 rows, ahead는 1,024 rows이며 allocation alignment가 더해집니다.
- MTP 포함 attention 11 layers, KV heads 2, head width 256 기준 KV 본체:

| Context | Strata FP32 | Poly FP16 | Poly Q8_0 |
|---|---:|---:|---:|
| 32,768 | 1.375 GiB | 0.688 GiB | 0.365 GiB |
| 65,536 | 2.750 GiB | 1.375 GiB | 0.730 GiB |
| 131,072 | 5.500 GiB | 2.750 GiB | 1.461 GiB |
| 163,840 | 6.875 GiB | 3.438 GiB | 1.826 GiB |

- Q8_0는 scale 비용 포함 FP32보다 약 73.4% 작습니다. 위 숫자는 KV 본체만이며 Engine·staging·scratch·allocation 여유는 별도입니다.
- GPU는 RTX 5080, `nvidia-smi` 보고 전체 16,303 MiB였습니다. 사용자는 heavy Comfy 영상 작업 때 LLM VRAM 약 8 GiB, LLM용 남는 System RAM 약 30 GB라는 보수적인 운영 예산을 제시했습니다. 현재 live 여유량을 뜻하지 않습니다.
- 이 예산에서 Q4 weights + Q8_0 KV를 유력한 후보로 판단했습니다. Q4의 RAM 약 24–28 GiB는 정적 계획 범위이며 실측이 아닙니다. Q8_0 weights는 GGUF 자체가 약 35.2 GiB여서 RAM 30 GiB 안에서 매끄러운 상주 운영이 불리합니다. 사용자는 최종적으로 공식 기본 목록의 Q4_K_M을 선택했습니다.
- PolyStrata는 experts를 GGUF mmap에서 직접 읽습니다. 기존 Strata Qwen3.6의 별도 전체 host expert arena 숫자를 PolyStrata에 그대로 대입하면 안 됩니다. File cache와 pinned staging을 구분합니다.
- Setup은 여러 conversation의 RAM 보관에 최대 **8 GiB**를 추가할 수 있습니다. RAM 30 GiB 예산에는 별도 반영해야 합니다.
- 공식 `qwen36` Setup 모델은 `UD-Q2_K_XL`, `UD-Q3_K_M`, `UD-Q4_K_M`입니다. `qwen36-strata`는 이전 Strata 전용 Engine이므로 혼동하지 않습니다.
- Engine은 `--kv q8_0`를 받지만 Setup의 `--kv` CLI 선택지는 아직 `int8/q4_0/k8v4` 중심입니다. Engine args와 Setup option을 구분해야 합니다.
- Windows CUDA 13 ready-made Engine release가 존재합니다. 조사 시 최신 release는 `v0.1.45-poly.2` (2026-10-20)였고 Q8 KV와 Qwen3.6 실행 사례를 포함합니다. `STRATA_FATTN=1`·`STRATA_FDEC=1`은 opt-in입니다. 설치나 해당 hardware 검증은 하지 않았습니다.

## 구현 시 확인할 현재 코드 경계

- `management_server/configuration.py`: `llm.adapter == strata`만 허용합니다.
- `management_server/integrations.py`: `StrataAdapter` 하나, 고정 Strata runner와 native config를 사용합니다. Status의 model 이름도 config에서 읽으므로 미래의 실제 active instance 식별과 구분해야 합니다.
- `management_server/monitoring.py`: 생성 시 adapter 하나를 고정합니다.
- `management_server/application.py`: `ControlInput`은 요청 UUID만 받고 LLM 로그 경로도 Strata 고정입니다.
- `management_server/operations.py`: DB에는 target/action만 저장하며 profile/revision 정보는 아직 없습니다. 기존 제어 이력·재부팅 복구 변경을 보존하면서 확장해야 합니다.
- `management_server/worker.py`: 실행 시 `load_configuration()`을 다시 읽습니다. 향후 접수 당시 profile 고정이 필요한 지점입니다.
- `scripts/Strata/strata_runner.py`: `SOURCE_ROOT=external_repo/Strata`, `strata.local.json`, saved profile `sc117-iq3-xxs`와 SC117 assets 검증에 고정되어 있습니다. 새 Qwen model을 경로만 바꿔 그대로 준비할 수 없습니다.
- 기존 native config의 `exe=component:strata-engine` symbolic resolution과 managed `runtime/profile` CLI가 PolyStrata에 그대로 존재하지 않습니다. PolyStrata `serve/server.py`는 executable path를 받습니다. Adapter 추가는 단순 source root 교체가 아닙니다.
- `external_repo/PolyStrata/polystrata.py --model ...`는 server를 시작하거나 `/api/models/load`를 호출할 수 있습니다. 조사·상태 확인 명령으로 실행하지 않습니다.
- `config/LibreChat/librechat.local.yaml.template`와 `scripts/LibreChat/prepare-environment.ps1`에는 Strata model/context·제목·요약 model과 endpoint/key 고정값이 있습니다. 사용자가 채택한 정적 model 목록 방식으로 후속 확장합니다.
- 대용량 assets는 `C:/Strata-data`에 재사용하고 `.venv/PolyStrata`, `config/PolyStrata`, `runtime/PolyStrata`, `scripts/PolyStrata`, `requirements/PolyStrata` 등은 필요한 구현 시 시스템별로 분리합니다. 아직 폴더 전체를 준비하지 않았습니다.

## 검증 및 다음 작업의 범위

- 이번 대화에서 Engine 실행·실제 inference·RAM/VRAM 실측은 하지 않았습니다. 문서·코드·웹 조사와 산술 확인만 수행했습니다.
- Downloader는 syntax 확인 후 실제 백그라운드 전송과 완료 검증 기록을 확인했습니다. 문서 수정은 `git diff --check`로 확인했습니다.
- 앞서 만든 Strata 32K/Q4_K_XL·Q6·Q8 template과 계산 문서는 superseded 검토 초안입니다. 삭제하지 말라는 사용자 의도를 유지하되 새 설계의 현재 설정으로 인용하지 않습니다.
- 다음 구현은 사용자 지시에 따라 시작합니다. 목표는 1차 PolyStrata + Qwen3.6 추가, 준비 단계와 기동 단계 분리, 정적 model catalog·profile·adapter·제어 이력·선택 UI 확장입니다. 정확한 약 150K token 수, 실제 KV/profile·port/key mapping은 후속 정의 대상입니다.
- Comfy 작업 중 실제 model Load를 검증하지 않습니다. 이를 이유로 구현할 수 있는 read-only 설계 검토나 Mock 기반 검증까지 불필요하게 중단할 필요는 없습니다.

## 주요 근거

- Local: `external_repo/PolyStrata/docs/BACKENDS.md`, `docs/Q8_KV.md`, `src/poly/engine.cpp`, `qwen35.cpp`, `main.cpp`, `runtime.hpp`, `cpu_experts.cpp`, `setup.py`.
- https://github.com/VecSzn/PolyStrata/blob/main/docs/BACKENDS.md
- https://github.com/VecSzn/PolyStrata/blob/main/docs/Q8_KV.md
- https://github.com/VecSzn/PolyStrata/releases/tag/v0.1.45-poly.2
- https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/blob/5bc3e238d916f48a861bac2f8a1990a0e9b7e98d/Qwen3.6-35B-A3B-UD-Q4_K_M.gguf
