# Basalt 운영 환경

공식 Windows `v0.5.7` Engine과 전용 Python/CUDA 환경을 향후 모델 테스트용으로 보존합니다.
현재 등록된 model profile과 LibreChat 연결은 없으며 Engine은 종료 상태입니다.

## 보존한 구성

| 항목 | 위치 |
|---|---|
| 공식 Engine | `data/Basalt/components/engine/v0.5.7/` |
| Release와 공식 archive hash | `config/Basalt/engine-release.json` |
| 전용 Python·CUDA DLL | `.venv/Basalt/` |
| Dependency 목록 | `requirements/Basalt/runtime.txt` |
| Engine 설치 도구 | `scripts/Basalt/prepare-environment.ps1` |
| 공통 실행 wrapper | `scripts/Basalt/serve_profile.py` |
| 관리 adapter | `management_server/basalt.py` |
| Profile 제어 | `run-basalt.ps1` |

공식 source·전역 CUDA·driver·전역 PATH는 변경하지 않습니다.
CUDA DLL과 temporary 경로는 Basalt process에만 적용합니다.

## 상태와 향후 준비

```powershell
.\run-basalt.ps1 status
```

등록된 Basalt profile이 없으면 `installed: true`, `state: stopped`, `profiles: []`로 표시합니다.
모델 없이 start를 요청하면 기동하지 않고 등록이 필요하다는 메시지를 반환합니다.

Engine을 다시 준비할 경우 다음 명령을 사용합니다. 모델 다운로드·등록·기동은 수행하지 않습니다.

```powershell
.\scripts\Basalt\prepare-environment.ps1
```

향후 모델을 선택하면 파일·hash 검증 receipt·`config/Basalt/` local 설정·관리 catalog를 새로 준비합니다.
설정을 처리할 때는 `-ConfigurationPath`를 명시합니다. 여러 Basalt profile을 등록한 경우
`run-basalt.ps1 start -ProfileIdentifier <등록한 profile>`로 대상을 지정합니다.
공통 API `0.0.0.0:8488`과 기존 API key를 사용하며, LibreChat model 등록은 별도로 진행합니다.
