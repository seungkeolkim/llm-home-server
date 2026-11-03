"""완료된 최적화 실험의 공개 가능한 지표만 하나의 checkpoint로 모읍니다."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from optimize_api_profile import DEFAULT_OUTPUT_DIRECTORY, atomic_json, geometric_mean, timestamp


DEFAULT_SUMMARY_PATH = Path(__file__).resolve().parents[2] / "docs/Strata/benchmarks/2026-11-03-optimization-engine-screen.json"


def paired_comparisons(trials: list[dict]) -> list[dict]:
    """같은 round의 앞뒤 기준값으로 후보의 속도와 A/A 변동을 계산합니다."""
    groups = {}
    for trial in trials:
        if trial["status"] != "completed":
            continue
        round_name, arm = trial["trial"].split("-", 1)
        groups.setdefault(round_name, {})[arm] = trial
    comparisons = []
    for round_name, arms in groups.items():
        first = arms.get("baseline") or arms.get("mtp-on")
        last = arms.get("baseline-tail")
        if not first or not last:
            continue
        decode_reference = geometric_mean([first["decode_geometric_mean"], last["decode_geometric_mean"]])
        prefill_reference = geometric_mean([first["prefill_tokens_per_second"], last["prefill_tokens_per_second"]])
        for arm, trial in arms.items():
            if arm in ("baseline", "baseline-tail", "mtp-on"):
                continue
            comparisons.append({
                "round": round_name, "arm": arm, "control_trials": [first["trial"], last["trial"]],
                "baseline_decode_absolute_drift": abs(last["decode_geometric_mean"] / first["decode_geometric_mean"] - 1),
                "baseline_prefill_absolute_drift": abs(last["prefill_tokens_per_second"] / first["prefill_tokens_per_second"] - 1),
                "decode_ratio": trial["decode_geometric_mean"] / decode_reference,
                "prefill_ratio": trial["prefill_tokens_per_second"] / prefill_reference,
            })
    return comparisons


def summarize_trials(output_directory: Path, summary_path: Path = DEFAULT_SUMMARY_PATH) -> dict:
    """API key·환경 원본·전체 응답을 제외하고 완료된 trial의 측정값을 보존합니다."""
    trials = []
    for result_path in sorted((output_directory / "restart-screen").glob("*/summary.json")):
        result = json.loads(result_path.read_text(encoding="utf-8"))
        trial = {key: result.get(key) for key in (
            "trial", "finished_at", "status", "settings", "decode_geometric_mean",
            "prefill_tokens_per_second", "long_prompt_ttft_seconds", "gpu_peak_used_mib",
            "strata_peak_working_set_sum_gib", "ram_min_available_gib",
            "quality_all_passed", "quality_failures", "quality_checks", "retrieval_passed",
        )}
        trial["cases"] = [{key: case.get(key) for key in (
            "case", "passed", "http_status", "elapsed_seconds", "first_token_seconds",
            "usage", "timings", "done_received", "error",
        )} for case in result["results"]]
        trial["facts"] = result.get("facts", {})
        actual_arguments = trial["facts"].get("actual_native_arguments", [])
        log_paths = sorted(result_path.parent.glob("worker-attempt-*/engine-*.log"))
        engine_log = log_paths[-1].read_text(encoding="utf-8", errors="replace") if log_paths else ""
        engine_command = next((line for line in engine_log.splitlines() if "engine started:" in line), "")
        trial["actual_key_arguments"] = {}
        for flag in ("--kv-resident", "--max-context", "--vram-reserve-mib", "--prefill", "--spec", "--pool-workers", "--host-core", "--mtp"):
            if actual_arguments:
                value = actual_arguments[actual_arguments.index(flag) + 1] if flag in actual_arguments else None
            else:
                matched = re.search(re.escape(flag) + r"\s+(\S+)", engine_command)
                value = matched.group(1) if matched else None
            trial["actual_key_arguments"][flag] = value
        trials.append(trial)
    summary = {
        "updated_at": timestamp(), "context_tokens": 262144, "reserve_mib": 8192,
        "model": "sc117-qwen3.8-flash-next-abliterated-iq3_xxs",
        "protocol": "Fresh engine; two 64-token warmups; three 384-token decode prompts; cold 32K retrieval; arithmetic off and medium.",
        "interpretation": "completed means valid API measurement, not full semantic correctness; inspect quality fields. r01 predates separated quality fields.",
        "trials": trials, "paired_comparisons": paired_comparisons(trials),
    }
    atomic_json(summary_path, summary)
    return summary


def main() -> None:
    """저장 경로를 선택해 완료된 trial의 집계를 갱신합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--summary-path", type=Path, default=DEFAULT_SUMMARY_PATH)
    arguments = parser.parse_args()
    summary = summarize_trials(arguments.output_directory, arguments.summary_path)
    print(json.dumps({"trials": len(summary["trials"]), "summary_path": str(arguments.summary_path)}))


if __name__ == "__main__":
    main()
