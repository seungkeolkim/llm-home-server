# Strata 0.2.10·IQ3_XXS·262K API baseline

측정일: 2026-11-03, Windows / Asia/Seoul.

사용자가 요청한 Strata 업데이트와 Context 확대 후, 후속 최적화의 비교 기준을 기록합니다.
주 측정은 17:37~17:46에 수행했고, 이후 관리 경로 재기동과 공개 이슈의 추가 재현 검사를 진행했습니다.
이 기록은 최신 환경의 baseline입니다. 이전 Engine으로 동일 suite를 실행하지 않았으므로
업데이트 전후의 속도 향상률이나 모델의 일반적인 답변 품질 향상을 의미하지 않습니다.

API 검사 **33건 모두 기대한 결과**를 냈습니다. 이 중 2건은 정상적인 HTTP 400 거부 검사입니다.
NaN 두 건의 cold 일반 JSON 재현은 모두 `cached_tokens=0`이었고 HTTP 200을 반환했습니다.
일부 짧은 생성의 `length` 종료와 본문 없는 thinking 응답은 아래의 시험용 출력 제한 설명을 함께 봅니다.

## 버전과 변경 범위

| 항목 | 측정 기준 |
| --- | --- |
| 공식 release | [v0.2.10](https://github.com/Niko1221/Strata/releases/tag/v0.2.10) |
| Source commit | `ffa80d73133ea5c548aefe57889a16e8085a938f` |
| Terminal / Control | `0.2.10` / build `0.1.56` |
| 설치 Engine | `0.1.56-windows-x86_64-cuda-cuda13` |
| Engine BUILD commit | `06698c674673`, CUDA `13.0`, `sm_120` 포함 |
| 이전 Engine | `0.1.45.3-windows-x86_64-cuda-cuda13` — 설치 폴더와 복구 snapshot 보존 |
| CPU | AMD Ryzen 7 9800X3D, 8 physical cores / 16 logical processors |
| GPU / driver | RTX 5080 16 GB / `610.88` |
| 시스템 RAM | 약 `93.56 GiB` |
| 바깥 작업 branch | `experiment/strata-upgrade-iq3-xxs` |
| 바깥 baseline tag | `baseline/2026-11-03-strata-0.2.10-iq3-xxs-262k` |
| 공식 source 작업 branch | `experiment/strata-upgrade-iq3-xxs`, release commit에서 생성 |

공식 updater의 서명된 v0.2.10 feed(sequence 120)로 Engine을 설치하고,
signature·파일 hash와 짧은 기동 probe를 통과한 뒤 활성화했습니다.
Python Control/server는 공식 source checkout을 사용하므로 별도 Control 설치본으로 전환하지 않았습니다.
Source의 자체 수정·설치 산출물·bytecode는 없습니다.
기존 venv 안의 dependency만 갱신했고, 주요 변경은 `certifi==2026.10.19`와 `truststore==0.10.5`입니다.
시스템 Python, CUDA Toolkit, PATH와 driver는 변경하지 않았습니다.

## 기준 실행 설정

| 항목 | 값 |
| --- | --- |
| Profile / Model ID | `sc117-iq3-xxs` / `sc117-qwen3.8-flash-next-abliterated-iq3_xxs` |
| Weights / Pack | 기존 SC117 IQ3_XXS와 `C:/Strata-data/packs/sc117_iq3_xxs` 재사용 |
| Context | **262,144 tokens**, Prompt와 생성 token의 합계 기준 |
| KV | `int8`, GPU resident `32768` |
| Drafting | **MTP**, `--spec 4`, `--spec-min-p 0.5`; `drafting: mtp` 명시 |
| VRAM reserve | `8192 MiB` |
| Expert cache / prefill | `auto` / `auto` |
| Parallel | `1` |
| Vision | 새 Engine package의 reader, CPU 8 threads, 최대 image tokens 300 |
| Production thinking | 기존 shared `reasoning_effort: medium` 유지 |
| 반복 중단 | `reasoning_loop_recovery: stop`, `repeat_stop_tokens: 256` 유지 |

기동 로그에서 CPU pool 7 workers, MTP layer 837 MiB, draft head 178.4 MiB,
GPU expert cache 343 slots / 0.57 GiB, host KV 3.09 GiB를 확인했습니다.
Conversation cache는 당시 여유 RAM에 따라 4,864 MiB로 자동 설정됐습니다.
PCIe share는 0.55에서 0.50으로 자동 조정됐고, route tail skip 기본값 7은 유지했습니다.
이러한 자동 동작과 CPU/GPU 연산 차이 때문에 seed·temperature를 고정해도 답변의 완전한 동일성을 보장하지 않습니다.

이번에는 Context와 버전 변경 외의 성능 최적화 조합을 탐색하지 않았습니다.
DFlash2로 바꾸거나 기존 Pack을 재생성하지 않았습니다.

## 측정 방법

- 생성 API는 `POST /v1/chat/completions`를 사용했습니다. 주 측정은 SSE이고, 공개 NaN 재현 검사는 일반 JSON 응답도 확인했습니다.
- 일반 속도·검색 검사는 `temperature=0`, `top_p=0.95`, `top_k=20`, `min_p=0`,
  `frequency_penalty=0`, `presence_penalty=0`, `repeat_penalty=1`, `seed=20261103`, thinking off입니다.
- `reasoning-medium`은 별도 검사로 thinking budget 256, 최대 생성 512를 사용했습니다.
  최소 공개 재현 요청은 Sampling·thinking을 생략해 서버의 기존 기본값도 확인했습니다.
- 긴 문서는 고정 seed로 만든 서로 다른 record이며 약 5%·50%·95% 위치의 세 key/value를 검색합니다.
  생성 전 token-count API로 길이를 맞추고, 표의 최종 token 수는 실제 생성 API의 `usage`입니다.
- 긴 입력 4건은 모두 `cached_tokens=0`입니다. 각 입력 길이는 한 번씩 측정했습니다.
- GPU·RAM은 약 2초 간격으로 sampling했습니다. API timing과 외부 wall time을 별도로 보존했습니다.
- OS page cache나 Engine의 적응 상태를 초기화하지 않았고, 다른 앱을 종료하거나 ComfyUI 모델을 unload하지 않았습니다.
  확인 시점의 ComfyUI 실행·대기 queue는 모두 0이었습니다.

## 속도와 정확성

### 짧은 입력

| 검사 | Prompt / 생성 tokens | 첫 token | 전체 시간 | Engine decode |
| --- | --- | --- | --- | --- |
| 검산·JSON 출력 | 40 / 23 | 0.561 s | 0.810 s | 87.2 tokens/s |
| 한국어 지침 생성 1 | 63 / 512 | 0.648 s | 6.546 s | 86.6 tokens/s |
| 같은 Prompt 생성 2 | 63 / 512 | 0.264 s | 5.909 s | 90.5 tokens/s |
| 같은 Prompt 생성 3 | 63 / 431 | 0.300 s | 4.976 s | 91.9 tokens/s |

검산 결과 `17*23+19=410`과 지정 label을 확인했습니다.
한국어 생성 3회의 decode 중앙값은 **90.5 tokens/s**입니다.
두 번째·세 번째 요청은 Prompt 56 tokens를 재사용했습니다.
첫 두 출력은 시험용 512-token 제한에 도달했고, 세 번째는 자연 종료했습니다.
따라서 이 3건의 pass는 API 생성·계측 성공을 뜻하며, 모든 지침이 완결됐다는 품질 판정은 아닙니다.
후속 비교에서는 생성 token 수·cache 재사용·종료 사유를 함께 비교해야 합니다.

### 긴 입력: cache 없는 첫 처리

| 실제 Prompt tokens | 첫 token | 전체 시간 | Engine prefill | Engine decode | 검색 정답 |
| --- | --- | --- | --- | --- | --- |
| 8,171 | 6.705 s | 7.197 s | 1,255.2 tokens/s | 72.6 tokens/s | 3/3 |
| 32,768 | 26.585 s | 26.940 s | 1,242.1 tokens/s | 92.7 tokens/s | 3/3 |
| 131,051 | 112.179 s | 112.554 s | 1,170.5 tokens/s | 90.1 tokens/s | 3/3 |
| 259,997 | 235.123 s | 235.497 s | 1,107.4 tokens/s | 84.3 tokens/s | 3/3 |

모든 길이에서 입력의 앞·중간·뒤에 있는 값이 일치했습니다.
긴 입력 세 건의 생성 속도는 약 84~93 tokens/s였지만, 긴 입력의 첫 처리에는 수분이 걸립니다.
이는 synthetic 검색 task의 결과이며 262K 전역의 추론·요약 품질을 보장하는 시험은 아닙니다.

### 긴 대화의 후속 요청과 복원

| 검사 | Prompt tokens | 재사용 tokens | 첫 token | 전체 시간 | 결과 |
| --- | --- | --- | --- | --- | --- |
| 260K 대화의 새 후속 질문 | 260,067 | 260,032 | 0.685 s | 0.832 s | 정답 |
| 다른 대화 후 긴 대화 복원 | 260,067 | 260,060 | 0.535 s | 0.688 s | 정답 |

후속 질문은 이전 assistant 답변에 없던 문서 중간 record의 `zone` 값을 물었습니다.
그 사이 1,434-token의 별도 대화를 넣은 뒤에도 원래 대화의 정답이 유지됐습니다.
별도의 짧은 A→B→A 검사에서도 A와 B의 비밀값이 섞이지 않았습니다.

## 리소스

| 지표 | 주 측정·회귀 검사에서 관측한 값 |
| --- | --- |
| 전체 GPU 사용량 최대 | **10,001 MiB ≈ 9.77 GiB** |
| 전체 GPU 여유량 최소 | 약 **5,977 MiB** |
| Strata 관련 프로세스 Working Set 합계 최대 | **52.85 GiB** |
| 시스템 available RAM 최소 | **9.69 GiB** |
| 관리 경로 첫 재기동 | 약 **30.9 s**, ready / generation_ready 확인 |

GPU 수치는 다른 앱을 포함한 전체 GPU 값입니다. Working Set 합계는 공유 page를 중복 계산할 수 있으며,
Strata의 독점 RAM 사용량이나 commit 사용량과 같지 않습니다. 짧은 순간의 peak는 sampling 사이에서 누락될 수 있습니다.

`--vram-reserve-mib 8192`가 실제 Engine 인자로 전달되고 cache 크기 계산에 사용되는 것은 확인했습니다.
그러나 위 측정에서 GPU 여유량은 8 GiB보다 작았습니다. 이 옵션은 다른 앱에 8 GiB를 항상 남기는 hard limit이 아닙니다.
향후 튜닝에서는 생성 속도와 함께 실제 GPU 여유량·RAM peak를 비교해야 합니다.

## 앞서 조사한 이슈의 재현 여부

| 이슈 | 이번 확인 | 해석과 범위 |
| --- | --- | --- |
| [#5055: RTX 5080 non-finite logits](https://github.com/Niko1221/Strata/issues/5055) | **미재현** | `Hello local AI`, 긴 생성, 8K~260K 및 재기동 후 검사에서 NaN/503 없음. 보고 환경의 driver 617.42·공식 weights와 이번 driver 610.88·SC117은 다릅니다. |
| [#3465: percent-encoded URL Prompt NaN](https://github.com/Niko1221/Strata/issues/3465) | **미재현** | 공개 JSON의 messages를 사용해 SSE·일반 JSON과 thinking off·기존 기본값을 검사했습니다. 새 Engine의 cache 없는 요청도 별도 확인했습니다. |
| [#4891: 삭제된 옛 Vision 경로의 doctor 판정](https://github.com/Niko1221/Strata/issues/4891) | **격리 fixture에서 재현** | 옛 reader가 없는 설정을 doctor는 missing으로 판정하지만 runtime은 새 package reader로 보정합니다. 실제 옛 Engine은 삭제하지 않았고, 실제 설정은 새 reader 경로로 갱신했습니다. |
| [#5059: Desktop의 RAM budget 누락·기동 timeout](https://github.com/Niko1221/Strata/issues/5059) | **Desktop 재현 대상 아님** | 현재 custom runner의 262K 기동과 관리 경로 재기동은 성공했습니다. Desktop App을 실행하거나 해당 RAM 제한 조건을 만들지는 않았습니다. |
| [#4892: 설치된 NVFP4의 잘못된 디스크 공간 검사](https://github.com/Niko1221/Strata/issues/4892) | **미검사** | NVFP4 Pack을 설치·변환하지 않았고 Desktop의 Download and prepare 경로도 사용하지 않았습니다. |
| [#4826: 성능 저하 보고](https://github.com/Niko1221/Strata/issues/4826) | **구버전 대비 판정 없음** | 보고자가 warm cache 조건 차이로 철회한 건입니다. 이번 최신 버전 수치를 보존했으며 동일 suite의 구버전 측정은 없습니다. |
| [#4996: Blackwell 2-GPU NVFP4 버전별 속도](https://github.com/Niko1221/Strata/issues/4996) | **현재 구성에 해당 없음** | 단일 GPU·IQ3_XXS이며 해당 2-GPU NVFP4 조건을 재현하지 않았습니다. |

추가 회귀 검사에서는 다음을 확인했습니다.

- 긴 대화 복원과 A→B→A 격리: 정답 유지, 잘못된 대화 재사용 없음.
- 정상 Tool call: `lookup_code`와 지정 argument가 실제 `tool_calls`로 반환됨. Tool 자체는 실행하지 않음.
- 코드 fence 속 `<tool_call>` 예시: Tools 미선언·선언 양쪽 모두 literal로 반환되며 실제 호출로 변환되지 않음.
- SSE `[DONE]` 직후 client 종료와 다음 요청: 정상 응답, 해당 검사 구간에 잘못된 cancellation 기록 없음.
- CPU Vision: 새 reader로 빨간 224×224 PNG를 `Red`로 식별, 전체 약 1.14 s. OCR·grounding 품질 검사는 아님.
- Context 초과: 420,012-token Prompt를 HTTP 400으로 거부하며 조용히 잘라내지 않음.
- 미실행 model ID: 생성 전에 HTTP 400으로 거부.
- Thinking medium 검산: 최종 정답 410 확인.
- 기동 및 전체 API 검사 로그에서 non-finite logits, DONE nonfinite, CUDA error, OOM, 잘못된 Request cancelled를 찾지 못함.
  OOM을 일부러 유발하는 checkpoint 실패 시험은 하지 않았으므로 그 오류 경로의 해결 여부는 판정하지 않음.

공개 최소 재현 요청의 `max_tokens: 8` 또는 `64`는 기본 thinking에 모두 소모되어 본문 없이 `length`로 끝날 수 있습니다.
해당 검사는 HTTP 503·non-finite 발생 여부를 판정하며 답변 완결성 평가로 집계하지 않습니다.

## 결과 파일과 재실행

- [측정 JSON](benchmarks/2026-11-03-engine-0.1.56-context-262144.json): 개별 결과, API usage/timing, 응답·정답, 리소스 요약, 버전과 검증 정보.
- [API 측정 harness](../../scripts/Strata/measure_api_baseline.py): 기존 서비스를 대상으로 순차 측정하며 lifecycle은 변경하지 않음.
- 당시 로컬 원본은 `runtime/Strata/benchmarks/2026-11-03-engine-0.1.56-context-262144/`였으며 완료 후 중복 산출물을 정리했습니다.
  Synthetic 요청과 정답 fixture는 Git archive에 보존했고, 설정 백업은
  `runtime/Strata/rollback/2026-11-03-test-configurations/after-upgrade/`로 옮겨 SHA-256 일치를 확인했습니다.
  현재 재사용 도구·입력·복구 파일은 [테스트 안내](BENCHMARKS.md)를 따릅니다. 비밀값이 있는 백업은 Git에서 제외합니다.

기본 suite 재실행 예시는 다음과 같습니다. 기존 출력 폴더에는 쓰지 않습니다.

```powershell
.\.venv\Strata\Scripts\strata-runtime-python.exe -X utf8 -I -B scripts/Strata/measure_api_baseline.py `
  --suite all `
  --target-lengths 8192 32768 131072 260000 `
  --short-repeats 3 `
  --output-directory runtime/Strata/benchmarks/next-measurement
```

이번 주 측정과 긴 후속·복원 검사는 `core/`, `regressions/`로 나누어 실행했습니다.
최종 harness는 이 요청들을 하나의 suite로 재실행할 수 있게 정리했습니다.
재기동 직후의 추가 검사는 별도 `restart-smoke/`, `cold-nonstream-reproductions/`에 기록합니다.
API 요청 전체의 성공 여부는 JSON의 개별 `passed`와 `api_expectations_passed`를 기준으로 봅니다.

기존 request policy unit test 5개, Management Server profile test 7개와 `pip check`도 통과했습니다.
관리 화면은 실제 instance를 소유한 `ready` 상태이며, 인증한 LibreChat `/api/config`에서도
QFN의 `maxContextTokens: 262144`를 확인했습니다. PolyStrata 두 profile의 153,600은 유지했습니다.

이전 환경 복구는 [복구 기준](ROLLBACK_BASELINE_2026-11-03.md)을 따릅니다.
이번에 바꾼 LibreChat local YAML의 원본은
`runtime/Strata/rollback/2026-11-03-test-configurations/librechat-before-context-change.local.yaml`에 보관합니다.
이 파일은 Git에 넣지 않습니다.
