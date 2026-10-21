"""실행 중인 관리 서버의 실제 제어와 reload 내구성을 확인합니다."""

import argparse
import json
from pathlib import Path
import time

import httpx


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]


def wait_operation(client, identifier):
    """API reload 중 연결 재시도를 허용하며 작업 결과를 기다립니다."""
    deadline = time.monotonic() + 680
    while time.monotonic() < deadline:
        try:
            response = client.get("/api/operations")
            response.raise_for_status()
            operation = next(item for item in response.json() if item["identifier"] == identifier)
            if operation["status"] not in {"queued", "running"}:
                if operation["status"] == "failed":
                    raise RuntimeError(operation["message"])
                return operation
        except (httpx.TransportError, httpx.HTTPStatusError):
            pass
        time.sleep(1)
    raise TimeoutError("관리 서버 제어 작업이 제한 시간을 넘겼습니다.")


def perform_action(client, csrf_token, target, action):
    """인증과 CSRF token으로 한 번의 제어 작업을 접수합니다."""
    response = client.post(f"/api/services/{target}/{action}", headers={"X-CSRF-Token": csrf_token})
    response.raise_for_status()
    return response.json()["identifier"]


def wait_snapshot(client):
    """Reload 직후 첫 상태 수집이 끝날 때까지 기다립니다."""
    for attempt_number in range(30):
        try:
            response = client.get("/api/status")
            response.raise_for_status()
            snapshot = response.json()
            if snapshot.get("ready"):
                return snapshot
        except httpx.TransportError:
            pass
        time.sleep(1)
    raise TimeoutError("관리 서버의 첫 상태 수집이 끝나지 않았습니다.")


def main():
    """Comfy queue를 변경하지 않고 LLM 제어·reload·LibreChat 기동을 검증합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cycle-llm", action="store_true", help="Idle LLM을 한 번 종료 후 복구합니다.")
    arguments = parser.parse_args()
    configuration = json.loads((WORKSPACE_DIRECTORY / "config/ManagementServer/management.local.json").read_text())
    evidence = {"operations": []}
    with httpx.Client(base_url="http://127.0.0.1:8788", trust_env=False, timeout=15) as client:
        assert client.get("/api/status").status_code == 401
        unlocked = client.post("/api/access", json={"access_string": configuration["access_string"]})
        unlocked.raise_for_status()
        csrf_token = unlocked.json()["csrf"]
        status = wait_snapshot(client)
        assert status["ready"] and status["comfy"]["connected"]
        evidence["initial"] = status
        if arguments.cycle_llm:
            assert not status["llm"]["in_flight"], "LLM 생성 중에는 cycle 검증을 수행하지 않습니다."
            assert not status["comfy"]["running"] and not status["comfy"]["pending"], "Comfy queue가 남아 있습니다."
            stopped_identifier = perform_action(client, csrf_token, "llm", "stop")
            evidence["operations"].append(wait_operation(client, stopped_identifier))
            print("LLM stop verified", flush=True)
            started_identifier = perform_action(client, csrf_token, "llm", "start")
            time.sleep(2)
            (WORKSPACE_DIRECTORY / "management_server/security.py").touch()
            evidence["operations"].append(wait_operation(client, started_identifier))
            print("LLM start survived API reload; existing session retained", flush=True)
        librechat_identifier = perform_action(client, csrf_token, "librechat", "start")
        evidence["operations"].append(wait_operation(client, librechat_identifier))
        time.sleep(4)
        final = client.get("/api/status")
        final.raise_for_status()
        evidence["final"] = final.json()
        assert evidence["final"]["llm"]["state"] == "ready"
        assert evidence["final"]["librechat"]["engine_available"]
        assert evidence["final"]["resources"]["gpus"]
    destination = WORKSPACE_DIRECTORY / "runtime/ManagementServer/diagnostics/integration.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Integration verified:", destination, flush=True)


if __name__ == "__main__":
    main()
