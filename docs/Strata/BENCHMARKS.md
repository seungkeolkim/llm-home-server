# Strata 성능 기록과 테스트 재사용

## 현재 결론과 기록

IQ3_XXS는 Context 262144 / reserve 8192MiB / MTP on을 유지하며,
layer-major prefill의 residual을 pinned RAM, super-chunk를 16384로 설정합니다.
긴 입력 처리는 최적화 전보다 약 2.2배 빨라졌고, 웹 관리 화면에서 OFF/ON한 뒤에도 재현됐습니다.
MTP off는 VRAM을 절약했지만 출력이 느려 채택하지 않았습니다.

| 확인할 내용 | 기록 |
| --- | --- |
| 최종 설정·후보 비교·MTP on/off·설정 원복 | [최적화 결과](OPTIMIZATION_RESULTS_2026-11-03.md) |
| 웹 관리 재기동 후 동일 성능 확인 | [재기동 재검증](WEB_RESTART_REVALIDATION_2026-11-03.md) |
| 업데이트 직후의 최적화 전 성능·issue 재현 | [262K API baseline](API_BASELINE_2026-11-03.md) |
| 구버전 source·Engine·venv 복구 | [업데이트 전 복구 기준](ROLLBACK_BASELINE_2026-11-03.md) |
| 후보 선정과 중간 실패를 포함한 당시 작업 이력 | [진행 기록](OPTIMIZATION_PROGRESS_2026-11-03.md) |
| 개별 수치와 공개 가능한 응답·검증 정보 | [측정 JSON 폴더](benchmarks/) |

기존 tag `rollback/2026-11-03-iq3-xxs-baseline`,
`baseline/2026-11-03-strata-0.2.10-iq3-xxs-262k`,
`baseline/2026-11-03-iq3-xxs-optimized-262k`를 유지합니다.

## 원본 입력 보존

[입력 manifest](../../tests/Strata/fixtures/2026-11-03-api-inputs/manifest.json)와
[입력 archive](../../tests/Strata/fixtures/2026-11-03-api-inputs/requests.zip)를 Git에 보관합니다.
업데이트 baseline·최적화·웹 재기동 검사에서 사용한 **614개 요청/fixture 원본**을 byte 단위로 보존했고,
내용이 같은 파일은 SHA-256 기준으로 중복 제거하여 116개로 저장했습니다.
Archive는 약 445KiB이며 manifest에 원래 경로·길이·hash·archive entry가 있습니다.

실제로 사용한 긴 입력은 목표 8192 / 32768 / 131072 / 260000,
실제 8171 / 32768 / 131051 / 259997 tokens입니다. 64K 입력은 당시 시험하지 않았습니다.
64K **KV resident 설정 후보**와 64K **입력 문서**는 서로 다릅니다.
문서의 5·50·95% 위치 정답, follow-up·긴 생성·격리·Tool·URL·Vision 입력과 Sampling도 요청 원본에 포함합니다.

[입력 loader](../../scripts/Strata/benchmark_inputs.py)는 archive와 개별 파일 hash를 확인합니다.
API harness는 기존 네 길이의 원문과 정답을 archive에서 읽고 다시 생성하거나 token count API로 맞추지 않습니다.
새 길이를 요청한 경우에만 synthetic 입력을 생성합니다. 향후 새 입력도 별도 fixture로 보존해야 다음 비교에 사용할 수 있습니다.
입력이 같아도 GPU 계산·Sampling·cache 상태로 출력이나 token 수는 달라질 수 있습니다.

```powershell
# LLM에 접속하지 않고 입력 원본 전체 검증
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/benchmark_inputs.py
```

특정 과거 요청은 manifest의 `files[].source`로 찾은 뒤 `archive_entry`를
`benchmark_inputs.read_archived_input()`에 넘기면 읽을 수 있습니다.
`canonical_inputs`는 네 길이와 #3465의 대표 원본을 지정합니다.

## 테스트 실행

