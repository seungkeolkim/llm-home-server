# Paseo 외 원격 지원 정리

2026-11-14 사용자 요청으로 Paseo 외 원격 지원 설치를 정리했습니다. 영구 파일 삭제가 자동 승인 검사에서 거부되어 사용자가 허용한 **휴지통 이동**으로 수행했습니다. 휴지통은 비우지 않았습니다.

## 정리한 항목

- Remote Pi Relay container `llm-home-server-remote-pi-relay-1`, 전용 image `fdc9aa78918d…`, 전용 DB volume `llm-home-server-remote-pi_relay-data`를 제거했습니다.
- 사용하지 않는 staging 인증서 volume `llm-home-server-remote-pi-caddy-staging`을 제거했습니다. 연결된 container가 없음을 먼저 확인했습니다.
- Windows Credential의 Remote Pi 전용 `dev.remotepi.pi / longterm-ed25519`를 제거했습니다. 이전 service `dev.remotepi.mac`도 해당 credential이 없음을 확인했습니다. Paseo key·credential은 유지합니다.
- 아래 전용 파일·폴더 10개를 휴지통으로 이동했고 Recycle Bin의 원래 경로 10개와 대조했습니다.

```text
runtime/PiCodingAgent/agent/extensions/remote-pi.ts
config/RemotePi/remote-pi.local.json
config/RemotePi/remote-pi.local.json.template
requirements/RemotePi/
scripts/RemotePi/
data/RemotePi/
runtime/RemotePi/
data/PiCodingAgent/downloads/pi-remote-0.7.7-android-arm64.apk
scripts/PiCodingAgent/verify_android_apk.py
C:\Users\azzib\.pi\remote\
```

전용 npm dependency·조사 clone·APK·Pairing 파일도 위 폴더와 함께 이동했습니다. Pi Desktop 다운로드 manifest에서 이전 Android APK를 제외했고 설치 검증의 APK 호출도 제거하여 기본 준비 명령이 다시 설치하지 않도록 했습니다.

Remote Pi를 load했던 기존 Pi Desktop만 종료했습니다. 당시 실행 중인 모델 요청이 Paseo 소유임을 PID ancestry로 확인한 뒤 Desktop의 소유 process tree만 종료했으며 공통 gateway PID `17032`를 유지했습니다. Pi SDK·billion-context·Browser·기존 Session과 로컬 Pi Desktop 배포 파일은 Paseo 의존성 또는 기존 local 환경이므로 보존했습니다.

## 보존한 공유 구성

| 항목 | 유지 상태 |
|---|---|
| Paseo daemon·Desktop | PID·생성 시각 동일, 재시작 없음 |
| Paseo Relay | container ID·시작 시각 동일, healthy |
| Caddy | `llm-home-server-remote-pi-caddy-1`, ID·시작 시각·mount 동일, healthy |
| Docker network | 기존 internal·egress network 그대로 사용 |
| TLS | production 인증서·Caddy config volume·인증서 fingerprint 동일 |
| 외부 포트·Firewall | 38789 → 8789와 인증서용 443 유지, rule 변경 없음 |
| Pi 기반 구성 | 기존 gateway·CLI·Extension dependency·모델 설정 유지 |
| 보호 설정 | 기존 8개와 Paseo 8개, 합계 16개 Hash 동일 |

`config/RemotePi/compose.yaml`에는 Caddy만 남았습니다. 기존 `name`·network·volume·환경변수·bind mount 경로를 유지한 이유는 Paseo가 현재 사용 중이기 때문입니다. Remote Pi 전용 service·volume·depends_on은 제거했습니다. Caddy의 `/ws`·`/paseo-health`는 Paseo로 전달하고 이전 Remote Pi 경로는 404입니다.

공유 helper는 `scripts/Paseo/manage-proxy.ps1`, `enable-https-firewall.ps1`, `update-duckdns.ps1`에 있습니다. 기존 Firewall rule 이름은 유지하며 새 rule·Task·DDNS 갱신은 수행하지 않았습니다. 보호 Hash 기준은 `data/Paseo/backups/remote-support/protected-hashes.json`로 보존했습니다.

## 검증과 기록

- 공인 DDNS `https://azzi-home.duckdns.org:38789/paseo-health` HTTP 200, TLS 검증 유지.
- 이전 `/health` HTTP 404로 Remote Pi route 제거 확인.
- 공식 Pairing offer와 Node transport의 protected E2EE 연결·재접속 2회 성공.
- Paseo process·container·설정·인증서 불변 확인. 기존 모델 요청을 취소하거나 LLM을 재시작하지 않았습니다.
- 원본 전후 기록과 휴지통 대조는 `data/Paseo/cleanup/remote-support/`에 저장하며 Git에 포함하지 않습니다.

재사용 스크립트는 `scripts/Paseo/move-unused-remote-support-to-recycle-bin.ps1`입니다. 기본은 대상 조회이며 `-Execute`를 지정해야 고정 목록만 휴지통으로 옮깁니다. 공유 설정 Hash·허용 경로·link를 검사합니다. 현재는 이동이 완료되어 다시 실행해도 해당 대상이 없습니다.

휴지통에서 설치 파일을 복원해도 삭제한 Docker DB·Credential은 되돌아오지 않으므로 Remote Pi를 다시 쓰려면 재구축과 새 Pairing이 필요합니다. 현재 운영은 Paseo를 사용합니다.
