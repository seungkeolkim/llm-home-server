# IQ3_XXS 최적화 진행 기록

## 고정 조건과 복구 기준

- 사용자 요청: reserve `8192 MiB`, Context `262144` 유지. 진행 상황과 측정값을 단계마다 보존합니다.
- Branch: `experiment/strata-upgrade-iq3-xxs`.
- 기준 commit: `565803dc0f79c3b99df05348722177918808e1a8`.
- 기준 tag: `baseline/2026-11-03-strata-0.2.10-iq3-xxs-262k`.
- Source: v0.2.10, `ffa80d73133ea5c548aefe57889a16e8085a938f`; Engine 0.1.56 CUDA 13.
- 모델은 SC117 IQ3_XXS를 유지합니다. 다른 quantization, routing prior 강화, Model weights 변경, driver·전역 CUDA 변경은 이번 최적화에 포함하지 않습니다.
- 기존 [262K API baseline](API_BASELINE_2026-11-03.md)의 33개 검사를 최종 회귀 비교 기준으로 사용합니다.

## 조사한 방법

1. [공식 tuner 후보·안전 범위](../../external_repo/Strata/strata_control/tune_knobs.py): 사용자 설정에서 한 항목씩 변경하며 PCIe share, speculative confidence, spec 3, KV resident 64K, host core 등을 비교합니다.
2. [공식 autotuner](https://github.com/Niko1221/Strata/blob/v0.2.10/strata_control/autotune.py): 순서를 바꾼 interleaved 반복, A/A 변동 측정, 최소 3% 이득과 다른 지표의 퇴보 검사를 사용합니다.
3. [RTX 5080·9900X3D 사용자 기록](https://github.com/Niko1221/Strata/blob/v0.2.10/bench/results/2026-10-05-community-rtx5080-9900x3d/README.md): PCIe 분담률과 spec-min-p를 조정하고 여러 입력 길이·needle 검사로 비교했습니다. 다른 quantization과 작은 reserve의 수치를 현재 구성의 예상 속도로 사용하지 않습니다.
4. [2×5060 Ti Windows 사용자 비교 #3978](https://github.com/Niko1221/Strata/issues/3978): prefill, spec, KV resident, async, host core를 비교했으며 자동 튜닝의 퇴보도 보고했습니다. 단일 GPU인 이번 환경에서는 항목별 후보 선정 근거로만 사용합니다.
5. [RTX 3090 Windows async 비교](https://github.com/Niko1221/Strata/blob/v0.2.10/bench/results/2026-10-11-community-rtx3090-5600x-arena-async/README.md): 새로운 Prompt와 순서를 뒤집은 반복으로 비교했고, 긴 입력에서는 이득이 작았습니다.
6. [KV resident·confidence 사용자 기록 #3563](https://github.com/Niko1221/Strata/issues/3563): GPU의 KV와 expert cache 사이의 공간 배분, spec-min-p 0.5/0.7을 비교했습니다. 단일 설정의 효과가 분리되지 않은 부분은 그대로 채택하지 않습니다.

## 계획과 현재 상태

1. 진행 기록과 원본 설정 snapshot 생성.
2. API per-request 조절이 가능한 PCIe share·spec-min-p를 교차 순서로 screening.
3. 재기동이 필요한 worker 수·prefill·KV resident·spec·async 후보를 항목별 screening.
4. 상위 후보를 baseline과 반복 비교하고 이득이 noise보다 큰지 확인.
5. 선택 설정으로 짧은·32K·128K·260K 입력, cache 복원, Tool·Vision·NaN 회귀 검사.
6. 유효한 설정만 실제 profile에 반영하고 관리 경로로 기동한 뒤 문서·측정 요약을 commit.

현재 단계: API screening 완료, 재기동 후보 screening 진행 중. 아직 최적화 설정을 채택하지 않았습니다.

### 재기동 screening checkpoint (18:58 KST)

| 후보 | 짧은 decode 기하평균 (tok/s) | cold 32K prefill (tok/s) | 전체 GPU peak (MiB) |
| --- | ---: | ---: | ---: |
| baseline, round 2 | 83.99 | 1234.7 | 9981 |
| prefill 4096 | 91.14 | 477.6 | 9089 |
| prefill 8192 | 89.81 | 472.6 | 9089 |

두 fixed prefill 후보 모두 검색 3/3, medium 검산 정답, 기존 greedy 검산 오답을 유지했습니다.
짧은 decode의 이득만으로 채택하지 않습니다. 32K 입력 처리량이 약 61~62% 감소했습니다.
또한 native Engine 로그에서 실제 `--kv-resident`가 32768에서 4096으로 바뀌었습니다.
공식 `vram_fit.fit_start`는 `user_args`로 고정되지 않은 KV window를 줄일 수 있으므로,
이 결과는 prefill 하나만의 순수한 효과가 아닌 자동 조정까지 포함한 결과입니다.
운영 원본 설정은 바꾸지 않았습니다. 이후 trial에서는 native process의 실제 인자를 함께 저장하고
Context·reserve가 실제 기동 명령에서도 유지되는지 검사합니다.

숫자형 prefill 추가 시험과 KV 16K·worker 4/5는 제외합니다.
공식 tuner의 좁은 범위를 우선하여 worker 6, host last, spec 3, KV 48K/64K,
async, adaptive 속도, CPU prefill share off, overlap을 이어서 비교합니다.
완료된 결과는 [Engine screening JSON](benchmarks/2026-11-03-optimization-engine-screen.json)에 후보별로 자동 저장합니다.

### API screening 결과

3개 task × 7개 arm(앞·뒤 baseline 포함) × 3 rounds = 63 requests, 오류 0.
입력 prefix가 겹치지 않도록 식별자를 넣고 384-token 출력을 사용했습니다.
Round 앞·뒤 baseline 차이의 중앙값은 약 2.71%였습니다.

| 후보 | baseline 대비 decode 비율 중앙값 | 판단 |
| --- | --- | --- |
| PCIe share 0.0 | 0.7648 | 제외 |
| PCIe share 0.2 | 0.8243 | 제외 |
| PCIe share 0.35 | 0.9128 | 제외 |
| PCIe share 0.5 | 1.0115 | 변동 범위, 미채택 |
| Spec confidence 0.7 | 1.0057 | 변동 범위, 미채택 |

따라서 다음 단계는 자동 PCIe share와 spec-min-p 0.5를 유지합니다.
다른 기기의 0.2 또는 0.35 설정을 그대로 복사하면 이 PC에서는 손해였습니다.
원본은 로컬 작업 폴더의 `api-screen/summary.json`과 요청별 파일에 보존했습니다.

### 재기동 측정에서 확인한 baseline 오답

첫 재기동 baseline(`r01-baseline`)에서 긴 검색은 3/3이었지만, thinking off의
`17*23+19를 계산해서 숫자만 출력하세요.`에 `390`을 반환했습니다(정답 410).
최적화 인자를 바꾸기 전 결과이며 원본 파일과 failed summary를 그대로 보존했습니다.
기존 33건의 다른 형식 검산 결과를 수정하거나 이 오답을 숨기지 않습니다.

이후 측정은 API·계측 유효성과 semantic 정답을 별도 필드로 기록합니다.
`status: completed`는 측정 완료를 뜻하고, `quality_all_passed`·`quality_failures`·`retrieval_passed`로 정답을 판단합니다.
기존 greedy 검산에 더해 실사용 thinking medium(256-token budget) 검산을 추가하며, 새로운 round부터 적용합니다.
최종 선택에서는 baseline보다 품질이 나빠지는 후보를 제외합니다.

재개 명령:

```powershell
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/optimize_api_profile.py --phase api-screen --rounds 3
```

재기동 단계는 [Engine 후보 측정 script](../../scripts/Strata/measure_engine_candidates.py)를 사용합니다.
공식 `WorkerSession`이 복사 설정·별도 port로 후보를 실행합니다. 단계 시작 때 관리 중인 IQ3_XXS만 종료하고,
성공·실패 모두 `finally`에서 기존 운영 profile을 다시 기동합니다. 중단 전 완료된 `summary.json`은 건너뜁니다.

```powershell
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/measure_engine_candidates.py --round 2 --trials baseline prefill-4096 prefill-8192
```

진행 중인 후속 batch:

```powershell
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/measure_engine_candidates.py --round 2 --trials workers-6 host-core-last spec-3 kv-resident-48k kv-resident-64k adapt-async adapt-faster prefill-cpu-share-off adapt-overlap
```

## 중단 후 이어가기

- 로컬 작업 폴더: `runtime/Strata/tuning/2026-11-03-iq3-xxs-reserve8192-context262144/`.
- `state.json`: 현재 단계·마지막 작업·완료 여부. `events.jsonl`: 시간순 기록.
- API 요청별 결과와 원본 응답은 단계별 하위 폴더에 보존합니다. 완료된 요청은 재실행 시 건너뜁니다.
- local 설정·API key·로그·임시 candidate config는 Git에 넣지 않습니다.
- 이어가기 전 이 문서, `state.json`, 가장 최근 summary, 실제 `/health`·관리 상태를 함께 확인합니다.
- 결과가 없는 running 표시는 성공으로 해석하지 않습니다. 오류가 난 후보는 Engine 로그를 확인하고 기록합니다.
- 기존 baseline과 source는 보존합니다. 다른 앱이나 ComfyUI의 작업·모델은 변경하지 않습니다.
