"""실제 Pi RPC와 로컬 SSE fixture로 압축 실패의 자동 중단을 검증합니다."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import queue
import subprocess
import threading
import time


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
VERIFICATION_DIRECTORY = WORKSPACE_DIRECTORY / "runtime/Paseo/verification/compression-runtime"
STATUS_TEXT = "Compressible ranges (1, oldest first):\n  m00001–m00010  10 msgs  4K\n\nSTORAGE"


class CompressionBackendHandler(BaseHTTPRequestHandler):
    """정해진 tool call을 반환하여 요청 수로 무한 재시도 방지를 확인합니다."""

    def do_POST(self):
        """외부 LLM 대신 OpenAI Compatible SSE를 반환합니다."""
        request_body = self.rfile.read(int(self.headers["Content-Length"]))
        json.loads(request_body)
        request_number = self.server.request_count
        self.server.request_count += 1
        planned_calls = self.server.planned_calls
        tool_name = planned_calls[request_number] if request_number < len(planned_calls) else None
        if tool_name is None:
            delta = {"role": "assistant", "content": "FIXTURE_DONE"}
        else:
            content = "m00001–m00010\nA concise fixture summary."
            if self.server.scenario == "bounds":
                content = "m00001–m00030\nDo not fold protected recent history."
            arguments = json.dumps({"content": content}) if tool_name == "compress" else "{}"
            if self.server.scenario == "malformed" and tool_name == "compress":
                arguments = '{"content":"' + "x" * 9000
            delta = {"role": "assistant", "tool_calls": [{"index": 0,
                "id": f"fixture-call-{request_number}", "type": "function",
                "function": {"name": tool_name, "arguments": arguments}}]}
        completion = {"id": f"fixture-{request_number}", "object": "chat.completion.chunk",
            "created": 1, "model": "fixture", "choices": [{"index": 0, "delta": delta,
                "finish_reason": None}]}
        final_chunk = {**completion, "choices": [{"index": 0, "delta": {},
            "finish_reason": "tool_calls" if tool_name else "stop"}],
            "usage": {"prompt_tokens": 500, "completion_tokens": 30, "total_tokens": 530}}
        response_body = ("data: " + json.dumps(completion) + "\n\n" +
            "data: " + json.dumps(final_chunk) + "\n\ndata: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, message_format, *arguments):
        """Fixture의 일반 access log는 생략합니다."""
        return


def read_rpc_output(output_stream, messages):
    """Windows pipe를 별도 thread로 읽어 main thread의 timeout을 유지합니다."""
    for output_line in output_stream:
        try:
            messages.put(json.loads(output_line))
        except json.JSONDecodeError:
            continue


def wait_for_rpc(messages, predicate):
    """일치하는 RPC event까지 최대 20초 동안 기다립니다."""
    deadline = time.monotonic() + 20
    received = []
    while time.monotonic() < deadline:
        message = messages.get(timeout=max(0.01, deadline - time.monotonic()))
        received.append(message)
        if predicate(message):
            return received
    raise TimeoutError("Pi RPC fixture timed out")


def verify_scenario(scenario):
    """운영 session과 공통 lock 없이 실제 Pi에서 중단과 다음 입력을 확인합니다."""
    fixture_directory = VERIFICATION_DIRECTORY / scenario
    agent_directory = fixture_directory / "agent"
    agent_directory.mkdir(parents=True, exist_ok=True)
    backend = ThreadingHTTPServer(("127.0.0.1", 0), CompressionBackendHandler)
    backend.request_count = 0
    backend.scenario = scenario
    backend.planned_calls = ["compress", "acp_status", "compress", "acp_status", "compress"]
    threading.Thread(target=backend.serve_forever, daemon=True).start()
    fixture_extension_path = fixture_directory / "fixture-tools.ts"
    execution_log_path = fixture_directory / "executions.jsonl"
    execution_log_path.write_text("", encoding="utf-8")
    guard_path = (WORKSPACE_DIRECTORY / "scripts/Paseo/compression-guard.ts").as_posix()
    fixture_extension_path.write_text('''
import fs from "node:fs";
import { registerCompressionGuard } from GUARD_PATH;
/** 운영 policy와 동일한 compression guard에 fixture tool을 연결합니다. */
export default function registerFixture(extensionApi) {
    registerCompressionGuard(extensionApi);
    for (const toolName of ["compress", "acp_status"]) {
        extensionApi.registerTool({ name: toolName, label: toolName, description: "Fixture only",
            parameters: toolName === "compress"
                ? {type: "object", properties: {content: {type: "string"}}, required: ["content"]}
                : {type: "object", properties: {}},
            /** 외부 API나 사용자 파일 변경 없이 압축 결과만 재현합니다. */
            async execute() {
                fs.appendFileSync(EXECUTION_PATH, JSON.stringify({toolName}) + "\\n");
                return toolName === "acp_status"
                    ? {content: [{type:"text",text:STATUS_TEXT}], details:{}}
                    : {content: [{type:"text",text:FAILURE_TEXT}],
                       details:{outcome:"refused",blocksCreated:0},isError:true};
            },
        });
    }
}
'''.replace("GUARD_PATH", json.dumps(guard_path))
        .replace("EXECUTION_PATH", json.dumps(str(execution_log_path)))
        .replace("FAILURE_TEXT", json.dumps("Compression REFUSED: " +
            ("compress.requireRecommendation" if scenario == "bounds" else "compress.requireNudge")))
        .replace("STATUS_TEXT", json.dumps(STATUS_TEXT)), encoding="utf-8")
    models = {"providers": {"fixture": {"baseUrl": f"http://127.0.0.1:{backend.server_port}/v1",
        "api": "openai-completions", "apiKey": "fixture-only", "models": [{"id": "fixture",
            "name": "Fixture", "reasoning": False, "input": ["text"], "contextWindow": 262144,
            "maxTokens": 16384, "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}}]}}}
    settings = {"defaultProvider": "fixture", "defaultModel": "fixture", "compaction": {"enabled": False},
        "retry": {"enabled": False}, "extensions": [str(fixture_extension_path)]}
    (agent_directory / "models.json").write_text(json.dumps(models), encoding="utf-8")
    (agent_directory / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    environment = os.environ.copy()
    environment["PI_CODING_AGENT_DIR"] = str(agent_directory)
    environment["PI_CODING_AGENT_SESSION_DIR"] = str(fixture_directory / "sessions")
    cli_path = WORKSPACE_DIRECTORY / "data/PiCodingAgent/npm/node_modules/@earendil-works/pi-coding-agent/dist/cli.js"
    process = subprocess.Popen(["node", str(cli_path), "--mode", "rpc"], cwd=fixture_directory,
        env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8")
    messages = queue.Queue()
    threading.Thread(target=read_rpc_output, args=(process.stdout, messages), daemon=True).start()
    try:
        process.stdin.write(json.dumps({"type": "prompt", "message": "Run compression fixture"}) + "\n")
        process.stdin.flush()
        events = wait_for_rpc(messages, lambda message: message.get("type") == "agent_end")
        assert backend.request_count == 5, (scenario, backend.request_count, events)
        tool_messages = [event["message"] for event in events if event.get("type") == "message_end"
            and event.get("message", {}).get("role") == "toolResult"
            and event["message"].get("toolName") == "compress"]
        assert len(tool_messages) == 3, (scenario, events)
        assert tool_messages[-1]["details"]["compressionGuard"]["stopped"] is True
        assert any(event.get("method") == "notify" for event in events), events
        if scenario == "malformed":
            assert all(len(message["content"][0]["text"]) < 3000 for message in tool_messages)
        executions = [json.loads(line) for line in execution_log_path.read_text(encoding="utf-8").splitlines()]
        compress_execution_count = sum(record["toolName"] == "compress" for record in executions)
        expected_executions = {"nudge": 3, "bounds": 1, "malformed": 0}[scenario]
        assert compress_execution_count == expected_executions, executions
        process.stdin.write(json.dumps({"type": "prompt", "message": "A new user request"}) + "\n")
        process.stdin.flush()
        followup = wait_for_rpc(messages, lambda message: message.get("type") == "agent_end")
        assert backend.request_count == 6
        assert any(event.get("type") == "message_end" and
            "FIXTURE_DONE" in json.dumps(event.get("message", {})) for event in followup)
        return {"scenario": scenario, "modelRequestsBeforeStop": 5, "compressionFailures": 3,
            "compressExecutions": compress_execution_count, "fourthFailureRequestPrevented": True,
            "warningObserved": True, "nextUserRequestWorks": True}
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait(timeout=5)
        error_text = process.stderr.read()
        (fixture_directory / "stderr.log").write_text(error_text, encoding="utf-8")
        backend.shutdown()
        backend.server_close()


def verify_compression_runtime():
    """세 가지 실패 경로를 검증하고 재실행 가능한 결과를 남깁니다."""
    results = [verify_scenario(scenario) for scenario in ["nudge", "bounds", "malformed"]]
    (VERIFICATION_DIRECTORY / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results))


if __name__ == "__main__":
    verify_compression_runtime()
