# Strata 업데이트·IQ3_XXS 최적화 전 복구 기준

기록일: 2026-11-03, Asia/Seoul. 로컬 snapshot 생성 시각: 17:25:07.

사용자가 요청한 버전 변경 테스트와 IQ3_XXS 최적화에 앞서 기존 실행 환경을 보존한 기록입니다.
이번 작업은 백업·문서화·Git 복구 지점 생성까지만 수행합니다. Source pull, Engine 업데이트,
dependency 설치, 서비스 start/stop과 추론 테스트는 수행하지 않습니다.

## 복구할 버전

| 대상 | 기준 |
| --- | --- |
| 바깥 repo의 백업 전 branch | `feature/qfn-q2-profile` |
| 바깥 repo의 백업 전 commit | `9bd557dae8958ac15510d63ad2af7eb57b0806e4` |
| 바깥 repo의 문서 포함 복구 tag | `rollback/2026-11-03-iq3-xxs-baseline` — 이 문서의 백업 commit을 가리킵니다. |
| 후속 작업 branch | `experiment/strata-upgrade-iq3-xxs` |
| 공식 source | `external_repo/Strata`, branch `main`, tag `v0.2.1.1` |
| 공식 source commit | `9ae93f7b1fe989d04a8e404d32cddaeeff10505f` |
| 공식 source 복구 tag | `rollback/2026-11-03-iq3-xxs-baseline` |
| Engine package | `0.1.45.3-windows-x86_64-cuda-cuda13` |
| Engine build | `f6d65cb584c0`, CUDA `13.0` |
| Engine 원래 위치 | `C:/Strata-data/components/engine/0.1.45.3-windows-x86_64-cuda-cuda13` |
| Python 환경 | `.venv/Strata`, Python `3.13.15` |
| Python base | `C:/Users/azzib/AppData/Local/Programs/Python/Python313` |
| CUDA wheels | `nvidia-cublas==13.0.2.14`, `nvidia-cuda-runtime==13.0.96` |

공식 source는 snapshot 준비 시 tracked/untracked 변경이 없는 상태였습니다.
바깥 repo의 `.codex-remote-attachments/`와 `scinario_samples.md`는 사용자 파일로 그대로 두며
백업 commit이나 복구 대상에 포함하지 않습니다. PolyStrata와 LibreChat은 이번 변경 대상이 아닙니다.

## 실행 설정 기준

| 항목 | 값 |
| --- | --- |
| Profile | `sc117-iq3-xxs` |
| Model ID | `sc117-qwen3.8-flash-next-abliterated-iq3_xxs` |
| 실행 설정 | `config/Strata/strata.local.json` |
| Engine 선택 | `component:strata-engine` |
| Pack | `C:/Strata-data/packs/sc117_iq3_xxs` |
| Model 디렉터리 | `C:/Strata-data/models/SC117/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-GGUF` |
| MTP | 위 Model 디렉터리의 `strata/rt` |
| Speculation | `--spec 4`, `--spec-min-p 0.5` |
| Context / KV | `153600`, `int8`, GPU resident `32768` |
| VRAM reserve | `8192 MiB` — 실제 VRAM 사용량의 hard limit은 아닙니다. |
| Expert cache / prefill | `auto` / `auto` |
| Parallel | `1` |
| Vision | CPU, `8` threads, 최대 image tokens `300` |
| Reasoning | shared settings의 `reasoning_effort: medium` |
| 반복 중단 정책 | `reasoning_loop_recovery: stop`, `repeat_stop_tokens: 256` |

실제 local 설정에는 API key가 있으므로 Git에 넣지 않습니다. 정확한 설정 전체는 아래 로컬 백업으로 보존합니다.
준비 시점에 TCP 8488 listener는 없었습니다. 이번에는 모델을 Load하여 실행 상태나 성능을 재검증하지 않았습니다.

## 로컬 백업

위치: `runtime/Strata/rollback/2026-11-03-before-upgrade-iq3-xxs/`

이 경로는 기존 `/runtime/` 규칙으로 Git에서 제외합니다. 총 크기는 약 1.62 GB이며,
로컬 백업에는 API key를 포함한 설정이 있으므로 공개하거나 Git에 추가하지 않습니다.

| 백업 항목 | 내용 |
| --- | --- |
| `configuration/` | `config/Strata/` 전체 70개 파일: local config, shared settings, saved profile 및 하위 설정 포함 |
| `python-environment/` | `.venv/Strata/` 전체 3,075개 파일, 실행용 Python과 CUDA DLL 포함 |
| `engine-package/` | 기존 Engine package 전체 7개 파일, manifest·signature·BUILD 기록·DLL 포함 |
| `requirements/` | 기존 `requirements/Strata/` |
| `python-packages.txt` | 기존 환경의 `pip freeze --all` 결과 |
| `python-version.txt` | Python 상세 버전과 base 경로 |
| `engine-update-state.json` | `C:/Strata-data/components/.updates/state.json` 원본 |
| `strata-source.bundle` | 공식 source의 복구 tag와 그 commit까지의 전체 Git history |
| `pack-metadata/` | 기존 Pack의 conversions, index, native expert 목록과 tokenizer |
| `backup-manifest.json` | 원래 경로, 버전, 복사 파일별 크기·SHA-256, Pack 파일 목록과 재사용 자산 경로 |

