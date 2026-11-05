"""실제 모델 Load 없이 Infernix 준비·identity·native 제어 계약을 검증합니다."""

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import tomllib

import httpx
import pytest
import yaml

from management_server import infernix
from management_server.llm_runtime import ProfileRuntime
from scripts.Infernix.configure_librechat import add_model_configuration, MODEL_IDENTIFIER


def write_json(path, document):
    """독립 fixture 경로에 JSON을 저장합니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


@pytest.fixture
def prepared_profile(tmp_path, monkeypatch):
    """다섯 개의 작은 파일과 hash receipt로 다운로드 완료 상태를 구성합니다."""
    monkeypatch.setattr(infernix, "WORKSPACE_DIRECTORY", tmp_path)
    files = []
    receipts = []
    destinations = ["models/first.infernix", "models/second.infernix", "models/third.infernix",
                    "components/ple.ngram", "components/draft.infernix"]
    for destination in destinations:
        payload = destination.encode()
        file_path = tmp_path / "data/Infernix" / destination
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(payload)
        digest = hashlib.sha256(payload).hexdigest()
        files.append({"destination": destination, "expected_bytes": len(payload), "sha256": digest})
        receipts.append({"path": str(file_path), "bytes": len(payload), "sha256": digest})
    manifest_path = tmp_path / "manifest.json"
    status_path = tmp_path / "download.json"
    write_json(manifest_path, {"files": files})
    write_json(status_path, {"state": "completed", "manifest_path": str(manifest_path), "verified_files": receipts})
    engine_directory = tmp_path / "engine"
    engine_directory.mkdir()
    (engine_directory / "infernix-serve.exe").write_bytes(b"fixture")
    (engine_directory / "template.jinja").write_text("fixture", encoding="utf-8")
    write_json(engine_directory / "BUILD.json", {"release": "fixture", "interface_verified": True})
    configuration = {
        "exe": str(engine_directory / "infernix-serve.exe"), "engine_release": "fixture",
        "model_path": receipts[0]["path"], "ngram_volume": receipts[3]["path"],
        "draft_model": receipts[4]["path"], "chat_template": str(engine_directory / "template.jinja"),
        "model_name": "fixture-infernix", "api_key": "fixture-secret", "host": "0.0.0.0", "port": 8488,
        "args": ["--max-context", "262144", "--vram-headroom-mib", "8192", "--lm-head-draft"],
        "download_manifest_path": str(manifest_path),
        "native_configuration_path": str(tmp_path / "runtime/Infernix/server.local.toml"),
        "cwd": str(tmp_path / "runtime/Infernix/working"),
    }
    configuration_path = tmp_path / "configuration.json"
    write_json(configuration_path, configuration)
    profile = {"identifier": "fixture", "engine": "infernix", "model": "fixture-model",
               "model_name": configuration["model_name"], "label": "Fixture",
               "configuration_path": str(configuration_path), "download_status_path": str(status_path),
               "log_path": str(tmp_path / "server.log"), "minimum_ram_gib": 0, "minimum_free_vram_mib": 0}
    catalog_path = tmp_path / "catalog.json"
    write_json(catalog_path, {"engines": {"infernix": "Infernix"},
                             "models": {"fixture-model": {"label": "Fixture", "context_tokens": 262144}},
                             "profiles": [profile]})
    runtime = ProfileRuntime({"catalog_path": str(catalog_path), "configuration_path": str(configuration_path)},
                             runtime_directory=tmp_path / "runtime/ManagementServer")
    monkeypatch.setattr(runtime, "port_in_use", lambda: False)
    return SimpleNamespace(configuration=configuration, profile=profile, runtime=runtime,
                           status_path=status_path, manifest_path=manifest_path, receipts=receipts)


@pytest.mark.parametrize("option", ["--any-model-name", "--model-id", "--api-key", "--plan", "--config"])
def test_fixed_identity_options_cannot_be_overridden(prepared_profile, option):
    """Profile args로 model identity·인증·실행 모드를 우회하지 못합니다."""
    configuration = copy.deepcopy(prepared_profile.configuration)
    configuration["args"].append(option)
    with pytest.raises(ValueError, match="덮어쓸"):
        infernix.native_options(configuration)


def test_native_configuration_preserves_reserve_without_key_in_command(prepared_profile):
    """TOML 직렬화와 기존 8 GiB reserve, command line의 secret 제외를 검증합니다."""
    command = infernix.server_command(prepared_profile.configuration)
    assert "fixture-secret" not in " ".join(command)
    with Path(command[-1]).open("rb") as source:
        document = tomllib.load(source)
    assert document["api-key"] == "fixture-secret"
    assert document["model-id"] == "fixture-infernix"
    assert document["vram-headroom-mib"] == "8192"
    assert document["lm-head-draft"] is True


@pytest.mark.parametrize("state", sorted(infernix.ACTIVE_DOWNLOAD_STATES))
def test_download_in_progress_never_allows_start(prepared_profile, state):
    """최종 파일이 있어도 다운로드·검증 worker가 진행 중이면 기동을 거부합니다."""
    write_json(prepared_profile.status_path, {"state": state, "progress_percent": 99})
    description = prepared_profile.runtime.catalog.describe(prepared_profile.profile)
    assert description["state"] == "downloading"
    with pytest.raises(RuntimeError, match="다운로드"):
        prepared_profile.runtime.pin_operation("start", "fixture", "unused")


@pytest.mark.parametrize("damage", ["missing_shard", "truncated_ple", "wrong_receipt", "wrong_manifest", "missing_engine"])
def test_readiness_requires_every_pinned_asset(prepared_profile, damage):
    """Shard·PLE·drafter와 검증 receipt 중 하나라도 다르면 준비 완료로 표시하지 않습니다."""
    assert prepared_profile.runtime.catalog.describe(prepared_profile.profile)["state"] == "available"
    if damage == "missing_shard":
        Path(prepared_profile.receipts[2]["path"]).unlink()
    elif damage == "truncated_ple":
        Path(prepared_profile.receipts[3]["path"]).write_bytes(b"short")
    elif damage == "missing_engine":
        Path(prepared_profile.configuration["exe"]).unlink()
    else:
        status = json.loads(prepared_profile.status_path.read_text())
        if damage == "wrong_receipt":
            status["verified_files"][4]["sha256"] = "invalid"
        else:
            status["manifest_path"] = str(prepared_profile.status_path)
        write_json(prepared_profile.status_path, status)
    assert prepared_profile.runtime.catalog.describe(prepared_profile.profile)["state"] != "available"


def test_corrupt_download_status_does_not_break_catalog(prepared_profile):
    """손상된 상태 파일은 해당 profile의 오류로 표시하며 전체 관리 상태를 깨지 않습니다."""
    prepared_profile.status_path.write_text("{", encoding="utf-8")
    assert prepared_profile.runtime.catalog.public_profiles()[0]["state"] == "invalid"


def native_documents():
    """Upstream native API의 최소 응답을 구성합니다."""
    return {"/health": {"status": "ok"},
            "/v1/models": {"data": [{"id": "fixture-infernix", "owned_by": "infernix", "max_model_len": 262144}]},
            "/metrics": {"engine": {"name": "infernix", "model": "fixture-infernix"},
                         "live": {"running": 1, "waiting": 2, "prefilling": 1, "instance_id": "native-instance"}}}


def test_native_status_counts_prefill_once_and_uses_read_only_routes(prepared_profile):
    """Prefill은 running의 부분집합이며 상태 조회에 generation·Load API를 쓰지 않습니다."""
    documents = native_documents()
    requests = []

    def handle_request(request):
        """인증과 조회 route를 기록하고 fixture 응답만 반환합니다."""
        requests.append(request)
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer fixture-secret"
        return httpx.Response(200, json=documents[request.url.path])

    async def read_status():
        """독립 MockTransport로 async adapter 계약을 조회합니다."""
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle_request)) as client:
            return await infernix.query_status(client, prepared_profile.configuration)

    result = asyncio.run(read_status())
    assert result["activity"]["in_flight"] == 3
    assert result["engine_instance_id"] == "native-instance"
    assert len(requests) == 3
    assert requests[-1].url.query == b"format=json"


@pytest.mark.parametrize("damage", ["model", "context", "engine", "instance"])
def test_wrong_native_identity_cannot_be_ready(prepared_profile, damage):
    """다른 모델·Context·Engine과 instance identity 누락을 거부합니다."""
    documents = native_documents()
    if damage == "model":
        documents["/v1/models"]["data"][0]["id"] = "other-model"
    elif damage == "context":
        documents["/v1/models"]["data"][0]["max_model_len"] = 32768
    elif damage == "engine":
        documents["/metrics"]["engine"]["name"] = "other-engine"
    else:
        del documents["/metrics"]["live"]["instance_id"]
    with pytest.raises(ValueError):
        infernix.normalize_status(*documents.values(), prepared_profile.configuration)


def test_start_uses_native_process_and_pins_engine_instance(prepared_profile, monkeypatch):
    """단일 native executable과 TOML로 실행하며 소유 listener의 readiness를 기록합니다."""
    runtime = prepared_profile.runtime
    monkeypatch.setattr(runtime, "check_resources", lambda profile: None)
    process = SimpleNamespace(pid=12345, create_time=lambda: 100,
                              net_connections=lambda kind: [SimpleNamespace(status="LISTEN", laddr=SimpleNamespace(port=8488))])
    monkeypatch.setattr(runtime, "owned_process", lambda instance: process if instance and instance.get("pid") else None)
    monkeypatch.setattr("management_server.llm_runtime.psutil.Process", lambda identifier: process)
    commands = []

    def spawn_process(command, **options):
        """실제 native 실행 없이 command와 실행 경계를 검증합니다."""
        commands.append(command)
        assert Path(options["cwd"]) == Path(prepared_profile.configuration["cwd"])
        assert "fixture-secret" not in " ".join(command)
        return process

    monkeypatch.setattr("management_server.llm_runtime.subprocess.Popen", spawn_process)
    monkeypatch.setattr(infernix, "query_status_sync", lambda client, configuration: {
        "loaded": True, "engine_instance_id": "native-instance"})
    revision = runtime.catalog.revision(prepared_profile.profile)
    selection = runtime.pin_operation("start", "fixture", revision)
    instance = runtime.start(selection)
    assert commands[0][0] == prepared_profile.configuration["exe"]
    assert commands[0][1] == "--config"
    assert instance["engine_instance_id"] == "native-instance"
    assert runtime.read_instance()["pid"] == 12345


def test_librechat_registration_is_idempotent_and_preserves_existing_models():
    """Infernix 목록만 추가하고 기존 endpoint·models·주석과 설정은 보존합니다."""
    template_path = Path(__file__).resolve().parents[2] / "config/LibreChat/librechat.local.yaml.template"
    document = yaml.safe_load(template_path.read_text(encoding="utf-8"))
    endpoint = next(entry for entry in document["endpoints"]["custom"] if entry["name"] == "Strata")
    endpoint["models"]["default"].remove(MODEL_IDENTIFIER)
    del endpoint["tokenConfig"][MODEL_IDENTIFIER]
    document["modelSpecs"]["list"] = [entry for entry in document["modelSpecs"]["list"]
                                         if entry["preset"]["model"] != MODEL_IDENTIFIER]
    original = "# keep this comment\n" + yaml.safe_dump(document, allow_unicode=True, sort_keys=False)
    updated = add_model_configuration(original)
    assert updated.startswith("# keep this comment\n")
    assert add_model_configuration(updated) == updated
    actual = yaml.safe_load(updated)
    actual_endpoint = next(entry for entry in actual["endpoints"]["custom"] if entry["name"] == "Strata")
    assert actual_endpoint["models"]["default"][:-1] == endpoint["models"]["default"]
    assert actual["summarization"] == document["summarization"]
