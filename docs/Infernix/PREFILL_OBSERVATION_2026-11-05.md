# Infernix 긴 입력 Prefill 진입 실패 관측 — 2026-11-05

현재 상태에서는 긴 입력이 Prefill을 느리게 진행하는 대신, **KV 자원 부족으로 HTTP 503을 즉시 반환**했습니다.
128K와 8K 모두 처리된 Prefill tokens가 0이어서 Prefill 처리량이나 TTFT의 비교 수치는 산출할 수 없습니다.
이는 Infernix NVFP4 자체의 처리량 benchmark 결과가 아니라 현재 동시 실행·메모리 설정의 admission 실패입니다.

## 입력과 관측 한계

- 이전 Strata 최적화의 [동일 archive](../../tests/Strata/fixtures/2026-11-03-api-inputs/requests.zip)와
  [Manifest](../../tests/Strata/fixtures/2026-11-03-api-inputs/manifest.json)를 loader로 읽고 hash를 검증했습니다.
- `canonical_inputs[131072]` 요청을 먼저 사용하고 `8192` 요청으로 재현 범위를 확인했습니다.
  원본 messages와 sampling·stream 옵션은 유지하고 model ID만 Infernix로 변경했습니다.
- 과거 요청의 `reasoning_effort=none`, `max_tokens=256`도 유지했습니다. Thinking 표시 유무를
  판단한 검사가 아니라, Engine의 Prefill 진행량과 admission 오류를 직접 관측한 검사입니다.
- 긴 요청은 최대 120초 관측 후 stream을 닫도록 구성했습니다. 실제로는 서버가 즉시 거부하여
  취소 deadline 전에 연결이 종료됐고, 두 요청 이후 running·waiting 모두 0임을 확인했습니다.
- Infernix·ComfyUI 재기동, 모델 unload, Context·headroom·cache 설정 변경은 수행하지 않았습니다.

| 입력 | 과거 Strata 입력 tokens | HTTP | 응답 headers 도착 | 처리된 Prefill tokens | Engine 오류 |
|---|---:|---:|---:|---:|---|
| 128K | 131051 | 503 | 20.05 ms | 0 | first unit에 main KV 1984 pages 추가 필요 |
| 8K | 8171 | 503 | 2.34 ms | 0 | first unit에 main KV 64 pages 추가 필요 |

입력 token 수는 과거 Strata fixture의 값이며, 이번 Infernix에서 성공적으로 처리한 token 수가 아닙니다.
원본 128K request archive entry는
`sha256/db5c3d5b216db2884e2583911e7a1b5a01cf9870592a58591f1e7f1f450f40b6.json`입니다.

대표 응답은 다음과 같습니다.

```text
the Engine cannot admit this request: its first unit needs state=0, main_kv=1984,
backend_kv=0 more than an idle Engine has
```

## 당시 실행 상태와 해석

- Engine은 기존 `windows-2026.11.01`, Orcarouter NVFP4, Context 262144, INT8 KV,
  concurrency 1, DFlash2, Vision RAM offload, VRAM headroom 8192 MiB였습니다.
- Native `/health`는 HTTP 200이었으며 관리 서버도 `ready`로 표시했습니다.
  이는 특정 길이의 요청이 실제로 admission 가능한지까지 보장하지는 않았습니다.
- Prometheus gauge는 Device KV 사용 0 pages / virtual capacity 4097 pages,
  Host context cache 사용 961658880 bytes / capacity 2146959360 bytes,
  VRAM expert cache 0 frames였습니다. Virtual capacity를 즉시 확보 가능한 물리 자원으로
  해석하면 안 됩니다. 두 요청의 첫 작업 자체가 자원 검사에서 거부됐습니다.
- 측정 직전 GPU 사용은 13261 MiB, 여유는 2717 MiB, 가용 system RAM은 약 6.35 GiB였습니다.
  ComfyUI queue는 비어 있었으며 ComfyUI의 resident 모델·cache는 변경하지 않았습니다.
- Startup에서 Prefill chunk 16384가 workspace 7614 MiB를 요구하지만 expert cache가
  395 MiB만 빌려줄 수 있어 chunk를 640, KV 증가 시 512까지 줄인다는 경고도 있었습니다.
  실제 진입 뒤의 Prefill이 느릴 가능성은 있으나, 이번 실패로 그 속도를 측정한 것은 아닙니다.
- 기존 로그에는 사용자의 긴 대기 시간대에 503이 반복된 기록과, 별도 요청이 Decode 중
  main KV 1 page 부족으로 HTTP 500에 종료된 기록도 있었습니다.
  LibreChat 재시도가 대기 시간을 늘렸는지는 이번 관측만으로 확정하지 않습니다.

공식 [VRAM 설명](https://github.com/Wallawalla47/Infernix/blob/main/docs/qwen3_8-flash-next.md#vram)은
긴 요청이 추가 KV 공간을 expert cache에서 가져오는 구조를 설명합니다.
로컬 source `src/runtime/engine/engine_core.h`의 admission 경로도 idle 상태에서 해소할 수 없는
자원 부족을 `Unavailable`로 반환합니다. 현재 Expert cache가 0인 상황과 일치합니다.
실제 Prefill 처리량을 측정하려면 먼저 이 물리 KV 자원 조건을 해결해야 합니다.

원본 요청·sampling·stream 결과·전후 metrics·요약은 Git에서 제외한
`runtime/Infernix/diagnostics/prefill-20261105/`에 보관합니다.
