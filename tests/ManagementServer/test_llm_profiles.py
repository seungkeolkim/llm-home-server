"""실제 LLM Load 없이 선택 고정·단일 instance·기존 이력 보존을 검증합니다."""

import json
from types import SimpleNamespace

import pytest

from management_server.llm_runtime import ProfileRuntime
from management_server.operations import OperationStore


@pytest.fixture
def runtime(tmp_path, monkeypatch):
    """실제 설정과 process를 건드리지 않는 독립 catalog를 만듭니다."""
    native_path = tmp_path / "native.json"
    native_path.write_text(json.dumps({"port": 8488, "api_key": "fixture-key", "model_name": "fixture-model",
                                      "args": ["--max-context", "153600"]}), encoding="utf-8")
    catalog_path = tmp_path / "catalog.json"
    catalog_path.write_text(json.dumps({"engines": {"strata": "Strata"},
        "models": {"model": {"label": "Fixture", "context_tokens": 153600}},
        "profiles": [{"identifier": "fixture", "engine": "strata", "model": "model",
                      "configuration_path": str(native_path), "label": "Fixture",
                      "log_path": str(tmp_path / "engine.log"), "minimum_ram_gib": 0,
                      "minimum_free_vram_mib": 0}]}), encoding="utf-8")
    runtime = ProfileRuntime({"catalog_path": str(catalog_path), "configuration_path": str(native_path)},
                             runtime_directory=tmp_path / "runtime")
    monkeypatch.setattr(runtime, "port_in_use", lambda: False)
    return runtime


def test_revision_change_after_selection_is_rejected_before_execution(runtime, monkeypatch):
    """접수한 profile의 파일이 바뀌어도 최신 설정으로 바꿔 기동하지 않습니다."""
    profile = runtime.catalog.get("fixture")
    monkeypatch.setattr(runtime.catalog, "describe", lambda profile: {
        "state": "available", "revision": runtime.catalog.revision(profile)})
    selection = runtime.pin_operation("start", "fixture", runtime.catalog.revision(profile))
    native_path = runtime.catalog.profiles["fixture"]["configuration_path"]
    with open(native_path, "w", encoding="utf-8") as output:
        json.dump({"changed": True}, output)
    monkeypatch.setattr(runtime, "check_resources", lambda profile: pytest.fail("기동하면 안 됩니다."))
    with pytest.raises(RuntimeError, match="설정이 변경"):
        runtime.start(selection)


def test_occupied_port_blocks_start_without_stopping_foreign_process(runtime, monkeypatch):
    """관리 외 process가 공통 port를 쓰면 process를 종료하거나 덮어쓰지 않습니다."""
    monkeypatch.setattr(runtime.catalog, "describe", lambda profile: {"state": "available", "revision": "fixed"})
    monkeypatch.setattr(runtime, "port_in_use", lambda: True)
    with pytest.raises(RuntimeError, match="이미 실행"):
        runtime.pin_operation("start", "fixture", "fixed")
    assert not runtime.record_path.exists()


def test_stop_pins_actual_instance_and_rejects_replacement(runtime, monkeypatch):
    """다음 선택값과 무관하게 실제 instance를 고정하며 교체되면 종료하지 않습니다."""
    instance = {"identifier": "actual-instance", "profile_id": "fixture", "configuration_revision": "old-revision"}
    runtime.write_instance(instance)
    monkeypatch.setattr(runtime, "owned_process", lambda instance: object())
    selection = runtime.pin_operation("stop", "different-next-selection", "different-revision")
    assert selection["instance_id"] == "actual-instance"
    assert selection["configuration_revision"] == "old-revision"
    runtime.write_instance({**instance, "identifier": "replacement"})
    with pytest.raises(RuntimeError, match="instance가 변경"):
        runtime.stop(selection)


def test_reused_pid_is_never_owned(runtime, monkeypatch):
    """이전 instance의 PID를 재사용한 다른 process를 소유하지 않습니다."""
    process = SimpleNamespace(create_time=lambda: 200, cmdline=lambda: ["expected-marker"])
    monkeypatch.setattr("management_server.llm_runtime.psutil.Process", lambda identifier: process)
    assert runtime.owned_process({"pid": 123, "process_created_at": 100,
                                  "process_marker": "expected-marker"}) is None


def test_protected_strata_uses_native_identity_instead_of_command_line(runtime, monkeypatch):
    """Strata의 보호된 command line을 읽지 않고 검증된 native instance를 확인합니다."""
    def forbidden_command_line():
        """보호된 process 조회가 호출되면 실패시킵니다."""
        pytest.fail("Strata command line을 조회하면 안 됩니다.")

    process = SimpleNamespace(create_time=lambda: 200, cmdline=forbidden_command_line)
    monkeypatch.setattr("management_server.llm_runtime.psutil.Process", lambda identifier: process)
    monkeypatch.setattr(runtime, "strata_status", lambda: {
        "owner_id": "native-owner", "instance_id": "native-instance", "child_pid": 123})
    instance = {"pid": 123, "process_created_at": 200, "native_owner_id": "native-owner",
                "native_instance_id": "native-instance"}
    assert runtime.owned_process(instance) is process
    assert runtime.owned_process({**instance, "native_instance_id": "previous-instance"}) is None


def test_profile_metadata_migration_preserves_existing_history(tmp_path):
    """이전 SQLite schema와 이력을 보존하며 새 profile metadata만 추가합니다."""
    import sqlite3
    database_path = tmp_path / "operations.sqlite3"
    with sqlite3.connect(database_path) as connection:
        connection.execute("""CREATE TABLE operations(identifier TEXT PRIMARY KEY, target TEXT NOT NULL,
            action TEXT NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, finished_at REAL,
            worker_pid INTEGER, message TEXT NOT NULL DEFAULT '')""")
        connection.execute("INSERT INTO operations VALUES('old','llm','start','succeeded',1,2,NULL,'preserved')")
    store = OperationStore(database_path)
    selection = {"profile_id": "fixture", "configuration_revision": "fixed-revision", "instance_id": None}
    identifier = store.create("llm", "start", selection=selection)
    assert store.get("old")["message"] == "preserved"
    assert store.get(identifier)["profile_id"] == "fixture"
    assert "fixture-key" not in json.dumps(store.recent())


def test_public_catalog_hides_keys_and_rejects_context_mismatch(runtime):
    """표시 목록에 secret을 노출하지 않고 Engine context 차이를 검출합니다."""
    native_path = runtime.catalog.profiles["fixture"]["configuration_path"]
    with open(native_path, "w", encoding="utf-8") as output:
        json.dump({"port": 8488, "api_key": "fixture-key", "model_name": "fixture-model",
                   "args": ["--max-context", "32768"]}, output)
    public_profiles = runtime.catalog.public_profiles()
    assert "fixture-key" not in json.dumps(public_profiles)
    assert public_profiles[0]["state"] == "invalid"
