# Qwen3.6 CPU Vision과 VRAM reserve 설정 초안

작성 기준: 2026-10-22. **Strata 기동·모델 Load·생성 요청·benchmark를 실행하지 않았습니다.**

> 이 문서는 PolyStrata 도입 전 Strata Qwen3.6용 **초기 검토 이력**입니다. 아래의 기동 금지·미준비 상태·32K 가정은 작성 당시의 조건입니다.
> 현재 Qwen3.6은 [PolyStrata 운영 안내](../PolyStrata/README.md)의 Unsloth·Hauhau profile로 지원하며 context 153,600, KV Q8_0, CPU Vision을 사용합니다.
> 아래 template과 정적 계산은 현재 실행 설정·실측으로 사용하지 않습니다. 사용자 요청에 따라 검토 이력으로 보존합니다.

## 사용자 운영 의도와 현재 상태

- Vision encoder는 CPU에서 실행하고 host RAM을 사용합니다.
- 기존 Flash-Next의 `--vram-reserve-mib 8192`와 비슷한 메모리 여유를 목표로 합니다.
- ComfyUI가 작업 중이므로 Strata와 모델을 기동하지 않습니다.
- Qwen3.6 모델과 tokenizer는 아직 준비되지 않았습니다. 작성한 파일은 별도 template이며 현재 설정·saved profile·관리 서버에 연결하지 않았습니다.
- Context 선택에 대한 사용자 답변이 없어 **32K를 초안의 가정**으로 사용합니다. 동시 요청은 1개입니다. 기존 163,840 context를 그대로 유지하는 설정이 아닙니다.

## 계산 기준

- GPU: NVIDIA GeForce RTX 5080, `nvidia-smi` 보고 용량 **16,303 MiB**.
- 목표 reserve: 8,192 MiB. 따라서 Strata용 가상 예산은 8,111 MiB입니다. 다른 프로그램의 사용량은 이 가상 예산에서 별도로 차감하지 않았습니다.
- Strata source: `9ae93f7b1fe989d04a8e404d32cddaeeff10505f`.
- 모델: `unsloth/Qwen3.6-35B-A3B-MTP-GGUF`, pinned revision `5bc3e238d916f48a861bac2f8a1990a0e9b7e98d`.
- 각 GGUF의 처음 16 MiB에 대한 HTTP Range 요청으로 metadata와 tensor 목록만 확인했습니다. 모델 전체를 다운로드하지 않았으며 payload의 SHA-256 검증도 수행하지 않았습니다.
- 32,768 context, prompt chunk 512, MTP 2, parallel 1, CPU Vision 300 image tokens / 8 threads입니다.
- Engine의 MMQ prompt path를 가정합니다. 실제 설치된 Engine의 지원 여부와 runtime 사용량은 검증하지 않았습니다.

참고 source:

- [`q36_engine.cu`](../../external_repo/Strata/src/qwen35/q36_engine.cu): dense 업로드, Engine buffers, session cache, expert stride alignment와 hybrid staging.
- [`gemm.cu`](../../external_repo/Strata/src/prefill/gemm.cu): 32 MiB workspace와 FP16 dequantization scratch.
- [`native_mmvq.cu`](../../external_repo/Strata/src/kernels/cuda/native_mmvq.cu): Q8 packed 복제본의 대상 shape와 환경변수.
- [`QWEN36.md`](../../external_repo/Strata/docs/QWEN36.md): 모델별 실행 기능과 제약.

## 계산 방법과 결과

세 quantization의 expert 외 GPU weights는 같습니다. F32로 확장하는 tensor와 router 추가 배열을 포함하면 약 **2.615 GiB**입니다. 기본 Q8 packed 복제본은 여기에 약 **1.782 GiB**를 더 사용합니다.

8 GiB 여유를 확보할 수 있도록 template에 `env.STRATA_Q8_PACKED = "0"`을 넣었습니다. 원본 quantized weights로 계산하며 packed decode 최적화가 해제되므로 decode 성능이 달라질 수 있습니다. Prompt chunk는 자동 크기 변동을 피하고 buffer 비용을 줄이기 위해 512로 고정했습니다. Auto보다 긴 prompt의 prefill이 느릴 수 있습니다.

계산한 공통 Engine buffers는 약 **2,410.68 MiB**입니다. 여기에는 session KV cache, recurrent state, attention scores, prompt activations, MMQ 및 GEMM scratch, hybrid CPU 결과의 GPU buffer, Vision position table 등이 포함됩니다. Driver·CUDA context·내부 임시 할당·정렬 오차 등 계산에 포함하지 못한 비용에 대해 **768 MiB의 추정 margin**을 별도로 뒀습니다. 이 margin은 실측값이 아닙니다.

