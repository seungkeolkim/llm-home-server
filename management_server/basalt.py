"""Basalt의 고정 모델, 검증된 다운로드와 공식 Python server 계약을 연결합니다."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re

from .configuration import WORKSPACE_DIRECTORY, read_json, resolve_workspace_path


ACTIVE_DOWNLOAD_STATES = {
    "starting", "preparing", "connecting", "downloading", "retrying", "hashing_existing",
    "verifying", "verifying_existing", "file_completed",
}
RESERVED_OPTIONS = {
    "config", "model", "alias", "engine-bin", "api-key", "api-key-file", "host", "port",
    "mock-engine", "lazy", "open", "allowed-host", "totals-file",
}


def model_options(configuration: dict) -> dict:
    """고정 Model ID·인증·서버 주소를 덮어쓰지 못하는 단일 모델 설정을 만듭니다."""
    options = {"model": configuration["model_path"], "alias": configuration["model_name"]}
    arguments = configuration["args"]
    argument_index = 0
    while argument_index < len(arguments):
        argument = arguments[argument_index]
        if not isinstance(argument, str) or not re.fullmatch(r"--[a-z][a-z0-9-]*", argument):
            raise ValueError("Basalt args의 옵션 이름이 올바르지 않습니다.")
        option_name = argument[2:]
        if option_name in RESERVED_OPTIONS or option_name in options:
            raise ValueError("Basalt args가 고정 Profile 옵션을 덮어쓸 수 없습니다.")
        argument_index += 1
        option_value = True
        if argument_index < len(arguments) and not str(arguments[argument_index]).startswith("--"):
            option_value = arguments[argument_index]
            argument_index += 1
        options[option_name] = option_value
    if int(options.get("parallel", 1)) != 1:
        raise ValueError("현재 Basalt Profile은 단일 요청만 지원합니다.")
    return options


def write_native_configuration(configuration: dict) -> Path:
    """공식 v2 JSON과 별도 key 파일을 runtime/Basalt에만 기록합니다."""
    configuration_path = resolve_workspace_path(configuration["native_configuration_path"])
    runtime_directory = (WORKSPACE_DIRECTORY / "runtime/Basalt").resolve()
    if not configuration_path.resolve().is_relative_to(runtime_directory):
        raise ValueError("Basalt native 설정은 runtime/Basalt 아래에 저장해야 합니다.")
    api_key = configuration.get("api_key", "")
    if not api_key or api_key.startswith("CHANGE_ME") or "\n" in api_key or "\r" in api_key:
        raise ValueError("Basalt API key 설정이 올바르지 않습니다.")
    native_configuration = {
        "version": 2,
        "models": [model_options(configuration)],
        "server": {
            "host": configuration["host"], "port": configuration["port"],
            "allowed-host": configuration.get("allowed_hosts", ["host.docker.internal"]),
            "totals-file": str(runtime_directory / "totals.json"),
        },
    }
    configuration_path.parent.mkdir(parents=True, exist_ok=True)
    configuration_path.write_text(json.dumps(native_configuration, ensure_ascii=False, indent=2) + "\n",
                                  encoding="utf-8")
    configuration_path.with_suffix(".key").write_text(api_key + "\n", encoding="utf-8")
    return configuration_path


def runtime_environment(configuration: dict) -> dict:
    """Basalt 프로세스에만 전용 CUDA DLL·temporary 경로를 적용합니다."""
    environment = os.environ.copy()
    environment.update(PYTHONDONTWRITEBYTECODE="1", PYTHONNOUSERSITE="1", PYTHONUTF8="1")
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    environment_directory = Path(configuration["python"]).resolve().parents[1]
    nvidia_directory = environment_directory / "Lib/site-packages/nvidia"
    library_directories = {str(Path(configuration["exe"]).parent)}
    for library_path in nvidia_directory.rglob("*.dll"):
        library_directories.add(str(library_path.parent))
    environment["PATH"] = os.pathsep.join(sorted(library_directories)) + os.pathsep + environment.get("PATH", "")
    temporary_directory = WORKSPACE_DIRECTORY / "runtime/Basalt/temporary"
    temporary_directory.mkdir(parents=True, exist_ok=True)
    environment["TEMP"] = str(temporary_directory)
    environment["TMP"] = str(temporary_directory)
    return environment


def server_command(configuration: dict) -> list[str]:
    """공식 server를 전용 wrapper에서 실행하고 command line에 secret을 넣지 않습니다."""
    configuration_path = write_native_configuration(configuration)
    return [configuration["python"], "-X", "utf8", "-u", "-B",
            str(WORKSPACE_DIRECTORY / "scripts/Basalt/serve_profile.py"),
            "--config", str(configuration_path), "--engine-bin", configuration["exe"],
            "--api-key-file", str(configuration_path.with_suffix(".key"))]


def preparation_problem(configuration: dict, download_status_path: str) -> tuple | None:
    """모델 Load 없이 pinned 모델 파일·검증 receipt·설치 인터페이스를 확인합니다."""
    model_options(configuration)
    status_path = resolve_workspace_path(download_status_path)
    if not status_path.is_file():
        return "files_missing", "Basalt 모델 다운로드·SHA-256 검증 기록이 없습니다."
    download_status = read_json(status_path)
    if download_status.get("state") in ACTIVE_DOWNLOAD_STATES:
        percent = float(download_status.get("progress_percent", 0))
        return "downloading", f"Basalt 모델 다운로드·검증 중 ({percent:.1f}%)"
    if download_status.get("state") != "completed":
        return "files_missing", "Basalt 모델 다운로드가 완료되지 않았습니다. 상태·로그를 확인해 주세요."
    manifest_path = resolve_workspace_path(configuration["download_manifest_path"])
    if Path(download_status["manifest_path"]).resolve() != manifest_path.resolve():
        return "invalid", "Basalt 다운로드 검증 기록의 Manifest가 다릅니다."
    manifest = read_json(manifest_path)
    download_directory = (WORKSPACE_DIRECTORY / "data/Basalt").resolve()
    expected_model_path = Path(configuration["model_path"]).resolve()
    receipts = {}
    for receipt in download_status.get("verified_files", []):
        receipts[Path(receipt["path"]).resolve()] = receipt
    matched_model = False
    for entry in manifest["files"]:
        if not entry.get("sha256"):
            continue
        file_path = (download_directory / entry["destination"]).resolve()
        if not file_path.is_relative_to(download_directory):
            return "invalid", "Basalt Manifest의 다운로드 경로가 올바르지 않습니다."
        receipt = receipts.get(file_path, {})
        if (not file_path.is_file() or file_path.stat().st_size != entry["expected_bytes"] or
                receipt.get("bytes") != entry["expected_bytes"] or receipt.get("sha256") != entry["sha256"]):
            return "files_missing", "Basalt 모델 파일 또는 pinned SHA-256 검증 기록이 다릅니다."
        if file_path == expected_model_path:
            matched_model = True
    if not matched_model:
        return "invalid", "Basalt Profile이 pinned 모델 파일을 참조하지 않습니다."
    engine_directory = Path(configuration["engine_root"])
    for required_path in (Path(configuration["exe"]), Path(configuration["python"]),
                          engine_directory / "serve/server.py", engine_directory / "BUILD.json"):
        if not required_path.is_file():
            return "engine_missing", "Basalt Windows Engine·전용 Python 준비가 필요합니다."
    build = read_json(engine_directory / "BUILD.json")
    if build.get("release") != configuration["engine_release"] or not build.get("interface_verified"):
        return "engine_missing", "Basalt Release·인터페이스 검증 기록이 다릅니다."
    return None


def normalize_status(status: dict, models: dict, configuration: dict) -> dict:
    """공식 status와 model 목록의 이름·Context·서버 시작 시각을 함께 대조합니다."""
    options = model_options(configuration)
    expected_context = int(options["max-context"])
    entries = models.get("data", [])
    if status.get("service") != "basalt" or status.get("model") != configuration["model_name"]:
        raise ValueError("Basalt status의 Engine·Model ID가 다릅니다.")
    if len(entries) != 1:
        raise ValueError("Basalt는 고정 모델 하나만 등록해야 합니다.")
    model = entries[0]
    if (model.get("id") != configuration["model_name"] or model.get("owned_by") != "basalt" or
            model.get("meta", {}).get("n_ctx") != expected_context or
            status.get("context", {}).get("max_positions") != expected_context):
        raise ValueError("Basalt Model ID·Context가 Profile과 다릅니다.")
    started_at = status.get("started")
    if not isinstance(started_at, int) or started_at <= 0:
        raise ValueError("Basalt server 시작 시각이 없습니다.")
    in_flight = status.get("activity", {}).get("in_flight")
    if not isinstance(in_flight, int) or isinstance(in_flight, bool) or in_flight < 0:
        raise ValueError("Basalt 요청 수가 올바르지 않습니다.")
    return {"loaded": status.get("loaded") is True and model.get("status", {}).get("value") == "loaded",
            "activity": {"in_flight": in_flight}, "engine_instance_id": f"basalt:{started_at}"}


async def query_status(client, configuration: dict) -> dict:
    """생성·Load 없이 인증된 공식 status와 model 목록만 비동기로 조회합니다."""
    headers = {"Authorization": "Bearer " + configuration["api_key"]}
    documents = []
    for route in ("/v1/status", "/v1/models"):
        response = await client.get("http://127.0.0.1:8488" + route, headers=headers, timeout=3)
        response.raise_for_status()
        documents.append(response.json())
    return normalize_status(*documents, configuration)


def query_status_sync(client, configuration: dict) -> dict:
    """기동 worker에서 동일한 공식 readiness·identity 계약을 확인합니다."""
    headers = {"Authorization": "Bearer " + configuration["api_key"]}
    documents = []
    for route in ("/v1/status", "/v1/models"):
        response = client.get("http://127.0.0.1:8488" + route, headers=headers, timeout=3)
        response.raise_for_status()
        documents.append(response.json())
    return normalize_status(*documents, configuration)
