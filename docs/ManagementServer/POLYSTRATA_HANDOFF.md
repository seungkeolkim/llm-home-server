# PolyStrata 추가 지원 handoff

갱신 기준: 2026-10-22. Workspace: `C:/Users/azzib/Desktop/workspace_local/llm-home-server`.
이 문서는 다음 대화에서 구현·운영 상태를 이어가기 위한 현재 기준입니다. 초기 조사 당시의 기동 금지·config 보류·미커밋 상태를 현재 지시로 적용하지 않습니다.
실제 실행 상태는 바뀔 수 있으므로 작업 전 관리 API와 Git 상태를 확인합니다. 상태 확인을 위해 모델을 Load하지 않습니다.

## 먼저 읽을 문서

1. Repo `AGENTS.md`와 [운영 계획](OPERATING_PLAN.md).
2. [PolyStrata 설정·준비·실측](../PolyStrata/README.md).
3. [LibreChat model 선택](../LibreChat/README.md#모델-선택과-실행-profile), [Strata 정책 검증](../Strata/RESTORATION.md#후속-변경-model-id-검증과-thinking-loop-중단).

## 구현 완료 상태

| 관리 profile | Engine / model | API model ID |
|---|---|---|
| `strata-qwen-flash-next` | Strata / SC117 QFN IQ3_XXS | `sc117-qwen3.8-flash-next-abliterated-iq3_xxs` |
| `polystrata-qwen36-q4km` | PolyStrata / Unsloth Qwen3.6 UD-Q4_K_M | `qwen3.6-35b-a3b-ud-q4_k_m` |
| `polystrata-qwen36-hauhau-q4km` | PolyStrata / Hauhau Aggressive TTQ Q4_K_M + MTP | `qwen3.6-35b-a3b-hauhau-ttq-q4_k_m` |

- 세 profile의 context는 모두 **153,600 tokens**입니다. 관리 catalog와 LibreChat model 목록은 정적 설정입니다.
- 관리 화면의 켜기에서 profile을 선택합니다. 취소하면 요청하지 않습니다. LLM은 공통 port `8488`에서 하나만 실행합니다.
- LibreChat endpoint 이름 `Strata`는 과거 대화를 보존하는 공통 식별자입니다. LibreChat에서 model만 바꿔도 실행 Engine이 바뀌지 않습니다.
- Strata·PolyStrata 모두 다른 model ID는 생성 전에 HTTP 400으로 거부합니다. Model ID를 생략한 기존 client는 현재 model을 사용합니다.
- 두 Engine의 thinking loop는 `reasoning_loop_recovery: "stop"`입니다. 중단 사유는 API `length`와 서버 로그에 남으며 LibreChat 전용 loop 알림은 없습니다.
- PolyStrata 두 profile은 일반 thinking 공식 sampling인 temperature 1.0, top_p 0.95, top_k 20, min_p 0, presence_penalty 1.5, repetition_penalty 1.0을 명시합니다. 요청 값이 우선합니다.
- QFN은 GPU resident KV 32,768 / INT8입니다. PolyStrata Qwen3.6은 GPU KV Q8_0 whole이며 active KV의 CPU streaming은 지원하지 않습니다.
- 세 profile 모두 reserve 8,192 MiB와 CPU Vision 8 threads / 최대 300 image tokens를 사용합니다. Reserve는 사용량 hard limit이나 실제 free VRAM 보장이 아닙니다.
- 초기 기동 금지·config 보류 이후 사용자가 개발·Load·실측·재시작을 허용하여 구현을 완료했습니다. 현재 task가 문서 작업이면 서비스는 조작하지 않습니다.

## 실행 파일과 코드 경계

- 공식 clone: `external_repo/Strata`, `external_repo/PolyStrata`, `external_repo/LibreChat`. 자체 수정·설치 산출물을 추가하지 않습니다.
- Strata source 기준: `9ae93f7b1fe989d04a8e404d32cddaeeff10505f`.
- PolyStrata source 기준: `4e14403c6b0259ac3b61eefd3209f40d71bbd993`.
- PolyStrata Engine: `v0.1.45-poly.2`, 데이터 root의 `components/PolyStrata/v0.1.45-poly.2/strata-poly.exe`.
- Dependency는 `.venv/Strata`와 `.venv/PolyStrata`, CUDA DLL은 해당 venv 내부에 둡니다. 전역 CUDA·PATH·driver는 바꾸지 않습니다.
- `config/ManagementServer/llm-profiles.json`: Engine·model·실행 profile과 context·사전 리소스 검사 기준.
- `management_server/llm_profiles.py`, `llm_runtime.py`: 준비 상태·revision·단일 instance·process 소유권·실행 수명.
- `management_server/application.py`, `operations.py`, `worker.py`: 접수한 profile/revision/instance를 고정하고 SQLite 이력과 독립 worker를 유지합니다.
- `scripts/Strata/strata_entrypoint.py`: CLI·managed host·server를 외부 wrapper로 연결하여 model ID를 검증합니다. Native owner pipe·identity·attestation은 유지합니다.
- `scripts/PolyStrata/serve_profile.py`: model ID 검증과 관리 외부의 Load·Unload·설정 변경 API 거부.
- `scripts/PolyStrata/prepare_environment.py`: 기존 Unsloth assets 기반 Engine·dependency 경로·tokenizer·설정 준비.
- `scripts/PolyStrata/prepare_hauhau_environment.py`: 본체·MTP·projector 검증 완료 상태 확인 및 Hauhau tokenizer·설정 준비. 설치·다운로드·Load는 수행하지 않습니다.
- `config/LibreChat/librechat.local.yaml.template`: 세 model·tokenConfig·modelSpecs, title current_model, summarization은 현재 대화 model을 따릅니다.
- 실제 key·local 설정과 runtime evidence는 Git 제외 대상입니다. Template을 수정해도 기존 local 설정을 자동 갱신하지 않습니다.

## 다운로드와 assets

데이터 root는 `config/Strata/environment.local.json`의 `data_directory`이며 현재 `C:/Strata-data`입니다.

- Unsloth 본체·Vision: `models/qwen36-UD-Q4_K_M`. 본체에 MTP가 포함됩니다.
- Hauhau 본체·MTP·Vision: `models/qwen36-HauhauCS-TTQ-Q4_K_M`. 본체에는 MTP가 없어 `--draft-model`로 sidecar를 연결합니다.
- Tokenizer: `packs/qwen36-ud-q4_k_m/tokenizer`, `packs/qwen36-hauhau-ttq-q4_k_m/tokenizer`.
- 본체·MTP downloader: `scripts/PolyStrata/download_hauhau_qwen36_ttq_q4_k_m.py`.
- Vision projector는 별도 다운로드이며 원래 worker는 Git 제외 runtime에 있었습니다. 새 환경에서의 준비 절차는 PolyStrata 운영 안내를 따릅니다.
- 완료된 세 Hauhau 파일은 크기·SHA-256 검증을 통과했습니다. 다운로드 완료 상태와 pinned revision은 `runtime/PolyStrata/downloads`의 상태 파일에 남아 있습니다.
- 정기 모니터링·알림은 설정하지 않습니다. 사용자가 물으면 확인합니다. 완료한 worker의 과거 PID로 process를 제어하지 않습니다.

## 검증과 증거

- 세 profile의 관리 API start/stop·readiness 및 LibreChat 실제 채팅이 통과했습니다.
- Unsloth: GPU 전체 peak 약 8.40 GiB, OS 가용 RAM 감소 약 23.78 GiB.
- Hauhau: GPU 전체 peak 8,620 MiB, OS 가용 RAM 감소 약 22.58 GiB. 실제 MTP 활동과 CPU Vision 파란색 분석을 확인했습니다.
- QFN: 150K context, GPU KV 32K INT8 구성에서 RAM 감소 약 45.8 GiB를 관측했습니다.
- 메모리 수치는 짧은 생성·이미지 등의 검증 기록입니다. 150K 전체 prefill·heavy Comfy 동시 실행의 보장값이 아니며 working set과 RAM 감소량을 합산하지 않습니다.
- 마지막 Strata 정책 적용에서는 QFN을 관리 API로 재시작한 뒤 identity·attestation·generation readiness를 검증했습니다. 실제 API의 잘못된 model 요청 8건 및 LibreChat의 잘못된 PolyStrata 선택을 400으로 거부했습니다.
- 정책·managed launch 테스트 5개, upstream CPU-only loop 회귀 18개, 관리 profile pytest 7개가 통과했습니다. 실제 model을 반복 상태로 유도하지는 않았습니다.
- 증거: `runtime/ManagementServer/verification-*.json`, `runtime/Strata/request-policy-verification.json`, `runtime/LibreChat/diagnostics/verification-hauhau-chat.json`, `verification-strata-model-mismatch.json`.

## Git와 후속 범위

작업 branch는 `migration/polystrata`입니다. 주요 구현 commit은 다음과 같으며 문서 갱신 commit은 별도로 추가될 수 있습니다.

- `dc34254`: PolyStrata 초기 profile·LibreChat 통합.
- `32ad470`: Qwen3.6 sampling·loop stop와 Hauhau downloader.
- `1f2c658`: Hauhau profile·MTP·Vision·LibreChat 연결.
- `5516c51`: Strata model ID 검증·loop 중단과 회귀 테스트.

위 구현 commit은 local에 작성했으며 push하지 않았습니다. 실제 HEAD·upstream 관계와 미commit 파일은 작업 시작 시 `git status --short --branch`, `git log`로 확인합니다.
사용자 첨부 폴더 `.codex-remote-attachments/`는 작업 commit에 포함하지 않았습니다.

- PolyStrata + QFN 추가는 후속입니다. 기존 Strata + QFN은 유지합니다.
- Engine을 유지한 model·KV unload/offload는 TODO입니다. 자동 전환·drain·실패 시 이전 profile 자동 복구도 구현하지 않습니다.
- 초기 Strata Qwen3.6 Q4_K_XL·Q6·Q8 / 32K 검토 template은 [초안 문서](../Strata/QWEN36_CONFIGURATION.md)와 함께 보존하며 현재 설정으로 사용하지 않습니다.
