# Remote Pi 설치 계획

이 문서는 과거 구축 이력입니다. 2026-11-14에 Remote Pi 전용 구성을 정리했으며 현재 원격 연결은 [Paseo](../Paseo/README.md)를 사용합니다. [정리 범위](../Paseo/REMOTE_SUPPORT_CLEANUP.md)를 우선합니다.

확인일: 2026-11-13. 기존 branch: `feature/pi-local-coding-agent`.

## 공식 배포 확인

- Repository: <https://github.com/jacobaraujo7/remote_pi>
- 확인한 main commit: `f52d54a854087a15dfa952f02de669a14be26382`.
- Extension: npm `remote-pi@0.7.0`, Node.js 20 이상. 기존 Pi SDK dependency와 버전 차이가 있으므로 실제 Windows Native Pi에서 별도 검증합니다.
- Android: `app-v1.2.0`의 `RemotePi.apk`. 최신 Cockpit Release는 다른 앱이므로 혼용하지 않습니다.
- Android Release source의 `relay_config.dart`는 `https://hostname:port`를 허용하고 문자열의 port를 유지해 `wss://hostname:port`로 변환합니다. 입력란은 `wss://`를 받지 않습니다.
- Relay: 공식 `jacobmoura7/remote-pi-relay` Linux amd64 image를 digest로 고정합니다. README에 명시된 `REMOTEPI_RELAY_PORT`, `REMOTEPI_MESH_DB_PATH`를 사용합니다.
- Caddy: 공식 `2.11.9-alpine` image를 digest로 고정합니다.
- Desktop QR 호환 renderer: `qrcode@1.5.4` (Node.js 10.13 이상). 공식 pairing URI를 로컬 PNG로 표시하며 별도 Remote Pi dependency에만 설치합니다.

## 배치 및 보존 범위

1. 별도 Compose project `llm-home-server-remote-pi`에서 Relay와 Caddy만 관리합니다.
2. Relay에는 host port를 publish하지 않습니다. `internal: true` network와 데이터 전용 named volume만 연결합니다.
3. Caddy만 private Relay network와 인터넷 연결용 network를 함께 사용합니다. Host TCP 443 및 8789를 container 443으로 연결합니다.
4. Router 외부 443 → host 443은 TLS-ALPN-01 발급·갱신에 사용합니다. Android는 외부 38789 → host 8789를 사용합니다.
5. HTTP-01을 끄고 Let's Encrypt Staging에서 외부 challenge를 먼저 검증한 뒤 Production을 사용합니다. Staging과 Production 인증서 volume을 분리합니다.
6. 인증서 검증은 비활성화하지 않습니다. 발급 실패 시 원인과 대안을 보고하고 연결 단계는 진행하지 않습니다.
7. Pi는 기존 Windows Native 실행 방식과 Home Server ON/OFF를 유지합니다. Docker에 개발 디렉터리를 mount하지 않습니다.
8. Extension dependency와 Remote Pi 상태를 별도 경로에 둡니다. 기존 Pi 설정·Extension 및 Infernix 설정을 덮어쓰지 않습니다. 새 Extension의 SDK 호환성을 확인한 후 additive loader로 연결합니다.
9. Relay/Caddy에는 `restart: unless-stopped`를 적용하고 Pi 종료에 연동하지 않습니다.

현재 실행 중인 LLM은 Strata입니다. Infernix로 전환하지 않으며 기존 Context·Parallel 설정을 그대로 보존합니다.

## 검증 순서

- 기존 container/network/listener 및 보호 설정 hash 기록.
- Compose validation, Relay health, private network/host port 확인.
- Staging TLS-ALPN-01 성공 여부로 외부 443의 CA 도달 여부 확인.
- Production 인증서 및 정상 trust 검증 HTTPS/WSS, 데이터 영속성·자동 갱신 설정 확인.
- Windows Native Pi Extension load/relay 연결, 기존 Extension 공존, Pi 종료 후 container 유지.
- Android 실기기에서 Custom Relay 설정 → QR pairing → 기존 session 제어 → 연결 해제/재접속. 실기기 확인이 없으면 미검증으로 기록합니다.
