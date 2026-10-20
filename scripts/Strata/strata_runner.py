"""공식 source를 수정하지 않고 로컬 환경과 Strata managed runtime을 연결합니다."""

from __future__ import annotations

import argparse
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys


RUNNER_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = RUNNER_ROOT / "external_repo" / "Strata"
CONFIGURATION_ROOT = RUNNER_ROOT / "config" / "Strata"
RUNTIME_ROOT = RUNNER_ROOT / "runtime" / "Strata"
LOCAL_CONFIGURATION = CONFIGURATION_ROOT / "strata.local.json"
ENVIRONMENT_CONFIGURATION = CONFIGURATION_ROOT / "environment.local.json"
PROFILE_NAME = "sc117-iq3-xxs"


def read_json(path: Path) -> dict:
    """UTF-8 BOM 유무와 관계없이 JSON object를 읽습니다."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, value: dict) -> None:
    """읽기 쉬운 UTF-8 JSON을 바깥 설정 폴더에 저장합니다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def runtime_environment(data_directory: Path) -> dict[str, str]:
    """자식 프로세스에만 적용할 dependency 및 runtime 경로를 구성합니다."""
    environment = os.environ.copy()
    environment.update({
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "STRATA_NO_ACQUIRE": "1",
        "STRATA_REQUIRE_SIGNED_COMPONENTS": "1",
        "STRATA_COMPONENTS_DIR": str(data_directory / "components"),
        "STRATA_PROFILE_DIR": str(CONFIGURATION_ROOT / "profiles"),
        "STRATA_RUNTIME_DIR": str(RUNTIME_ROOT / "managed"),
    })
    # 외부 Python 경로가 이 환경에 주입되지 않도록 자식 환경에서만 제거합니다.
    environment.pop("PYTHONPATH", None)
    environment.pop("PYTHONHOME", None)
    return environment


def invoke_strata(arguments: list[str], environment: dict[str, str]) -> int:
    """바깥 Python으로 공식 CLI를 실행하고 원래 exit code를 돌려줍니다."""
    command = [sys.executable, "-B", str(SOURCE_ROOT / "strata.py"), *arguments]
    completed = subprocess.run(command, cwd=RUNNER_ROOT, env=environment, check=False)
    return completed.returncode


def expand_template(value: object, substitutions: dict[str, str]) -> object:
    """JSON 구조를 유지하며 명시된 경로 placeholder만 확장합니다."""
    if isinstance(value, dict):
        return {key: expand_template(item, substitutions) for key, item in value.items()}
    if isinstance(value, list):
        return [expand_template(item, substitutions) for item in value]
    if isinstance(value, str):
        for placeholder, replacement in substitutions.items():
            value = value.replace(placeholder, replacement)
    return value


def validate_assets(data_directory: Path, configuration: dict) -> None:
    """기존 모델의 크기와 Pack, tokenizer, CUDA DLL의 존재를 확인합니다."""
    model_directory = data_directory / "models/SC117/Qwen3.8-Flash-Next-GSQ-RCO-abliterated-GGUF"
    manifest = read_json(model_directory / "download_manifest.json")
    for entry in manifest["files"]:
        model_file = model_directory / entry["rfilename"]
        if model_file.stat().st_size != entry["size"]:
            raise ValueError(f"Model size mismatch: {model_file}")
    pack_directory = data_directory / "packs/sc117_iq3_xxs"
    for filename in ("dense.bin", "index.txt", "native_experts.txt", "conversions.json"):
        if not (pack_directory / filename).is_file():
            raise FileNotFoundError(pack_directory / filename)
    tokenizer_directory = Path(configuration["tokenizer"])
    if not (tokenizer_directory / "tokenizer.json").is_file():
        raise FileNotFoundError(tokenizer_directory / "tokenizer.json")
    for filename in ("cudart64_13.dll", "cublas64_13.dll", "cublasLt64_13.dll"):
        library_path = Path(configuration["lib_dirs"][0]) / filename
        if not library_path.is_file():
            raise FileNotFoundError(library_path)
    print(f"Model manifest sizes, Pack, tokenizer and venv CUDA DLLs checked: {data_directory}", flush=True)


