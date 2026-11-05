"""공식 Windows Release와 local Profile만 준비하며 모델이나 서비스를 기동하지 않습니다."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import urlopen
import zipfile


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY))
from management_server.configuration import read_json
from management_server.infernix import native_options, write_native_configuration


def install_engine(release):
    """고정 SHA-256의 Release만 공식 source 밖에 압축 해제합니다."""
    downloads = WORKSPACE_DIRECTORY / "runtime/Infernix/downloads/engine"
    downloads.mkdir(parents=True, exist_ok=True)
    archive_path = downloads / (release["release"] + ".zip")
    partial_path = archive_path.with_suffix(".zip.part")
    if not archive_path.exists():
        print("Downloading official Infernix Windows release", flush=True)
        with urlopen(release["url"], timeout=90) as response:
            with partial_path.open("wb") as destination:
                shutil.copyfileobj(response, destination, length=1024 * 1024)
        if partial_path.stat().st_size != release["size"]:
            raise ValueError("Engine archive 크기가 공식 Release와 다릅니다.")
        with partial_path.open("rb") as source:
            if hashlib.file_digest(source, "sha256").hexdigest() != release["sha256"]:
                raise ValueError("Engine archive SHA-256 검증 실패")
        partial_path.rename(archive_path)
    else:
        with archive_path.open("rb") as source:
            if (archive_path.stat().st_size != release["size"] or
                    hashlib.file_digest(source, "sha256").hexdigest() != release["sha256"]):
                raise ValueError("기존 Engine archive 검증 실패; 파일은 보존합니다.")
    engine_directory = WORKSPACE_DIRECTORY / "data/Infernix/components/engine" / release["release"]
    build_path = engine_directory / "BUILD.json"
    if build_path.exists():
        if read_json(build_path).get("archive_sha256") != release["sha256"]:
            raise ValueError("기존 Engine 설치의 Release가 다릅니다.")
        return engine_directory
    engine_directory.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            member_path = Path(member.filename.replace("\\", "/"))
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError("Engine archive에 허용하지 않은 경로가 있습니다.")
            if not member_path.parts or member_path.parts[0] != release["archive_root"]:
                raise ValueError("Engine archive root가 pinned Release와 다릅니다.")
            relative_path = Path(*member_path.parts[1:])
            destination_path = (engine_directory / relative_path).resolve()
            if not destination_path.is_relative_to(engine_directory.resolve()):
                raise ValueError("Engine archive가 설치 경로 밖을 가리킵니다.")
            if member.is_dir():
                destination_path.mkdir(parents=True, exist_ok=True)
                continue
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source, destination_path.open("wb") as destination:
                shutil.copyfileobj(source, destination, length=1024 * 1024)
    if not (engine_directory / "infernix-serve.exe").is_file():
        raise ValueError("공식 Release에 infernix-serve.exe가 없습니다.")
    build_path.write_text(json.dumps({
        "release": release["release"], "archive_sha256": release["sha256"],
        "source": release["url"], "installed_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n", encoding="utf-8")
    return engine_directory


def prepare_local_configuration():
    """기존 local 값을 보존하고 최초 준비에서만 경로와 기존 공통 API key를 채웁니다."""
    configuration_path = WORKSPACE_DIRECTORY / "config/Infernix/orcarouter-nvfp4.local.json"
    if not configuration_path.exists():
        template_path = configuration_path.with_name(configuration_path.name + ".template")
        configuration_text = template_path.read_text(encoding="utf-8")
        configuration_text = configuration_text.replace("${WORKSPACE_ROOT}", WORKSPACE_DIRECTORY.as_posix())
        configuration = json.loads(configuration_text)
        shared_configuration = read_json(WORKSPACE_DIRECTORY / "config/Strata/strata.local.json")
        configuration["api_key"] = shared_configuration["api_key"]
        configuration_path.write_text(json.dumps(configuration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    configuration = read_json(configuration_path)
    if not configuration.get("api_key") or configuration["api_key"].startswith("CHANGE_ME_"):
        raise ValueError("Infernix api_key를 공통 LLM API key로 설정해 주세요.")
    for field_name in ("cwd", "log"):
        directory = Path(configuration[field_name])
        if field_name == "log":
            directory = directory.parent
        directory.mkdir(parents=True, exist_ok=True)
    write_native_configuration(configuration)
    return configuration


def verify_engine_interface(configuration):
    """모델 Load 없이 설치된 executable의 --help와 Profile 옵션을 대조합니다."""
    completed = subprocess.run([configuration["exe"], "--help"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=30,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    if completed.returncode:
        raise RuntimeError("Infernix --help 실행 실패; Release DLL과 Visual C++ Runtime을 확인해 주세요.")
    help_text = completed.stdout + completed.stderr
    for option_name in native_options(configuration):
        if option_name != "model" and "--" + option_name not in help_text:
            raise ValueError(f"설치된 Infernix가 Profile 옵션을 지원하지 않습니다: --{option_name}")
    evidence_path = WORKSPACE_DIRECTORY / "runtime/Infernix/engine-help.txt"
    evidence_path.write_text(help_text, encoding="utf-8")
    build_path = Path(configuration["exe"]).parent / "BUILD.json"
    build = read_json(build_path)
    build["interface_verified"] = True
    build["supported_profile_options"] = list(native_options(configuration))
    build_path.write_text(json.dumps(build, indent=2) + "\n", encoding="utf-8")


def main():
    """다운로드·설정 준비와 실행 파일 인터페이스 확인을 모델 준비 상태와 구분합니다."""
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--configuration-only", action="store_true")
    arguments = argument_parser.parse_args()
    if not arguments.configuration_only:
        release = read_json(WORKSPACE_DIRECTORY / "config/Infernix/engine-release.json")
        install_engine(release)
    configuration = prepare_local_configuration()
    if not arguments.configuration_only:
        verify_engine_interface(configuration)
    print("Infernix configuration prepared; no model or service was started.", flush=True)


if __name__ == "__main__":
    main()
