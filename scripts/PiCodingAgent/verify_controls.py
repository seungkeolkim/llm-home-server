"""인증된 실제 관리 API에서 Pi만 종료·기동되고 기존 서비스가 유지되는지 검증합니다."""

import json
import time
import uuid

import httpx
import psutil

from service_runtime import WORKSPACE_DIRECTORY, RUNTIME_DIRECTORY, read_json


def listener_process_id(port):
    """지정한 기존 LLM listener의 실제 PID를 조회합니다."""
    for connection in psutil.net_connections(kind="tcp"):
        if connection.status == psutil.CONN_LISTEN and connection.laddr.port == port:
            return connection.pid
    return None


def wait_for_snapshot(client):
    """관리 서버 reload 후 첫 정상 상태 수집을 기다립니다."""
    for attempt in range(30):
        snapshot = client.get("/api/status").json()
        if snapshot.get("ready"):
            return snapshot
        time.sleep(0.3)
    raise RuntimeError("관리 서버 상태를 수집하지 못했습니다.")


def control_and_wait(client, csrf_token, action):
    """하나의 Pi 제어 작업이 완료된 뒤 다음 단계로 진행합니다."""
    response = client.post(f"/api/services/pi/{action}", headers={"X-CSRF-Token": csrf_token},
                           json={"identifier": uuid.uuid4().hex})
    response.raise_for_status()
    operation_identifier = response.json()["identifier"]
    for attempt in range(200):
        history_response = client.get("/api/operations")
        history_response.raise_for_status()
        operation = next(record for record in history_response.json() if record["identifier"] == operation_identifier)
        if operation["status"] not in {"queued", "running"}:
            if operation["status"] != "succeeded":
                raise RuntimeError(operation["message"])
            return operation
        time.sleep(0.2)
    raise TimeoutError("Pi 제어 작업의 완료 확인 시간이 초과됐습니다.")


def main():
    """Pi OFF/ON 전후의 native PID와 LibreChat 상태를 비교하고 마지막에 Pi를 켭니다."""
    management_configuration = read_json(WORKSPACE_DIRECTORY / "config/ManagementServer/management.local.json")
    base_url = "http://127.0.0.1:" + str(management_configuration["port"])
    with httpx.Client(base_url=base_url, trust_env=False, timeout=15) as client:
        access = client.post("/api/access", json={"access_string": management_configuration["access_string"]})
        access.raise_for_status()
        csrf_token = access.json()["csrf"]
        baseline = wait_for_snapshot(client)
        if any(operation["status"] in {"queued", "running"} for operation in baseline["operations"]):
            raise RuntimeError("다른 관리 작업이 진행 중이므로 검증을 시작하지 않았습니다.")
        original_llm_process_id = listener_process_id(8488)
        stopped_operation = control_and_wait(client, csrf_token, "stop")
        time.sleep(3.5)
        stopped = wait_for_snapshot(client)
        if stopped["pi"]["state"] != "stopped":
            raise AssertionError("Pi 종료 상태가 아닙니다.")
        if listener_process_id(8488) != original_llm_process_id:
            raise AssertionError("Pi 종료 중 기존 LLM PID가 바뀌었습니다.")
        started_operation = control_and_wait(client, csrf_token, "start")
        time.sleep(3.5)
        started = wait_for_snapshot(client)
        if started["pi"]["state"] != "running" or not started["pi"]["desktop_running"]:
            raise AssertionError("Pi Desktop의 실행 상태를 확인하지 못했습니다.")
        if listener_process_id(8488) != original_llm_process_id:
            raise AssertionError("Pi 시작 중 기존 LLM PID가 바뀌었습니다.")
        if baseline["librechat"] != stopped["librechat"] or baseline["librechat"] != started["librechat"]:
            raise AssertionError("Pi 제어 전후 LibreChat 상태가 다릅니다.")
        summary = {"pi_stop": stopped_operation["status"], "pi_start": started_operation["status"],
                   "llm_process_id_preserved": original_llm_process_id, "librechat_state_preserved": True,
                   "pi_final": started["pi"], "management_health": client.get("/api/health").json()}
    (RUNTIME_DIRECTORY / "verification/control-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