명령은 repo root에서 실행합니다. 생성 테스트 전에 관리 화면에서 IQ3_XXS를 켜고 다른 생성 작업이 없는지 확인합니다.
`--output-directory`에는 매번 새로운 폴더를 사용합니다. API key와 local 설정은 Git에 넣지 않습니다.

```powershell
# 실행 중인 서비스의 전체 API 28건: 짧은 생성, 8K~260K, cache, Tool, Vision, issue 검사
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/measure_api_baseline.py `
  --suite all --output-directory runtime/Strata/benchmarks/next-api-run

# 현재 최적화 설정의 웹 재기동 재검증 46건: 위 28건 + decode·긴 생성·정답·한국어 서술/대화
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/revalidate_api_profile.py `
  --output-directory runtime/Strata/revalidation/next-managed-run
```

두 도구는 설정과 서비스 lifecycle을 변경하지 않습니다. 재검증 도구는 실제 native 인자·환경변수·설치 build,
요청별 진행 상태·script hash·정답 12문제와 종료 후 관리 상태를 별도 저장합니다.
출력의 `summary.json`, `quality-validation.json`, `runtime-before.json`, `runtime-after.json`을 함께 확인합니다.
Doctor를 따로 실행한다면 운영 경로인 `STRATA_COMPONENTS_DIR=C:/Strata-data/components`를 해당 process에 지정합니다.

추가 튜닝에는 다음 도구를 재사용합니다. **Engine 후보 측정은 운영 Strata를 종료하고 마지막에 다시 기동합니다.**
원본 설정과 state는 새 run에서 자동 준비되며, private 설정이 있으므로 출력은 `runtime/Strata/` 아래로 제한합니다.

```powershell
# 재기동 없이 PCIe share / speculative confidence를 반복 비교
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/optimize_api_profile.py `
  --output-directory runtime/Strata/tuning/next-candidate-run --rounds 3

# 새 Engine으로 MTP on/off 등의 후보 비교; trial의 기준은 이 run 시작 시 설정
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/measure_engine_candidates.py `
  --output-directory runtime/Strata/tuning/next-candidate-run `
  --round 1 --trials baseline mtp-off baseline-tail --quality-suite --long-suite

# 저장된 후보 결과 집계; 기본 출력은 해당 run의 engine-screen-summary.json
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/summarize_optimization_results.py `
  --output-directory runtime/Strata/tuning/next-candidate-run
```

동일 run 경로를 다시 주면 완료된 후보/요청을 재사용합니다. 서로 다른 설정 비교에는 새 run을 사용합니다.
후속 튜닝의 기본 집계는 과거 공개 JSON을 덮어쓰지 않습니다.
Engine 64K 요청이 자동 fit으로 20K가 된 사례처럼 설정 파일과 실제 native 인자가 다를 수 있으므로 실제 인자를 확인합니다.

## 정리 후 남긴 것

- Git: 재사용 도구·offline 검증·원본 입력 archive/manifest·결과 문서와 측정 JSON.
- 로컬 복구 설정: `runtime/Strata/rollback/2026-11-03-test-configurations/`.
  `after-upgrade/`, `before-optimization/`, `before-application/`, `optimized-configuration/` 및 LibreChat 변경 전 YAML,
  복사본 155개의 SHA-256 manifest를 보존합니다. 비밀값이 있어 Git에 넣지 않습니다.
- 기존 구버전 Engine·venv 전체 복구 백업은 `runtime/Strata/rollback/2026-11-03-before-upgrade-iq3-xxs/`에 그대로 둡니다.

완료된 세 run의 임시 candidate 설정·반영 도구·중복 요청/응답·상세 resource sample·log·script 사본은 제거했습니다.
총 2491개 파일, 약 76MiB를 workspace 밖의 Windows 휴지통으로 옮겼으며 휴지통 자체는 비우지 않았습니다.
과거 문서와 JSON 속 runtime 경로는 당시 출처입니다. 현재 재사용 경로는 이 문서의 도구와 입력 archive를 따릅니다.
현재 운영 log·managed 상태·working 폴더·모델·Pack·사용자 첨부 파일·`scinario_samples.md`는 정리 대상에서 제외했습니다.
