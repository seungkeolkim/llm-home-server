"""고정 Context·reserve 아래에서 API 튜닝 실험을 저장하고 중단 후 이어갑니다."""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
import shutil
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_api_baseline import BaselineMeasurement


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIRECTORY = WORKSPACE_DIRECTORY / "runtime/Strata/tuning/iq3-xxs-reserve8192-context262144"
CONFIGURATION_PATH = WORKSPACE_DIRECTORY / "config/Strata/strata.local.json"
TASKS = {
    "korean": "한국어로 로컬 서버 운영 체크리스트 50개를 작성하세요. 각 항목은 구체적인 두 문장으로 쓰고 50번까지 계속하세요. 설명을 생략하거나 항목을 합치지 마세요.",
    "code": "Write a complete Python module implementing a persistent job queue with SQLite, retries, transactions, leases and tests. Include full functions and docstrings. Continue writing code until the module and tests are complete.",
    "english": "Explain how a modern computer processes a network request in 50 numbered steps. Give two detailed sentences per step, from DNS through TLS, HTTP, application logic and storage. Continue until all 50 steps are complete.",
}
API_ARMS = {
    "auto-head": {}, "pcie-000": {"pcie_frac": 0.0}, "pcie-020": {"pcie_frac": 0.2},
    "pcie-035": {"pcie_frac": 0.35}, "pcie-050": {"pcie_frac": 0.5},
    "spec-confidence-070": {"spec_min_p": 0.7}, "auto-tail": {},
}


def timestamp() -> str:
    """사용자 timezone이 포함된 현재 시각을 반환합니다."""
    return datetime.now().astimezone().isoformat()


