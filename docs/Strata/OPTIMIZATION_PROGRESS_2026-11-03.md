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

현재 단계: API screening 진행 중. 3개 task와 round 앞·뒤 baseline, 후보 5개를 3회 교차 순서로 측정합니다. 요청마다 원본과 결과를 저장하며 아직 최적화 설정을 채택하지 않았습니다.

재개 명령:

```powershell
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/optimize_api_profile.py --phase api-screen --rounds 3
```

## 중단 후 이어가기

- 로컬 작업 폴더: `runtime/Strata/tuning/2026-11-03-iq3-xxs-reserve8192-context262144/`.
- `state.json`: 현재 단계·마지막 작업·완료 여부. `events.jsonl`: 시간순 기록.
- API 요청별 결과와 원본 응답은 단계별 하위 폴더에 보존합니다. 완료된 요청은 재실행 시 건너뜁니다.
- local 설정·API key·로그·임시 candidate config는 Git에 넣지 않습니다.
- 이어가기 전 이 문서, `state.json`, 가장 최근 summary, 실제 `/health`·관리 상태를 함께 확인합니다.
- 결과가 없는 running 표시는 성공으로 해석하지 않습니다. 오류가 난 후보는 Engine 로그를 확인하고 기록합니다.
- 기존 baseline과 source는 보존합니다. 다른 앱이나 ComfyUI의 작업·모델은 변경하지 않습니다.
