# 기동 복원 검증 기록

검증일: 2026-10-21, Windows / PowerShell, Asia/Seoul.

## 동작을 확인한 조합

| 항목 | 값 |
| --- | --- |
| 공식 source | `Niko1221/Strata`, commit `9ae93f7b1fe989d04a8e404d32cddaeeff10505f` |
| Engine package | 기존 `0.1.45.3-windows-x86_64-cuda-cuda13` |
| Engine build | `f6d65cb584c0+cuda13.0`, version 출력은 `0.1.45` |
| Python | 3.13.15, `.venv/Strata`, `include-system-site-packages = false` |
| CUDA Python wheels | `nvidia-cublas==13.0.2.14`, `nvidia-cuda-runtime==13.0.96` |
| GPU / driver | RTX 5080 16 GB / 610.88 |
| 데이터 | 기존 `C:\Strata-data`의 Engine, GGUF, Pack, MTP 재사용 |
| API / Web UI | `http://127.0.0.1:8488` |
| Profile | `sc117-iq3-xxs` |
| 모델 | `sc117-qwen3.8-flash-next-abliterated-iq3_xxs` |

공식 source의 commit은 변경하지 않았고 Engine도 업데이트하지 않았습니다.
이 source와 기존 Engine의 조합은 아래 smoke 범위에서 동작했습니다.

## 보존한 설정

- 최대 context `163840`, GPU resident KV `32768`, KV `int8`, parallel `1`.
- VRAM reserve `7168 MiB`, expert cache / prefill `auto`.
- MTP `--spec 4`, `--spec-min-p 0.5`, vision off.
- 최신 기존 shared settings의 `reasoning_effort: medium`.
- 기존 shared settings에는 `max_tokens`가 없었으므로 migration 문서에 적힌 `8000`은 추가하지 않았습니다.

현재 Engine의 cwd는 바깥 `runtime/Strata/working`, 로그는 바깥 `runtime/Strata`를 사용합니다.
expert profile은 현재 공식 clone의 `data/expert-profile.bin`을 읽습니다.

## 확인한 항목

- `pip check`, 필수 Python module import, venv CUDA DLL 존재.
- 기존 download manifest의 9개 파일에 대해 존재 및 크기 일치. 약 78 GB의 전체 hash는 재계산하지 않았습니다.
- Pack과 tokenizer 존재.
- 공식 CLI `components engine --full` 통과: Engine package의 모든 파일 hash와 signature 검증, `usable: true`.
- Python / PowerShell 문법 확인.
- 준비 스크립트를 반복 실행해도 local config와 shared settings의 hash가 유지됨.
- 준비 스크립트가 호출자의 process 환경변수를 원래 상태로 복원함.
- 실행용 Python의 `Popen.pid`와 자식의 실제 PID 일치, venv prefix 및 dependency import 확인.
- managed runtime의 `state: ready`, `api_identity_verified`, `launch_attested`, `generation_ready` 확인.
- `/health`: `loaded: true`, context `163840`.
- `/v1/models`: 해당 모델이 `loaded`로 등록됨. Web UI: HTTP 200.
- `run-strata.ps1 verify`: `verified_now: true`.
- `reasoning_effort: medium`, `max_tokens: 256`의 짧은 요청에서 `READY` 답변과 `finish_reason: stop` 확인.
- `stop` 후 8488 listener와 소유 host/server/Engine process 종료 확인.
- 다시 `start`한 인스턴스에서도 verify와 같은 실제 응답 재확인. 최종 상태는 서버 실행 중.
- 공식 clone의 tracked/untracked 변경과 ignored 산출물 모두 없음.

현재 실행 로그는 Git에서 제외한 `runtime/Strata/`에 있습니다. 아래 초기 복원 과정의 임시 로그와 테스트 응답 파일은 새 실행 환경에서 사용하지 않습니다.
10K benchmark, 큰 context의 실제 입력, ComfyUI 동시 생성 부하는 이번에 검사하지 않았습니다.

## 복원 중 확인한 문제

첫 시도에서는 다른 앱이 약 4.4 GiB의 VRAM을 사용 중이었습니다.
Engine은 expert cache를 0으로 축소한 뒤 MTP verification에 필요한 expert tier가 없다는 이유로 종료했습니다.
사용자가 다른 앱의 메모리를 정리한 후 동일한 reserve `7168 MiB`로 기동에 성공했습니다.
다른 앱의 프로세스나 설정은 실행 스크립트에서 변경하지 않습니다.

