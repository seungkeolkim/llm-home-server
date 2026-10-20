# Strata Home Server

Strata와 향후 추가할 채팅 서버, 하네스, 검색 서버의 실행 환경을 관리하는 repo입니다.
현재는 공식 Strata clone을 수정하지 않고 Windows / PowerShell에서 기동합니다.
현재 모델은 SC117 Qwen3.8-Flash-Next GSQ-RCO abliteration / IQ3_XXS이며,
모든 IPv4 interface의 **0.0.0.0:8488**에서 API와 Web UI를 제공합니다.
이 PC에서는 **http://127.0.0.1:8488**, 다른 기기에서는 **http://<서버의 LAN IP>:8488**로 접속합니다.

## 준비 및 실행

`external_repo/Strata`에 공식 source와 기존 `C:\Strata-data`의 Engine, 모델, Pack이 필요합니다.
기존 대용량 text model과 Pack은 재사용합니다. 이미지 입력용 mmproj만 준비 작업에서 별도로 다운로드합니다.

```powershell
.\prepare-strata-environment.ps1
.\run-strata.ps1 plan
.\run-strata.ps1 start
.\run-strata.ps1 status
.\run-strata.ps1 verify
.\run-strata.ps1 stop
```

`start`는 공식 managed runtime으로 서버를 백그라운드 실행합니다.
터미널이 닫혀도 계속 실행되며, `stop`으로 이 profile의 서버와 Engine을 종료합니다.
기동 확인은 최대 600초 기다립니다. `verify`는 실제 한 token generation도 수행합니다.
foreground 실행이 필요하면 `foreground`를 사용하고, 해당 터미널에서 Ctrl+C로 종료합니다.
같은 포트를 사용하는 다른 서버가 있다면 소유 관계를 확인하고 먼저 종료해야 합니다.

기본 Python은 `%LOCALAPPDATA%\Programs\Python\Python313\python.exe`입니다.
다른 Python 경로나 데이터 경로는 준비할 때 지정할 수 있습니다.

```powershell
.\prepare-strata-environment.ps1 -PythonExecutable 'C:\path\to\python.exe' -DataDirectory 'D:\Strata-data'
```

현재 검증 대상 Python은 3.13.15입니다. 준비 작업은 Strata 전용 `.venv/Strata`를 새로 만들고
공식 `requirements.txt` 및 검증한 CUDA 13 Python wheel을 설치합니다.
CUDA Toolkit이나 driver 설치, 사용자/시스템 PATH 변경은 수행하지 않습니다.
기동 시 필요한 환경변수도 자식 프로세스에만 전달합니다. Engine package에 원래 포함된 DLL도 사용합니다.

Windows venv의 기본 `python.exe`는 별도 process로 실제 Python을 실행하는 launcher입니다.
공식 managed runtime은 자신이 시작한 PID와 ready record의 PID가 같아야 하므로,
준비 스크립트는 기존 base Python executable과 core DLL의 복사본을 `.venv/Strata/Scripts` 안에 둡니다.
실행에는 `strata-runtime-python.exe`를 사용합니다. venv dependency와 Python isolation은 유지하며,
기존 Python 설치 및 기본 venv launcher는 수정하지 않습니다. 준비할 때 child PID 일치도 검사합니다.

## 폴더 및 설정

```text
Strata-home-server/
  prepare-strata-environment.ps1
  run-strata.ps1
  requirements/Strata/runtime.txt
  scripts/Strata/strata_runner.py
  docs/Strata/RESTORATION.md
  config/
    Strata/
      strata.template.json                # 추적하는 초기 설정
      shared-settings.template.json       # 최초 shared settings
      vision-projector.source.json        # mmproj revision, 크기, SHA-256
      strata.local.json                   # 생성된 실행 설정, Git 제외
      strata.local.shared-settings.json   # Web UI에서 저장하는 설정, Git 제외
      environment.local.json              # 기존 데이터 경로, Git 제외
      profiles/                           # 공식 saved profile, Git 제외
  .venv/Strata/                           # Strata Python과 CUDA runtime, Git 제외
  runtime/
    Strata/                               # Strata 실행 산출물, Git 제외
      working/                            # Engine 작업 폴더
      logs/strata-engine.log               # Engine 로그
      managed/sc117-iq3-xxs.server.log      # API server 로그
      managed/sc117-iq3-xxs.host.log        # managed runtime 로그
  external_repo/Strata/                    # 독립된 공식 clone, 전체 Git 제외
```

새 시스템은 같은 상위 폴더 아래에 해당 시스템 이름의 폴더를 추가합니다.
예를 들어 채팅 서버의 설정은 `config/<시스템 이름>/`, 실행 데이터는
`runtime/<시스템 이름>/`에 둡니다. Python을 사용한다면 `.venv/<시스템 이름>/`으로 분리합니다.
루트에는 repo 공통 문서와 시스템별 준비·실행 명령을 둡니다.

모델, Pack, MTP, Engine은 기존 데이터 폴더를 직접 사용합니다.
공식 Strata가 관리하는 소량의 process identity 기록은 `%LOCALAPPDATA%\Strata\procs`에도 저장됩니다.
`external_repo/Strata` 안에는 venv, 설정, 로그, bytecode를 만들지 않습니다.