설정·Python 환경·Engine·requirements의 총 3,153개 복사 파일은 원본과 SHA-256 일치를 확인했습니다.
Source bundle은 `git bundle verify`를 통과했습니다.
Source bundle SHA-256: `9b6025309923cb0d46156d693c8672bafec8819afaa7a56f4fd99ae157094046`.

대용량 Model GGUF, Pack의 `dense.bin`, MTP 본체는 복제하지 않았습니다.
기존 파일은 유지하고, 후속 테스트에서 재변환·재패킹이 필요하면 별도 경로를 사용합니다.
이 파일들의 전체 hash 재계산이나 모델 품질·속도 측정은 이번 백업 검증에 포함하지 않았습니다.
Snapshot 이후 기존 백업 폴더에 새 테스트 결과를 추가하거나 파일을 덮어쓰지 않습니다.

## 되돌리는 순서

아래 절차는 복구가 필요할 때 실행하며, 이번 백업 작업에서 실행하지 않았습니다.

1. 실행 중인 Strata와 요청 상태를 확인하고 기존 관리 경로로 종료합니다. 최신 환경의 변경 사항은
   먼저 별도 commit 또는 백업으로 보존합니다. 사용자 파일을 지우는 `git clean`이나 강제 reset은 사용하지 않습니다.
2. 바깥 repo와 공식 source를 각각 복구 tag로 전환합니다. 두 저장소의 tag는 서로 독립적입니다.

   ```powershell
   git switch --detach rollback/2026-11-03-iq3-xxs-baseline
   git -C external_repo/Strata switch --detach rollback/2026-11-03-iq3-xxs-baseline
   ```

3. 현재 `config/Strata`와 `.venv/Strata`를 각각 같은 상위 폴더 안의 별도 보관 이름으로 바꾼 뒤,
   snapshot의 `configuration/`과 `python-environment/`를 원래 경로로 복사합니다.
   작업 전 원본·보관·복원 경로가 이 workspace 안인지 확인합니다. 기존 폴더 위에 파일만 겹쳐 복사하면
   새 버전의 잔여 dependency가 남을 수 있으므로 폴더 단위로 교체합니다.
   백업 위치의 venv를 직접 실행하지 않고 원래 `.venv/Strata` 경로에 복구합니다.
   Python base 설치 경로와 버전도 위 기준을 유지해야 합니다.
4. 기존 Engine 폴더가 그대로 있으면 보존된 SHA-256과 대조하여 재사용합니다. 없거나 변경됐으면
   해당 폴더를 별도 보관하고 snapshot의 `engine-package/`를 위 Engine 원래 위치로 복사합니다.
5. 새 Engine이 함께 설치돼 있으면 source를 되돌린 것만으로 구버전이 선택되지는 않습니다.
   `C:/Strata-data/components/.updates/state.json`의 `engine.active`와 `engine.pinned`를 모두
   `0.1.45.3-windows-x86_64-cuda-cuda13`으로 지정합니다. `engine.pinned`가 없으면 추가합니다.
   다른 component 및 update 이력은 보존하며, state 파일 자체가 없으면 백업 원본을 복사한 뒤 pin을 추가합니다.
   기준 source는 사용 가능한 pinned Engine을 최신 설치 버전보다 먼저 선택합니다.
6. `config/Strata/strata.local.json`의 CPU Vision executable도 기존 Engine 폴더를 가리키는지 확인합니다.
   Model·Pack·MTP와 공식 source의 expert profile이 기준 경로에 남아 있는지 확인합니다.
7. 복구 후 `run-strata.ps1 plan`으로 선택 Engine과 경로를 확인하고,
   서비스 기동·모델 Load·생성 검증은 당시 사용자가 요청한 범위에서 별도로 진행합니다.

여러 버전을 거친 뒤에는 공식 `components rollback`의 previous가 이 기준 버전을 뜻하지 않을 수 있습니다.
이 기록의 정확한 source commit, Engine 폴더와 snapshot을 복구 기준으로 사용합니다.
공식 source tag가 없어졌다면 `strata-source.bundle`에서 해당 tag를 fetch하여 복구할 수 있습니다.

## 후속 테스트의 경계

- 먼저 기존 IQ3_XXS·MTP·Context·reserve를 유지해 버전 변경 효과를 비교합니다.
- Engine과 Python Control/server source는 별도 구성 요소이므로 실제 선택 버전을 함께 기록합니다.
- 최적화 설정 변경과 버전 변경 결과는 구분해서 기록합니다.
- 이 백업은 테스트 준비 완료를 뜻하며, 업그레이드 성공이나 현재 설정의 최적성을 뜻하지 않습니다.