Python 3.13 Windows venv의 기본 launcher를 사용하면 `Popen.pid`와 서버의 ready record PID가 달라
API가 응답해도 managed runtime은 계속 `starting`으로 남았습니다.
이를 해결하기 위해 실행용 Python과 필요한 Python core DLL 복사본을 만들었습니다.
현재 실행용 Python 경로는 `.venv/Strata/Scripts/strata-runtime-python.exe`입니다.
공식 source와 시스템 Python을 수정하지 않고 PID 일치 및 managed lifecycle 동작을 확인했습니다.

마지막 짧은 추론 후 `nvidia-smi`의 GPU 사용량은 `10056 MiB`, free는 `5922 MiB`였습니다.
reserve `7168 MiB`가 실제 7 GiB의 여유를 항상 보장하지 않는다는 점도 확인했습니다.
전체 RAM은 약 93.56 GiB, 서버 로드 후 한 측정 시점의 available RAM은 약 30.27 GiB였습니다.
이는 PC 전체의 순간 사용량이며 Strata 단독 사용량은 아닙니다.

Git commit/push는 수행하지 않았습니다.

## 후속 변경: VRAM reserve 8 GiB

2026-10-21 사용자 요청으로 local config와 template의 `--vram-reserve-mib`를
`7168`에서 `8192`로 변경하고 서버를 종료 후 다시 기동했습니다.
최대 context, KV, MTP 및 shared settings는 유지했습니다.

Engine 로그의 `8192 MiB reserved`, managed runtime의 `ready`,
`verify` 성공, `/health`의 `loaded: true`, 실제 `READY` 답변을 확인했습니다.
짧은 추론 후 GPU 사용량은 `8839 MiB`, free는 `7139 MiB`였습니다.
이는 순간 측정값이며 8 GiB의 실제 여유를 항상 보장한다는 뜻은 아닙니다.
서버는 변경한 설정으로 실행 중입니다.

## 후속 변경: 시스템별 폴더 분리

2026-10-21 여러 시스템을 같은 repo에서 관리하기 위해 Strata 전용 경로로 분리했습니다.

| 항목 | 현재 경로 |
| --- | --- |
| 실행 설정 및 shared settings | `config/Strata/` |
| saved profile | `config/Strata/profiles/` |
| Engine 작업 폴더 | `runtime/Strata/working/` |
| Engine 로그 | `runtime/Strata/logs/` |
| managed runtime 기록 및 API 로그 | `runtime/Strata/managed/` |
| Python 및 CUDA dependency | `.venv/Strata/` |
| 실행 helper | `scripts/Strata/strata_runner.py` |
| Python requirements | `requirements/Strata/runtime.txt` |
| 검증 문서 | `docs/Strata/RESTORATION.md` |

root의 `prepare-strata-environment.ps1`, `run-strata.ps1` 명령은 유지했습니다.
Windows venv는 이동해서 재사용하지 않고 새 경로에 다시 만들었습니다.
local config의 cwd, log, CUDA DLL 경로 및 saved profile의 source_config를 새 경로로 변경했습니다.
현재 reserve `8192 MiB`, context `163840`, shared reasoning effort `medium`을 보존했습니다.

확인한 결과:

- 새 경로에서 준비, Engine hash/signature 검증 및 기동 plan 통과.
- managed runtime `ready`, identity/attestation/generation 검증 및 `verify` 통과.
- `/health`: `loaded: true`, 최대 context `163840`.
- 한국어 첫 대화: `안녕하세요, 민수님! 반갑습니다.`
- 같은 대화에서 이름을 다시 질문한 답변: `민수`.
- 준비 작업 재실행 후 local config와 shared settings의 hash 유지.
- Python / PowerShell 문법과 Strata 전용 Python prefix 확인.
- 공식 source의 tracked/untracked 변경 및 ignored 산출물 없음.
- 두 차례 채팅 후 GPU 사용량 `8868 MiB`, free `7110 MiB`.

서버는 새 경로에서 실행 중입니다. 새 구조의 Python과 source 및 데이터는 서로 분리되어 있습니다.

### 정리 완료

2026-10-21 사용자가 이전 venv, profile operation 기록, runtime 로그와 임시 테스트 파일을
삭제한 뒤 대상 경로가 모두 없어졌는지 확인했습니다. 비어 있던
`runtime/Strata/migration/` 폴더도 제거했습니다.

현재 사용 중인 `runtime/Strata/managed/`, `runtime/Strata/logs/`,
`runtime/Strata/working/`, `.venv/Strata/`, `config/Strata/`는 보존했습니다.
정리 후 managed runtime은 `ready`, `/health`는 `loaded: true`였으며
공식 source의 변경이나 새 산출물도 없었습니다.

초기 commit 대상은 실행 스크립트, requirements, 설정 template과 문서입니다.
공식 clone, venv, local config, saved profile 및 runtime 데이터는 Git에서 제외합니다.

