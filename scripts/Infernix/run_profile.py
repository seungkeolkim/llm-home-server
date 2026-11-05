"""관리 외 이중 기동을 막고 LLM Home Server의 Infernix Profile을 제어합니다."""

import argparse
import asyncio
import json
from pathlib import Path
import subprocess
import sys

import httpx


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY))
from management_server.configuration import load_configuration
from management_server.infernix import server_command
from management_server.llm_runtime import ProfileRuntime


PROFILE_IDENTIFIER = "infernix-orcarouter-nvfp4"


async def read_status(runtime):
    """Load나 generation 없이 등록된 Profile과 현재 실행 instance를 조회합니다."""
    async with httpx.AsyncClient(trust_env=False) as client:
        return await runtime.status(client)


def main():
    """관리 화면과 동일한 lock·revision·process identity로 명시적 제어만 실행합니다."""
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("action", choices=("status", "start", "stop", "plan"))
    arguments = argument_parser.parse_args()
    runtime = ProfileRuntime(load_configuration()["llm"])
    profile = runtime.catalog.get(PROFILE_IDENTIFIER)
    if arguments.action == "status":
        print(json.dumps(asyncio.run(read_status(runtime)), ensure_ascii=False, indent=2))
        return
    if arguments.action == "start":
        revision = runtime.catalog.revision(profile)
        operation = runtime.pin_operation("start", PROFILE_IDENTIFIER, revision)
    elif arguments.action == "stop":
        instance = runtime.read_instance()
        if not instance or instance["profile_id"] != PROFILE_IDENTIFIER:
            raise RuntimeError("실행 중인 Infernix instance가 아닙니다. 다른 Engine은 종료하지 않습니다.")
        operation = runtime.pin_operation("stop")
    else:
        description = runtime.catalog.describe(profile)
        if description["state"] != "available":
            raise RuntimeError(description["problem"])
        configuration = runtime.catalog.native_configuration(profile)
        plan_path = WORKSPACE_DIRECTORY / "runtime/Infernix/plan.json"
        command = [*server_command(configuration), "--plan", str(plan_path)]
        completed = subprocess.run(command, cwd=configuration["cwd"], check=False,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        print(f"Plan: {plan_path}")
        raise SystemExit(completed.returncode)
    operation["action"] = arguments.action
    runtime.execute(operation)
    print(f"Infernix {arguments.action} completed.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