`--expert-vram`은 resident experts만의 크기가 아닙니다. Hybrid MMQ에서는 최대 layer를 읽을 staging buffer 두 개를 이 예산에서 먼저 차감합니다. Quantization마다 최대 layer와 stride가 달라 아래와 같이 역산했습니다.

```text
resident experts에 남는 예산
  = GPU 전체 - 목표 reserve - dense weights - Engine buffers
    - runtime margin - staging buffer 두 개

layer당 resident expert 수
  = floor(남는 예산 / 모든 layer의 expert stride 합계)

--expert-vram
  = (staging buffer 두 개 + resident expert 수 × stride 합계)를 GiB로 변환
    후 소수 셋째 자리까지 올림
```

| Quantization | `--expert-vram` GiB | Staging GiB | 예상 layer당 GPU experts / 256 | Margin 포함 예상 VRAM GiB | 용량에서 계산상 남는 GiB |
|---|---:|---:|---:|---:|---:|
| UD-Q4_K_XL | 2.200 | 1.102 | 15 | 7.919 | 8.002 |
| UD-Q6_K_XL | 2.142 | 1.594 | 5 | 7.861 | 8.060 |
| Q8_0 | 2.105 | 1.594 | 4 | 7.823 | 8.097 |

단위는 GiB이며, 소수 표시는 반올림했습니다. 원본 byte별 계산은 [QWEN36_MEMORY_ESTIMATES.json](QWEN36_MEMORY_ESTIMATES.json)에 보관합니다.

**위 수치는 실측 여유 VRAM이나 Engine의 hard limit을 뜻하지 않습니다.** ComfyUI·desktop 등 다른 프로그램이 사용 중이면 시스템 전체 free VRAM은 더 작습니다. `--expert-vram`은 전체 프로세스 메모리 상한도 아닙니다. 현재 ComfyUI가 full load로 작업 중인 상태에서는 이 설정으로 Strata를 함께 켤 수 있다고 판단하지 않습니다.

이 예산에서는 대부분의 experts가 CPU에서 계산됩니다. Host expert arena만 Q4 약 18.745 GiB, Q6 약 28.034 GiB, Q8 약 32.672 GiB이며, GGUF mapping·CPU Vision·OS·ComfyUI 등은 별도입니다. GPU expert 수는 top-8 활성 expert 수와 의미가 다릅니다.

기존 163,840 context의 KV cache는 45,056 bytes/token × 163,840 = **6.875 GiB**입니다. 여기에 packed 복제본을 끈 dense weights만 더해도 약 9.490 GiB이므로 16 GB GPU에서 8 GiB 여유를 목표로 하는 현재 예산에 들어가지 않습니다.

## 작성한 template

`config/Strata/` 아래 다음 세 파일입니다.

- `qwen3.6-35b-a3b-ud-q4_k_xl-context-32768-reserve-8192-cpu-vision.local.json.template`
- `qwen3.6-35b-a3b-ud-q6_k_xl-context-32768-reserve-8192-cpu-vision.local.json.template`
- `qwen3.6-35b-a3b-q8_0-context-32768-reserve-8192-cpu-vision.local.json.template`

`vision.gpu: false`는 encoder를 CPU에서 실행한다는 뜻입니다. 이미지에서 얻은 embeddings는 text Engine의 GPU 연산에 들어가므로 이미지 입력 전체의 GPU 사용량이 0이 되는 것은 아닙니다. Qwen3.6 전용 `mmproj-F16.gguf`가 필요합니다.

모델·tokenizer 경로는 upstream Setup이 사용하는 `models/qwen36-<quantization>/`와 `packs/qwen36-<quantization 소문자>/tokenizer`를 예상한 것입니다. 실제 파일 준비 시 경로와 무결성을 확인해야 합니다. API key와 경로 placeholder도 아직 확장하지 않았습니다.

현재 `prepare-strata-environment.ps1`과 `run-strata.ps1`은 기존 SC117 모델 및 `strata.local.json`을 기준으로 동작합니다. 새 template을 복사하는 것만으로 Qwen3.6 준비·기동이 완료되지 않습니다. Runner의 모델별 검증과 profile 선택 연동은 별도 후속 범위입니다.

`lazy_load: true`와 `open_browser: false`를 설정했지만 lazy mode는 생성 요청이 오면 모델을 자동 Load합니다. ComfyUI 작업 중 사용자의 기동 금지 지시를 대신하는 차단 장치가 아닙니다.

## 후속 검증

현재는 JSON 구조, 옵션 조합과 계산의 일관성만 확인합니다. 실제 검증은 사용자가 Strata 실행을 허용하고 ComfyUI 작업이 끝난 뒤 진행해야 합니다. 그때 idle GPU 사용량, Engine 기동 후 사용량, 긴 prompt 및 이미지 요청의 peak를 확인해 `--expert-vram`을 보정합니다. Context·parallel·prefill 크기·packed 설정·Engine 버전이 바뀌면 재계산해야 합니다.
