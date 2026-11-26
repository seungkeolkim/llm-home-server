"""관리 화면과 동일한 lock·revision·process 소유권으로 Basalt만 제어합니다."""

import argparse
import asyncio
import json
from pathlib import Path
import sys

import httpx


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY))
from management_server.configuration import load_configuration
from management_server.llm_runtime import ProfileRuntime


async def read_status(runtime: ProfileRuntime) -> dict:
    """모델 Load 없이 Basalt 설치·등록 목록과 실제 실행 상태를 조회합니다."""
    async with httpx.AsyncClient(trust_env=False) as client:
        runtime_status = await runtime.status(client)
    profiles = [profile for profile in runtime_status["profiles"] if profile["engine"] == "basalt"]
    profile_identifiers = {profile["identifier"] for profile in profiles}
    basalt_running = runtime_status.get("profile_id") in profile_identifiers
    release_path = WORKSPACE_DIRECTORY / "config/Basalt/engine-release.json"
    release = json.loads(release_path.read_text(encoding="utf-8-sig"))
    engine_directory = WORKSPACE_DIRECTORY / "data/Basalt/components/engine" / release["release"]
    required_paths = [engine_directory / "bin/basalt.exe", engine_directory / "serve/server.py",
                      WORKSPACE_DIRECTORY / ".venv/Basalt/Scripts/python.exe"]
    return {"engine": "basalt", "installed": all(path.is_file() for path in required_paths),
            "state": runtime_status["state"] if basalt_running else "stopped", "profiles": profiles,
            "instance_id": runtime_status["instance_id"] if basalt_running else None}


def main() -> None:
    """선택한 Basalt를 명시적으로 기동하거나 실제 Basalt instance만 종료합니다."""
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("action", choices=("status", "start", "stop"))
    argument_parser.add_argument("--profile", help="등록된 Basalt profile identifier")
    arguments = argument_parser.parse_args()
    runtime = ProfileRuntime(load_configuration()["llm"])
    if arguments.action == "status":
        print(json.dumps(asyncio.run(read_status(runtime)), ensure_ascii=False, indent=2))
        return
    if arguments.action == "start":
        profiles = [profile for profile in runtime.catalog.profiles.values() if profile["engine"] == "basalt"]
        if not profiles:
            raise RuntimeError("등록된 Basalt model profile이 없습니다. 모델 준비와 profile 등록 후 기동해 주세요.")
        if not arguments.profile and len(profiles) != 1:
            raise RuntimeError("기동할 Basalt profile을 --profile로 지정해 주세요.")
        profile = runtime.catalog.get(arguments.profile or profiles[0]["identifier"])
        if profile["engine"] != "basalt":
            raise RuntimeError("Basalt profile만 기동할 수 있습니다.")
        operation = runtime.pin_operation("start", profile["identifier"], runtime.catalog.revision(profile))
    else:
        instance = runtime.read_instance()
        if not instance or runtime.catalog.get(instance["profile_id"])["engine"] != "basalt":
            raise RuntimeError("실행 중인 Basalt instance가 아닙니다. 다른 Engine은 종료하지 않습니다.")
        if arguments.profile and instance["profile_id"] != arguments.profile:
            raise RuntimeError("실행 중인 Basalt instance가 지정한 profile과 다릅니다.")
        operation = runtime.pin_operation("stop")
    operation["action"] = arguments.action
    runtime.execute(operation)
    print(f"Basalt {arguments.action} completed.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
