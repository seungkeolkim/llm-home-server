"""Infernix의 고정 Profile, 다운로드 검증 기록과 native HTTP 계약을 연결합니다."""

import json
from pathlib import Path
import re

from .configuration import WORKSPACE_DIRECTORY, read_json, resolve_workspace_path


ACTIVE_DOWNLOAD_STATES = {
    "starting", "preparing", "connecting", "downloading", "retrying", "hashing_existing",
    "verifying", "verifying_existing", "file_completed",
}
RESERVED_OPTIONS = {"config", "model", "model-id", "api-key", "host", "port", "any-model-name", "plan"}


def native_options(configuration):
    """고정 model identity와 인증을 우회하는 옵션 없이 native 설정을 구성합니다."""
    options = {
        "model": configuration["model_path"],
        "model-id": configuration["model_name"],
        "host": configuration["host"],
        "port": configuration["port"],
        "api-key": configuration["api_key"],
        "ngram-volume": configuration["ngram_volume"],
        "draft-model": configuration["draft_model"],
        "chat-template": configuration["chat_template"],
    }
    arguments = configuration["args"]
    argument_index = 0
    while argument_index < len(arguments):
        argument = arguments[argument_index]
        if not isinstance(argument, str) or not re.fullmatch(r"--[a-z][a-z0-9-]*", argument):
            raise ValueError("Infernix args의 옵션 이름이 올바르지 않습니다.")
        option_name = argument[2:]
        if option_name in RESERVED_OPTIONS or option_name in options:
            raise ValueError("Infernix args가 고정 Profile 옵션을 덮어쓸 수 없습니다.")
        argument_index += 1
        option_value = True
        if argument_index < len(arguments) and not str(arguments[argument_index]).startswith("--"):
            option_value = arguments[argument_index]
            argument_index += 1
        options[option_name] = option_value
    return options


def write_native_configuration(configuration):
    """API key를 command line 대신 Git에서 제외한 native TOML에 기록합니다."""
    options = native_options(configuration)
    configuration_path = resolve_workspace_path(configuration["native_configuration_path"])
    if not configuration_path.resolve().is_relative_to((WORKSPACE_DIRECTORY / "runtime/Infernix").resolve()):
        raise ValueError("Native 설정은 runtime/Infernix 아래에 저장해야 합니다.")
    configuration_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    for option_name, option_value in options.items():
        lines.append(f"{option_name} = {json.dumps(option_value, ensure_ascii=False)}")
    configuration_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return configuration_path


def server_command(configuration):
    """Shell이나 자동 model 전환 launcher 없이 단일 native 서버만 실행합니다."""
    configuration_path = write_native_configuration(configuration)
    return [configuration["exe"], "--config", str(configuration_path)]