def atomic_json(output_path: Path, value: object) -> None:
    """Windows에서 잠깐 잠긴 상태 파일도 이전 JSON을 보존하며 교체합니다."""
    temporary_path = output_path.with_suffix(output_path.suffix + ".pending")
    temporary_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt in range(5):
        try:
            temporary_path.replace(output_path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


def record_progress(output_directory: Path, event: str, **details) -> None:
    """요청 전후의 상태와 append-only 이력을 즉시 저장합니다."""
    state_path = output_directory / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state.update(updated_at=timestamp(), event=event, **details)
    atomic_json(state_path, state)
    with (output_directory / "events.jsonl").open("a", encoding="utf-8") as event_stream:
        event_stream.write(json.dumps({"at": state["updated_at"], "event": event, **details}, ensure_ascii=False) + "\n")


def initialize_optimization_run(output_directory: Path) -> None:
    """새 실험에만 원본 설정과 상태를 만들고 기존 진행 기록은 보존합니다."""
    runtime_directory = (WORKSPACE_DIRECTORY / "runtime/Strata").resolve()
    if not output_directory.resolve().is_relative_to(runtime_directory):
        raise ValueError("Optimization output must stay under runtime/Strata because it includes private configuration")
    state_path = output_directory / "state.json"
    original_directory = output_directory / "original-configuration"
    original_path = original_directory / "strata.local.json"
    if state_path.exists():
        if not original_path.exists():
            raise ValueError("The existing run has no original configuration")
        return
    if output_directory.exists() and any(output_directory.iterdir()):
        raise ValueError("Refusing to initialize a nonempty run without state.json")
    configuration = json.loads(CONFIGURATION_PATH.read_text(encoding="utf-8-sig"))
    check_fixed_configuration(configuration)
    original_directory.mkdir(parents=True)
    shutil.copy2(CONFIGURATION_PATH, original_path)
    atomic_json(state_path, {"started_at": timestamp(), "stage": "prepared", "status": "prepared",
                            "fixed": {"context_tokens": 262144, "reserve_mib": 8192,
                                      "model": configuration["model_name"]}})


def check_fixed_configuration(configuration: dict) -> None:
    """사용자가 고정한 두 인자가 달라지면 실험 전에 중단합니다."""
    arguments = configuration["args"]
    for flag, expected in (("--max-context", "262144"), ("--vram-reserve-mib", "8192")):
        if str(arguments[arguments.index(flag) + 1]) != expected:
            raise RuntimeError("Fixed setting changed: " + flag)


def completed_result(suite_directory: Path, identifier: str) -> dict | None:
    """완전하게 저장된 결과만 재사용하며 중간에 끊긴 파일은 재측정합니다."""
    result_path = suite_directory / (identifier + ".response.json")
    if not result_path.exists():
        return None
    try:
        return json.loads(result_path.read_text(encoding="utf-8"))["result"]
    except (ValueError, KeyError):
        return None


def geometric_mean(values: list[float]) -> float:
    """서로 다른 task의 상대 속도를 같은 비중으로 합칩니다."""
    return math.exp(sum(math.log(value) for value in values) / len(values))


def summarize_api_screen(suite_directory: Path, rounds: int) -> dict:
    """각 round의 앞·뒤 baseline으로 drift를 계산하고 후보의 상대 속도를 비교합니다."""
    results = {}
    for result_path in suite_directory.glob("*.response.json"):
        result = json.loads(result_path.read_text(encoding="utf-8"))["result"]
        results[result["case"]] = result
    summaries = {}
    baseline_drift = []
    for arm_name in API_ARMS:
        if arm_name.startswith("auto-"):
            continue
        round_ratios = []
        for round_number in range(1, rounds + 1):
            ratios = []
            for task_name in TASKS:
                candidate = results.get(f"r{round_number:02d}-{arm_name}-{task_name}")
                first = results.get(f"r{round_number:02d}-auto-head-{task_name}")
                last = results.get(f"r{round_number:02d}-auto-tail-{task_name}")
                if not all((candidate, first, last)):
                    continue
                if not all(result["passed"] and result["usage"].get("completion_tokens", 0) >= 256 for result in (candidate, first, last)):
                    continue
                first_rate = first["timings"]["predicted_per_second"]
                last_rate = last["timings"]["predicted_per_second"]
                control_rate = math.sqrt(first_rate * last_rate)
                ratios.append(candidate["timings"]["predicted_per_second"] / control_rate)
                if arm_name == "pcie-000":
                    baseline_drift.append(abs(last_rate / first_rate - 1))
            if len(ratios) == len(TASKS):
                round_ratios.append(geometric_mean(ratios))
        summaries[arm_name] = {"request_settings": API_ARMS[arm_name], "round_ratios": round_ratios,
                               "median_ratio": statistics.median(round_ratios) if round_ratios else None,
                               "faster_rounds": sum(ratio > 1 for ratio in round_ratios)}
    ranked = sorted(summaries, key=lambda name: summaries[name]["median_ratio"] or 0, reverse=True)
    return {"created_at": timestamp(), "stage": "api-screen", "request_count": len(results),
            "failed_requests": [name for name, result in results.items() if not result["passed"]],
            "baseline_median_absolute_drift": statistics.median(baseline_drift) if baseline_drift else None,
            "arms": summaries, "ranked_arms": ranked, "adopted": False,
            "note": "Screening only. A candidate still needs fresh-engine paired confirmation, long-context and correctness checks."}


def screen_api(output_directory: Path, rounds: int) -> None:
    """재기동 없이 적용되는 인자를 순서를 바꾼 반복으로 측정합니다."""
    suite_directory = output_directory / "api-screen"
    measurement = BaselineMeasurement(CONFIGURATION_PATH, suite_directory)
    check_fixed_configuration(measurement.configuration)
    if not (suite_directory / "environment.json").exists():
        measurement.record_environment()
    candidates = [name for name in API_ARMS if not name.startswith("auto-")]
    completed_count = len(list(suite_directory.glob("*.response.json")))
    record_progress(output_directory, "api_screen_started", stage="api-screen", status="running", completed_requests=completed_count)
    for round_number in range(1, rounds + 1):
        candidate_order = list(candidates)
        if round_number % 2 == 0:
            candidate_order.reverse()
        else:
            offset = (round_number - 1) % len(candidate_order)
            candidate_order = candidate_order[offset:] + candidate_order[:offset]
        for arm_name in ["auto-head", *candidate_order, "auto-tail"]:
            for task_name, task in TASKS.items():
                identifier = f"r{round_number:02d}-{arm_name}-{task_name}"
                previous = completed_result(suite_directory, identifier)
                if previous is not None:
                    continue
                record_progress(output_directory, "request_started", current_request=identifier)
                nonce = hashlib.sha256(identifier.encode()).hexdigest()[:12]
                prompt = f"Reference {nonce}. Ignore this reference identifier in your answer.\n{task}"
                payload = measurement.request_payload([{"role": "user", "content": prompt}], 384)
                payload["strata_checkpoint"] = False
                if API_ARMS[arm_name]:
                    payload["strata_tune"] = API_ARMS[arm_name]
                result = measurement.measure(identifier, payload)
                completed_count += 1
                record_progress(output_directory, "request_finished", current_request=identifier,
                                completed_requests=completed_count, last_passed=result["passed"])
                if not result["passed"]:
                    raise RuntimeError("API screening failed: " + identifier)
        summary = summarize_api_screen(suite_directory, rounds)
        atomic_json(suite_directory / "summary.json", summary)
    summary = summarize_api_screen(suite_directory, rounds)
    atomic_json(suite_directory / "summary.json", summary)
    record_progress(output_directory, "api_screen_completed", stage="api-screen", status="completed",
                    ranked_arms=summary["ranked_arms"], next_action="Review screen results and test restart knobs.")


def main() -> None:
    """중단된 단계는 같은 명령으로 이어가며 완료된 요청을 덮어쓰지 않습니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--phase", choices=("api-screen",), default="api-screen")
    parser.add_argument("--rounds", type=int, default=3)
    arguments = parser.parse_args()
    if arguments.rounds < 1:
        parser.error("--rounds must be positive")
    initialize_optimization_run(arguments.output_directory)
    screen_api(arguments.output_directory, arguments.rounds)


if __name__ == "__main__":
    main()
