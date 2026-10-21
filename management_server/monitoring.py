"""브라우저 수와 관계없이 한 번씩 Windows 및 서비스 상태를 수집합니다."""

import asyncio
import csv
import io
import time

import httpx
import psutil

from .integrations import comfy_queue, create_llm_adapter, librechat_status, run_command


async def collect_resources():
    """Host RAM·CPU와 NVIDIA GPU 사용량을 조회합니다."""
    memory = psutil.virtual_memory()
    result = {"ram": {"total_bytes": memory.total, "available_bytes": memory.available,
                       "used_bytes": memory.total - memory.available, "percent": memory.percent},
              "cpu_percent": psutil.cpu_percent(), "gpus": []}
    try:
        output = await run_command([
            "nvidia-smi", "--query-gpu=name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits"], 4)
        for row in csv.reader(io.StringIO(output), skipinitialspace=True):
            result["gpus"].append({"name": row[0], "used_mib": float(row[1]), "total_mib": float(row[2]),
                                   "utilization_percent": float(row[3]), "temperature_c": float(row[4]),
                                   "power_w": row[5]})
    except (OSError, RuntimeError, ValueError):
        result["gpu_error"] = "GPU 정보를 읽지 못했습니다."
    return result


class SnapshotMonitor:
    """수집 오류가 이전 정상 값으로 보이지 않도록 현재 결과와 시각을 보관합니다."""

    def __init__(self, configuration, operations):
        """공통 HTTP client와 serving engine adapter를 준비합니다."""
        self.configuration = configuration
        self.operations = operations
        self.adapter = create_llm_adapter(configuration["llm"])
        self.client = httpx.AsyncClient(trust_env=False)
        self.snapshot = {"ready": False, "at": None}

    async def read_comfy(self):
        """ComfyUI 연결 오류를 queue 0개와 구분합니다."""
        try:
            return await comfy_queue(self.client, self.configuration["comfy_url"])
        except (httpx.HTTPError, ValueError):
            return {"connected": False, "running": [], "pending": [], "error": "ComfyUI 8188에 연결할 수 없습니다."}

    async def refresh(self):
        """독립 조회를 병렬 수집하고 완성된 snapshot을 한 번에 교체합니다."""
        resources, llm, librechat, comfy = await asyncio.gather(
            collect_resources(), self.adapter.status(self.client), librechat_status(), self.read_comfy())
        await asyncio.to_thread(self.operations.recover_interrupted)
        operations = await asyncio.to_thread(self.operations.recent)
        self.snapshot = {"ready": True, "at": time.time(), "resources": resources,
                         "llm": llm, "librechat": librechat, "comfy": comfy, "operations": operations}

    async def run(self):
        """수동 제어와 독립적으로 3초 간격 수집을 계속합니다."""
        while True:
            try:
                await self.refresh()
            except Exception:
                self.snapshot = {"ready": False, "at": time.time(), "error": "상태 수집 실패. 잠시 후 다시 확인해 주세요."}
            await asyncio.sleep(3)

    async def close(self):
        """관리 서버 종료 시 조회용 연결만 해제합니다."""
        await self.client.aclose()
