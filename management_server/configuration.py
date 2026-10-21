"""관리 서버 전용 local 설정과 기존 LLM 설정을 읽습니다."""

import json
import os
from pathlib import Path


WORKSPACE_DIRECTORY = Path(__file__).resolve().parent.parent
CONFIGURATION_PATH = WORKSPACE_DIRECTORY / "config/ManagementServer/management.local.json"


def read_json(configuration_path):
    """BOM이 있는 기존 Windows JSON 설정도 읽습니다."""
    return json.loads(Path(configuration_path).read_text(encoding="utf-8-sig"))


def load_configuration():
    """실행 환경에서 지정한 설정 또는 기본 local 설정을 검증합니다."""
    configuration_path = Path(os.environ.get("LLM_HOME_CONFIGURATION", CONFIGURATION_PATH))
    if not configuration_path.is_file():
        raise FileNotFoundError(
            "management.local.json.template을 management.local.json으로 복사하고 필수 값을 바꿔 주세요."
        )
    configuration = read_json(configuration_path)
    for field_name in ("access_string", "session_secret"):
        field_value = configuration.get(field_name)
        if not isinstance(field_value, str) or not field_value.strip() or field_value.startswith(
            ("CHANGE_ME_", "REPLACE_LOCALLY", "GENERATE_LOCALLY")
        ):
            raise ValueError(f"관리 서버 설정의 {field_name} 항목을 실제 값으로 바꿔 주세요.")
    if len(configuration["session_secret"]) < 32:
        raise ValueError("관리 서버 설정의 session_secret은 32자 이상이어야 합니다.")
    if configuration["llm"]["adapter"] != "strata":
        raise ValueError("현재 지원하는 LLM adapter는 strata입니다.")
    return configuration


def resolve_workspace_path(relative_path):
    """Repo 기준 경로를 절대 경로로 바꿉니다."""
    return WORKSPACE_DIRECTORY / relative_path
