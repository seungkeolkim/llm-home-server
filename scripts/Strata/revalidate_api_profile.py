"""웹 관리 화면으로 재기동한 실제 운영 instance를 기존 API protocol로 재검증합니다."""

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time

import psutil
import requests

WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY / "scripts/Strata"))
from measure_api_baseline import BaselineMeasurement, DEFAULT_CONFIGURATION, write_json
from measure_engine_candidates import ManagementClient
from measure_optimization_quality import measure_quality, measure_style
from optimize_api_profile import TASKS, check_fixed_configuration

class RevalidationMeasurement(BaselineMeasurement):
    """요청마다 별도 재검증 상태를 저장하며 기존 baseline 결과는 보존합니다."""

    def measure(self, identifier, payload, expected_fragments=None, expected_http_status=200):
        """완료된 요청과 현재 요청을 기록해 긴 입력 중에도 진행을 확인할 수 있게 합니다."""
        write_json(self.output_directory / "state.json", {"status": "running", "current_request": identifier,
                   "completed_requests": len(self.results), "updated_at": datetime.now().astimezone().isoformat()})
        result = super().measure(identifier, payload, expected_fragments, expected_http_status)
        write_json(self.output_directory / "state.json", {"status": "running", "current_request": None,
                   "completed_requests": len(self.results), "last_case": identifier, "last_passed": result["passed"],
                   "updated_at": datetime.now().astimezone().isoformat()})
        return result


def capture_runtime(output_directory: Path) -> dict:
    """실제 native 인자·선택한 환경변수·설치 build와 관리 상태만 저장합니다."""
    state = ManagementClient(output_directory).status()["llm"]
    native_processes = []
    for process in psutil.process_iter(["name", "pid", "cmdline", "create_time"]):
        if process.info["name"] == "strata.exe":
            environment = process.environ()
            native_processes.append({**process.info, "environment": {key: environment.get(key) for key in
                ("STRATA_PREFILL_LAYER_MAJOR", "STRATA_PREFILL_LM_R", "STRATA_PREFILL_LM_TOKENS")}})
    if len(native_processes) != 1:
        raise RuntimeError("Expected one native Strata Engine")
    native = native_processes[0]
    check_fixed_configuration({"args": native["cmdline"]})
    expected_environment = {"STRATA_PREFILL_LAYER_MAJOR": "1", "STRATA_PREFILL_LM_R": "host",
                            "STRATA_PREFILL_LM_TOKENS": "16384"}
    if native["environment"] != expected_environment or "--mtp" not in native["cmdline"]:
        raise RuntimeError("The live Engine is not running the selected optimized profile")
    build_path = Path(native["cmdline"][0]).parent / "BUILD.json"
    return {"recorded_at": datetime.now().astimezone().isoformat(), "native": native,
            "build": json.loads(build_path.read_text(encoding="utf-8")),
            "management": {key: state.get(key) for key in ("state", "in_flight", "instance_id", "port", "model")}}


def main() -> None:
    """설정이나 lifecycle을 바꾸지 않고 생성·검색·회귀·정답 검사를 순차 실행합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True)
    arguments = parser.parse_args()
    output_directory = arguments.output_directory
    if output_directory.exists() and any(output_directory.iterdir()):
        parser.error("Use a new empty output directory; existing results are never overwritten")
    output_directory.mkdir(parents=True, exist_ok=True)
    before = capture_runtime(output_directory)
    if before["management"]["state"] != "ready" or before["management"]["in_flight"]:
        raise RuntimeError("The production Engine is not idle and ready")
    queue = requests.get("http://127.0.0.1:8188/queue", timeout=10).json()
    if queue.get("queue_running") or queue.get("queue_pending"):
        raise RuntimeError("ComfyUI has queued work")
    write_json(output_directory / "runtime-before.json", before)
    snapshots = output_directory / "protocol-snapshots"
    snapshots.mkdir()
    manifest = {}
    for name in ("revalidate_api_profile.py", "benchmark_inputs.py", "measure_api_baseline.py",
                 "measure_optimization_quality.py", "optimize_api_profile.py", "measure_engine_candidates.py",
                 "summarize_optimization_results.py"):
        source = WORKSPACE_DIRECTORY / "scripts/Strata" / name
        shutil.copy2(source, snapshots / name)
        manifest[name] = hashlib.sha256(source.read_bytes()).hexdigest()
    write_json(snapshots / "manifest.json", manifest)
    measurement = RevalidationMeasurement(DEFAULT_CONFIGURATION, output_directory)
    measurement.record_environment()
    quality_checks = []
    completed = False
    try:
        for task_name, prompt in TASKS.items():
            payload = measurement.request_payload([{"role": "user", "content": prompt}], 384)
            payload["strata_checkpoint"] = False
            measurement.measure("decode-" + task_name, payload)
        measurement.core_suite([8192, 32768, 131072, 260000], 3)
        retrieval = next(result for result in measurement.results if result["case"] == "retrieval-260000")
        payload = json.loads((output_directory / "retrieval-260000.request.json").read_text(encoding="utf-8"))
        records = re.findall(r"record (\d+): zone=([0-9a-f]+);", payload["messages"][0]["content"])
        record_number, expected_zone = records[len(records) // 3]
        messages = [*payload["messages"], {"role": "assistant", "content": retrieval["content"]},
                    {"role": "user", "content": f"원래 문서의 record {record_number}의 zone 값을 첫 줄에 정확하게 쓰세요. 이어서 로컬 LLM 서버 운영 체크리스트 30개를 한국어로 쓰세요. 각 항목은 두 문장으로 쓰고 끝까지 계속하세요."}]
        measurement.measure("long-generation-260k", measurement.request_payload(messages, 512), [expected_zone])
        measurement.issue_suite()
        quality_checks = measure_quality(measurement)
        measure_style(measurement)
        completed = True
    finally:
        measurement.finish()
        after = capture_runtime(output_directory)
        write_json(output_directory / "runtime-after-immediate.json", after)
        for attempt in range(15):
            if after["management"]["state"] == "ready" and not after["management"]["in_flight"]:
                break
            time.sleep(1)
            after = capture_runtime(output_directory)
        write_json(output_directory / "runtime-after.json", after)
        passed = completed and all(result["passed"] for result in measurement.results) and all(check["passed"] for check in quality_checks)
        passed = passed and before["management"]["instance_id"] == after["management"]["instance_id"]
        passed = passed and after["management"]["state"] == "ready" and not after["management"]["in_flight"]
        write_json(output_directory / "state.json", {"status": "completed" if completed else "interrupted",
                   "passed": passed, "completed_requests": len(measurement.results),
                   "quality_passed": sum(check["passed"] for check in quality_checks), "quality_total": len(quality_checks),
                   "updated_at": datetime.now().astimezone().isoformat()})
    if not passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
