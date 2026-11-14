# Paseo 압축 실패 보호

2026-11-14, branch `fix/paseo-compression-loop`.

## 발생한 문제

Windows Native Pi 1.5.2 + billion-context 0.1.213에서 긴 작업 중 `compress`가 11회 모두 실패했습니다.
`requireNudge` 거절 7회, 추천 범위 이탈 2회, 인자 형식 오류 2회였으며 압축 block은 생성되지 않았습니다.
마지막에는 다른 작업 없이 압축만 5회 연속 재시도했습니다. 사용자가 해당 작업을 중지했습니다.

nudge는 실제로 생성됐지만 호출한 round에는 유효하지 않은 경우가 있었고, 마지막 두 호출은 같은 추천 밖 범위를 포함했습니다.
따라서 nudge 전달 전체의 실패나 메모리 부족으로 단정하지 않습니다.
설치 버전의 `requireNudge`·`requireRecommendation` 거절 경로는 내부 압축 실패 집계 전에 반환합니다.
Pi의 schema 검증 실패와 실행 전 차단도 `tool_result` hook을 생략하므로 이 hook만으로 전체 실패를 감지할 수 없습니다.

## 적용한 동작

기존 `scripts/Paseo/pi-policy-extension.ts`에서 `compression-guard.ts`를 등록합니다.
공식 package와 원래 Pi 설정은 수정하지 않습니다.

- 사용자 요청에서 **성공한 압축 없이 실패가 3회 누적되면 현재 Pi run을 abort**합니다. 중간의 bash·read·acp_status 성공은 실패 수를 초기화하지 않습니다.
- 실제 block을 생성한 `applied`·`partial` 결과는 실패 수를 초기화합니다. block 없는 no-op은 진행 없는 압축으로 집계합니다.
- schema 검증 실패와 실행 전 차단은 `message_end`에서도 처리하며, 같은 tool call을 두 hook에서 중복 집계하지 않습니다.
- 압축 실패 후에는 성공한 `acp_status`에서 최신 추천 목록을 얻어야 다시 `compress`를 실행할 수 있습니다. 목록을 읽지 못했거나 status 호출이 실패하면 재시도를 허용하지 않습니다.
- 확인한 추천 범위의 부분집합은 허용하고, 범위 사이의 빈틈·추천 밖 최근 대화는 실행 전에 거절합니다. 범위나 summary를 자동으로 잘라 맞추지 않습니다. 최종 허용 여부는 기존 billion-context도 검사합니다.
- `requireNudge` 거절 시 새 nudge가 올 때까지 원래 작업을 진행하도록 안내합니다. `acp_status` 조회는 압축 허가를 대신하지 않습니다.
- 새 사용자 요청의 system prompt에 nudge·추천 범위·인자 형식·실패 제한을 명시합니다. 자동 custom 메시지는 실패 예산을 초기화하지 않습니다.
- malformed JSON 오류에 포함된 `Received arguments:`의 긴 복사본을 제거하고 오류 설명은 최대 2400자로 제한합니다. 원래 assistant tool call과 기존 session 기록은 삭제하지 않습니다.
- 중단 시 UI 알림과 `paseo-compression-stop` custom 메시지를 남깁니다. daemon·Relay·Caddy·LLM은 계속 실행합니다. 자동으로 작업을 재개하지 않습니다.

`config/PiCodingAgent/billion-context.local.json`의 `requireNudge: true`, `requireRecommendation: true`,
최근 32768 tokens 보호와 기존 model·Parallel 설정은 그대로입니다.
이 보호는 **압축 도구 실패**를 대상으로 하며 일반 Thinking loop나 끝나지 않는 단일 모델 응답의 감지 기능은 아닙니다.

## 운영 방법

새 Pi 프로세스는 변경한 policy를 로드합니다. 이미 열려 있는 Paseo Pi session에는 idle 상태를 확인하고 공식 SDK의 `agent.reload()`를 적용합니다.
이 작업은 provider session을 다시 열며 daemon·Desktop·Relay·모델을 재기동하지 않습니다. 실행 중인 작업에는 reload를 적용하지 않습니다.

보호 기능으로 중단되면 마지막 Compress 결과의 실패 원인을 확인하고 새 사용자 메시지로 목적과 남은 작업을 전달합니다.
새 요청에서는 실패 예산이 초기화됩니다. 이전 파일 변경과 session을 되돌리거나 삭제하는 동작은 없습니다.
같은 session에서 곧바로 반복 중단되면 해당 기록을 바탕으로 nudge·범위·입력 형식 문제를 추가로 진단합니다.

## 검증

```powershell
node scripts/Paseo/verify_compression_guard.mjs
python -X utf8 -B scripts/Paseo/verify_compression_runtime.py
node scripts/Paseo/verify_approval_mode.mjs
python -X utf8 -B scripts/Paseo/verify_policy.py
```

- Unit 검사: 최신 추천 목록과 UNCOVERED HISTORY 구분, 추천의 부분집합·범위 사이의 빈틈, 실패 누적·중복 이벤트, 성공/partial 초기화, 새 사용자 요청과 custom 구분, 오류 인자 복사본 축약을 확인했습니다.
- 실제 Pi RPC + loopback SSE fixture: nudge 거절·범위 이탈·malformed JSON 세 경로에서 각각 3회 실패 후 추가 모델 요청이 차단됐습니다. 중간 acp_status 2회를 포함해 모델 요청은 5회였고 4번째 실패를 위한 요청은 없었습니다.
- 범위 이탈 fixture는 압축 tool 본체가 1회만 실행됐고 이후 2회는 실행 전에 차단됐습니다. malformed JSON fixture는 본체 실행 0회였지만 3회 실패를 모두 집계했습니다.
- 세 경우 모두 중단 알림과 다음 사용자 요청의 정상 완료를 확인했습니다. 외부 LLM과 운영 session을 사용하지 않는 재현 검사입니다.
- 기존 자동/수동 승인·Subagent 차단·Metadata 차단·공통 turn lock 검사를 통과했습니다.
- 운영 중이던 Pi session 2개의 idle 상태를 확인한 뒤 공식 SDK로 reload했습니다. daemon·Desktop·Relay·Caddy·LLM은 재시작하지 않았습니다.
- 별도의 테스트 Agent에서 실제 Strata QFN이 `GUARD_READY`를 응답하고 idle로 완료했습니다. 자체 Relay의 TLS·E2EE 연결과 gateway `in_flight: 0`, `maximum_in_flight: 1`을 확인했습니다.
- 원래 Pi·모델 설정·dependency lock·기존 session JSONL을 포함한 보호 파일 12개의 SHA256이 적용 전후 일치했습니다. 기존 session 파일은 byte 단위로 유지됐습니다.

원본 결과는 `runtime/Paseo/verification/compression-guard-unit.json`, `compression-runtime/results.json`에 저장합니다.
운영 적용과 실제 모델 응답은 `compression-guard-live.json`, 보호 파일 Hash는 `compression-guard-before.json`을 기준으로 확인합니다.
이는 실제 장시간 작업의 성공이나 전체 262K 압축·복원 품질 검증을 대신하지 않습니다.