def preparation_problem(configuration, download_status_path):
    """파일을 Load하거나 매 조회마다 대용량 hash를 읽지 않고 준비 상태를 확인합니다."""
    native_options(configuration)
    status_path = resolve_workspace_path(download_status_path)
    if not status_path.is_file():
        return "files_missing", "Infernix 다운로드·hash 검증 기록이 없습니다."
    download_status = read_json(status_path)
    if download_status.get("state") in ACTIVE_DOWNLOAD_STATES:
        percent = float(download_status.get("progress_percent", 0))
        return "downloading", f"Model·PLE·DFlash2 다운로드·검증 중 ({percent:.1f}%)"
    if download_status.get("state") != "completed":
        return "files_missing", "다운로드가 완료되지 않았습니다. 다운로드 상태·로그를 확인해 주세요."
    manifest_path = resolve_workspace_path(configuration["download_manifest_path"])
    manifest = read_json(manifest_path)
    if Path(download_status["manifest_path"]).resolve() != manifest_path.resolve():
        return "invalid", "다운로드 검증 기록의 Manifest가 다릅니다."
    verified_files = {}
    for verified_file in download_status.get("verified_files", []):
        verified_files[Path(verified_file["path"]).resolve()] = verified_file
    large_files = {}
    for entry in manifest["files"]:
        if not entry.get("sha256"):
            continue
        file_path = (WORKSPACE_DIRECTORY / "data/Infernix" / entry["destination"]).resolve()
        if not file_path.is_relative_to((WORKSPACE_DIRECTORY / "data/Infernix").resolve()):
            return "invalid", "Manifest의 다운로드 경로가 올바르지 않습니다."
        receipt = verified_files.get(file_path, {})
        if (not file_path.is_file() or file_path.stat().st_size != entry["expected_bytes"] or
                receipt.get("bytes") != entry["expected_bytes"] or receipt.get("sha256") != entry["sha256"]):
            return "files_missing", "Model·PLE·DFlash2의 파일 또는 pinned hash 검증 기록이 다릅니다."
        large_files[file_path] = entry
    for field_name in ("model_path", "ngram_volume", "draft_model"):
        if Path(configuration[field_name]).resolve() not in large_files:
            return "invalid", "Profile이 pinned 다운로드 파일을 참조하지 않습니다."
    executable_path = Path(configuration["exe"])
    if not executable_path.is_file():
        return "engine_missing", "Infernix Windows Engine 준비가 필요합니다."
    build_path = executable_path.parent / "BUILD.json"
    if not build_path.is_file():
        return "engine_missing", "Infernix 설치 Release 검증 기록이 없습니다."
    build = read_json(build_path)
    if build.get("release") != configuration["engine_release"] or not build.get("interface_verified"):
        return "engine_missing", "Infernix 설치 Release 검증 기록이 다릅니다."
    if not Path(configuration["chat_template"]).is_file():
        return "files_missing", "Infernix의 Qwen3.8 Chat template이 없습니다."
    return None


def verified_model_response(models, configuration):
    """Native 서버의 정확한 Model ID와 Context를 확인합니다."""
    entries = models.get("data", [])
    if len(entries) != 1:
        return False
    arguments = configuration["args"]
    expected_context = int(arguments[arguments.index("--max-context") + 1])
    model = entries[0]
    return (model.get("id") == configuration["model_name"] and
            model.get("owned_by") == "infernix" and model.get("max_model_len") == expected_context)


def normalize_status(health, models, metrics, configuration):
    """Prefill·Decode와 대기 요청을 모두 종료 확인용 in-flight 수에 반영합니다."""
    if health.get("status") != "ok" or not verified_model_response(models, configuration):
        raise ValueError("Infernix Model ID·Context·readiness가 Profile과 다릅니다.")
    engine = metrics["engine"]
    if engine.get("name") != "infernix" or engine.get("model") != configuration["model_name"]:
        raise ValueError("Infernix metrics의 Engine identity가 다릅니다.")
    live = metrics["live"]
    if not isinstance(live.get("instance_id"), str) or not live["instance_id"]:
        raise ValueError("Infernix metrics의 실행 instance identity가 없습니다.")
    in_flight = int(live["running"]) + int(live["waiting"])
    if int(live["running"]) < 0 or int(live["waiting"]) < 0:
        raise ValueError("Infernix 요청 수가 올바르지 않습니다.")
    return {"loaded": True, "activity": {"in_flight": in_flight},
            "engine_instance_id": live.get("instance_id")}


async def query_status(client, configuration):
    """Load·생성 요청 없이 native health·model identity·활동 상태만 조회합니다."""
    headers = {"Authorization": "Bearer " + configuration["api_key"]}
    documents = []
    for route in ("/health", "/v1/models", "/metrics?format=json"):
        response = await client.get("http://127.0.0.1:8488" + route, headers=headers, timeout=3)
        response.raise_for_status()
        documents.append(response.json())
    return normalize_status(*documents, configuration)


def query_status_sync(client, configuration):
    """기동 worker에서도 동일한 native readiness·identity 계약을 사용합니다."""
    headers = {"Authorization": "Bearer " + configuration["api_key"]}
    documents = []
    for route in ("/health", "/v1/models", "/metrics?format=json"):
        response = client.get("http://127.0.0.1:8488" + route, headers=headers, timeout=3)
        response.raise_for_status()
        documents.append(response.json())
    return normalize_status(*documents, configuration)
