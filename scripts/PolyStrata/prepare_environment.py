"""공식 source 밖에 고정 release·CPU Vision·tokenizer·실행 설정을 준비합니다."""

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import requests


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
ENGINE_URL = "https://github.com/VecSzn/PolyStrata/releases/download/v0.1.45-poly.2/strata-poly-windows-x64-4fa9bedab2538cec.zip"
ENGINE_SHA256 = "839a2c3f72e2aaa48ba650666639b17afe630cc8c18ab30392b90a7b974d8c5a"
PROJECTOR_URL = "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/resolve/5bc3e238d916f48a861bac2f8a1990a0e9b7e98d/mmproj-F16.gguf"
PROJECTOR_SHA256 = "71f3cbc1f7cc0f30d09d41cfa924c0060827ebc33bf15ace7e86661e856f0160"


def read_json(path):
    """Windows BOM이 있는 local 설정도 읽습니다."""
    return json.loads(path.read_text(encoding="utf-8-sig"))


def verify_download(path, url, expected_hash):
    """명시적 준비 단계에서만 다운로드하고 SHA-256을 검증합니다."""
    if not path.is_file():
        temporary_path = path.with_suffix(path.suffix + ".part")
        with requests.get(url, stream=True, timeout=(20, 120)) as response:
            response.raise_for_status()
            with temporary_path.open("wb") as output:
                for chunk in response.iter_content(4 * 1024 * 1024):
                    output.write(chunk)
        os.replace(temporary_path, path)
    with path.open("rb") as source:
        actual_hash = hashlib.file_digest(source, "sha256").hexdigest()
    if actual_hash != expected_hash:
        raise ValueError(f"SHA-256 검증 실패: {path.name}")


def main():
    """설치를 준비하고 서비스나 model을 시작하지 않습니다."""
    environment = read_json(WORKSPACE_DIRECTORY / "config/Strata/environment.local.json")
    data_directory = Path(environment["data_directory"])
    downloads = WORKSPACE_DIRECTORY / "runtime/PolyStrata/downloads"
    downloads.mkdir(parents=True, exist_ok=True)
    engine_archive = downloads / "engine.zip"
    verify_download(engine_archive, ENGINE_URL, ENGINE_SHA256)
    engine_directory = data_directory / "components/PolyStrata/v0.1.45-poly.2"
    engine_directory.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(engine_archive) as archive:
        for member in archive.infolist():
            if Path(member.filename).name != member.filename:
                raise ValueError("Engine archive에 예상하지 않은 경로가 있습니다.")
        archive.extractall(engine_directory)
    model_directory = data_directory / "models/qwen36-UD-Q4_K_M"
    projector = downloads / "mmproj-F16.gguf"
    destination = model_directory / projector.name
    if not destination.exists():
        verify_download(projector, PROJECTOR_URL, PROJECTOR_SHA256)
        os.replace(projector, destination)
    else:
        verify_download(destination, PROJECTOR_URL, PROJECTOR_SHA256)
    model_path = model_directory / "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
    if model_path.stat().st_size != 22663387424:
        raise ValueError("완료된 UD-Q4_K_M weights가 필요합니다.")
    tokenizer_command = [sys.executable, "-B", str(WORKSPACE_DIRECTORY / "external_repo/PolyStrata/tools/strata_tokenizer.py"),
                         "--gguf", str(model_path), "--out", str(data_directory / "packs/qwen36-ud-q4_k_m"), "--check"]
    subprocess.run(tokenizer_command, check=True)
    for directory in ("runtime/PolyStrata/working", "runtime/PolyStrata/logs"):
        (WORKSPACE_DIRECTORY / directory).mkdir(parents=True, exist_ok=True)
    local_configuration_path = WORKSPACE_DIRECTORY / "config/PolyStrata/qwen36.local.json"
    if not local_configuration_path.exists():
        shared_configuration = read_json(WORKSPACE_DIRECTORY / "config/Strata/strata.local.json")
        configuration_text = (WORKSPACE_DIRECTORY / "config/PolyStrata/qwen36.local.json.template").read_text(encoding="utf-8")
        configuration_text = configuration_text.replace("__DATA__", data_directory.as_posix())
        configuration_text = configuration_text.replace("__WORKSPACE__", WORKSPACE_DIRECTORY.as_posix())
        configuration = json.loads(configuration_text)
        configuration["api_key"] = shared_configuration["api_key"]
        local_configuration_path.write_text(json.dumps(configuration, ensure_ascii=False, indent=2), encoding="utf-8")
    print("PolyStrata 준비 완료. Service/model은 기동하지 않았습니다.")


if __name__ == "__main__":
    main()
