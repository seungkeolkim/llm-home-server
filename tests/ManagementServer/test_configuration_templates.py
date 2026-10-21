"""복사한 template의 필수 입력 검사와 기존 local 설정 보존을 검증합니다."""

import importlib.util
import json
from pathlib import Path

import pytest

from management_server.configuration import load_configuration


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]


@pytest.fixture
def management_configuration_path(tmp_path, monkeypatch):
    """실제 local 설정 대신 임시 설정 파일을 사용합니다."""
    configuration_path = tmp_path / "management.local.json"
    monkeypatch.setenv("LLM_HOME_CONFIGURATION", str(configuration_path))
    return configuration_path


def test_missing_management_configuration_requires_manual_copy(management_configuration_path):
    """파일이 없을 때 secret을 자동 생성하지 않고 복사할 template을 안내합니다."""
    with pytest.raises(FileNotFoundError, match=r"management.local.json.template"):
        load_configuration()
    assert not management_configuration_path.exists()


@pytest.mark.parametrize("field_name", ("access_string", "session_secret"))
def test_management_configuration_rejects_template_placeholders(management_configuration_path, field_name):
    """길이 조건을 만족하는 안내 문자열도 실제 secret으로 받아들이지 않습니다."""
    template_path = WORKSPACE_DIRECTORY / "config/ManagementServer/management.local.json.template"
    configuration = json.loads(template_path.read_text(encoding="utf-8"))
    configuration["access_string"] = "fixture-access"
    configuration["session_secret"] = "fixture-secret-" * 4
    configuration[field_name] = "CHANGE_ME_" + "placeholder" * 5
    management_configuration_path.write_text(json.dumps(configuration), encoding="utf-8")
    before_contents = management_configuration_path.read_bytes()
    with pytest.raises(ValueError, match=field_name):
        load_configuration()
    assert management_configuration_path.read_bytes() == before_contents


def test_management_configuration_preserves_user_values(management_configuration_path):
    """사용자가 정한 접속 문자열과 session secret을 그대로 읽고 파일을 쓰지 않습니다."""
    template_path = WORKSPACE_DIRECTORY / "config/ManagementServer/management.local.json.template"
    configuration = json.loads(template_path.read_text(encoding="utf-8"))
    configuration["access_string"] = "fixture-access"
    configuration["session_secret"] = "fixture-secret-" * 4
    management_configuration_path.write_text(json.dumps(configuration), encoding="utf-8")
    before_contents = management_configuration_path.read_bytes()
    assert load_configuration() == configuration
    assert management_configuration_path.read_bytes() == before_contents


@pytest.fixture
def strata_runner(tmp_path, monkeypatch):
    """Strata source·Engine·설정 경로를 임시 workspace로 격리합니다."""
    script_path = WORKSPACE_DIRECTORY / "scripts/Strata/strata_runner.py"
    specification = importlib.util.spec_from_file_location("template_test_strata_runner", script_path)
    runner = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(runner)
    configuration_directory = tmp_path / "config/Strata"
    configuration_directory.mkdir(parents=True)
    source_directory = tmp_path / "external_repo/Strata"
    source_directory.mkdir(parents=True)
    (source_directory / "strata.py").write_text("", encoding="utf-8")
    replacements = {
        "RUNNER_ROOT": tmp_path,
        "SOURCE_ROOT": source_directory,
        "CONFIGURATION_ROOT": configuration_directory,
        "RUNTIME_ROOT": tmp_path / "runtime/Strata",
        "LOCAL_CONFIGURATION": configuration_directory / "strata.local.json",
        "ENVIRONMENT_CONFIGURATION": configuration_directory / "environment.local.json",
    }
    for constant_name, replacement in replacements.items():
        monkeypatch.setattr(runner, constant_name, replacement)
    for template_name in ("strata.local.json.template", "strata.local.shared-settings.json.template"):
        source_path = WORKSPACE_DIRECTORY / "config/Strata" / template_name
        (configuration_directory / template_name).write_bytes(source_path.read_bytes())
    return runner


def test_strata_missing_or_unedited_configuration_is_not_generated(strata_runner):
    """설정 파일을 자동 생성하지 않고 편집하지 않은 API key도 거부합니다."""
    with pytest.raises(FileNotFoundError, match=r"strata.local.json.template"):
        strata_runner.read_local_configuration()
    assert not strata_runner.LOCAL_CONFIGURATION.exists()
    template_path = strata_runner.CONFIGURATION_ROOT / "strata.local.json.template"
    strata_runner.LOCAL_CONFIGURATION.write_bytes(template_path.read_bytes())
    with pytest.raises(ValueError, match="api_key"):
        strata_runner.read_local_configuration()


def test_strata_preparation_expands_paths_once_and_preserves_api_key(strata_runner, tmp_path, monkeypatch):
    """복사한 설정의 경로만 확장하고 재준비해도 key와 shared settings를 유지합니다."""
    configuration = json.loads((strata_runner.CONFIGURATION_ROOT / "strata.local.json.template").read_text(encoding="utf-8"))
    configuration["api_key"] = "fixture-strata-api-key"
    strata_runner.write_json(strata_runner.LOCAL_CONFIGURATION, configuration)
    monkeypatch.setattr(strata_runner.importlib, "import_module", lambda name: None)
    monkeypatch.setattr(strata_runner, "resolve_engine_package", lambda environment: {"root": str(tmp_path / "engine")})
    monkeypatch.setattr(strata_runner, "ensure_vision_projector", lambda *arguments: None)
    monkeypatch.setattr(strata_runner, "validate_assets", lambda *arguments: None)
    monkeypatch.setattr(strata_runner, "invoke_strata", lambda *arguments: 0)
    assert strata_runner.prepare_environment(tmp_path / "models") == 0
    prepared_configuration = strata_runner.read_local_configuration()
    assert prepared_configuration["api_key"] == "fixture-strata-api-key"
    assert prepared_configuration["cwd"] == (tmp_path / "runtime/Strata/working").as_posix()
    shared_settings_path = strata_runner.CONFIGURATION_ROOT / "strata.local.shared-settings.json"
    shared_settings_path.write_text('{"reasoning_effort":"high"}', encoding="utf-8")
    before_contents = strata_runner.LOCAL_CONFIGURATION.read_bytes()
    assert strata_runner.prepare_environment(tmp_path / "models") == 0
    assert strata_runner.LOCAL_CONFIGURATION.read_bytes() == before_contents
    assert json.loads(shared_settings_path.read_text(encoding="utf-8")) == {"reasoning_effort": "high"}
