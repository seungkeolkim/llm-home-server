# 웹 관리 화면 재기동 후 IQ3_XXS 재검증 — 2026-11-03

사용자가 웹 관리 화면에서 OFF/ON한 Strata를 21:44~21:48에 API로 다시 측정했습니다.
**최적화된 긴 입력 성능이 재현됐습니다.** 32K·128K·260K의 첫 응답 시간 차이는 이전 최적화 측정 대비 약 0.14% 이내였습니다.
짧은 생성 반복의 중앙값은 89.0 → 87.3 tok/s로 약 1.9% 감소했습니다.

비교 기준은 [최적화 실측 결과](OPTIMIZATION_RESULTS_2026-11-03.md)의 최종 운영 API run이며,
세부 요청·정답·timing·runtime·비교 값은 [재검증 JSON](benchmarks/2026-11-03-web-restart-revalidation.json)에 보존합니다.
설정 변경이나 추가 재기동 없이 사용자가 켜 놓은 동일 instance에서 모든 검사를 수행했습니다.

## 실제 기동 상태와 검사 방법

- 관리 instance: `1727f3a9465d466d9efd86658ae4682f`, native PID `9212`. 이전 최적화 적용 instance와 달라 재기동을 확인했습니다.
- 실제 executable: `C:/Strata-data/components/engine/0.1.56-windows-x86_64-cuda-cuda13/strata.exe`.
- 설치 `BUILD.json`: Engine `0.1.56`, commit `06698c674673`, CUDA `13.0`.
- Model ID: `sc117-qwen3.8-flash-next-abliterated-iq3_xxs`.
- 실제 native 인자: Context `262144`, reserve `8192MiB`, KV int8 / resident `32768`, MTP on / spec 4 / min-p 0.5.
- 실제 process 환경변수: `STRATA_PREFILL_LAYER_MAJOR=1`, `STRATA_PREFILL_LM_R=host`, `STRATA_PREFILL_LM_TOKENS=16384`.
- 저장한 공개 설정은 이전 최종 운영 측정과 동일했습니다. 실제 기동 로그에서도 pinned RAM residual의 layer-major 처리를 확인했습니다.

기존 `measure_api_baseline.py`의 전체 suite 28건을 동일한 입력 길이와 생성 반복 3회로 실행했습니다.
추가로 기존 세 decode 작업, 260K 이후 512-token 생성, medium 정답 12문제, 한국어 서술·대화 각 512 tokens를 검사하여 총 46건입니다.
요청은 순차 실행했고 비교용 Sampling은 기존 harness의 temperature 0 / seed 20261103 등을 그대로 사용했습니다.
medium 정답 검사는 budget 512를 사용합니다. ComfyUI queue는 시작 시 비어 있었으며 동시 이미지 생성은 시험하지 않았습니다.

## 입력 처리와 출력 속도

| 검색 입력 | 이전 최적화 TTFT (초) | 웹 재기동 후 TTFT (초) | 변화 | 검색 정답 |
| --- | ---: | ---: | ---: | --- |
| 8K | 3.792 | 3.871 | +2.11% | 3/3 |
| 32K | 12.215 | 12.199 | -0.14% | 3/3 |
| 128K | 50.793 | 50.852 | +0.12% | 3/3 |
| 260K | 109.393 | 109.507 | +0.10% | 3/3 |

실제 입력은 각각 8171 / 32768 / 131051 / 259997 tokens이며 네 요청 모두 cached tokens가 **0**입니다.
문서의 5·50·95% 위치 값을 모두 찾았습니다. 32K·128K·260K의 prompt 처리량은 각각
2730.2 / 2589.6 / 2381.1 tok/s로 이전 2727.7 / 2593.5 / 2383.6 tok/s와 거의 같았습니다.

| 출력 지표 | 이전 최적화 | 웹 재기동 후 |
| --- | ---: | ---: |
| 운영 지침 생성 3회 중앙값 (tok/s) | 89.0 | 87.3 |
| 한국어 서술 512 tokens (tok/s) | 84.7 | 82.7 |
| 한국어 대화 512 tokens (tok/s) | 84.2 | 83.2 |
| 260K 이후 생성 512 tokens (tok/s) | 87.5 | 83.6 |

