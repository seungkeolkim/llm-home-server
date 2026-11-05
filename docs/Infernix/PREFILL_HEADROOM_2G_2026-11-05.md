# Infernix VRAM headroom 2 GiB · 128K Prefill 관측

사용자가 Comfy GPU 메모리를 수동 반환한 뒤 Infernix의 `--vram-headroom-mib`를
8192에서 2048로 바꾸고 재기동했습니다. 이전 Strata 최적화의 동일한 128K 입력이
HTTP 200으로 admission됐고 **131051 tokens를 약 46.86초, 2796.63 tok/s**로 처리했습니다.
첫 생성 delta를 받은 47.12초에 stream을 닫고, 48.15초에 running·waiting 0을 확인했습니다.

이전의 [KV admission 실패](PREFILL_OBSERVATION_2026-11-05.md)는 이 실행 조건에서 재현되지 않았습니다.
Comfy GPU 메모리 반환과 headroom 변경이 함께 이루어졌으므로 headroom만의 A/B 결과는 아닙니다.

## 적용 설정과 실행 상태

- 공식 `windows-2026.11.01`, Orcarouter NVFP4 / FP8 dense, Context 262144, concurrency 1.
- KV INT8, DFlash2 auto, Vision RAM offload, FP8 PLE volume, exclusive expert RAM layout.
- VRAM headroom 2048 MiB, RAM 여유 8192 MiB, Host context cache 2048 MiB.
- Local JSON·native TOML·template·관리 catalog 표시와 resource budget을 함께 변경했습니다.
  이전 local JSON은 `data/Infernix/backups/`에 백업했습니다.
- 기존 소유 instance만 종료하고 새 instance를 기동했습니다. ComfyUI·LibreChat은 변경하지 않았습니다.
  새 실행의 configuration revision과 관리 profile revision이 일치했습니다.

Startup 로그의 배분은 다음과 같습니다.

| 항목 | 2 GiB headroom 재기동 결과 |
|---|---:|
| VRAM expert cache | 2530 frames / 약 6.5 GiB |
| KV | 초기 0.16 GiB / Context에 따라 최대 3.28 GiB |
| Prefill chunk | 10624 tokens / Context 증가 시 5248까지 축소 |
| Expert RAM | 약 53.3 GiB / 초과 expert는 SSD tier |
| Host prefix cache | 2.0 GiB |
| 실제 GPU free, warmup 직후 | 약 1354 MiB |
| 실제 GPU free, 측정 종료 후 | 약 1452 MiB |

Headroom은 native 예산 설정이며 warmup·driver 등의 추가 할당 이후 실제 free VRAM을
정확히 2 GiB로 보장하는 hard limit이 아닙니다. 이전 8 GiB startup에서는 expert cache가
199 frames, Prefill chunk가 640 (Context 증가 시 512)이었습니다.

## 보존 입력과 진행률

[기존 archive](../../tests/Strata/fixtures/2026-11-03-api-inputs/requests.zip)의
`canonical_inputs[131072]`를 hash 검증 후 읽었습니다. Model ID만 Infernix로 바꾸고
원문·sampling·`reasoning_effort=none`·`max_tokens=256`·stream 옵션을 유지했습니다.
측정 제한은 120초이며, 그 전에 첫 생성 delta가 도착하면 바로 stream을 닫도록 했습니다.
Prefix cache에서 재사용한 입력은 0 tokens입니다. Engine은 이전 expert state를 복원했으므로
완전히 초기화된 expert cache에 대한 cold-start 측정은 아닙니다.

| 경과 | 처리된 입력 tokens | 단계 |
|---|---:|---|
| 15.04초 | 39040 | Prefill |
| 30.08초 | 78080 | Prefill |
| 45.11초 | 124928 | Prefill |
| 47.12초 | 131051 | 첫 생성 delta 수신 후 stream 종료 |
| 48.15초 | 131051 | Engine idle 확인 |

엔진이 정산한 Prefill 시간은 46.860초, 처리량은 2796.63 tok/s, TTFT는 47.119초였습니다.
5초 간격 throughput은 주로 3.12K tok/s였고 chunk 완료 시점에 따라 일부 구간은 1.56K tok/s였습니다.
시간 구간별 수치 대신 요청 전체 Prefill 시간·token 수로 계산한 정산 처리량을 대표값으로 사용합니다.

Native 종료 사유는 `cancelled`, 출력은 3 tokens였습니다. Transport의 HTTP 499는
의도한 client disconnect 기록이며, 완성된 답변이나 긴 Decode 성능·정답률을 측정하지 않았습니다.
샘플에서 관측한 최소 가용 system RAM은 약 4.66 GiB였습니다.

Startup에서 PLE volume의 읽기 속도 약 87332 reads/s 경고도 있었습니다.
따라서 SSD tier·PLE I/O·Prefill chunk의 제약은 남아 있지만, 이번 요청은 이전처럼 KV 부족으로
진입 자체가 거부되는 상태는 아니었습니다. 최대 262K·Vision·Comfy 재부하와의 동시 사용은
이번 측정 범위에 포함하지 않았습니다.

[공개 가능한 수치](measurements/2026-11-05-headroom-2g.json)와 원본 evidence
`runtime/Infernix/diagnostics/prefill-headroom-2g-20261105/`에 요청·전후 metrics·진행 샘플·요약을 보관합니다.
