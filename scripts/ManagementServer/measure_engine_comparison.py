"""보존한 요청으로 선택 Engine을 측정하며 설정 변경 없이 결과와 실행 증거를 저장합니다."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import time
import uuid

import psutil
import requests


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY))
sys.path.insert(0, str(WORKSPACE_DIRECTORY / "scripts/Strata"))

from benchmark_inputs import read_archived_input, read_input_manifest
from measure_api_baseline import BaselineMeasurement, command_output, write_json
from management_server.configuration import load_configuration
from management_server.llm_profiles import ProfileCatalog


class ComparisonManagementClient:
    """기존 관리 API의 profile·revision·instance 조건으로만 모델을 제어합니다."""

    def __init__(self) -> None:
        """관리 인증값은 저장하거나 출력하지 않고 session 안에서만 사용합니다."""
        configuration = load_configuration()
        self.catalog = ProfileCatalog(configuration["llm"])
        self.session = requests.Session()
        self.base_url = "http://127.0.0.1:8788"
        response = self.session.post(self.base_url + "/api/access",
                                     json={"access_string": configuration["access_string"]}, timeout=20)
        response.raise_for_status()
        self.session.headers["X-CSRF-Token"] = response.json()["csrf"]

    def status(self) -> dict:
        """모델을 Load하지 않고 관리 서버의 현재 상태를 읽습니다."""
        response = self.session.get(self.base_url + "/api/status", timeout=20)
        response.raise_for_status()
        return response.json()

    def control(self, action: str, profile_identifier: str) -> dict:
        """다른 모델이나 사용 중인 요청을 중단하지 않고 선택 profile만 제어합니다."""
        profile = self.catalog.get(profile_identifier)
        configuration = self.catalog.native_configuration(profile)
        state = self.status()["llm"]
        if state.get("in_flight"):
            raise RuntimeError("생성 요청이 진행 중입니다.")
        if action == "stop" and state["state"] == "stopped":
            return state
        if state["state"] != "stopped" and state.get("model") != configuration["model_name"]:
            raise RuntimeError("다른 profile이 실행 중입니다.")
        if action == "start" and state["state"] in ("ready", "starting", "loading"):
            return self.wait_ready(configuration)
        operation_identifier = uuid.uuid4().hex
        payload = {"identifier": operation_identifier, "profile_id": profile_identifier,
                   "configuration_revision": self.catalog.revision(profile)}
        response = self.session.post(self.base_url + "/api/services/llm/" + action, json=payload, timeout=20)
        response.raise_for_status()
        deadline = time.monotonic() + 660
        while time.monotonic() < deadline:
            response = self.session.get(self.base_url + "/api/operations", timeout=20)
            response.raise_for_status()
            operation = next(item for item in response.json() if item["identifier"] == operation_identifier)
            if operation["status"] not in ("queued", "running"):
                if operation["status"] != "succeeded":
                    raise RuntimeError(operation["message"])
                print(json.dumps({"event": action, "operation": operation}, ensure_ascii=False), flush=True)
                if action == "start":
                    return self.wait_ready(configuration)
                for attempt in range(30):
                    state = self.status()["llm"]
                    if state["state"] == "stopped":
                        return state
                    time.sleep(1)
                raise TimeoutError("Engine 종료 후 관리 상태가 갱신되지 않았습니다.")
            time.sleep(2)
        raise TimeoutError("관리 작업을 완료하지 못했습니다.")

    def wait_ready(self, configuration: dict) -> dict:
        """실제 HTTP health와 관리 상태가 함께 준비될 때까지 기다립니다."""
        deadline = time.monotonic() + 650
        while time.monotonic() < deadline:
            state = self.status()["llm"]
            if state["state"] == "ready" and not state.get("in_flight"):
                health = requests.get("http://127.0.0.1:" + str(configuration["port"]) + "/health",
                                      headers={"Authorization": "Bearer " + configuration["api_key"]}, timeout=10)
                if health.status_code == 200:
                    return state
            if state["state"] in ("error", "stopped"):
                raise RuntimeError("Engine이 준비되지 않았습니다: " + json.dumps(state, ensure_ascii=False))
            time.sleep(2)
        raise TimeoutError("Engine readiness 대기 시간이 지났습니다.")


class EngineComparisonMeasurement(BaselineMeasurement):
    """기존 SSE 계측을 유지하며 Infernix의 native telemetry도 함께 정산합니다."""

    def measure(self, identifier, payload, expected_fragments=None, expected_http_status=200):
        """요청 hash·진행 상태와 Engine별 원본 timing을 보존합니다."""
        previous_request_id = 0
        if self.configuration.get("engine_release"):
            previous_requests = self.get_json("/metrics?format=json").get("requests", [])
            previous_request_id = max((item["id"] for item in previous_requests), default=0)
        write_json(self.output_directory / "state.json", {"status": "running", "case": identifier,
                   "completed_requests": len(self.results), "updated_at": datetime.now().astimezone().isoformat()})
        result = super().measure(identifier, payload, expected_fragments, expected_http_status)
        if self.configuration.get("engine_release"):
            metrics = self.get_json("/metrics?format=json")
            write_json(self.output_directory / (identifier + ".metrics.json"), metrics)
            native_requests = [item for item in metrics.get("requests", []) if item["id"] > previous_request_id]
            if native_requests:
                native = max(native_requests, key=lambda item: item["id"])
                result["native_metrics"] = native
                if not result["timings"]:
                    result["timings"] = {
                        "cache_n": native["reused"], "prompt_n": native["prompt_tokens"] - native["reused"],
                        "prompt_ms": native["prompt_ms"], "prompt_per_second": native["prefill_tok_s"],
                        "predicted_n": native["output_tokens"], "predicted_ms": native["decode_ms"],
                        "predicted_per_second": native["decode_tok_s"],
                        "draft_n": native["drafts_offered"], "draft_n_accepted": native["drafts_accepted"],
                    }
                write_json(self.output_directory / (identifier + ".normalized.json"), result)
                print(json.dumps({"event": "native_timing", "case": identifier, "native_metrics": native}), flush=True)
        return result


def archived_cases(full_suite: bool) -> list[tuple[dict, dict]]:
    """직전 Strata 재검증의 요청 순서와 원본 payload를 hash 검증 후 복원합니다."""
    baseline = json.loads((WORKSPACE_DIRECTORY / "docs/Strata/benchmarks/2026-11-03-web-restart-revalidation.json")
                          .read_text(encoding="utf-8"))
    saved_files = read_input_manifest()["files"]
    selected_cases = []
    for result in baseline["managed_api"]["results"]:
        identifier = result["case"]
        if not full_suite:
            shared_case = identifier.startswith(("decode-", "short-generation-", "style-"))
            shared_case = shared_case or identifier in ("warmup", "retrieval-8192", "retrieval-32768", "retrieval-131072")
            if not shared_case:
                continue
        suffix = "/2026-11-03-web-restart/" + identifier + ".request.json"
        entries = [entry for entry in saved_files if entry["source"].replace("\\", "/").endswith(suffix)]
        if len(entries) != 1:
            raise ValueError("원본 요청을 확정할 수 없습니다: " + identifier)
        payload = read_archived_input(entries[0]["archive_entry"])
        request_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if request_hash != result["request_sha256"]:
            raise ValueError("Baseline 요청 hash가 다릅니다: " + identifier)
        selected_cases.append((result, payload))
    return selected_cases


def payload_for_profile(original_payload: dict, model_name: str) -> dict:
    """정상 실행 model만 치환하며 미실행 model 거부 검사의 입력은 보존합니다."""
    payload = dict(original_payload)
    if payload.get("model") == "sc117-qwen3.8-flash-next-abliterated-iq3_xxs":
        payload["model"] = model_name
    return payload


def capture_runtime(configuration: dict, client: ComparisonManagementClient) -> dict:
    """Secret 없는 실행 인자·환경·BUILD와 관리 instance를 기록합니다."""
    native_processes = []
    for process in psutil.process_iter(["pid", "name", "cmdline", "create_time"]):
        if process.info["name"] not in ("strata.exe", "strata-poly.exe", "infernix-serve.exe"):
            continue
        record = dict(process.info)
        environment = process.environ()
        record["environment"] = {name: value for name, value in environment.items() if name.startswith("STRATA_PREFILL_")}
        build_path = Path(record["cmdline"][0]).parent / "BUILD.json"
        if build_path.exists():
            record["build"] = json.loads(build_path.read_text(encoding="utf-8-sig"))
        native_processes.append(record)
    return {"recorded_at": datetime.now().astimezone().isoformat(), "native": native_processes,
            "management": client.status()["llm"], "model": configuration["model_name"]}


def main() -> None:
    """명시한 profile의 기동·종료 또는 동일 입력 측정을 수행하며 설정을 바꾸지 않습니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--action", choices=("start", "stop", "measure"), default="measure")
    parser.add_argument("--output-directory", type=Path)
    parser.add_argument("--full-strata-suite", action="store_true")
    parser.add_argument("--historical-polystrata-note", action="store_true")
    parser.add_argument("--historical-note-sampling", choices=("profile", "legacy-greedy"), default="profile")
    arguments = parser.parse_args()
    client = ComparisonManagementClient()
    profile = client.catalog.get(arguments.profile)
    if arguments.action != "measure":
        print(json.dumps(client.control(arguments.action, arguments.profile), ensure_ascii=False), flush=True)
        return
    if arguments.output_directory is None:
        parser.error("--output-directory가 필요합니다.")
    output_directory = arguments.output_directory
    if output_directory.exists() and any(output_directory.iterdir()):
        parser.error("기존 결과를 보존하기 위해 새로운 output directory를 사용합니다.")
    output_directory.mkdir(parents=True, exist_ok=True)
    configuration_path = WORKSPACE_DIRECTORY / profile["configuration_path"]
    measurement = EngineComparisonMeasurement(configuration_path, output_directory)
    before = capture_runtime(measurement.configuration, client)
    if before["management"]["state"] != "ready" or before["management"].get("in_flight"):
        raise RuntimeError("선택 Engine이 idle·ready 상태여야 합니다.")
    if before["management"]["model"] != measurement.configuration["model_name"]:
        raise RuntimeError("실행 중인 모델이 선택 profile과 다릅니다.")
    queue_response = requests.get("http://127.0.0.1:8188/queue", timeout=10)
    queue_response.raise_for_status()
    queue = queue_response.json()
    if queue.get("queue_running") or queue.get("queue_pending"):
        raise RuntimeError("ComfyUI queue에 작업이 있습니다.")
    configuration_hash = hashlib.sha256(configuration_path.read_bytes()).hexdigest()
    write_json(output_directory / "runtime-before.json", before)
    measurement.record_environment()
    environment_path = output_directory / "environment.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8"))
    engine_directory_name = {"strata": "Strata", "polystrata": "PolyStrata", "infernix": "Infernix"}[profile["engine"]]
    environment["source_commit"] = command_output(["git", "-C", str(WORKSPACE_DIRECTORY / "external_repo" / engine_directory_name),
                                                    "rev-parse", "HEAD"])
    environment["comparison_harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    environment["resource_note"] = "RAM and GPU samples describe the whole system; the legacy Strata Working Set field is not used for other engines."
    write_json(environment_path, environment)
    input_evidence = []
    completed = False
    try:
        if arguments.historical_polystrata_note:
            historical_payload = {
                "model": measurement.configuration["model_name"], "max_tokens": 128, "reasoning_effort": "none",
                "messages": [{"role": "user", "content": "Summarize the following repeated operational note in three sentences. "
                              + "The local LLM uses CPU Vision, a Q8 KV cache, and one active execution profile. " * 180}],
            }
            if arguments.historical_note_sampling == "legacy-greedy":
                historical_payload.update(temperature=0, presence_penalty=0, repetition_penalty=1, frequency_penalty=0)
            measurement.measure("historical-polystrata-note", historical_payload)
        for baseline, original_payload in archived_cases(arguments.full_strata_suite):
            payload = payload_for_profile(original_payload, measurement.configuration["model_name"])
            expected_status = baseline["http_status"]
            measurement.measure(baseline["case"], payload, baseline.get("expected_fragments"), expected_status)
            input_evidence.append({"case": baseline["case"], "baseline_request_sha256": baseline["request_sha256"],
                                   "model_only_replaced": payload != original_payload,
                                   "messages_sha256": hashlib.sha256(json.dumps(payload["messages"], sort_keys=True,
                                                                               ensure_ascii=False).encode()).hexdigest()})
        completed = True
    finally:
        measurement.finish()
        write_json(output_directory / "input-evidence.json", input_evidence)
        write_json(output_directory / "runtime-after.json", capture_runtime(measurement.configuration, client))
        unchanged = configuration_hash == hashlib.sha256(configuration_path.read_bytes()).hexdigest()
        write_json(output_directory / "state.json", {"status": "completed" if completed else "interrupted",
                   "completed_requests": len(measurement.results), "configuration_unchanged": unchanged,
                   "passed": sum(result["passed"] for result in measurement.results),
                   "updated_at": datetime.now().astimezone().isoformat()})
        if not unchanged:
            raise RuntimeError("측정 중 실행 설정이 변경됐습니다.")
    if any(not result["passed"] for result in measurement.results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
