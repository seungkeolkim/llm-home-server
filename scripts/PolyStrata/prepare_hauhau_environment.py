"""다운로드가 검증된 Hauhau 파일로 tokenizer와 전용 실행 설정을 준비합니다."""

import json
from pathlib import Path
import subprocess
import sys


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]


def read_json(configuration_path):
    """Windows BOM을 허용하며 local 설정과 다운로드 검증 결과를 읽습니다."""
    return json.loads(configuration_path.read_text(encoding="utf-8-sig"))


def require_verified_download(status_path):
    """Pinned SHA-256 검증 완료 기록과 실제 파일 크기가 모두 맞아야 준비합니다."""
    status = read_json(status_path)
    if status.get("state") != "completed" or status.get("detail") != "size and SHA-256 verified":
        raise ValueError(f"다운로드·SHA-256 검증이 완료되지 않았습니다: {status_path}")
    model_path = Path(status["model_path"])
    if model_path.stat().st_size != status["expected_bytes"]:
        raise ValueError(f"검증 완료 후 파일 크기가 달라졌습니다: {model_path.name}")
    return model_path


def main():
    """Model·MTP·Vision 준비를 확인하며 서비스나 model을 기동하지 않습니다."""
    environment = read_json(WORKSPACE_DIRECTORY / "config/Strata/environment.local.json")
    data_directory = Path(environment["data_directory"])
    downloads_directory = WORKSPACE_DIRECTORY / "runtime/PolyStrata/downloads"
    model_path = require_verified_download(downloads_directory / "hauhau-ttq-q4km-mtp/model/status.json")
    require_verified_download(downloads_directory / "hauhau-ttq-q4km-mtp/mtp/status.json")
    require_verified_download(downloads_directory / "hauhau-projector/status.json")
    tokenizer_command = [
        sys.executable, "-B", str(WORKSPACE_DIRECTORY / "external_repo/PolyStrata/tools/strata_tokenizer.py"),
        "--gguf", str(model_path), "--out", str(data_directory / "packs/qwen36-hauhau-ttq-q4_k_m"), "--check",
    ]
    subprocess.run(tokenizer_command, check=True)
    (WORKSPACE_DIRECTORY / "runtime/PolyStrata/hauhau/working").mkdir(parents=True, exist_ok=True)
    (WORKSPACE_DIRECTORY / "runtime/PolyStrata/logs").mkdir(parents=True, exist_ok=True)
    local_configuration_path = WORKSPACE_DIRECTORY / "config/PolyStrata/qwen36-hauhau.local.json"
    if not local_configuration_path.exists():
        shared_configuration = read_json(WORKSPACE_DIRECTORY / "config/Strata/strata.local.json")
        template_path = WORKSPACE_DIRECTORY / "config/PolyStrata/qwen36-hauhau.local.json.template"
        configuration_text = template_path.read_text(encoding="utf-8")
        configuration_text = configuration_text.replace("__DATA__", data_directory.as_posix())
        configuration_text = configuration_text.replace("__WORKSPACE__", WORKSPACE_DIRECTORY.as_posix())
        configuration = json.loads(configuration_text)
        configuration["api_key"] = shared_configuration["api_key"]
        local_configuration_path.write_text(json.dumps(configuration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Hauhau tokenizer와 local 설정 준비 완료. Service/model은 기동하지 않았습니다.")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
