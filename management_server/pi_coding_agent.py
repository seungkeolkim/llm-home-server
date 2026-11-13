"""Pi Coding Agent를 기존 LLM 및 LibreChat과 독립적으로 조회하고 제어합니다."""

import asyncio

from scripts.PiCodingAgent.service_runtime import service_status, start_service, stop_service


async def pi_status():
    """Pi 설정 준비 여부와 실제 gateway/Desktop 실행 상태를 수집합니다."""
    return await asyncio.to_thread(service_status)


async def control_pi(action):
    """Pi에만 start/stop을 적용하고 다른 서비스는 제어하지 않습니다."""
    if action == "start":
        await asyncio.to_thread(start_service)
        return "succeeded", "Pi gateway를 시작하고 Desktop 실행을 요청했습니다."
    if action == "stop":
        await asyncio.to_thread(stop_service)
        return "succeeded", "Pi를 종료했습니다. 세션과 기존 LLM 서버는 유지됩니다."
    raise ValueError("지원하지 않는 Pi 제어입니다.")