서술·대화·긴 문서 이후 생성의 이전 값은 최종 후보를 검사한 round 7의 동일 작업입니다.
한국어 서술·대화는 약 2.4% / 1.2%, 긴 문서 이후 생성은 약 4.5% 낮았습니다.
추가 세 decode 작업의 기하평균은 86.02 tok/s였으나 개별 작업은 이전보다 약 -5.7~+14.1%로 달랐습니다.
생성된 문자열과 작업 순서·cache 상태가 달라질 수 있으므로 이 한 번의 재측정으로 decode 향상이나 성능 퇴행을 단정하지 않습니다.
기존 3회 A/B/A를 다시 수행한 실험은 아니며, 긴 입력의 약 2.2배 개선 유지와 운영 재기동 후 동작 확인이 목적입니다.

긴 follow-up의 TTFT는 0.508초, 다른 대화 뒤 복원은 0.518초였습니다.
새 record 값을 묻는 512-token 생성도 정답이었고 prefix 259990 tokens를 재사용했습니다.
수동 확인한 한국어 512-token 샘플에는 이전 Q2에서 보였던 음절 반복이 관측되지 않았습니다.

## 정답·회귀·자원과 종료 상태

- 기존 전체 API 기대 결과 **28/28**, 추가 검사를 포함한 기대 결과 **46/46**, 별도 medium exact 정답 **12/12**.
- 긴 문서 검색·follow-up·대화 복원, cache 격리, Tool 호출과 literal, DONE 이후 재요청, reasoning medium을 통과했습니다.
- #5055 Hello / #3465 URL의 stream·nonstream 기본값 입력을 통과했습니다. 이 검사는 기동 직후 첫 생성이라는 조건을 보장하지 않습니다.
- CPU Vision은 `Red`. Context 초과와 잘못된 Model ID는 기대한 HTTP 400을 반환했습니다.
- 현재 기동 구간 로그에서 NaN·non-finite·CUDA error·OOM·assert failure·memory guard 거부 일치 **0건**.
- 운영 component 경로를 사용한 doctor는 `ok=true / issues=[]`. #4891의 새 Vision reader 경로 보정이 유지됐습니다.
- 전체 GPU 관측 peak **10442MiB**(이전 10437MiB), 최소 여유 RAM **13.03GiB**(이전 9.52GiB).
  2초 간격 전체 시스템 관측이며 백그라운드 사용량이 달라 RAM 절약 효과로 해석하지 않습니다.
- 최종 `/health` 정상, 관리 상태 `ready`, in-flight 0, port 8488. 검사 전후 instance와 native PID를 유지했습니다.
- `external_repo/Strata`는 ignored 산출물까지 clean이며 서비스 설정·upstream source를 변경하지 않았습니다.

처음 별도 shell에서 실행한 doctor는 `STRATA_COMPONENTS_DIR`가 없어 AppData 기본 경로에서 Engine을 찾지 못했습니다.
실제 운영 component 경로 `C:/Strata-data/components`를 해당 진단 process에만 지정해 다시 조회했고 정상 판정을 받았습니다.
두 결과를 모두 보존했으며 운영 환경이나 파일을 수정하지 않았습니다.
생성 직후 관리 snapshot의 `generating / in-flight 1`은 갱신 후 `ready / 0`임을 다시 확인했습니다.

당시 로컬 산출물 경로는 `runtime/Strata/revalidation/2026-11-03-web-restart/`였으며 작업 완료 후 중복 산출물을 정리했습니다.
입력 원본은 Git archive, 측정·응답·process·진단 요약은 위 JSON, 재사용 도구는
[테스트 안내](BENCHMARKS.md)에 보존합니다. API key와 임시 실행 파일은 commit하지 않습니다.
기존 baseline 및 최적화 완료 tag는 그대로 유지합니다.
