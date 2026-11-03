# IQ3_XXS 최적화 실측 결과 — 2026-11-03

완료: 3회 A/B/A를 통과하여 20:12에 운영 설정을 반영했고, 20:19에 실제 운영 API 회귀 검증과 최종 상태 확인을 완료했습니다.
진행 이력은 [checkpoint 문서](OPTIMIZATION_PROGRESS_2026-11-03.md), 전체 수치는
[Engine 측정 JSON](benchmarks/2026-11-03-optimization-engine-screen.json)에 보존합니다.
사용자가 웹 관리 화면으로 재기동한 뒤의 성능 재현은 [재기동 재검증](WEB_RESTART_REVALIDATION_2026-11-03.md)에 기록합니다.
재사용 도구·보존 입력·정리 후 파일 위치는 [테스트 안내](BENCHMARKS.md)를 따릅니다.

## 유지한 조건과 변경 후보

- RTX 5080 16GB, Ryzen 7 9800X3D, RAM 96GB, Windows.
- Strata v0.2.10 / Engine 0.1.56 CUDA 13, source `ffa80d73133ea5c548aefe57889a16e8085a938f`.
- SC117 Qwen3.8-Flash-Next IQ3_XXS, Context **262144**, reserve **8192MiB**.
- MTP on, spec 4 / min-p 0.5, KV int8 / resident 32768, prefill auto,
  PCIe auto, worker 기본 7개, host core 기본값을 유지합니다.
- Model weights·quantization·driver·전역 CUDA·Sampling 설정은 변경하지 않습니다.

반영한 변경은 다음 환경변수 세 개뿐입니다. `16384`는 layer-major의 **super-chunk**이며,
`--prefill 16384`와 다릅니다. 기본 prefill chunk의 자동 선택은 유지합니다.

```json
"env": {
  "STRATA_PREFILL_LAYER_MAJOR": "1",
  "STRATA_PREFILL_LM_R": "host",
  "STRATA_PREFILL_LM_TOKENS": "16384"
}
```

