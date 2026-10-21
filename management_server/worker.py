"""사용자가 요청한 한 번의 제어 작업을 API reload와 독립적으로 수행합니다."""

import asyncio
import subprocess
import sys

import httpx

from .configuration import WORKSPACE_DIRECTORY, load_configuration
from .integrations import compose_arguments, create_llm_adapter
from .operations import OperationStore


async def execute_operation(operation, configuration):
    """허용한 서비스 조작만 실행하고 Comfy unload의 접수와 완료를 구분합니다."""
    target, action = operation["target"], operation["action"]
    async with httpx.AsyncClient(trust_env=False) as client:
        if target == "comfy":
            response = await client.post(configuration["comfy_url"] + "/free", timeout=15,
                                         json={"unload_models": True, "free_memory": True})
            response.raise_for_status()
            return "accepted", "모델·cache unload 요청을 접수했습니다. 작업 중이면 처리 후 반영됩니다. RAM·VRAM을 확인해 주세요."
        if target == "llm":
            command = create_llm_adapter(configuration["llm"]).control_command(action)
        elif target == "librechat":
            command = [*compose_arguments(), "up", "-d", "--wait", "--wait-timeout", "240"] if action == "start" else [*compose_arguments(), "stop"]
        else:
            raise ValueError("허용되지 않은 서비스입니다.")
        completed = await asyncio.to_thread(subprocess.run, command, cwd=WORKSPACE_DIRECTORY,
                                            timeout=660, check=False, creationflags=subprocess.CREATE_NO_WINDOW)
        if completed.returncode:
            raise RuntimeError("서비스 제어에 실패했습니다. 작업 로그와 현재 서비스 상태를 확인해 주세요.")
        return "succeeded", "기동을 완료했습니다." if action == "start" else "종료를 완료했습니다."


def main():
    """이미 접수된 작업을 수행하고 결과를 지속성 DB에 남깁니다."""
    store = OperationStore()
    identifier = sys.argv[1]
    operation = store.get(identifier)
    if not operation or operation["status"] != "queued":
        raise SystemExit("실행 대기 중인 작업을 찾지 못했습니다.")
    store.begin(identifier)
    try:
        status, message = asyncio.run(execute_operation(operation, load_configuration()))
    except Exception as error:
        print(f"{type(error).__name__}: {error}", flush=True)
        store.finish(identifier, "failed", str(error)[:500])
        raise SystemExit(1) from None
    store.finish(identifier, status, message)


if __name__ == "__main__":
    main()