## 후속 변경: 이미지 입력 활성화

2026-10-21 기존 SC117 IQ3_XXS 모델, Pack 및 Engine을 유지하고 mmproj만 추가했습니다.
SC117 모델 작성자가 upstream projector 재사용을 명시하고 있습니다.

- 출처: `ISTA-DASLab/Qwen3.8-Flash-Next-GSQ-RCO-GGUF`.
- revision: `ed59f92082b1e93c0e96d60a8b11aab089b52f09`.
- 파일: `mmproj-Qwen3.8-Flash-Next-BF16.gguf`, `907543008` bytes.
- SHA-256: `b1a82259702816a5330d7bd7607cd9676b11780e79ff7348c21103ff3ce49bd0`.
- 저장 위치: `C:\Strata-data\models\ISTA-DASLab\Qwen3.8-Flash-Next-GSQ-RCO-GGUF\`.
- Encoder: 기존 signed Engine package의 `strata-vision.exe`, CPU 8 threads, 최대 300 image tokens.
- 기존 context `163840`, KV resident `32768`, reserve `8192 MiB`, reasoning effort `medium` 유지.

공식 source를 수정하거나 시스템 CUDA를 설치하지 않았습니다.
local config와 template에 `--vision` 및 vision section을 추가했습니다.
준비 스크립트는 projector의 크기와 hash를 검증하고 없으면 pinned 파일만 다운로드합니다.
Engine package 경로는 공식 component inventory로 resolve한 뒤 template에 반영합니다.
기동 과정에서는 다운로드하지 않습니다.

재기동 후 확인한 결과:

- `/health`: `images: true`, `loaded: true`.
- `/v1/models`: input modalities가 `text`, `image`.
- managed runtime `ready`, `verify` 및 generation 검증 통과.
- 흰 배경의 왼쪽 파란 직사각형과 오른쪽 빨간 원을 그린 PNG를 base64 image_url로 전송.
- 실제 답변: `Left: blue rectangle. Right: red circle.`, finish reason `stop`.
- 텍스트만 전송하는 요청에서도 `READY` 응답 확인.
- 기존 mmproj 재검증 및 준비 작업 반복 실행 후 local config/shared settings hash 유지.
- Python, PowerShell, JSON 문법 및 diff 검사 통과. 공식 clone 변경 및 산출물 없음.
- 마지막 GPU 측정: used `8750 MiB`, free `7228 MiB` (PC 전체 순간 사용량).

검증용 PNG와 응답 JSON은 Git에서 제외한 `runtime/Strata/diagnostics/vision-smoke*`에 있습니다.
작은 글씨의 OCR, 많은 이미지, 고해상도 문서 인식 품질은 별도로 측정하지 않았습니다.
종료·기동 소요 시간 측정 요청은 사용자 취소로 수행하지 않았습니다.

## 후속 변경: 외부 interface 및 OpenAI-compatible API

2026-10-21 bind 주소를 `127.0.0.1`에서 `0.0.0.0`으로 바꿨습니다.
현재 LAN 주소는 `192.168.0.8`이며 OpenAI-compatible Base URL은
`http://192.168.0.8:8488/v1`입니다. API는 별도 옵션 없이 기동 시 기본 제공됩니다.

현재 공식 CLI와 server는 non-loopback bind에 API key를 필수로 요구합니다.
사용자가 지정한 key를 Git에서 제외된 local config에 저장했으며 실제 값은 문서와 template에 넣지 않았습니다.
template의 key placeholder는 최초 준비 시 확장하고, 기존 local key는 유지합니다.
context, vision, VRAM reserve 등의 추론 설정은 변경하지 않았습니다.

재기동 후 확인한 결과:

- 실제 TCP listener가 `0.0.0.0:8488`.
- localhost와 이 PC의 LAN 주소 양쪽에서 health 및 Web UI HTTP 200.
- `/health`: loaded, images 및 API key 활성화 상태 확인.
- key를 포함한 `GET /v1/models`는 HTTP 200, key 없는 요청은 HTTP 401.
- LAN 주소의 `POST /v1/chat/completions`에서 실제 `READY` 응답 확인.
- managed runtime `ready`, identity/attestation/generation 및 `verify` 통과.
- 실제 key가 들어 있는 local config는 Git ignore 대상이고 공식 clone도 변경 없음.

LAN 주소 검증은 이 PC에서 수행했습니다. 다른 기기에서의 inbound 접속까지는 검증하지 않았습니다.
Windows Firewall 규칙 조회는 현재 process에 관리자 권한이 없어 Access denied였으며,
방화벽 규칙은 변경하지 않았습니다.
