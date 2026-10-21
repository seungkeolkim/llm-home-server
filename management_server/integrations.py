"""LLM adapter와 Docker·ComfyUI의 읽기 및 제어 경계를 정의합니다."""

import asyncio
import json
import subprocess

import httpx

from .configuration import WORKSPACE_DIRECTORY, read_json, resolve_workspace_path


async def run_command(arguments, timeout_seconds=15):
    """고정 인자 명령을 shell 없이 실행하고 제한 시간과 exit code를 확인합니다."""
    try:
        # Windows reload의 Selector loop는 비동기 subprocess를 지원하지 않으므로 thread에서 실행합니다.
        completed = await asyncio.to_thread(
            subprocess.run, list(map(str, arguments)), cwd=WORKSPACE_DIRECTORY,
            capture_output=True, text=True, encoding="utf-8-sig", errors="replace",
            timeout=timeout_seconds, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("상태 조회 명령의 응답 시간이 초과됐습니다.") from None
    if completed.returncode:
        raise RuntimeError("서비스 명령 실패: " + completed.stderr[-300:])
    return completed.stdout


class StrataAdapter:
    """현재 Strata에 맞춘 LLM adapter이며 화면과 일반 제어 코드는 엔진명에 의존하지 않습니다."""

    def __init__(self, configuration):
        """기존 Strata 설정을 참조하되 모델이나 key를 복제하지 않습니다."""
        self.configuration = configuration
        self.native_configuration = read_json(resolve_workspace_path(configuration["configuration_path"]))
        self.base_url = f"http://127.0.0.1:{self.native_configuration['port']}"

    async def status(self, client):
        """모델을 자동 Load하지 않는 상태 API만 호출합니다."""
        result = {"adapter": "strata", "name": self.configuration.get("name", "Strata"),
                  "model": self.native_configuration.get("model_name", ""),
                  "port": self.native_configuration["port"], "state": "stopped", "in_flight": 0}
        try:
            response = await client.get(self.base_url + "/v1/status", headers={
                "Authorization": "Bearer " + self.native_configuration["api_key"]}, timeout=3)
            response.raise_for_status()
            status = response.json()
            result["in_flight"] = status.get("activity", {}).get("in_flight", 0)
            result["state"] = "generating" if result["in_flight"] else "ready" if status.get("loaded") else "unloaded"
        except httpx.ConnectError:
            pass
        except (httpx.HTTPError, ValueError):
            result["state"] = "unavailable"
        return result

    def control_command(self, action):
        """기존 runner에 허용한 start/stop 동작만 전달합니다."""
        if action not in {"start", "stop"}:
            raise ValueError("지원하지 않는 LLM 제어입니다.")
        return [str(WORKSPACE_DIRECTORY / ".venv/Strata/Scripts/strata-runtime-python.exe"),
                "-I", "-B", str(WORKSPACE_DIRECTORY / "scripts/Strata/strata_runner.py"), action]


def create_llm_adapter(configuration):
    """설정한 serving engine에 해당하는 adapter를 선택합니다."""
    if configuration["adapter"] == "strata":
        return StrataAdapter(configuration)
    raise ValueError("등록되지 않은 LLM adapter입니다.")


def compose_arguments():
    """현재 LibreChat stack으로 범위를 제한한 Compose 인자를 반환합니다."""
    return ["docker", "compose", "--env-file", str(WORKSPACE_DIRECTORY / "config/LibreChat/.env.local"),
            "-f", str(WORKSPACE_DIRECTORY / "config/LibreChat/compose.yaml")]


async def librechat_status():
    """Docker 연결 오류와 각 container의 실행·health를 구분합니다."""
    try:
        output = await run_command([*compose_arguments(), "ps", "--all", "--format", "json"], 6)
        if output.strip().startswith("["):
            records = json.loads(output)
        else:
            records = [json.loads(line) for line in output.splitlines() if line.strip()]
        services = {}
        for record in records:
            services[record["Service"]] = {"state": record.get("State", "unknown"),
                                            "health": record.get("Health", "")}
        for service_name in ("librechat", "mongodb"):
            services.setdefault(service_name, {"state": "stopped", "health": ""})
        return {"engine_available": True, "services": services}
    except (OSError, RuntimeError, ValueError):
        return {"engine_available": False, "services": {}, "error": "Docker Engine에 연결할 수 없습니다."}


async def comfy_queue(client, base_url):
    """ComfyUI 8188의 실행·대기 목록만 읽고 취소·삭제 API는 제공하지 않습니다."""
    response = await client.get(base_url + "/api/jobs", params={"status": "pending,in_progress"}, timeout=4)
    running_jobs, pending_jobs = [], []
    if response.status_code in {404, 405}:
        response = await client.get(base_url + "/queue", timeout=4)
        response.raise_for_status()
        queue_document = response.json()
        for queue_name, destination in (("queue_running", running_jobs), ("queue_pending", pending_jobs)):
            for item in queue_document.get(queue_name, []):
                destination.append({"identifier": str(item[1]), "position": item[0]})
    else:
        response.raise_for_status()
        for job in response.json().get("jobs", []):
            destination = running_jobs if job.get("status") == "in_progress" else pending_jobs
            destination.append({"identifier": str(job["id"]), "position": job.get("number"),
                                "status": job.get("status")})
    return {"connected": True, "running": running_jobs, "pending": pending_jobs}
