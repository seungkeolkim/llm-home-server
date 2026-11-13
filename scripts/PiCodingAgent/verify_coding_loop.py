"""실제 Strata Pi RPC에서 승인, Coding Loop와 Session 재개를 검증합니다."""

from pathlib import Path
import json
import queue
import subprocess
import sys
import threading
import time

from service_runtime import (WORKSPACE_DIRECTORY, RUNTIME_DIRECTORY, PI_ENTRY_PATH, build_environment,
                             load_configuration, process_record, start_service)


class PiRpcSession:
    """하나의 실제 Pi RPC 프로세스와 순차 요청으로만 통신합니다."""

    def __init__(self, working_directory, session_path=None, environment_overrides=None):
        """승인 대상 작업 폴더와 durable JSONL Session을 연결합니다."""
        self.working_directory = working_directory
        self.events = []
        self.records = queue.Queue()
        self.approvals = []
        start_service(headless=True)
        command = ["node", str(PI_ENTRY_PATH), "--mode", "rpc"]
        if session_path:
            command.extend(["--session", str(session_path)])
        environment = build_environment(load_configuration())
        environment.update(environment_overrides or {})
        self.process = subprocess.Popen(command, cwd=working_directory, env=environment, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                        text=True, encoding="utf-8", bufsize=1)
        client_directory = RUNTIME_DIRECTORY / "clients"
        client_directory.mkdir(parents=True, exist_ok=True)
        self.client_path = client_directory / f"{self.process.pid}.json"
        self.client_path.write_text(json.dumps(process_record(self.process.pid)), encoding="utf-8")
        self.reader = threading.Thread(target=self.read_records, daemon=True)
        self.reader.start()

    def read_records(self):
        """JSONL 이벤트만 모아 모델 Streaming과 Extension UI를 순서대로 처리합니다."""
        for line in self.process.stdout:
            try:
                record = json.loads(line)
                self.events.append(record)
                self.records.put(record)
            except ValueError:
                self.events.append({"type": "non_json", "text": line.strip()})

    def send(self, command):
        """하나의 RPC command를 표준 입력에 기록합니다."""
        self.process.stdin.write(json.dumps(command) + "\n")
        self.process.stdin.flush()

    def receive_until(self, predicate, timeout=180):
        """테스트 fixture 범위의 명시한 작업만 승인하며 지정 이벤트를 기다립니다."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            record = self.records.get(timeout=max(0.1, deadline - time.monotonic()))
            if record.get("type") == "extension_ui_request" and record.get("method") == "confirm":
                operation = record.get("message", "")
                allowed = operation in {"count-items.cjs", "count-items.test.cjs", "node --test count-items.test.cjs"}
                allowed = allowed or operation in {str(self.working_directory / "count-items.cjs"),
                                                   str(self.working_directory / "count-items.test.cjs")}
                self.approvals.append({"operation": operation, "approved": allowed})
                self.send({"type": "extension_ui_response", "id": record["id"], "confirmed": allowed})
            if predicate(record):
                return record
        raise TimeoutError("Pi RPC 검증 시간이 초과됐습니다.")

    def command(self, command_type, **arguments):
        """응답을 기다린 후에만 다음 RPC command를 보냅니다."""
        command_identifier = str(time.time_ns())
        self.send({"id": command_identifier, "type": command_type, **arguments})
        return self.receive_until(lambda record: record.get("id") == command_identifier
                                  and record.get("type") == "response")

    def prompt(self, message):
        """Agent의 전체 turn 종료를 확인하여 LLM 호출이 겹치지 않게 합니다."""
        response = self.command("prompt", message=message)
        if not response["success"]:
            raise RuntimeError(response.get("error"))
        return self.receive_until(lambda record: record.get("type") == "agent_end")

    def close(self, log_path):
        """실행 로그를 보관하고 검증용 RPC 프로세스를 종료합니다."""
        self.process.stdin.close()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=5)
        stderr = self.process.stderr.read()
        self.client_path.unlink(missing_ok=True)
        log_path.write_text("\n".join(json.dumps(event, ensure_ascii=False) for event in self.events) + "\n", encoding="utf-8")
        log_path.with_suffix(".stderr.log").write_text(stderr, encoding="utf-8")


def main():
    """파일 읽기·수정·테스트와 재시작 후 기억 보존을 실제 모델로 검증합니다."""
    verification_directory = RUNTIME_DIRECTORY / "verification/coding"
    verification_directory.mkdir(parents=True, exist_ok=True)
    (verification_directory / "count-items.cjs").write_text(
        "/** Return the number of supplied items. */\nfunction countItems(items) {\n    return items.length - 1;\n}\nmodule.exports = { countItems };\n",
        encoding="utf-8")
    (verification_directory / "count-items.test.cjs").write_text(
        "const test = require('node:test');\nconst assert = require('node:assert/strict');\n"
        "const { countItems } = require('./count-items.cjs');\n"
        "/** Verify empty and populated collections. */\nfunction verifyCountItems() {\n"
        "    assert.equal(countItems([]), 0);\n    assert.equal(countItems(['a', 'b', 'c']), 3);\n}\n"
        "test('countItems returns the exact length', verifyCountItems);\n", encoding="utf-8")
    first_session = PiRpcSession(verification_directory)
    first_session.prompt(
        "This is an authorized test in the current fixture directory only. Remember the project decision code PI_CONTEXT_7319. "
        "Fix count-items.cjs so countItems returns the exact array length. Use the read tool to inspect count-items.cjs "
        "and count-items.test.cjs, then edit only count-items.cjs, then run the exact command `node --test count-items.test.cjs` "
        "with no additional arguments. "
        "Call one tool per response, complete the tasks, and report the test result. Do not use bash for reading or editing. "
        "The UI will explicitly approve fixture edits and that exact test command.")
    state = first_session.command("get_state")["data"]
    session_path = state["sessionFile"]
    compact_response = first_session.command("compact", customInstructions="Preserve PI_CONTEXT_7319 and the count-items fix.")
    first_session.close(RUNTIME_DIRECTORY / "verification/coding-loop.jsonl")
    completed = subprocess.run(["node", "--test", "count-items.test.cjs"], cwd=verification_directory,
                               capture_output=True, text=True, encoding="utf-8")
    tool_events = [event for event in first_session.events if event.get("type") == "tool_execution_end"]
    second_session = PiRpcSession(verification_directory, session_path)
    second_session.prompt("Without tools, recall the exact project decision code and the modified file from this session. Reply with both.")
    resumed_text = second_session.command("get_last_assistant_text")["data"]
    second_session.close(RUNTIME_DIRECTORY / "verification/session-resume.jsonl")
    summary = {"model": state["model"]["id"], "session_path": session_path,
               "context_window": state["model"]["contextWindow"],
               "tool_calls": [{"name": event["toolName"], "is_error": event.get("isError")} for event in tool_events],
               "approvals": first_session.approvals, "test_exit_code": completed.returncode,
               "test_output": completed.stdout, "compact_response": compact_response, "resume": resumed_text}
    successful_tool_names = {event["toolName"] for event in tool_events if not event.get("isError")}
    summary["coding_loop_passed"] = completed.returncode == 0 and {"read", "edit", "bash"}.issubset(successful_tool_names)
    summary["rejected_tool_calls"] = [event["toolName"] for event in tool_events if event.get("isError")]
    (RUNTIME_DIRECTORY / "verification/coding-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not summary["coding_loop_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
