"""같은 IQ3_XXS 설정에서 Engine 인자를 한 항목씩 바꾸어 API로 비교합니다."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import uuid

import psutil
import requests

SCRIPT_DIRECTORY = Path(__file__).resolve().parent
WORKSPACE_DIRECTORY = SCRIPT_DIRECTORY.parents[1]
sys.path.insert(0, str(SCRIPT_DIRECTORY))
sys.path.insert(0, str(WORKSPACE_DIRECTORY / "external_repo/Strata"))

from measure_api_baseline import BaselineMeasurement
from optimize_api_profile import (DEFAULT_OUTPUT_DIRECTORY, TASKS, atomic_json, check_fixed_configuration,
                                  geometric_mean, record_progress, timestamp)
from strata_control.tune_session import WorkerSession
from strata_control import draft_layer
from summarize_optimization_results import summarize_trials
from measure_optimization_quality import measure_quality, measure_style


CANDIDATES = {
    "baseline": {"args": {}, "env": {}},
    "baseline-tail": {"args": {}, "env": {}},
    "mtp-on": {"args": {}, "env": {}},
    "mtp-off": {"args": {}, "env": {}, "configuration": {"drafting": "off", "mtp": False}},
    "mtp-off-kv20k": {"args": {"--kv-resident": "20480"}, "env": {}, "configuration": {"drafting": "off", "mtp": False}},
    "prefill-4096": {"args": {"--prefill": "4096"}, "env": {}},
    "prefill-8192": {"args": {"--prefill": "8192"}, "env": {}},
    "prefill-16384": {"args": {"--prefill": "16384"}, "env": {}},
    "workers-4": {"args": {"--pool-workers": "4"}, "env": {}},
    "workers-5": {"args": {"--pool-workers": "5"}, "env": {}},
    "workers-6": {"args": {"--pool-workers": "6"}, "env": {}},
    "host-core-last": {"args": {"--host-core": "last"}, "env": {}},
    "spec-3": {"args": {"--spec": "3"}, "env": {}},
    "kv-resident-16k": {"args": {"--kv-resident": "16384"}, "env": {}},
    "kv-resident-20k": {"args": {"--kv-resident": "20480"}, "env": {}},
    "kv-resident-48k": {"args": {"--kv-resident": "49152"}, "env": {}},
    "kv-resident-64k": {"args": {"--kv-resident": "65536"}, "env": {}},
    "adapt-async": {"args": {"--adapt-async": "1"}, "env": {}},
    "adapt-faster": {"args": {"--adapt-every": "1", "--adapt-swaps": "80", "--adapt-decay": "0.97"}, "env": {}},
    "adapt-decay-09": {"args": {"--adapt-decay": "0.9"}, "env": {}},
    "prefill-cpu-share-off": {"args": {}, "env": {"STRATA_PREFILL_CPU_SHARE": "0"}},
    "adapt-overlap": {"args": {}, "env": {"STRATA_ADAPT_OVERLAP": "1"}},
    "pin-by-need": {"args": {}, "env": {"STRATA_PIN_BY_NEED": "1"}},
    "prefill-routed-stream": {"args": {}, "env": {"STRATA_PREFILL_ROUTED_STREAM": "1"}},
    "pcie-balance": {"args": {}, "env": {"STRATA_PCIE_BALANCE": "1"}},
    "prefill-unfused": {"args": {}, "env": {"STRATA_PF_FUSED": "0"}},
    "prefill-unfused-layer-major": {"args": {}, "env": {"STRATA_PF_FUSED": "0", "STRATA_PREFILL_LAYER_MAJOR": "1"}},
    "prefill-unfused-layer-major-kv20k": {"args": {"--kv-resident": "20480"},
                                          "env": {"STRATA_PF_FUSED": "0", "STRATA_PREFILL_LAYER_MAJOR": "1"}},
    "prefill-layer-major": {"args": {}, "env": {"STRATA_PREFILL_LAYER_MAJOR": "1"}},
    "prefill-layer-major-host": {"args": {}, "env": {"STRATA_PREFILL_LAYER_MAJOR": "1", "STRATA_PREFILL_LM_R": "host"}},
    "prefill-layer-major-host-4k": {"args": {}, "env": {"STRATA_PREFILL_LAYER_MAJOR": "1", "STRATA_PREFILL_LM_R": "host",
                                                       "STRATA_PREFILL_LM_TOKENS": "4096"}},
    "prefill-layer-major-host-16k": {"args": {}, "env": {"STRATA_PREFILL_LAYER_MAJOR": "1", "STRATA_PREFILL_LM_R": "host",
                                                        "STRATA_PREFILL_LM_TOKENS": "16384"}},
    "mtp-off-layer-major-host-16k": {"args": {}, "configuration": {"drafting": "off", "mtp": False},
                                    "env": {"STRATA_PREFILL_LAYER_MAJOR": "1", "STRATA_PREFILL_LM_R": "host",
                                            "STRATA_PREFILL_LM_TOKENS": "16384"}},
}

DEFAULT_CANDIDATES = ["baseline", "workers-6", "host-core-last", "spec-3", "kv-resident-48k", "kv-resident-64k",
                      "adapt-async", "adapt-faster", "prefill-cpu-share-off", "adapt-overlap", "baseline-tail"]


class ManagementClient:
    """기존 관리 API를 통해 현재 profile만 종료·복원합니다."""

    def __init__(self, output_directory: Path) -> None:
        """접속 문자열과 CSRF는 저장하거나 출력하지 않습니다."""
        self.output_directory = output_directory
        self.session = requests.Session()
        self.base_url = "http://127.0.0.1:8788"
        configuration = json.loads((WORKSPACE_DIRECTORY / "config/ManagementServer/management.local.json").read_text(encoding="utf-8-sig"))
        response = self.session.post(self.base_url + "/api/access", json={"access_string": configuration["access_string"]}, timeout=20)
        response.raise_for_status()
        self.session.headers["X-CSRF-Token"] = response.json()["csrf"]

    def status(self) -> dict:
        """현재 서비스 상태의 안전한 API 응답을 조회합니다."""
        response = self.session.get(self.base_url + "/api/status", timeout=20)
        response.raise_for_status()
        return response.json()

    def control(self, action: str) -> None:
        """실제 profile·revision을 고정해 한 번의 제어 작업을 완료합니다."""
        state = self.status()["llm"]
        if action == "stop" and state["state"] == "stopped":
            return
        if action == "start" and state["state"] == "ready":
            return
        if state.get("in_flight", 0):
            raise RuntimeError("A user request is in flight; refusing to interrupt it")
        if action == "stop" and state.get("model") != "sc117-qwen3.8-flash-next-abliterated-iq3_xxs":
            raise RuntimeError("The active model is not the requested IQ3_XXS profile")
        profile = next(profile for profile in state["profiles"] if profile["identifier"] == "strata-qwen-flash-next")
        identifier = uuid.uuid4().hex
        payload = {"identifier": identifier, "profile_id": profile["identifier"], "configuration_revision": profile["revision"]}
        response = self.session.post(self.base_url + "/api/services/llm/" + action, json=payload, timeout=20)
        response.raise_for_status()
        record_progress(self.output_directory, "management_" + action + "_accepted", management_operation=identifier)
        for _ in range(660):
            response = self.session.get(self.base_url + "/api/operations", timeout=20)
            response.raise_for_status()
            operation = next(operation for operation in response.json() if operation["identifier"] == identifier)
            if operation["status"] not in ("queued", "running"):
                record_progress(self.output_directory, "management_" + action + "_finished", management_result=operation)
                if operation["status"] != "succeeded":
                    raise RuntimeError("Managed " + action + " failed: " + operation["message"])
                return
            time.sleep(1)
        raise RuntimeError("Management operation timed out")


def changed_arguments(original_arguments: list[str], overrides: dict) -> list[str]:
    """명시한 인자만 바꾸고 나머지 실행 설정은 보존합니다."""
    arguments = list(original_arguments)
    for flag, value in overrides.items():
        if flag in arguments:
            arguments[arguments.index(flag) + 1] = str(value)
        else:
            arguments.extend([flag, str(value)])
    return arguments


def wait_for_memory() -> None:
    """이전 Engine의 RAM 반환을 기다리고 다른 앱의 queue가 비어 있는지 확인합니다."""
    for _ in range(90):
        if psutil.virtual_memory().available >= 54 * 2**30:
            break
        time.sleep(1)
    else:
        raise RuntimeError("Not enough RAM to start a fresh comparison worker")
    response = requests.get("http://127.0.0.1:8188/queue", timeout=10)
    response.raise_for_status()
    queue = response.json()
    if queue.get("queue_running") or queue.get("queue_pending"):
        raise RuntimeError("ComfyUI has work queued; comparison is paused without changing that work")


def trial_summary(trial_directory: Path, name: str, settings: dict, results: list[dict], facts: dict, quality_checks: list[dict]) -> dict:
    """후보의 API 속도·정답·메모리를 각각의 지표로 요약합니다."""
    decode_results = [result for result in results if result["case"].startswith("decode-")]
    retrieval = next(result for result in results if result["case"] == "retrieval-32768")
    valid = all(result["http_status"] == 200 and not result["error"] and result["done_received"] for result in results)
    valid = valid and all(result["usage"].get("completion_tokens", 0) >= 256 for result in decode_results)
    summary = {"trial": name, "finished_at": timestamp(), "status": "completed" if valid else "failed",
               "quality_all_passed": all(result["passed"] for result in results) and all(check["passed"] for check in quality_checks),
               "quality_checks": quality_checks,
               "quality_failures": [{"case": result["case"], "content": result["content"],
                                     "expected_fragments": result["expected_fragments"]}
                                    for result in results if not result["passed"]],
               "retrieval_passed": retrieval["passed"],
               "settings": settings, "decode_geometric_mean": geometric_mean([result["timings"]["predicted_per_second"] for result in decode_results]),
               "prefill_tokens_per_second": retrieval["timings"].get("prompt_per_second"),
               "long_prompt_ttft_seconds": retrieval["first_token_seconds"],
               "gpu_peak_used_mib": max(result["resources"].get("gpu_peak_used_mib", 0) for result in results),
               "strata_peak_working_set_sum_gib": max(result["resources"].get("strata_peak_working_set_sum_gib", 0) for result in results),
               "ram_min_available_gib": min(result["resources"].get("ram_min_available_gib", 1000) for result in results),
               "facts": facts, "results": results}
    atomic_json(trial_directory / "summary.json", summary)
    return summary


def measure_long_context(measurement: BaselineMeasurement, fixture_directory: Path, output_directory: Path) -> None:
    """동일한 128K·260K 문서 검색과 큰 KV를 재사용하는 512-token 생성을 비교합니다."""
    for target in (131072, 260000):
        name = "retrieval-" + str(target)
        payload = json.loads((fixture_directory / (name + ".request.json")).read_text(encoding="utf-8"))
        fixture = json.loads((fixture_directory / (name + ".fixture.json")).read_text(encoding="utf-8"))
        record_progress(output_directory, "long_request_started", current_request=name)
        result = measurement.measure(name, payload, fixture["values"])
        record_progress(output_directory, "long_request_finished", current_request=name, last_passed=result["passed"])
    content = payload["messages"][0]["content"]
    records = re.findall(r"record (\d+): zone=([0-9a-f]+);", content)
    record_number, expected_zone = records[len(records) // 3]
    messages = [*payload["messages"], {"role": "assistant", "content": result["content"]},
                {"role": "user", "content": f"원래 문서의 record {record_number}의 zone 값을 첫 줄에 정확하게 쓰세요. 이어서 로컬 LLM 서버 운영 체크리스트 30개를 한국어로 쓰세요. 각 항목은 두 문장으로 쓰고 끝까지 계속하세요."}]
    record_progress(output_directory, "long_request_started", current_request="long-generation-260k")
    result = measurement.measure("long-generation-260k", measurement.request_payload(messages, 512), [expected_zone])
    record_progress(output_directory, "long_request_finished", current_request="long-generation-260k", last_passed=result["passed"])


def measure_trial(output_directory: Path, identifier: str, settings: dict, request_settings: dict, quality_suite: bool = False,
                  long_suite: bool = False, style_suite: bool = False) -> dict:
    """공식 WorkerSession으로 복사된 설정을 기동하고 실제 HTTP API를 측정합니다."""
    trial_directory = output_directory / "restart-screen" / identifier
    if (trial_directory / "summary.json").exists():
        return json.loads((trial_directory / "summary.json").read_text(encoding="utf-8"))
    trial_directory.mkdir(parents=True, exist_ok=True)
    attempt_number = len(list(trial_directory.glob("worker-attempt-*"))) + 1
    attempt_name = f"attempt-{attempt_number:03d}"
    base = json.loads((output_directory / "original-configuration/strata.local.json").read_text(encoding="utf-8-sig"))
    base["args"] = changed_arguments(base["args"], settings["args"])
    base.update(copy.deepcopy(settings.get("configuration", {})))
    draft_layer.apply(base)
    check_fixed_configuration(base)
    atomic_json(trial_directory / "candidate.json", {"args": base["args"], "env": settings["env"], "request_settings": request_settings,
                                                    "configuration_overrides": settings.get("configuration", {})})
    wait_for_memory()
    extra_environment = {"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1", "PYTHONUTF8": "1",
                         "STRATA_NO_ACQUIRE": "1", "STRATA_REQUIRE_SIGNED_COMPONENTS": "1",
                         "STRATA_COMPONENTS_DIR": "C:/Strata-data/components",
                         "STRATA_PROFILE_DIR": str(WORKSPACE_DIRECTORY / "config/Strata/profiles")}
    worker_session = WorkerSession(base_config=base, python=sys.executable, serve_dir=WORKSPACE_DIRECTORY / "external_repo/Strata",
                                   workdir=trial_directory / ("worker-" + attempt_name), extra_env=extra_environment,
                                   log=lambda message: print(message, flush=True))
    record_progress(output_directory, "trial_started", stage="restart-screen", status="running", current_trial=identifier,
                    trial_status="running", current_request=None)
    with worker_session.engine(base["args"], settings["env"]) as engine:
        private_configuration = copy.deepcopy(base)
        private_configuration.update(port=engine.port, api_key=engine.key)
        configuration_path = trial_directory / ("measurement-" + attempt_name + ".local.json")
        atomic_json(configuration_path, private_configuration)
        measurement = BaselineMeasurement(configuration_path, trial_directory / ("api-" + attempt_name))
        measurement.record_environment()
        health = measurement.get_json("/health")
        if health.get("max_context") != 262144:
            raise RuntimeError("Candidate did not preserve the full Context")
        native_processes = []
        for process in psutil.process_iter(["name", "cmdline"]):
            try:
                if process.info["name"] == "strata.exe":
                    native_processes.append(process.info["cmdline"])
            except psutil.Error:
                continue
        if len(native_processes) != 1:
            raise RuntimeError("Expected exactly one native comparison Engine")
        check_fixed_configuration({"args": native_processes[0]})
        if settings.get("configuration", {}).get("mtp") is False and "--mtp" in native_processes[0]:
            raise RuntimeError("MTP off candidate still loaded the draft layer")
        engine.facts["actual_native_arguments"] = native_processes[0]
        for warmup_number in range(2):
            payload = measurement.request_payload([{"role": "user", "content": f"Warmup {warmup_number}: explain how a computer works in detail."}], 64)
            payload["strata_checkpoint"] = False
            measurement.measure(f"warmup-{warmup_number}", payload)
        for task_name, task in TASKS.items():
            payload = measurement.request_payload([{"role": "user", "content": task}], 384)
            payload["strata_checkpoint"] = False
            if request_settings:
                payload["strata_tune"] = request_settings
            result = measurement.measure("decode-" + task_name, payload)
            if not result["passed"]:
                raise RuntimeError("Decode probe failed")
        fixture_directory = WORKSPACE_DIRECTORY / "runtime/Strata/benchmarks/2026-11-03-engine-0.1.56-context-262144/core"
        payload = json.loads((fixture_directory / "retrieval-32768.request.json").read_text(encoding="utf-8"))
        fixture = json.loads((fixture_directory / "retrieval-32768.fixture.json").read_text(encoding="utf-8"))
        payload["strata_checkpoint"] = False
        if request_settings:
            payload["strata_tune"] = request_settings
        measurement.measure("retrieval-32768", payload, fixture["values"])
        payload = measurement.request_payload([{"role": "user", "content": "17*23+19를 계산해서 숫자만 출력하세요."}], 64)
        if request_settings:
            payload["strata_tune"] = request_settings
        measurement.measure("quality-arithmetic", payload, ["410"])
        payload = measurement.request_payload([{"role": "user", "content": "검산 후 답하세요. 23*17+19의 값은?"}], 512)
        payload.update(reasoning_effort="medium", reasoning_budget_tokens=256)
        if request_settings:
            payload["strata_tune"] = request_settings
        measurement.measure("quality-arithmetic-medium", payload, ["410"])
        quality_checks = measure_quality(measurement) if quality_suite else []
        if quality_suite or style_suite:
            measure_style(measurement)
        if long_suite:
            measure_long_context(measurement, fixture_directory, output_directory)
        measurement.finish()
        engine_log = next((trial_directory / ("worker-" + attempt_name)).glob("engine-*.log"))
        engine.facts["prompt_configuration_log"] = [line for line in engine_log.read_text(encoding="utf-8", errors="replace").splitlines()
                                                     if "prompt chunk" in line or "KV streaming:" in line or "short of GPU memory" in line]
        summary = trial_summary(trial_directory, identifier, settings, measurement.results, engine.facts, quality_checks)
    record_progress(output_directory, "trial_finished", current_trial=identifier, trial_status=summary["status"],
                    last_decode=summary["decode_geometric_mean"], last_prefill=summary["prefill_tokens_per_second"])
    summarize_trials(output_directory)
    print(json.dumps({key: summary[key] for key in ("trial", "status", "decode_geometric_mean", "prefill_tokens_per_second", "gpu_peak_used_mib")}), flush=True)
    return summary


def main() -> None:
    """실험 전 서비스만 종료하고 성공·실패 모두 원래 운영 profile을 다시 켭니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--trials", nargs="+", choices=list(CANDIDATES), default=DEFAULT_CANDIDATES)
    parser.add_argument("--round", type=int, default=1)
    parser.add_argument("--repeat-rounds", type=int, default=1)
    parser.add_argument("--request-settings", type=json.loads, default={})
    parser.add_argument("--quality-suite", action="store_true")
    parser.add_argument("--long-suite", action="store_true")
    parser.add_argument("--style-suite", action="store_true")
    arguments = parser.parse_args()
    if arguments.repeat_rounds < 1:
        parser.error("--repeat-rounds must be positive")
    snapshot_directory = arguments.output_directory / "protocol-snapshots" / uuid.uuid4().hex
    snapshot_directory.mkdir(parents=True)
    source_hashes = {}
    for filename in ("measure_engine_candidates.py", "measure_optimization_quality.py", "summarize_optimization_results.py",
                     "optimize_api_profile.py", "measure_api_baseline.py"):
        source_bytes = (SCRIPT_DIRECTORY / filename).read_bytes()
        (snapshot_directory / filename).write_bytes(source_bytes)
        source_hashes[filename] = hashlib.sha256(source_bytes).hexdigest()
    atomic_json(snapshot_directory / "manifest.json", {"created_at": timestamp(), "source_sha256": source_hashes,
                                                     "trials": arguments.trials, "round": arguments.round,
                                                     "repeat_rounds": arguments.repeat_rounds,
                                                     "quality_suite": arguments.quality_suite, "long_suite": arguments.long_suite,
                                                     "style_suite": arguments.style_suite})
    record_progress(arguments.output_directory, "batch_sources_saved", protocol_snapshot=str(snapshot_directory))
    manager = ManagementClient(arguments.output_directory)
    manager.control("stop")
    batch_completed = False
    try:
        for repetition in range(arguments.repeat_rounds):
            names = list(arguments.trials)
            if repetition % 2:
                names.reverse()
            for name in names:
                identifier = f"r{arguments.round + repetition:02d}-" + name
                try:
                    summary = measure_trial(arguments.output_directory, identifier, CANDIDATES[name], arguments.request_settings,
                                            quality_suite=arguments.quality_suite, long_suite=arguments.long_suite,
                                            style_suite=arguments.style_suite)
                except Exception as error:
                    record_progress(arguments.output_directory, "trial_failed", current_trial=identifier,
                                    status="failed", error=str(error), next_action="Inspect worker logs before retrying; production profile is restored in finally.")
                    raise
                if summary["status"] != "completed":
                    raise RuntimeError("Candidate API measurement is invalid: " + identifier)
        batch_completed = True
    finally:
        record_progress(arguments.output_directory, "restoring_production", status="restoring")
        manager.control("start")
        record_progress(arguments.output_directory, "restart_screen_completed" if batch_completed else "restart_screen_failed_and_restored",
                        stage="restart-screen", status="completed" if batch_completed else "failed",
                        next_action="Review candidate summaries, then run paired confirmation and the full regression suite."
                                    if batch_completed else "Inspect failed trial; the production profile has been restored.")


if __name__ == "__main__":
    main()
