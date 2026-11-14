"""Paseo가 실행하는 Pi RPC에 격리 설정과 기존 local Provider 환경만 전달합니다."""

from pathlib import Path
import json
import os
import subprocess
import sys


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY))

from scripts.PiCodingAgent.service_runtime import build_environment, load_configuration, PI_ENTRY_PATH


def build_paseo_pi_environment():
    """기존 설정은 읽기만 하고 Paseo의 Session·Context 저장소를 분리합니다."""
    environment = build_environment(load_configuration())
    environment.update({
        "PI_CODING_AGENT_DIR": str(WORKSPACE_DIRECTORY / "runtime/Paseo/agent"),
        "PI_CODING_AGENT_SESSION_DIR": str(WORKSPACE_DIRECTORY / "data/Paseo/pi-sessions"),
        "BILI_SESSIONS_DIR": str(WORKSPACE_DIRECTORY / "data/Paseo/context/sessions"),
        "ACP_LOG_FILE": str(WORKSPACE_DIRECTORY / "runtime/Paseo/bili.log"),
        "XDG_CONFIG_HOME": str(WORKSPACE_DIRECTORY / "runtime/Paseo/xdg/config"),
        "XDG_DATA_HOME": str(WORKSPACE_DIRECTORY / "runtime/Paseo/xdg/data"),
        "XDG_STATE_HOME": str(WORKSPACE_DIRECTORY / "runtime/Paseo/xdg/state"),
        "PI_WEB_ACCESS_CACHE_ROOT": str(WORKSPACE_DIRECTORY / "runtime/Paseo/web-cache"),
        "AGENT_BROWSER_SESSION": "llm-home-paseo",
    })
    for variable_name in list(environment):
        if variable_name.startswith(("OPENAI_", "ANTHROPIC_", "GEMINI_", "GOOGLE_API_", "GROQ_", "MISTRAL_")):
            environment.pop(variable_name)
    return environment


def normalize_rpc_output(output_line):
    """Pi 1.5의 handled 응답을 Paseo가 인식하는 추가 필드로 호환합니다."""
    try:
        message = json.loads(output_line)
    except json.JSONDecodeError:
        return output_line
    if not isinstance(message, dict):
        return output_line
    if message.get("type") == "response" and message.get("command") == "prompt":
        response_data = message.get("data")
        if isinstance(response_data, dict) and response_data.get("disposition") == "handled":
            response_data.setdefault("agentInvoked", False)
            return json.dumps(message, ensure_ascii=False) + "\n"
    return output_line


def run_paseo_pi():
    """RPC stdin을 직접 전달하고 stdout에는 필요한 호환 필드만 보완합니다."""
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    arguments = ["node", str(PI_ENTRY_PATH), *sys.argv[1:]]
    process = subprocess.Popen(
        arguments, env=build_paseo_pi_environment(), stdin=sys.stdin.buffer,
        stdout=subprocess.PIPE, stderr=sys.stderr.buffer, text=True, encoding="utf-8",
        creationflags=subprocess.CREATE_NO_WINDOW,
    )
    try:
        for output_line in process.stdout:
            sys.stdout.write(normalize_rpc_output(output_line))
            sys.stdout.flush()
        raise SystemExit(process.wait())
    finally:
        process.stdout.close()
        if process.poll() is None:
            process.terminate()
            process.wait(timeout=5)


if __name__ == "__main__":
    run_paseo_pi()
