"""실제 모델 Load 없이 Basalt 준비·인증·소유권을 검증합니다."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from management_server import basalt
from management_server.llm_runtime import ProfileRuntime


def write_document(document_path, document):
    """독립 fixture 디렉터리에 JSON 문서를 저장합니다."""
    document_path.parent.mkdir(parents=True, exist_ok=True)
    document_path.write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def prepared_profile(tmp_path, monkeypatch):
    """작은 모델 파일과 설치·hash 검증 receipt로 기동 가능한 fixture를 만듭니다."""
    monkeypatch.setattr(basalt, "WORKSPACE_DIRECTORY", tmp_path)
    model_path = tmp_path / "data/Basalt/models/model.basalt"
    model_path.parent.mkdir(parents=True)
    payload = b"fixture-basalt-model"
    model_path.write_bytes(payload)
    model_digest = hashlib.sha256(payload).hexdigest()
    manifest_path = tmp_path / "manifest.json"
    status_path = tmp_path / "download.json"
    write_document(manifest_path, {"files": [{"destination": "models/model.basalt",
                   "expected_bytes": len(payload), "sha256": model_digest}]})
    write_document(status_path, {"state": "completed", "manifest_path": str(manifest_path),
                   "verified_files": [{"path": str(model_path), "bytes": len(payload), "sha256": model_digest}]})
    engine_directory = tmp_path / "engine"
    for relative_path in ("bin/basalt.exe", "serve/server.py"):
        file_path = engine_directory / relative_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"fixture")
    python_path = tmp_path / ".venv/Basalt/Scripts/python.exe"
    python_path.parent.mkdir(parents=True)
    python_path.write_bytes(b"fixture")
    write_document(engine_directory / "BUILD.json", {"release": "fixture", "interface_verified": True})
    configuration = {
        "engine_release": "fixture", "engine_root": str(engine_directory),
        "exe": str(engine_directory / "bin/basalt.exe"), "python": str(python_path),
        "model_path": str(model_path), "model_name": "fixture-basalt", "api_key": "fixture-secret",
        "host": "0.0.0.0", "port": 8488, "args": ["--max-context", "262144", "--parallel", "1", "--kv", "int8"],
        "download_manifest_path": str(manifest_path),
        "native_configuration_path": str(tmp_path / "runtime/Basalt/working/server.local.json"),
        "cwd": str(tmp_path / "runtime/Basalt/working"),
    }
    configuration_path = tmp_path / "configuration.json"
    write_document(configuration_path, configuration)
    profile = {"identifier": "fixture", "engine": "basalt", "model": "fixture-model", "model_name": "fixture-basalt",
               "configuration_path": str(configuration_path), "download_status_path": str(status_path),
               "label": "Fixture", "log_path": str(tmp_path / "server.log"),
               "minimum_ram_gib": 0, "minimum_free_vram_mib": 0}
    catalog_path = tmp_path / "catalog.json"
    write_document(catalog_path, {"engines": {"basalt": "Basalt"},
                   "models": {"fixture-model": {"label": "Fixture", "context_tokens": 262144}}, "profiles": [profile]})
    runtime = ProfileRuntime({"catalog_path": str(catalog_path), "configuration_path": str(configuration_path)},
                             runtime_directory=tmp_path / "runtime/ManagementServer")
    return SimpleNamespace(configuration=configuration, profile=profile, runtime=runtime,
                           manifest_path=manifest_path, status_path=status_path, model_path=model_path)


@pytest.mark.parametrize("option", ["--alias", "--model", "--api-key", "--api-key-file", "--config", "--lazy", "--mock-engine"])
def test_fixed_profile_options_cannot_be_overridden(prepared_profile, option):
    """다른 모델·인증·자동 Load 모드가 args를 통해 삽입되지 못합니다."""
    configuration = copy.deepcopy(prepared_profile.configuration)
    configuration["args"].extend([option, "override"])
    with pytest.raises(ValueError, match="덮어쓸"):
        basalt.server_command(configuration)


def test_native_configuration_keeps_secret_outside_json_and_command(prepared_profile):
    """API key는 공식 --api-key-file로만 전달하고 model alias·Context는 고정합니다."""
    command = basalt.server_command(prepared_profile.configuration)
    native_path = Path(prepared_profile.configuration["native_configuration_path"])
    native_text = native_path.read_text(encoding="utf-8")
    native_configuration = json.loads(native_text)
    assert "fixture-secret" not in native_text
    assert "fixture-secret" not in " ".join(command)
    assert native_path.with_suffix(".key").read_text(encoding="utf-8") == "fixture-secret\n"
    assert native_configuration["models"][0]["alias"] == "fixture-basalt"
    assert native_configuration["models"][0]["max-context"] == "262144"
    assert native_configuration["server"]["port"] == 8488


@pytest.mark.parametrize("download_state", sorted(basalt.ACTIVE_DOWNLOAD_STATES))
def test_downloading_profile_cannot_start(prepared_profile, download_state):
    """최종 파일이 존재해도 백그라운드 다운로드·검증 중에는 기동을 차단합니다."""
    write_document(prepared_profile.status_path, {"state": download_state, "progress_percent": 42})
    description = prepared_profile.runtime.catalog.describe(prepared_profile.profile)
    assert description["state"] == "downloading"
    assert "42.0%" in description["problem"]
    with pytest.raises(RuntimeError, match="다운로드"):
        prepared_profile.runtime.pin_operation("start", "fixture", "unused")


@pytest.mark.parametrize("damage", ["truncated_model", "wrong_digest", "wrong_manifest", "missing_engine"])
def test_preparation_rejects_incomplete_or_unverified_installation(prepared_profile, damage):
    """파일 크기·hash receipt·Manifest·Engine 중 하나라도 다르면 available이 아닙니다."""
    catalog = prepared_profile.runtime.catalog
    assert catalog.describe(prepared_profile.profile)["state"] == "available"
    if damage == "truncated_model":
        prepared_profile.model_path.write_bytes(b"short")
    elif damage == "missing_engine":
        Path(prepared_profile.configuration["exe"]).unlink()
    else:
        download_status = json.loads(prepared_profile.status_path.read_text(encoding="utf-8"))
        if damage == "wrong_digest":
            download_status["verified_files"][0]["sha256"] = "different"
        else:
            download_status["manifest_path"] = str(prepared_profile.status_path)
        write_document(prepared_profile.status_path, download_status)
    assert catalog.describe(prepared_profile.profile)["state"] != "available"


def native_documents():
    """설치된 Basalt v0.5.7 공식 API 형태의 최소 응답을 반환합니다."""
    return {
        "/v1/status": {"service": "basalt", "model": "fixture-basalt", "loaded": True,
                       "started": 1234567890, "context": {"max_positions": 262144}, "activity": {"in_flight": 2}},
        "/v1/models": {"data": [{"id": "fixture-basalt", "owned_by": "basalt",
                                "status": {"value": "loaded"}, "meta": {"n_ctx": 262144}}]},
    }


def test_status_uses_authenticated_read_only_routes(prepared_profile):
    """생성이나 Load 요청 없이 정확한 Model ID·Context·진행 요청 수를 조회합니다."""
    documents = native_documents()
    requests = []

    def handle_request(request):
        """인증·method를 검사하고 공식 응답 fixture를 반환합니다."""
        requests.append(request)
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer fixture-secret"
        return httpx.Response(200, json=documents[request.url.path])

    async def read_status():
        """네트워크 접근 없이 async adapter를 실행합니다."""
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:
            return await basalt.query_status(client, prepared_profile.configuration)

    result = asyncio.run(read_status())
    assert result["loaded"] is True
    assert result["activity"]["in_flight"] == 2
    assert result["engine_instance_id"] == "basalt:1234567890"
    assert len(requests) == 2


@pytest.mark.parametrize("damage", ["service", "model", "context", "started", "activity"])
def test_other_engine_or_model_is_never_ready(prepared_profile, damage):
    """다른 Engine·모델·Context와 손상된 실행 identity를 ready로 표시하지 않습니다."""
    documents = native_documents()
    status = documents["/v1/status"]
    if damage == "context":
        documents["/v1/models"]["data"][0]["meta"]["n_ctx"] = 8192
    elif damage == "activity":
        status["activity"]["in_flight"] = -1
    elif damage == "started":
        status["started"] = None
    else:
        status[damage] = "other"
    with pytest.raises(ValueError):
        basalt.normalize_status(*documents.values(), prepared_profile.configuration)


def test_start_pins_official_server_identity_without_key_in_command(prepared_profile, monkeypatch):
    """소유 listener가 확인된 Basalt에만 연결하고 server 시작 시각을 instance에 고정합니다."""
    runtime = prepared_profile.runtime
    commands = []

    def check_resources(profile):
        """Fixture는 GPU를 조회하거나 변경하지 않습니다."""
        return None

    def port_in_use():
        """Fixture port는 비어 있습니다."""
        return False

    def process_created_at():
        """Fixture process의 고정 생성 시각을 반환합니다."""
        return 100

    process = SimpleNamespace(pid=12345, create_time=process_created_at)

    def owned_process(instance):
        """PID가 기록된 뒤에만 fixture process를 소유합니다."""
        return process if instance and instance.get("pid") else None

    def process_factory(process_identifier):
        """실제 process 대신 독립 fixture를 반환합니다."""
        return process

    def owns_listener(candidate):
        """기록된 process의 listener만 허용합니다."""
        return candidate is process

    def spawn_process(command, **options):
        """기동 command와 격리된 환경을 기록하고 실제 process는 만들지 않습니다."""
        commands.append(command)
        assert options["env"]["TEMP"].endswith("Basalt\\temporary")
        return process

    def handle_request(request):
        """공식 status·model 응답만 반환합니다."""
        return httpx.Response(200, json=native_documents()[request.url.path])

    original_client = httpx.Client

    def create_client(**options):
        """HTTP client를 실제 네트워크 대신 공식 응답 fixture에 연결합니다."""
        return original_client(transport=httpx.MockTransport(handle_request))

    monkeypatch.setattr(runtime, "check_resources", check_resources)
    monkeypatch.setattr(runtime, "port_in_use", port_in_use)
    monkeypatch.setattr(runtime, "owned_process", owned_process)
    monkeypatch.setattr(runtime, "process_tree_owns_listener", owns_listener)
    monkeypatch.setattr("management_server.llm_runtime.psutil.Process", process_factory)
    monkeypatch.setattr("management_server.llm_runtime.subprocess.Popen", spawn_process)
    monkeypatch.setattr("management_server.llm_runtime.httpx.Client", create_client)
    operation = {"profile_id": "fixture", "configuration_revision": runtime.catalog.revision(prepared_profile.profile)}
    instance = runtime.start(operation)
    assert instance["engine_instance_id"] == "basalt:1234567890"
    assert "scripts" in " ".join(commands[0])
    assert "serve_profile.py" in " ".join(commands[0])
    assert "fixture-secret" not in " ".join(commands[0])