준비 스크립트는 `.local.json`이 없을 때만 template에서 생성합니다.
이후의 로컬 수정 및 Web UI shared settings는 재실행해도 보존합니다.
실행 설정을 바꾸려면 `stop` 후 `config/Strata/strata.local.json`을 편집하고 `plan`, `start`로 확인합니다.
template 변경은 이미 생성한 로컬 설정에 자동 적용되지 않습니다.
repo를 옮기면 절대경로가 포함된 `.venv/Strata`, 로컬 설정, saved profile은 새 경로에서 다시 준비해야 합니다.

현재 기본값은 최대 context 163840, GPU resident KV 32768, KV int8,
VRAM reserve 8192 MiB (8 GiB), parallel 1, MTP spec 4입니다.
초기 shared reasoning effort는 기존 파일의 `medium`을 보존했습니다. 별도 출력 token limit은 추가하지 않았습니다.
VRAM reserve는 다른 프로그램의 사용 가능 VRAM을 항상 보장하지 않습니다.

## 네트워크 및 OpenAI-compatible API

OpenAI-compatible API는 서버 기동 시 같은 8488 포트의 `/v1`에서 기본 제공되며 별도 활성화 옵션은 없습니다.
채팅 서버나 하네스의 Base URL은 `http://<서버 주소>:8488/v1`,
모델 이름은 `sc117-qwen3.8-flash-next-abliterated-iq3_xxs`를 사용합니다.
모델 목록은 `GET /v1/models`, 채팅은 `POST /v1/chat/completions`입니다.

외부 interface에 bind할 때 Strata는 API key를 요구합니다.
준비 작업에서 key를 최초 생성해 Git에서 제외된 `config/Strata/strata.local.json`에 보존합니다.
사용자가 지정한 기존 key는 준비 작업이나 재기동 시 그대로 유지합니다.
실제 key를 template이나 문서에 넣지 않습니다. 로컬 PowerShell에서 다음과 같이 확인할 수 있습니다.

```powershell
(Get-Content .\config\Strata\strata.local.json -Raw | ConvertFrom-Json).api_key
```

OpenAI-compatible client에는 이 값을 API key로 입력합니다. HTTP 요청은
`Authorization: Bearer <API key>`를 사용합니다. Strata Web UI에서는 About > Settings에 key를 입력합니다.
인증하지 않은 `/v1` 요청은 401로 거부됩니다.
key를 바꾸려면 서버를 종료하고 local config의 `api_key`를 편집한 뒤 다시 기동합니다.
다른 기기에서 접근하려면 Windows Firewall에서도 TCP 8488의 inbound 연결이 허용되어 있어야 합니다.
`0.0.0.0`은 listen 주소이며 client의 접속 URL에는 서버의 실제 IP나 hostname을 사용합니다.

## 이미지 입력

현재 SC117 모델과 Pack을 유지하고, 호환되는 upstream BF16 mmproj를 추가하여 이미지 입력을 사용합니다.
OpenAI-compatible `/v1/chat/completions`의 `image_url` content part와 Strata Web UI의 이미지 첨부를 지원합니다.

16 GB GPU와 VRAM reserve 8 GiB 설정을 고려하여 image encoder는 CPU에서 실행합니다.
현재 CPU threads는 8, 이미지당 최대 token 수는 300입니다. 이미지 token 한도는 답변 출력 token 한도와 별개입니다.
세밀한 OCR이나 작은 글씨에 필요한 해상도를 높이려면 `vision.max_tokens`를 늘릴 수 있지만 CPU 처리 시간도 늘어납니다.

`prepare-strata-environment.ps1`은 vision을 사용하는 config에서 mmproj가 없으면
`config/Strata/vision-projector.source.json`의 pinned revision으로 다운로드하고 크기와 SHA-256을 검증합니다.
파일은 `C:\Strata-data\models\ISTA-DASLab\Qwen3.8-Flash-Next-GSQ-RCO-GGUF\`에 두며,
다운로드가 끊기면 다음 준비 작업에서 `.part` 파일을 이어받습니다. 기동 명령은 다운로드하지 않습니다.
이미 생성한 config에 vision을 처음 추가할 때는 template의 `vision` section과 `--vision` argument를
로컬 경로에 맞춰 적용해야 합니다. 기존 local config를 준비 스크립트가 덮어쓰지는 않습니다.

호환 근거는 [SC117 모델 설명](https://huggingface.co/SC117/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-GGUF)과
[Strata vision 문서](https://github.com/Niko1221/Strata/blob/main/docs/DETAILS.md#images-vision)입니다.

## 검증 및 업데이트

준비 작업은 `pip check`, 필수 module import, venv CUDA DLL 존재,
기존 download manifest의 모델 파일 크기, Pack/tokenizer 존재,
Engine 전체 hash 및 signature, mmproj hash 및 실행 plan을 확인합니다.
서버 기동 시에는 공식 runtime이 Engine을 다시 검증합니다.
`verify`와 `/health`, `/v1/models`로 기동 후 상태를 확인할 수 있습니다.

공식 source를 업데이트할 때는 서버를 먼저 종료하고, 해당 clone에서 업데이트한 뒤
준비 스크립트와 기동 검증을 다시 실행합니다. source 업데이트가 Engine 업데이트를 뜻하지는 않습니다.
실행이나 준비 작업에서 Engine updater를 자동 호출하지 않습니다.
현재 조합과 실측 검증 결과는 [Strata 검증 기록](docs/Strata/RESTORATION.md)에 기록합니다.