Layer-major는 여러 chunk의 expert 계산을 layer별로 모아서 expert를 다시 읽는 양을 줄입니다.
Residual buffer는 pinned RAM에 둡니다. 계산의 FP32 합산 순서가 달라질 수 있으므로
출력 문자열이 원본과 같다고 보장하지 않으며, 별도 정답·긴 입력 검사를 수행했습니다.
공식 구현은 [prefill.cpp](https://github.com/Niko1221/Strata/blob/v0.2.10/src/prefill/prefill.cpp),
자동 선택은 [generate.cpp](https://github.com/Niko1221/Strata/blob/v0.2.10/src/program/generate.cpp)에 있습니다.

## MTP on/off와 긴 입력 비교

아래는 같은 round 7에서 각각 새 Engine으로 측정한 결과입니다.
짧은 decode는 한국어 운영 지침·Python code·영문 설명 세 작업의 기하평균입니다.
한국어 서술·대화와 긴 문서 이후 생성은 각각 512 tokens를 출력했습니다.
PP는 prompt 처리량이며 TTFT·전체 요청 시간과 구분합니다.

| 지표 | 원본 MTP on | 기본 MTP off | 빠른 prefill + MTP on | 빠른 prefill + MTP off |
| --- | ---: | ---: | ---: | ---: |
| 짧은 decode (tok/s) | 83.44 | 74.12 | 83.44 | 74.21 |
| 한국어 서술 (tok/s) | 85.7 | 82.6 | 84.7 | 82.9 |
| 한국어 대화 (tok/s) | 83.8 | 80.0 | 84.2 | 81.5 |
| cold 32K PP (tok/s) | 1250.9 | 2501.9 | 2742.8 | 2747.3 |
| cold 128K prompt (초) | 112.411 | 55.561 | 50.422 | 50.449 |
| cold 260K prompt (초) | 232.904 | 119.596 | 108.928 | 108.979 |
| cold 260K TTFT (초) | 233.227 | 119.932 | 109.232 | 109.267 |
| 260K 이후 decode (tok/s) | 84.5 | 71.1 | 87.5 | 71.1 |
| 전체 GPU 관측 peak (MiB) | 9996 | 9360 | 10427 | 9269 |
| 시스템 최소 여유 RAM (GiB) | 11.05 | 11.01 | 10.41 | 10.75 |
| medium 정답 검사 | 12/12 | 12/12 | 12/12 | 12/12 |

문서 실제 입력은 131051 / 259997 tokens이며 cached prefix가 없는 요청입니다.
문서의 5·50·95% 위치 값 세 개를 모두 찾았습니다. 이후 문서의 다른 record 값을 찾은 뒤
512 tokens를 생성하는 검사도 모두 통과했고, 약 260032 tokens의 prefix를 재사용했습니다.

MTP off는 실제 native 명령에서 `--mtp`가 빠진 것을 확인했습니다. Text prompt lookup은 유지합니다.
기본 on/off 비교에서 GPU expert cache는 343 → 799 slots로 늘었습니다.
그러나 speculative decoding을 잃어 출력은 느려졌습니다. 입력의 큰 이득은 cache 여유와 함께
바뀐 prefill 자동 선택의 영향이 컸으며, 같은 빠른 prefill을 적용하면 on/off의 입력 속도는 거의 같았습니다.
따라서 균형을 우선하는 후보는 MTP on입니다. VRAM 절약을 우선하면 같은 prefill의 MTP off가 대안이며,
관측 GPU peak 약 1158MiB 절약 대신 긴 문서 이후 생성이 약 19% 느려졌습니다.

자원 수치는 2초 간격의 **전체 시스템/GPU 관측값**입니다. Strata 단독 사용량이나 순간 최대값이 아닙니다.
ComfyUI queue는 후보 시작 전마다 비어 있는지 확인했고 다른 앱의 모델을 내리지 않았습니다.
reserve 8192는 유지했으나 실제 GPU 여유 8GiB를 보장하는 hard cap은 아닙니다.
빠른 on 후보의 비용은 원본 대비 GPU 약 431MiB, RAM 약 0.64GiB 증가입니다.

## 조사·선별 방법과 제외한 설정

[공식 tuner](https://github.com/Niko1221/Strata/blob/v0.2.10/strata_control/autotune.py)의
단일 항목 비교·순서 교차·A/A 변동 확인 방식을 참고했습니다.
[RTX 5080 사용자 측정](https://github.com/Niko1221/Strata/blob/v0.2.10/bench/results/2026-10-05-community-rtx5080-9900x3d/README.md),
[Windows 다중 GPU 비교 #3978](https://github.com/Niko1221/Strata/issues/3978),
[RTX 3090 async 비교](https://github.com/Niko1221/Strata/blob/v0.2.10/bench/results/2026-10-11-community-rtx3090-5600x-arena-async/README.md)를
후보 선정에 사용했으며 다른 하드웨어·quantization·reserve의 수치를 이 PC의 성능으로 해석하지 않았습니다.

- API screening 63 requests: PCIe 0 / 0.2 / 0.35는 decode 약 24 / 18 / 9% 감소.
  PCIe 0.5와 spec-min-p 0.7은 약 1% 이득으로 변동 범위여서 제외했습니다.
- worker 6, host last, spec 3, async, 빠른 adaptive, decay 0.9, overlap,
  routed prefill, PCIe balance는 뚜렷한 종합 이득이 없었습니다.
- `pin-by-need`와 CPU prefill share off는 처리량이 떨어져 제외했습니다.
- 숫자형 `--prefill 4096/8192`는 자동 fit이 KV를 4096으로 줄였고 PP가 약 62% 감소했습니다.
- KV 48K는 decode가 느려졌습니다. KV 64K 요청은 실제로 20K로 축소됐습니다.
  실제 20K는 짧은 decode에 이득이 있었지만 긴 KV 축소에 대한 공식 경고와 추가 변수를 고려해 채택하지 않았습니다.
- PLE RAM/mmap, 더 강한 routing prior, quantization 변경과 worker 초과 증가는 시험하지 않았습니다.

정답 검사는 temperature 0의 비교용 Sampling, thinking medium / budget 512로 산술 4·논리 3·JSON 3·복사 1·한국어 추출 1을 검사합니다.
이 작은 검사 집합의 점수이며 일반적인 답변 품질 점수는 아닙니다.
thinking off의 짧은 `17*23+19를 계산해서 숫자만 출력하세요.`는 원본부터 `390`을 반환했습니다.
이 오답은 튜닝 후에도 관측됐으며 결과 파일에서 제외하지 않았습니다.
수동 검토한 한국어 512-token 샘플에서는 이전 Q2의 음절 반복 현상은 보이지 않았습니다.

## 최종 검증과 복구

새 Engine으로 `기준–후보–기준`을 3회 비교했고 두 번째 round는 실행 순서를 뒤집었습니다.
출력 5작업(기존 3개 + 한국어 서술/대화)과 cold 32K를 각 Engine에서 측정했습니다.

| round | decode 비율 | PP 비율 | 앞뒤 기준 decode 변동 |
| --- | ---: | ---: | ---: |
| 10 | 1.0021 | 2.2063 | 0.93% |
| 11 | 0.9891 | 2.2040 | 1.92% |
| 12 | 0.9874 | 2.2096 | 0.90% |
| 중앙값 | 0.9891 | 2.2063 | 0.93% |

짧은 출력 약 1.1% 감소는 이 비교의 변동 범위로 판단하며, 출력 속도 향상을 주장하지 않습니다.
각 개별 작업의 비율 중앙값도 0.98 이상이었습니다. 입력 이득은 세 round에서 모두 약 2.2배였습니다.

운영 반영 첫 시도는 테스트용 제어 도구가 관리 상태 snapshot을 준비 상태로 오인해 start를 건너뛰었습니다.
실제 native process가 없는 것을 확인해 중단하고 local 설정을 원본으로 복원했습니다.
제어 도구가 실제 운영 `/health`와 파일에서 다시 계산한 profile revision을 확인하도록 수정한 뒤 다시 적용했습니다.
Management Server와 upstream 코드는 변경하지 않았습니다.
두 번째 시도에서는 실제 native process의 인자·환경변수를 확인했고 기동 직후 cold nonstream 두 입력도 통과했습니다.

실제 관리 경로의 검증은 **28/28**, 별도 cold nonstream은 **2/2**를 통과했습니다.
전체 실험은 63개 API 조절 요청, 43차례 새 Engine 측정, 최종 운영 30건으로 총 522개 생성 요청을 보존했습니다.
이 중 알려진 thinking off 산술 오답은 실패로 그대로 남겼습니다. 522건 전체의 의미적 정답을 주장하지 않습니다.

| 실제 운영 cold 검색 | 업데이트 직후 TTFT (초) | 최적화 후 TTFT (초) | 값 검색 |
| --- | ---: | ---: | --- |
| 8K | 6.705 | 3.792 | 3/3 |
| 32K | 26.585 | 12.215 | 3/3 |
| 128K | 112.179 | 50.793 | 3/3 |
| 260K | 235.123 | 109.393 | 3/3 |

최적화 후 네 요청의 cached tokens는 모두 0입니다. 실제 260K prompt 처리는 109.076초 / 2383.6 tok/s였습니다.
기존 생성 반복의 중앙값은 90.5 → 89.0 tok/s로, 입력 이득과 달리 출력 향상으로 해석하지 않습니다.
이 표의 전 값은 [업데이트 직후 baseline](API_BASELINE_2026-11-03.md), 동일 round 비교는 앞의 round 7 표입니다.

- 긴 follow-up은 prefix 260033을 재사용해 TTFT 0.518초, 다른 대화 뒤 복원은 260060을 재사용해 0.532초였고 새 record 값도 정답이었습니다.
- Tool 호출·문자열 literal·대화 격리·DONE 이후 재요청·reasoning medium을 통과했습니다.
- Context 초과와 잘못된 Model ID는 기대한 HTTP 400으로 거부했습니다.
- #5055 Hello와 #3465 URL 입력은 stream/nonstream 및 별도 cold 기본값 검사에서 정상 처리됐습니다. cold 요청의 cached tokens는 0입니다.
- CPU Vision은 `Red`, doctor는 `ok=true / issues=[]`였습니다. #4891의 기존 새 reader 경로 보정은 유지됐습니다.
- 현재 기동 로그에서 NaN·OOM·CUDA error 등 critical 일치 0건, upstream `git status --short --ignored` 출력 없음.
- 최종 상태는 `strata-qwen-flash-next`, `ready`, in-flight 0, 8488입니다. LibreChat·MongoDB는 healthy를 유지했습니다.
- 최종 운영 suite의 전체 GPU 관측 peak는 10437MiB, 최소 여유 RAM은 9.52GiB였습니다. ComfyUI 동시 생성 부하는 시험하지 않았습니다.

공개 가능한 원본 요약은 [최종 운영 API JSON](benchmarks/2026-11-03-optimized-managed-api.json)에 보관합니다.
요청 원본과 정답 fixture는 hash로 검증한 Git archive에 보존했습니다. 사용 script는 측정 당시 commit으로 확인할 수 있습니다.
중복 runtime 상세 산출물은 테스트 정리 때 제거했으며 API key와 임시 파일은 commit하지 않습니다.

최적화만 원복하려면 관리 화면에서 Strata를 OFF한 뒤 `config/Strata/strata.local.json`의 `env`에서
위 세 키를 제거하고 다시 ON합니다. Engine과 모델, Context/reserve를 내릴 필요는 없습니다.
운영 반영 전 설정은 `runtime/Strata/rollback/2026-11-03-test-configurations/before-application/`에 보관합니다.
당시 임시 반영 도구는 검증 후 설정을 반영하고 실패 시 복원했으며, 작업 완료 후 제거했습니다.

기존 [업데이트 전 복구 기준](ROLLBACK_BASELINE_2026-11-03.md)과
[최적화 전 262K API baseline](API_BASELINE_2026-11-03.md)은 그대로 유지합니다.
최적화 완료 기준은 Git tag `baseline/2026-11-03-iq3-xxs-optimized-262k`로 보존합니다.
`external_repo/Strata`에는 수정이나 설치 산출물을 추가하지 않습니다.
