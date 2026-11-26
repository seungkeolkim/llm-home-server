# Engine 업데이트와 동일 입력 속도 비교 — 2026-11-26

Strata를 stable `v0.2.22` / Engine `0.1.69`, PolyStrata를 `v0.2.20-poly.5` / Engine `0.1.66`으로 갱신했습니다.
Infernix는 기존 `windows-2026.11.01`을 유지하고 같은 입력으로 추가 측정했습니다.
구버전은 재측정하지 않았으며 Engine tuning은 수행하지 않았습니다.

## 버전과 고정 조건

| 구성 | 이전 | 이번 측정 |
|---|---|---|
| Strata source / Engine | v0.2.10 / 0.1.56 | [v0.2.22](https://github.com/Niko1221/Strata/releases/tag/v0.2.22) / 0.1.69, build `a5bfe0369bfb` |
| PolyStrata source / Engine | v0.1.45-poly.2 / 0.1.45 | [v0.2.20-poly.5](https://github.com/simplexai-labs/PolyStrata/releases/tag/v0.2.20-poly.5) / 0.1.66, build `44f8847bd6b7fd1a` |
| Infernix | windows-2026.11.01 | 같은 release와 설정 |

- GPU: RTX 5080 16 GB, driver 610.88. Strata의 과거 기록도 같은 driver입니다. RAM 93.56 GiB, CPU 8 physical cores.
- Strata: SC117 Qwen3.8 Flash-Next IQ3_XXS, Context 262144, KV INT8 / resident 32768, reserve 8192 MiB, MTP / spec 4 / min-p 0.5.
- Strata의 layer-major prefill, pinned RAM residual, super-chunk 16384를 유지했습니다.
- PolyStrata 두 profile: Qwen3.6 Unsloth UD-Q4_K_M / Hauhau TTQ Q4_K_M, Context 153600, KV Q8_0 whole, reserve 8192 MiB, threads 8, tail skip 6, 기존 MTP와 CPU Vision.
- Infernix: Orcarouter NVFP4 / FP8 dense, Context 262144, INT8 KV, DFlash2, headroom 2048 MiB, RAM 여유 8192 MiB, Host context cache 2048 MiB, Vision RAM offload.
- ComfyUI queue가 비어 있는지 각 측정 시작 시 확인했습니다. 다른 앱·서비스를 종료하거나 메모리를 강제로 반환하지 않았습니다.

Source의 Python 코드가 `terminal/`로 이동하여 외부 wrapper·requirements·tokenizer 경로를 맞췄습니다.
Local 설정의 변경은 새 executable·Vision executable 경로와 이동한 expert-profile 경로뿐입니다.
기존·신규 expert-profile 파일의 Git blob hash는 `a4ed7e5feb68e68fa76df66b9109e99c1ef143b8`로 같습니다.
Model·Pack·tokenizer·Sampling 설정과 API key를 유지했고 시스템 CUDA Toolkit·PATH·driver를 변경하지 않았습니다.

## 입력과 측정 방법

직전 Strata [재검증 기록](../Strata/WEB_RESTART_REVALIDATION_2026-11-03.md)의 46개 요청을
[보존 archive](../../tests/Strata/fixtures/2026-11-03-api-inputs/requests.zip)에서 복원했습니다.
Archive·파일 hash와 과거 결과의 request hash를 확인한 뒤 원문·Sampling·출력 상한을 재사용했습니다.
다른 모델에는 정상 요청의 Model ID만 치환합니다. 의도적인 잘못된 Model ID 검사 입력은 유지합니다.

공통 suite는 decode 3종, warmup, 운영 지침 생성 3회, 8K·32K·128K 검색, 한국어 서술·대화의 12건입니다.
일반 속도 요청은 temperature 0 / seed 20261103 / reasoning none 등 과거의 명시적 Sampling을 그대로 사용합니다.
검색은 max_tokens 256, 운영 지침·서술·대화는 512, decode 3종은 384입니다.
실제 검색 입력은 8171 / 32768 / 131051 tokens이며 Strata는 259997-token 입력도 측정했습니다.
Prefill 비교에는 cache_n=0인 검색만 사용하고 decode 대표값은 운영 지침 3회 중앙값입니다.

모든 표는 원본 API의 `timings.prompt_per_second`와 `timings.predicted_per_second`를 사용합니다.
Infernix의 console/telemetry timing은 별도로 보존하며 API timing과 작은 정산 차이가 있습니다.
OS page cache·Engine expert state를 초기화하지 않았습니다. 같은 입력이라도 Engine·MTP·Sampling 구현에 따라 출력과 생성 token 수는 달라집니다.

## 측정 결과

현재 환경에서는 PolyStrata 두 구성이 가장 빨랐습니다. Strata 업데이트 후 긴 입력 prefill은 약 3~9% 빨라졌고,
운영 지침 3회 decode 중앙값은 약 25% 낮아졌습니다. 모든 수치의 단위는 tok/s입니다.
원본 API timing·request hash·build·개별 결과는 [측정 JSON](measurements/2026-11-26-engine-comparison.json)에 보존합니다.

| 현재 구성 | Prefill 8K | Prefill 32K | Prefill 128K | Decode 3회 중앙값 |
|---|---:|---:|---:|---:|
| Strata · SC117 IQ3_XXS | 2418.5 | 2812.8 | 2669.6 | 65.5 |
| PolyStrata · Unsloth UD-Q4_K_M | 3711.1 | 4833.5 | 3756.4 | 121.6 |
| PolyStrata · Hauhau TTQ Q4_K_M | 3761.6 | 4842.3 | 3742.4 | 137.1 |
| Infernix · Orcarouter NVFP4 | 1460.6 | 1822.4 | 1668.6 | 65.3 |

Decode 각 3회의 값은 Strata 63.7 / 67.8 / 65.5, Unsloth 109.7 / 121.6 / 131.2,
Hauhau 123.9 / 137.1 / 140.8, Infernix 51.04 / 65.29 / 66.12입니다.
생성은 최대 512 tokens이며 실제 출력 길이는 모델마다 달랐습니다.
검색 세 길이에서는 네 구성 모두 cached tokens가 0이고 문서의 5·50·95% 위치 값 3개를 모두 찾았습니다.

### Strata의 과거 대비 변화

| 항목 | 이전 0.1.56 | 현재 0.1.69 | 변화 |
|---|---:|---:|---:|
| Prefill 8K | 2212.8 | 2418.5 | +9.3% |
| Prefill 32K | 2730.2 | 2812.8 | +3.0% |
| Prefill 128K | 2589.6 | 2669.6 | +3.1% |
| Prefill 260K | 2381.1 | 2469.7 | +3.7% |
| 운영 지침 decode 중앙값 | 87.3 | 65.5 | -25.0% |
| 260K 이후 512-token decode | 83.6 | 65.0 | -22.2% |

260K 이후 첫 follow-up은 기존 prefix 260032 tokens를 재사용했습니다. 다른 대화를 처리한 뒤 복원한 요청은
기존 260060 cached tokens / TTFT 0.518초에서 이번 0 cached tokens / TTFT 106.043초로 바뀌었습니다.
긴 문서의 내용을 다시 처리한 결과이며 해당 요청의 prefill tok/s를 cache 재사용 속도와 직접 비교하지 않습니다.

### PolyStrata의 과거 대비 변화

과거 [profile 검증 코드](../../scripts/ManagementServer/verify_llm_profile.py)의 3624-token 운영 메모를 재사용했습니다.
Unsloth 최초 검증 당시에는 config의 Sampling block이 없었고 Engine의 기본 temperature가 0이었습니다.
이 사실을 당시 source `4e14403c:src/poly/main.cpp`의 `temperature = 0.f`와 초기 config template로 확인했습니다.
이번 비교용 요청에 temperature 0과 비활성 penalty를 명시해 그 조건을 복원했습니다.
현재 운영 config의 temperature 1.0 / presence penalty 1.5는 변경하지 않았습니다.
Hauhau는 과거와 현재 모두 기존 profile의 temperature 1.0 / presence penalty 1.5이며 seed는 고정되지 않았습니다.

| 3624-token 메모 | Prefill 이전 → 현재 | 변화 | Decode 이전 → 현재 | 변화 |
|---|---:|---:|---:|---:|
| Unsloth · 최초 greedy 조건 복원 | 1893.0 → 2618.9 | +38.3% | 75.1 → 82.6 | +10.0% |
| Hauhau · 기존 Sampling | 1974.9 → 2150.4 | +8.9% | 90.4 → 77.1 | -14.7% |

각각 출력은 40 → 41, 38 → 41 tokens이며 1회 측정입니다. 긴 512-token 생성의 향상률로 일반화할 수 없습니다.
최초 Unsloth 검증 때의 greedy 요청과 현재 공통 benchmark의 명시적 Sampling은 목적이 달라 두 표의 decode를 혼합하지 않습니다.
현재 운영 Sampling으로 같은 메모를 보낸 추가 참고값은 prefill 2014.3 / decode 59.7이었으며,
이 값은 최초 검증의 다른 Sampling과 직접 비교하지 않았습니다.

### 검증과 종료 상태

서비스 상태는 2026-11-26 측정 완료 시점 기준입니다.

- Strata의 유효한 기존 suite 46건과 별도 medium exact 정답 12/12를 확인했습니다.
  첫 replay에서 잘못된 Model ID를 정상 ID로 치환한 harness 오류 1건이 있었습니다. 해당 결과를 제외하고
  원본 요청을 별도로 재실행해 HTTP 400을 확인했습니다. 측정 JSON에 최초 45/46와 제외 사유·재검증을 모두 보존합니다.
  주요 prefill·decode 측정은 이 오류 요청보다 앞서 수행됐습니다.
- PolyStrata 각 13/13, Infernix 12/12 요청을 통과했습니다. Unsloth 최초 Sampling 조건 확인은 별도 2/2입니다.
- Archive·Model ID 보존·request 정책 unit test 13개와 관리 profile·template test 13개가 통과했습니다. 두 venv의 `pip check`도 통과했습니다.
- Local configuration 111개 파일의 hash를 대조했고, 바뀐 파일은 실행 경로를 갱신한 Strata·PolyStrata local config 3개뿐입니다.
  Infernix·Basalt·LibreChat·관리 서버·Pi·Paseo 설정은 유지했습니다.
- 최종 LLM은 작업 전과 같은 `stopped`, in-flight 0, port 8488 listener 없음입니다.
  관리 서버 8788은 계속 실행 중이며 LibreChat·MongoDB는 `running / healthy`입니다.
- 작업 branch는 `update/strata-polystrata-2026-11-26`입니다. 2026-11-27 사용자 요청으로 바깥 repo의 관련 변경을 commit에 포함했습니다. `external_repo/`는 제외하고 merge·push는 진행하지 않았습니다.

## 비교의 제한

- 서로 다른 모델·Quantization·speculative backend의 실사용 구성 비교입니다. 같은 weights를 여러 Engine에서 실행한 비교나 답변 품질 순위가 아닙니다.
- Strata의 이전 기록은 2026-11-03, PolyStrata의 이전 기록은 2026-10-22입니다. 구버전을 오늘 다시 실행하지 않았으므로 날짜별 background 부하·RAM·cache 차이를 제거한 A/B 실험은 아닙니다.
- PolyStrata의 과거 속도 기록은 3624-token 운영 메모 1회이며 출력도 38~40 tokens로 짧습니다. 공통 8K~128K·512-token 생성의 과거 결과는 없어 해당 항목의 업데이트 향상률은 계산할 수 없습니다.
- Infernix는 이번 기동 시 가용 RAM 53.9 GiB에서 expert RAM 40.2 GiB를 자동 배정했습니다. 과거 128K 기록의 expert RAM 약 53.3 GiB와 달라 SSD 의존도가 높습니다. 이를 Engine 버전 차이로 해석하지 않습니다.
- Strata의 260K 대화 복원은 이번 실행에서 cache_n=0으로 다시 처리됐습니다. 로그는 4579 MiB snapshot이 available budget을 초과해 parking을 생략했다고 기록합니다. 실제 가용 RAM과 cache 정책이 함께 작용하므로 원인을 Engine 변경 하나로 확정하지 않습니다.

## 재사용과 복구

실행 코드는 [measure_engine_comparison.py](../../scripts/ManagementServer/measure_engine_comparison.py)입니다.
Lifecycle 제어와 측정을 명시적으로 나누며 측정 명령은 설정·기동·종료를 변경하지 않습니다.

```powershell
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/ManagementServer/measure_engine_comparison.py `
  --profile polystrata-qwen36-q4km --action start

.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/ManagementServer/measure_engine_comparison.py `
  --profile polystrata-qwen36-q4km --output-directory runtime/PolyStrata/benchmarks/next-version-run

.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/ManagementServer/measure_engine_comparison.py `
  --profile polystrata-qwen36-q4km --action stop
```

Strata 전체 재검증에는 `--full-strata-suite`를 추가합니다. 기존 PolyStrata 메모에는
`--historical-polystrata-note`를 추가하며 최초 Unsloth의 Engine 기본 Sampling을 복원하려면
`--historical-note-sampling legacy-greedy`를 함께 줍니다. 이는 해당 benchmark 요청의 Sampling만 명시합니다.
다른 Engine 설정이나 운영 Sampling을 바꾸지 않습니다. 새 output directory를 사용해 기존 결과를 보존합니다.

업데이트 전 설정·source commit·branch·dependency 목록·configuration hash는
`runtime/Strata/rollback/2026-11-26-before-version-upgrade/`에 있습니다. Local 설정과 인증값이 있어 Git 제외 경로에 보관합니다.
구버전 Strata 0.1.56·0.1.45.3과 PolyStrata v0.1.45-poly.2 Engine 폴더도 유지했습니다.
최신 두 source clone은 release tag의 detached HEAD이며 공식 source를 수정하거나 산출물을 넣지 않습니다.
