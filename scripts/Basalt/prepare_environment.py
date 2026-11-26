"""Basalt 공식 Windows release와 전용 Python/CUDA 환경을 모델 기동 없이 준비합니다."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.request import urlopen
from urllib.parse import urlparse
import venv
import zipfile


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY))


def read_document(document_path: Path) -> dict:
    """UTF-8 JSON 설정을 BOM 유무와 관계없이 읽습니다."""
    return json.loads(document_path.read_text(encoding="utf-8-sig"))


def install_engine(release: dict) -> Path:
    """공식 SHA-256을 확인한 archive만 data/Basalt 아래에 압축 해제합니다."""
    downloads_directory = WORKSPACE_DIRECTORY / "runtime/Basalt/downloads/engine"
    downloads_directory.mkdir(parents=True, exist_ok=True)
    archive_path = downloads_directory / Path(release["url"]).name
    if not archive_path.is_file():
        partial_path = archive_path.with_suffix(".zip.part")
        print(f"Downloading Basalt {release['release']} Windows release", flush=True)
        with urlopen(release["url"], timeout=90) as response:
            with partial_path.open("wb") as destination_stream:
                shutil.copyfileobj(response, destination_stream, length=1024 * 1024)
        with partial_path.open("rb") as archive_stream:
            actual_sha256 = hashlib.file_digest(archive_stream, "sha256").hexdigest()
        if partial_path.stat().st_size != release["size"] or actual_sha256 != release["sha256"]:
            raise ValueError("Basalt archive의 공식 크기 또는 SHA-256 불일치; 부분 파일은 보존합니다.")
        partial_path.replace(archive_path)
    with archive_path.open("rb") as archive_stream:
        actual_sha256 = hashlib.file_digest(archive_stream, "sha256").hexdigest()
    if archive_path.stat().st_size != release["size"] or actual_sha256 != release["sha256"]:
        raise ValueError("기존 Basalt archive 검증 실패; 파일은 보존합니다.")
    engine_directory = WORKSPACE_DIRECTORY / "data/Basalt/components/engine" / release["release"]
    build_path = engine_directory / "BUILD.json"
    if build_path.is_file():
        if read_document(build_path).get("archive_sha256") != release["sha256"]:
            raise ValueError("기존 Basalt 설치의 Release가 다릅니다.")
        return engine_directory
    with zipfile.ZipFile(archive_path) as archive:
        for member in archive.infolist():
            member_path = Path(member.filename.replace("\\", "/"))
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError("Basalt archive에 허용하지 않은 경로가 있습니다.")
            if not member_path.parts or member_path.parts[0] != release["archive_root"]:
                raise ValueError(f"Basalt archive root가 다릅니다: {member_path.parts[:1]}")
            relative_path = Path(*member_path.parts[1:])
            destination_path = (engine_directory / relative_path).resolve()
            if not destination_path.is_relative_to(engine_directory.resolve()):
                raise ValueError("Basalt archive가 설치 경로 밖을 가리킵니다.")
            if member.is_dir():
                destination_path.mkdir(parents=True, exist_ok=True)
                continue
            destination_path.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(member) as source_stream, destination_path.open("wb") as destination_stream:
                shutil.copyfileobj(source_stream, destination_stream, length=1024 * 1024)
    for relative_path in ("bin/basalt.exe", "serve/server.py", "requirements.txt"):
        if not (engine_directory / relative_path).is_file():
            raise ValueError(f"Basalt release의 필수 파일이 없습니다: {relative_path}")
    build_path.write_text(json.dumps({
        "release": release["release"], "archive_sha256": actual_sha256,
        "source": release["url"], "installed_at": datetime.now(timezone.utc).isoformat(),
    }, indent=2) + "\n", encoding="utf-8")
    return engine_directory


def install_dependencies() -> Path:
    """전역 Python·CUDA·PATH를 바꾸지 않고 Basalt 전용 venv에 설치합니다."""
    environment_directory = WORKSPACE_DIRECTORY / ".venv/Basalt"
    python_path = environment_directory / "Scripts/python.exe"
    if not python_path.is_file():
        venv.EnvBuilder(with_pip=True).create(environment_directory)
    requirements_path = WORKSPACE_DIRECTORY / "requirements/Basalt/runtime.txt"
    subprocess.run([str(python_path), "-m", "pip", "install", "-r", str(requirements_path)],
                   check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    subprocess.run([str(python_path), "-m", "pip", "check"],
                   check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return python_path


def prepare_local_configuration(configuration_path: Path) -> dict:
    """명시한 설정에서만 공통 API key를 가져오고 이후 사용자 설정을 보존합니다."""
    from management_server.basalt import write_native_configuration

    configuration_path = configuration_path.resolve()
    if not configuration_path.is_relative_to((WORKSPACE_DIRECTORY / "config/Basalt").resolve()):
        raise ValueError("Basalt local 설정은 config/Basalt 아래에 지정해 주세요.")
    if not configuration_path.is_file():
        template_path = configuration_path.with_name(configuration_path.name + ".template")
        configuration_text = template_path.read_text(encoding="utf-8")
        configuration_text = configuration_text.replace("${WORKSPACE_ROOT}", WORKSPACE_DIRECTORY.as_posix())
        configuration = json.loads(configuration_text)
        shared_configuration = read_document(WORKSPACE_DIRECTORY / "config/Strata/strata.local.json")
        configuration["api_key"] = shared_configuration["api_key"]
        environment_path = WORKSPACE_DIRECTORY / "config/LibreChat/.env.local"
        if environment_path.is_file():
            for environment_line in environment_path.read_text(encoding="utf-8-sig").splitlines():
                setting_name, separator, setting_value = environment_line.partition("=")
                if separator and setting_name in {"DOMAIN_CLIENT", "DOMAIN_SERVER"}:
                    public_hostname = urlparse(setting_value.strip().strip("\"'")).hostname
                    if public_hostname and public_hostname not in configuration["allowed_hosts"]:
                        configuration["allowed_hosts"].append(public_hostname)
        configuration_path.write_text(json.dumps(configuration, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    configuration = read_document(configuration_path)
    if not configuration.get("api_key") or configuration["api_key"].startswith("CHANGE_ME"):
        raise ValueError("Basalt에 공통 LLM API key를 설정해 주세요.")
    for directory_path in (Path(configuration["cwd"]), Path(configuration["log"]).parent):
        directory_path.mkdir(parents=True, exist_ok=True)
    write_native_configuration(configuration)
    return configuration


def verify_engine_interface(configuration: dict) -> None:
    """모델 Load 없이 공식 executable과 Python server의 help를 확인합니다."""
    from management_server.basalt import runtime_environment

    verification_directory = WORKSPACE_DIRECTORY / "runtime/Basalt"
    commands = {
        "engine-help.txt": [configuration["exe"], "--help"],
        "server-help.txt": [configuration["python"], "-B",
                            str(Path(configuration["engine_root"]) / "serve/server.py"), "--help"],
    }
    for evidence_name, command in commands.items():
        completed = subprocess.run(command, env=runtime_environment(configuration),
                                   capture_output=True, text=True, encoding="utf-8", errors="replace",
                                   timeout=40, creationflags=subprocess.CREATE_NO_WINDOW)
        help_text = completed.stdout + completed.stderr
        (verification_directory / evidence_name).write_text(help_text, encoding="utf-8")
        if completed.returncode:
            raise RuntimeError(f"Basalt 인터페이스 검증 실패: {evidence_name}; runtime/Basalt 로그를 확인해 주세요.")
    build_path = Path(configuration["engine_root"]) / "BUILD.json"
    build = read_document(build_path)
    build["interface_verified"] = True
    build["python"] = configuration["python"]
    build_path.write_text(json.dumps(build, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    """기본값은 Engine만 준비하며 모델 설정은 명시한 경우에만 처리합니다."""
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--configuration-only", action="store_true")
    argument_parser.add_argument("--engine-only", action="store_true")
    argument_parser.add_argument("--configuration", type=Path)
    arguments = argument_parser.parse_args()
    if arguments.configuration_only and not arguments.configuration:
        argument_parser.error("--configuration-only에는 --configuration 경로가 필요합니다.")
    if arguments.engine_only and arguments.configuration:
        argument_parser.error("--engine-only와 --configuration을 함께 지정할 수 없습니다.")
    release = read_document(WORKSPACE_DIRECTORY / "config/Basalt/engine-release.json")
    if not arguments.configuration_only:
        install_engine(release)
        install_dependencies()
    engine_directory = WORKSPACE_DIRECTORY / "data/Basalt/components/engine" / release["release"]
    configuration = {"engine_root": str(engine_directory), "exe": str(engine_directory / "bin/basalt.exe"),
                     "python": str(WORKSPACE_DIRECTORY / ".venv/Basalt/Scripts/python.exe")}
    if arguments.configuration:
        configuration = prepare_local_configuration(arguments.configuration)
    verify_engine_interface(configuration)
    print("Basalt engine and interfaces verified; no model or service started.", flush=True)


if __name__ == "__main__":
    main()