def prepare_environment(data_directory: Path) -> int:
    """설정을 최초 생성하고 dependency와 Engine을 검증한 뒤 saved profile을 준비합니다."""
    data_directory = data_directory.resolve()
    if ENVIRONMENT_CONFIGURATION.exists():
        previous_directory = Path(read_json(ENVIRONMENT_CONFIGURATION)["data_directory"])
        if previous_directory != data_directory:
            raise ValueError(f"Existing data directory differs; review {ENVIRONMENT_CONFIGURATION} first.")
    if not (SOURCE_ROOT / "strata.py").is_file():
        raise FileNotFoundError(SOURCE_ROOT / "strata.py")
    for module_name in ("jinja2", "yaml", "regex", "psutil", "requests", "numpy", "PIL"):
        importlib.import_module(module_name)
    for directory in ("working", "logs"):
        (RUNTIME_ROOT / directory).mkdir(parents=True, exist_ok=True)
    if not LOCAL_CONFIGURATION.exists():
        substitutions = {
            "${RUNNER_ROOT}": RUNNER_ROOT.as_posix(),
            "${SOURCE_ROOT}": SOURCE_ROOT.as_posix(),
            "${DATA_ROOT}": data_directory.as_posix(),
        }
        configuration = expand_template(read_json(CONFIGURATION_ROOT / "strata.template.json"), substitutions)
        write_json(LOCAL_CONFIGURATION, configuration)
    configuration = read_json(LOCAL_CONFIGURATION)
    shared_settings_path = CONFIGURATION_ROOT / "strata.local.shared-settings.json"
    if not shared_settings_path.exists():
        write_json(shared_settings_path, read_json(CONFIGURATION_ROOT / "shared-settings.template.json"))
    validate_assets(data_directory, configuration)
    environment = runtime_environment(data_directory)
    # Full verification과 signature 검증은 공식 CLI의 component resolver에 맡깁니다.
    engine_exit_code = invoke_strata(["components", "engine", "--backend", "cuda", "--full", "--output", "json"], environment)
    if engine_exit_code:
        return engine_exit_code
    plan_exit_code = invoke_strata(["serve", "--profile", str(LOCAL_CONFIGURATION), "--plan", "--output", "json"], environment)
    if plan_exit_code:
        return plan_exit_code
    profile_path = CONFIGURATION_ROOT / "profiles" / f"{PROFILE_NAME}.json"
    if not profile_path.exists():
        create_exit_code = invoke_strata(["profile", "create", PROFILE_NAME, "--from-config", str(LOCAL_CONFIGURATION)], environment)
        if create_exit_code:
            return create_exit_code
    elif Path(read_json(profile_path)["source_config"]) != LOCAL_CONFIGURATION:
        raise ValueError(f"Saved profile references another configuration; review {profile_path} first.")
    write_json(ENVIRONMENT_CONFIGURATION, {"data_directory": str(data_directory)})
    print("Environment ready. Run .\\run-strata.ps1 start", flush=True)
    return 0


def main() -> int:
    """준비 또는 공식 managed runtime 명령을 선택합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "start", "stop", "status", "plan", "verify", "foreground"))
    parser.add_argument("--data-directory", type=Path, default=Path("C:/Strata-data"))
    arguments = parser.parse_args()
    if arguments.action == "prepare":
        return prepare_environment(arguments.data_directory)
    data_directory = Path(read_json(ENVIRONMENT_CONFIGURATION)["data_directory"])
    environment = runtime_environment(data_directory)
    if arguments.action == "foreground":
        command = ["serve", "--profile", PROFILE_NAME]
    elif arguments.action == "plan":
        command = ["serve", "--profile", PROFILE_NAME, "--plan", "--output", "json"]
    else:
        command = ["runtime", arguments.action, "--profile", PROFILE_NAME, "--output", "json"]
        if arguments.action in ("start", "verify"):
            command += ["--wait", "600"]
    return invoke_strata(command, environment)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"Strata runner: {error}", file=sys.stderr)
        raise SystemExit(1) from error
