"""Keyless Web 도구 또는 실제 Context 압축·복원을 순차 검증합니다."""

import argparse
import json
import time

from service_runtime import RUNTIME_DIRECTORY, WORKSPACE_DIRECTORY, read_json
from verify_coding_loop import PiRpcSession


def verify_web():
    """실제 모델이 Keyless Search와 URL 본문 fetch를 각각 수행하게 합니다."""
    verification_directory = RUNTIME_DIRECTORY / "verification/web"
    verification_directory.mkdir(parents=True, exist_ok=True)
    session = PiRpcSession(verification_directory)
    try:
        session.prompt(
            "Verify the installed web tools. First call web_search with a single query for the official Pi coding agent "
            "earendil-works/pi GitHub repository. Use workflow none and the configured keyless providers. "
            "Then call fetch_content on https://pi.dev and summarize one concrete detail from its actual page body. "
            "Do not use bash, write, edit, source_check, browser, or external model providers. Report any tool failure honestly.")
        tool_events = [event for event in session.events if event.get("type") == "tool_execution_end"]
        summary = {"tools": [{"name": event["toolName"], "is_error": event.get("isError"), "result": event.get("result")}
                             for event in tool_events]}
    finally:
        session.close(verification_directory / "events.jsonl")
    (verification_directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not {"web_search", "fetch_content"}.issubset({event["name"] for event in summary["tools"]}):
        raise SystemExit(1)
    if any(event["is_error"] for event in summary["tools"]):
        raise SystemExit(1)


def verify_context():
    """최소 압축 크기 이상의 실제 대화를 압축하고 프로세스 재시작 후 중요 결정을 복원합니다."""
    verification_directory = RUNTIME_DIRECTORY / "verification/context"
    verification_directory.mkdir(parents=True, exist_ok=True)
    test_configuration = read_json(WORKSPACE_DIRECTORY / "config/PiCodingAgent/billion-context.local.json")
    test_configuration["compress"]["preserveRecentTokens"] = 128
    test_configuration["compress"]["requireNudge"] = False
    test_configuration["compress"]["requireRecommendation"] = False
    test_configuration_path = verification_directory / "context-test.local.json"
    test_configuration_path.write_text(json.dumps(test_configuration, indent=2), encoding="utf-8")
    test_environment = {"BILI_CONFIG_FILE": str(test_configuration_path)}
    session = PiRpcSession(verification_directory, environment_overrides=test_environment)
    archive_notes = []
    for note_index in range(80):
        archive_notes.append(f"Archived note {note_index:03d}: The completed fixture task used a local array counter. "
                             "This note is redundant test context and can be discarded after compression. "
                             "Retain only the project decision, modified filename and passed test.")
    session.prompt("Context retention test. Remember decision code PI_CONTEXT_9427, changed file count-items.cjs, "
                   "fix return items.length, and node:test passed 1/1. All following archive notes are completed background. "
                   "Reply ACK only, without tools.\n" + "\n".join(archive_notes))
    for checkpoint_index in range(2):
        session.prompt(f"Checkpoint {checkpoint_index + 1}: previous archive notes are completed background. Reply OK only, without tools.")
    state = session.command("get_state")["data"]
    session.prompt("Explicit compression test: use acp_status if necessary to identify live refs. Use the compress tool to "
                   "compress ONLY the initial long user message with the archived notes, and no later messages. "
                   "Keep PI_CONTEXT_9427, count-items.cjs, return items.length, test passed 1/1 in the summary. "
                   "Call compress exactly once, and after a successful call reply DONE immediately; never compress the summary again. "
                   "Do not invent refs, do not compress dead refs, and do not call any filesystem or bash tool. "
                   "If compress refuses, report its error and stop.")
    compression_events = [event for event in session.events if event.get("type") == "tool_execution_end"
                          and event.get("toolName") == "compress"]
    session.close(verification_directory / "compression-events.jsonl")
    resumed_session = PiRpcSession(verification_directory, state["sessionFile"], test_environment)
    resumed_session.prompt("Without tools, recall the exact decision code, changed file, code fix and test result after compression.")
    recalled_text = resumed_session.command("get_last_assistant_text")["data"]
    resumed_session.close(verification_directory / "resume-events.jsonl")
    summary = {"session_path": state["sessionFile"], "compression_events": compression_events,
               "test_preserve_recent_tokens": 128, "production_preserve_recent_tokens": 32768,
               "resume": recalled_text, "checked_at": time.time()}
    (verification_directory / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if not compression_events:
        raise SystemExit(1)
    if not any(event.get("result", {}).get("details", {}).get("blocksCreated", 0) > 0 for event in compression_events):
        raise SystemExit(1)
    if "PI_CONTEXT_9427" not in json.dumps(recalled_text):
        raise SystemExit(1)


def main():
    """선택한 시나리오 하나만 실행하여 병렬 Agent 작업을 만들지 않습니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", choices=["web", "context"])
    arguments = parser.parse_args()
    if arguments.scenario == "web":
        verify_web()
    else:
        verify_context()


if __name__ == "__main__":
    main()
