"""실제 Pi RPC와 가짜 backend로 Metadata·중복 turn 차단을 검증합니다."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import threading
from uuid import uuid4


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
VERIFICATION_DIRECTORY = WORKSPACE_DIRECTORY / "runtime/Paseo/verification"
SHARED_LOCK_PATH = WORKSPACE_DIRECTORY / "runtime/PiCodingAgent/agent-turn.lock"


class ProbeBackendHandler(BaseHTTPRequestHandler):
    """LLM 요청이 발생하면 기록하고 실제 추론 없이 실패시킵니다."""

    def do_POST(self):
        """차단돼야 할 요청 수를 기록합니다."""
        self.server.request_count += 1
        self.send_error(500, "Unexpected LLM request")

    def log_message(self, message_format, *arguments):
        """Fixture의 일반 access log는 생략합니다."""
        return


def run_rpc_probe(agent_directory, no_session):
    """Pi에 prompt를 보내고 input hook이 Agent 호출 전에 처리했는지 확인합니다."""
    environment = os.environ.copy()
    environment["PI_CODING_AGENT_DIR"] = str(agent_directory)
    cli_path = WORKSPACE_DIRECTORY / "data/PiCodingAgent/npm/node_modules/@earendil-works/pi-coding-agent/dist/cli.js"
    command = ["node", str(cli_path), "--mode", "rpc"]
    if no_session:
        command.append("--no-session")
    response = subprocess.run(
        command, input=json.dumps({"id": "policy-probe", "type": "prompt", "message": "Reply OK"}) + "\n",
        cwd=agent_directory, env=environment, capture_output=True, text=True, encoding="utf-8",
        timeout=15, check=True,
    )
    messages = []
    for output_line in response.stdout.splitlines():
        try:
            messages.append(json.loads(output_line))
        except json.JSONDecodeError:
            continue
    acknowledgements = [message for message in messages if message.get("id") == "policy-probe"]
    assert acknowledgements and acknowledgements[-1]["success"]
    assert acknowledgements[-1]["data"]["disposition"] == "handled", acknowledgements
    assert any(message.get("method") == "notify" for message in messages), messages
    return {"agent_invoked": False, "notification_received": True}


def verify_policy():
    """실행 중 사용자 lock은 건드리지 않고 두 가지 차단 경로를 확인합니다."""
    agent_directory = VERIFICATION_DIRECTORY / "policy-fixture/agent"
    agent_directory.mkdir(parents=True, exist_ok=True)
    backend = ThreadingHTTPServer(("127.0.0.1", 0), ProbeBackendHandler)
    backend.request_count = 0
    threading.Thread(target=backend.serve_forever, daemon=True).start()
    models = {"providers": {"fixture": {"baseUrl": f"http://127.0.0.1:{backend.server_port}/v1",
        "api": "openai-completions", "apiKey": "fixture-only", "models": [
            {"id": "fixture", "name": "Fixture", "reasoning": False, "input": ["text"],
             "contextWindow": 4096, "maxTokens": 32,
             "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}}}
    settings = {"defaultProvider": "fixture", "defaultModel": "fixture", "extensions": [
        str(WORKSPACE_DIRECTORY / "scripts/Paseo/pi-policy-extension.ts")]}
    (agent_directory / "models.json").write_text(json.dumps(models), encoding="utf-8")
    (agent_directory / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    owner_token = str(uuid4())
    try:
        results = {"internal_metadata": run_rpc_probe(agent_directory, no_session=True)}
        with SHARED_LOCK_PATH.open("x", encoding="utf-8") as lock_stream:
            json.dump({"pid": os.getpid(), "ownerToken": owner_token}, lock_stream)
        try:
            results["occupied_shared_lock"] = run_rpc_probe(agent_directory, no_session=False)
        finally:
            lock_record = json.loads(SHARED_LOCK_PATH.read_text(encoding="utf-8"))
            if lock_record.get("ownerToken") == owner_token:
                SHARED_LOCK_PATH.unlink()
        results["llm_request_count"] = backend.request_count
        assert backend.request_count == 0
        (VERIFICATION_DIRECTORY / "policy.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results))
    finally:
        backend.shutdown()
        backend.server_close()


if __name__ == "__main__":
    verify_policy()
