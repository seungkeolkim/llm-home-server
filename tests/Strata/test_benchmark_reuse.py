"""실제 LLM에 접속하지 않고 보존 입력의 동일성과 실험 기록 보호를 검증합니다."""

import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY / "scripts/Strata"))
import benchmark_inputs
from measure_api_baseline import BaselineMeasurement
import optimize_api_profile
from summarize_optimization_results import summarize_trials


class BenchmarkReuseTests(unittest.TestCase):
    """청소 후에도 동일 입력을 사용하고 이전 실험과 설정을 덮어쓰지 않습니다."""

    def test_all_original_inputs_are_recoverable(self):
        """중복 제거 archive에서 원본 경로 614개를 손실 없이 읽을 수 있습니다."""
        summary = benchmark_inputs.verify_saved_inputs()
        self.assertEqual(summary["source_files"], 614)
        self.assertEqual(summary["unique_files"], 116)
        self.assertEqual(summary["saved_lengths"], ["8192", "32768", "131072", "260000"])

    def test_retrieval_requests_match_original_without_token_count_api(self):
        """보존된 네 길이의 요청이 token 재계산 없이 원본과 동일하게 만들어집니다."""
        measurement = BaselineMeasurement.__new__(BaselineMeasurement)
        for target_tokens in (8192, 32768, 131072, 260000):
            request, fixture = benchmark_inputs.saved_retrieval_input(target_tokens)
            measurement.configuration = {"model_name": request["model"]}
            with patch.object(measurement, "count_prompt", side_effect=AssertionError("Network access is forbidden")):
                content, expected_values, actual_fixture = measurement.long_prompt(target_tokens)
            actual_request = measurement.request_payload([{"role": "user", "content": content}], 256)
            self.assertEqual(actual_request, request)
            self.assertEqual(actual_fixture, fixture)
            self.assertEqual(expected_values, fixture["values"])
            for expected_value in expected_values:
                self.assertIn(expected_value, content)

    def test_archive_corruption_is_rejected(self):
        """손상된 원본 archive를 읽어 다른 입력을 조용히 사용하지 않습니다."""
        manifest = benchmark_inputs.read_input_manifest()
        with tempfile.TemporaryDirectory() as directory:
            input_directory = Path(directory)
            (input_directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            (input_directory / "requests.zip").write_bytes(b"corrupted archive")
            with patch.object(benchmark_inputs, "INPUT_DIRECTORY", input_directory):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    benchmark_inputs.saved_retrieval_input(32768)

    def test_optimization_resume_preserves_original_configuration(self):
        """재개 시 현재 설정으로 원본 snapshot이나 진행 상황을 덮어쓰지 않습니다."""
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            configuration_path = workspace / "strata.local.json"
            configuration = {"model_name": "fixture", "api_key": "fixture-key",
                             "args": ["--max-context", "262144", "--vram-reserve-mib", "8192"]}
            configuration_path.write_text(json.dumps(configuration), encoding="utf-8")
            output_directory = workspace / "runtime/Strata/tuning/new-run"
            with patch.object(optimize_api_profile, "WORKSPACE_DIRECTORY", workspace), \
                 patch.object(optimize_api_profile, "CONFIGURATION_PATH", configuration_path):
                optimize_api_profile.initialize_optimization_run(output_directory)
                original = output_directory / "original-configuration/strata.local.json"
                original_hash = hashlib.sha256(original.read_bytes()).hexdigest()
                configuration_path.write_text("{}", encoding="utf-8")
                optimize_api_profile.initialize_optimization_run(output_directory)
                self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), original_hash)

    def test_private_snapshot_stays_inside_ignored_runtime(self):
        """Git에 들어갈 수 있는 폴더로 secret이 포함된 snapshot을 만들지 않습니다."""
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            with patch.object(optimize_api_profile, "WORKSPACE_DIRECTORY", workspace):
                with self.assertRaisesRegex(ValueError, "runtime/Strata"):
                    optimize_api_profile.initialize_optimization_run(workspace / "docs/new-run")

    def test_default_summary_stays_in_its_run(self):
        """새 결과의 기본 집계가 과거의 공개 baseline JSON을 덮어쓰지 않습니다."""
        with tempfile.TemporaryDirectory() as directory:
            output_directory = Path(directory)
            summary = summarize_trials(output_directory)
            self.assertEqual(summary["trials"], [])
            self.assertTrue((output_directory / "engine-screen-summary.json").is_file())


if __name__ == "__main__":
    unittest.main()
