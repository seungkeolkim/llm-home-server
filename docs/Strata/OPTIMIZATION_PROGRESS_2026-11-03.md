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

현재 단계: **완료**. MTP on + layer-major / host residual / 16K super-chunk를 채택하고 실제 운영 30건 검증까지 통과했습니다.
최종 결과는 [실측 결과](OPTIMIZATION_RESULTS_2026-11-03.md)와 [최종 API JSON](benchmarks/2026-11-03-optimized-managed-api.json)을 기준으로 합니다.
아래 checkpoint는 작업 중의 당시 상태를 시간순으로 보존한 기록입니다.

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

19:03 checkpoint: worker 6 = decode 83.31 / PP 1230.7, host last = 83.98 / 1235.8,
spec 3 = 86.33 / 1240.5, KV 48K = 80.72 / 1229.5 tok/s입니다.
32K 검색은 모두 3/3, medium 검산은 정답, greedy 검산은 기존 오답 390을 유지했습니다.
아직 채택한 후보는 없습니다.

다음 추가 screening 후보는 공식 tuner의 `adapt-decay 0.9`·`STRATA_PIN_BY_NEED=1`과,
[DETAILS의 opt-in](https://github.com/Niko1221/Strata/blob/v0.2.10/docs/DETAILS.md)에 측정 사례가 있는
`STRATA_PREFILL_ROUTED_STREAM=1`·`STRATA_PCIE_BALANCE=1`입니다.
더 큰 prefill chunk는 현재 reserve에서 cache를 빌릴 공간이 부족하므로 우선하지 않습니다.

최종 후보와 baseline의 정답 비교를 위해 [12문제 quality suite](../../scripts/Strata/measure_optimization_quality.py)를 추가했습니다.
산술 4, 논리 3, JSON 3, 문자열 복사 1, 한국어 추출 1을 thinking medium / budget 512 / max 1024로 비교합니다.
부분 문자열 일치 대신 전체 문자열 또는 JSON 값을 비교합니다. `--quality-suite`를 붙인 새 round에서 실행합니다.

19:05 checkpoint: KV 64K를 요청한 후보는 decode 88.94 / PP 1245.8 tok/s였지만,
**실제 native 명령은 KV 20480**이었습니다. 64K의 성능 개선으로 해석하면 안 됩니다.
`vram_fit`의 자동 축소로 expert cache가 baseline 343에서 429 slots로 늘었습니다.
KV 48K 후보는 실제로 49152를 유지했고 cache 225 slots였습니다.
이 현상을 바탕으로 실제 20K 후보를 별도로 시험합니다. 공식 tuner는 기존 값보다 낮은 KV를 권장하지 않으므로
이 후보를 채택하려면 특히 128K·260K 입력과 긴 대화 생성에서 손해가 없는지 확인해야 합니다.

### 사용자 추가 요청: MTP on/off

19:07 요청을 반영하여 다음 batch의 첫 비교를 MTP off/on으로 변경합니다.
LM Studio에서 MTP off가 더 적은 메모리로 빨랐다는 사용자의 경험을 현재 Strata에서 직접 확인합니다.
공식 `draft_layer.py`도 draft layer 약 1GiB와 expert cache 사이의 trade-off를 설명합니다.
실험은 `drafting: off`, `mtp: false`와 공식 `draft_layer.apply`를 사용하고,
실제 native 명령에 `--mtp`가 남으면 실패로 처리합니다.
MTP만 끄며 기존 text prompt lookup은 유지합니다. Context 262144 / reserve 8192는 그대로입니다.
원본 profile은 MTP on으로 보존되어 있습니다.

후속 후보: `mtp-off mtp-on kv-resident-20k adapt-decay-09 pin-by-need prefill-routed-stream pcie-balance baseline-tail`.
최종 후보의 `--long-suite`는 동일한 기존 128K·260K fixture를 재사용하고,
260K 문서에서 새 record의 값을 찾은 뒤 512-token 출력을 생성해 긴 KV 상태의 decode도 측정합니다.

19:14 checkpoint (첫 on/off 비교, 반복 확인 전):

| 설정 | 짧은 decode (tok/s) | cold 32K prefill (tok/s) | GPU peak (MiB) | Expert cache |
| --- | ---: | ---: | ---: | ---: |
| MTP on, round 3 | 83.47 | 1246.2 | 9981 | 343 slots |
| MTP off, round 3 | 74.31 | 2503.6 | 9351 | 799 slots |
| MTP on + 실제 KV 20K | 87.50 | 1247.8 | 9979 | 429 slots |

off는 짧은 출력 약 11% 감소, 32K 입력 약 2배, GPU peak 약 630MiB 감소였습니다.
따라서 이득·손해를 분리해 보고하고 긴 입력 측정을 생략하지 않습니다.
Engine은 off에서 자동으로 `unfused experts + layer-major walk`, chunk 1024, cache 520 slots 대여를 선택했습니다.
MTP on baseline은 cache가 작아 prompt buffer를 따로 할당했습니다.
추가 후보 `prefill-unfused`와 `prefill-unfused-layer-major`는 MTP on을 유지한 채 이 prefill 경로를 비교합니다.
최종 quality 단계에는 한국어 서술·대화 각 512-token throughput도 추가합니다. 해당 두 문제는 언어 품질 점수로 해석하지 않습니다.

19:24 checkpoint: round 3 후반 baseline은 decode 81.84 / PP 1243.9였습니다.
앞 baseline 83.47과의 decode 차이는 약 1.95%입니다. 후보 채택 전 A/B/A 반복으로 이 변동을 보정합니다.
`pin-by-need`는 decode 75.34 / PP 1022.2로 제외합니다.
routed prefill과 PCIe balance는 각각 PP 1247.9 / 1239.7로 뚜렷한 이득이 없었습니다.

round 4의 `prefill-unfused`만 지정한 결과는 baseline 수준입니다.
`prefill-unfused-layer-major`는 **MTP on을 유지하면서** decode 83.60 / PP 2499.0을 기록했습니다.
GPU peak는 10501MiB로 baseline보다 약 520MiB 증가했습니다. 검색과 medium 검산은 통과했습니다.
원본 native 구현은 super-chunk 단위(기본 8192)로 처리하므로 문서 전체를 한꺼번에 중간 버퍼에 넣지는 않습니다.
`STRATA_PREFILL_LM_R=host`로 residual buffer를 RAM에 두는 후보와 불필요한 fused override를 제거한 후보도 비교할 예정입니다.
단일 32K 결과만으로 이 환경변수를 운영 설정에 넣지 않습니다.

현재 실행 명령:

```powershell
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/measure_engine_candidates.py --round 4 --trials prefill-unfused prefill-unfused-layer-major mtp-off-kv20k prefill-unfused-layer-major-kv20k baseline-tail
```

다음 단계의 paired confirmation은 `--round 10 --repeat-rounds 3 --trials baseline <candidate> baseline-tail` 형식입니다.
중간 round의 순서를 뒤집으며, 후보마다 새 Engine을 사용합니다. 아직 최종 candidate를 정하지 않았습니다.

19:33 checkpoint: MTP on + layer-major의 세부 비교는 다음과 같습니다.

| residual 위치 / super-chunk | decode (tok/s) | cold 32K PP (tok/s) | 전체 GPU peak (MiB) |
| --- | ---: | ---: | ---: |
| VRAM / 8K | 84.63 | 2495.5 | 10510 |
| pinned RAM / 4K | 84.51 | 1766.1 | 10134 |
| pinned RAM / 8K | 83.44 | 2313.9 | 10230 |
| pinned RAM / 16K | 85.23 | 2748.1 | 10428 |

reserve 인자는 모두 8192이고 실제 GPU 여유 8GiB를 보장하는 hard cap이 아닙니다.
16K host 후보는 원본 대비 GPU peak 약 447MiB 증가, PP 약 2.2배의 trade-off입니다.
VRAM 8K 후보보다 PP가 빠르고 GPU peak가 작아 후속 검증 대상으로 고릅니다.
아직 운영 설정에는 적용하지 않았습니다. KV 20K는 공식 tuner의 축소 경고를 감안하여 screening 결과로만 보존합니다.

사용자에게 MTP on의 균형과 off의 VRAM 절약 중 우선순위를 optional 질문으로 확인 중입니다.
응답을 기다리는 동안 네 가지 설정의 검증을 계속합니다. 별도 지시가 없다면 MTP on + 빠른 prefill의 균형을 우선합니다.

다음 긴 검증 명령:

```powershell
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/measure_engine_candidates.py --round 7 --trials baseline mtp-off prefill-layer-major-host-16k mtp-off-layer-major-host-16k --quality-suite --long-suite
```

기본 on/off와 동일한 prefill 설정을 적용한 on/off를 모두 비교합니다.
원본 모델·quantization·Sampling 설정과 고정 Context/reserve는 바꾸지 않습니다.

19:40 긴 검증 진행: `r07-baseline`의 medium 정답 검사 12/12,
한국어 서술/대화 각각 512-token 생성 완료(85.7 / 83.8 tok/s).
131051-token cold 문서는 검색 3/3, prompt 112.411초 / 1165.8 tok/s였습니다.
259997-token 문서는 처리 중입니다. 이어서 긴 KV 상태의 512-token 생성과 나머지 세 설정을 같은 순서로 측정합니다.
이 시점에도 운영 profile의 원본 설정은 바꾸지 않았습니다.

19:42 `r07-baseline` 완료: 260K 검색 3/3, TTFT 233.227초, PP 1116.3 tok/s.
260K 문서 이후 새 record 값을 찾고 512 tokens를 생성한 요청도 정답이며 decode 84.5 tok/s,
cached prefix 260033 tokens, TTFT 0.675초였습니다. 최소 여유 RAM은 약 11.05GiB였습니다.
새 medium 검사 12/12를 통과했고, 이전부터 알려진 thinking off 단문 산술 390 오답은 그대로입니다.
현재 `r07-mtp-off`를 측정 중이며 이후 on/off + host 16K prefill 후보를 측정합니다.

19:50 checkpoint:

- 기본 MTP off도 medium 정답 12/12, 128K·260K 검색과 새 record/512-token 생성까지 통과했습니다.
- off의 128K prompt 55.561초, 260K prompt 119.596초로 원본 대비 약 절반입니다.
- off의 긴 문서 이후 decode는 71.1 tok/s로 원본 84.5 대비 약 15.9% 감소했습니다.
- off의 한국어 서술/대화는 82.6 / 80.0 tok/s로 원본 85.7 / 83.8보다 약 4% 낮았습니다.
- 전체 GPU peak는 원본 9996MiB, off 9360MiB였습니다.
- MTP on + host 16K 후보도 medium 정답 12/12와 128K 검색 3/3을 통과했습니다.
- 해당 on 후보의 128K prompt는 50.422초 / 2599.1 tok/s였습니다. 260K 측정은 진행 중입니다.

후속 paired confirmation에는 `--style-suite`를 붙여 12문제 전체를 반복하지 않고
한국어 서술·대화의 512-token throughput도 3 rounds에서 함께 비교합니다.
정답 12문제와 긴 입력은 현재 네 가지 설정 각각에서 한 번 이상 검증합니다.

19:52 `r07-prefill-layer-major-host-16k` 완료:

- medium 정답 12/12, 128K·260K 검색 3/3씩, 새 record 확인 후 512-token 생성 통과.
- 짧은 세 작업 decode 기하평균 83.4422 tok/s (원본 83.4417).
- cold 32K PP 2742.8 tok/s (원본 1250.9).
- 128K prompt 50.422초 (원본 112.411), 260K prompt 108.928초 (원본 232.904).
- 260K 이후 512-token decode 87.5 tok/s (원본 84.5), prefix 260032 재사용.
- 전체 GPU peak 10427MiB (원본 9996), 최소 여유 RAM 10.41GiB (원본 11.05).

Context 262144 / reserve 8192 / KV resident 32768 / MTP on을 유지한 결과입니다.
추가 GPU 약 431MiB와 RAM 약 0.64GiB의 비용이 있으므로 자원 사용량도 함께 보고합니다.
현재 같은 prefill을 적용한 MTP off를 측정 중입니다. 다음 단계는 위 on 후보의 3회 A/B/A와 한국어 두 작업 비교입니다.

19:55 재개 안내: `r07-mtp-off-layer-major-host-16k`의 medium 12/12와 128K 검색 3/3은 통과했고,
128K prompt 50.449초로 동일 prefill의 on(50.422초)과 거의 같습니다. 260K는 진행 중입니다.
네 설정의 결과를 먼저 확인한 뒤 다음 명령으로 반복 검증합니다.

```powershell
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/measure_engine_candidates.py --round 10 --repeat-rounds 3 --trials baseline prefill-layer-major-host-16k baseline-tail --style-suite
```

최종 후보가 검증되면 관리 API로 운영 profile을 종료하고 local 설정과 template에만 해당 `env` 세 값을 반영합니다.
원본 `args`(262144 / 8192 / KV 32768 / MTP on)는 유지합니다.
다시 관리 API로 기동한 뒤 cold nonstream Hello·#3465 입력, 기존 `measure_api_baseline.py --suite all`의
8K·32K·128K·260K와 issue 검사를 별도 `managed-final` 폴더에서 실행합니다.
마지막으로 doctor의 설정된 Vision 경로·Engine 로그·관리 상태·source clean 상태를 확인하고 결과 문서와 summary를 commit합니다.
검증 실패 시 운영 설정을 `original-configuration/strata.local.json`으로 복원하며 원본 secret을 보존합니다.

20:13 checkpoint: 3회 A/B/A 완료, PP 비율 2.2063 / 2.2040 / 2.2096,
decode 비율 1.0021 / 0.9891 / 0.9874입니다. 개별 작업 비율 중앙값은 모두 0.98 이상입니다.
MTP on + host 16K 후보를 실제 local 설정에 반영했습니다. `args`는 변경하지 않았습니다.
첫 반영 도구의 stale 관리 snapshot/skip 문제는 실제 health 확인과 fresh revision 계산으로 수정했고,
실패 시도와 원본 복원 기록도 보존했습니다. 두 번째 반영에서 실제 native 환경변수와 고정 인자를 확인했습니다.
기동 직후 nonstream Hello·#3465는 HTTP 200 / cached tokens 0으로 통과했습니다.

현재 실행: `managed-final`의 기존 전체 API suite입니다. 로그는 `managed-final.log`입니다.
아직 최종 완료로 보지 않습니다. 다음은 결과 28건 확인, doctor·로그·관리 상태 확인,
공개 summary·결과 문서·README 갱신과 commit입니다.
반영 전 가장 최근 복원 파일은 `state.json`의 `rollback_configuration`입니다.
임시 반영 도구 `apply_confirmed_configuration.py`는 로컬 runtime 폴더에만 두며 commit하지 않습니다.

20:19 완료 checkpoint:

- 실제 운영 전체 API 28/28와 별도 cold nonstream 2/2 통과.
- doctor `ok=true / issues=[]`, CPU Vision `Red`, 현재 기동 critical 로그 일치 0.
- 실제 Native Engine의 환경변수 3개, Context 262144 / reserve 8192 / KV 32768 / MTP on 확인.
- 최종 관리 상태 `ready`, in-flight 0, profile `strata-qwen-flash-next`, port 8488.
- upstream clone은 ignored 산출물까지 clean. LibreChat·MongoDB healthy.
- 최종 운영 TTFT: 8K 3.792 / 32K 12.215 / 128K 50.793 / 260K 109.393초.
- 최종 운영 결과와 원본 설정 backup·원본 baseline·runtime 상세 로그를 보존했습니다.
- 후속 작업은 최종 결과 문서의 설정과 측정을 기준으로 시작합니다. 중간 후보나 최초 실패 summary를 최종 선택으로 해석하지 않습니다.

21:36 재개 확인:

- 사용량 제한 뒤 저장 상태와 결과를 확인했으며, 생성 테스트는 20:19에 완료되어 있었습니다.
- 실제 `/health` 정상, 관리 상태 `ready`, in-flight 0이며 20:12 기동한 동일 instance를 유지했습니다.
- 완료된 측정은 재실행하지 않고 최종 문서·설정 template·측정 summary·재현 script를 commit합니다.
- 최적화 완료 기준 tag는 `baseline/2026-11-03-iq3-xxs-optimized-262k`입니다. 기존 복구 기준은 보존합니다.

## 중단 후 이어가기

- 로컬 작업 폴더: `runtime/Strata/tuning/2026-11-03-iq3-xxs-reserve8192-context262144/`.
- `state.json`: 현재 단계·마지막 작업·완료 여부. `events.jsonl`: 시간순 기록.
- API 요청별 결과와 원본 응답은 단계별 하위 폴더에 보존합니다. 완료된 요청은 재실행 시 건너뜁니다.
- local 설정·API key·로그·임시 candidate config는 Git에 넣지 않습니다.
- 이어가기 전 이 문서, `state.json`, 가장 최근 summary, 실제 `/health`·관리 상태를 함께 확인합니다.
- 결과가 없는 running 표시는 성공으로 해석하지 않습니다. 오류가 난 후보는 Engine 로그를 확인하고 기록합니다.
- 기존 baseline과 source는 보존합니다. 다른 앱이나 ComfyUI의 작업·모델은 변경하지 않습니다.
