"""Engine 비교에서 과거 요청과 의도적인 잘못된 model 입력이 보존되는지 검증합니다."""

from pathlib import Path
import sys
import unittest


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY / "scripts/ManagementServer"))
from measure_engine_comparison import archived_cases, payload_for_profile


class EngineComparisonInputTests(unittest.TestCase):
    """실제 API 없이 원본 suite 전체와 cross-engine 치환의 경계를 확인합니다."""

    def test_same_profile_preserves_all_46_historical_requests(self):
        """같은 Strata profile 재생에는 거부 검사까지 모든 원본 필드가 일치합니다."""
        cases = archived_cases(True)
        self.assertEqual(len(cases), 46)
        for baseline, original_payload in cases:
            with self.subTest(case=baseline["case"]):
                self.assertEqual(payload_for_profile(original_payload,
                                 "sc117-qwen3.8-flash-next-abliterated-iq3_xxs"), original_payload)

    def test_cross_engine_preserves_negative_model_request(self):
        """실행 model을 치환해도 HTTP 400 검사 대상의 model을 정상 model로 바꾸지 않습니다."""
        cases = dict((baseline["case"], payload) for baseline, payload in archived_cases(True))
        rejected_payload = cases["wrong-model-rejected"]
        self.assertEqual(payload_for_profile(rejected_payload, "another-engine-model"), rejected_payload)
        original_payload = cases["retrieval-32768"]
        replacement = payload_for_profile(original_payload, "another-engine-model")
        self.assertEqual(replacement["model"], "another-engine-model")
        self.assertEqual({key: value for key, value in replacement.items() if key != "model"},
                         {key: value for key, value in original_payload.items() if key != "model"})
        self.assertNotEqual(original_payload["model"], replacement["model"])


if __name__ == "__main__":
    unittest.main()
