"""튜닝 전후에 동일한 작은 정답 집합을 thinking medium으로 비교합니다."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from measure_api_baseline import BaselineMeasurement
from optimize_api_profile import atomic_json


QUALITY_CASES = [
    {"name": "arithmetic-order", "prompt": "17*23+19의 값을 계산하세요. 숫자만 출력하세요.", "expected": "410"},
    {"name": "arithmetic-subtract", "prompt": "7*19-28의 값을 계산하세요. 숫자만 출력하세요.", "expected": "105"},
    {"name": "arithmetic-divide", "prompt": "144/12+37의 값을 계산하세요. 숫자만 출력하세요.", "expected": "49"},
    {"name": "arithmetic-modulo", "prompt": "Python 식 17 % 5 + 8 * 4의 값을 계산하세요. 숫자만 출력하세요.", "expected": "34"},
    {"name": "logic-order", "prompt": "A는 B보다 먼저, C는 A보다 먼저, D는 B보다 나중입니다. 앞에서 뒤 순서의 문자만 쉼표로 구분해 출력하세요.", "expected": "C,A,B,D"},
    {"name": "logic-machines", "prompt": "같은 속도의 기계 5대가 제품 5개를 만드는 데 5분 걸립니다. 같은 기계 100대가 제품 100개를 만드는 데 몇 분 걸립니까? 숫자만 출력하세요.", "expected": "5"},
    {"name": "logic-conditional", "prompt": "다음 규칙만 적용하세요. 모든 pine은 tree입니다. 어떤 tree는 red입니다. '모든 pine은 red다'가 반드시 참입니까? 예 또는 아니오 중 하나만 출력하세요.", "expected": "아니오"},
    {"name": "json-sort", "prompt": '값 [7, 2, 9, 2, 5]를 중복 제거 후 오름차순으로 정렬하세요. JSON만 출력하고 key는 values로 하세요.', "expected": {"values": [2, 5, 7, 9]}},
    {"name": "json-filter", "prompt": '재고: A=0, B=4, C=2, D=0. 재고가 양수인 항목의 이름만 입력 순서대로 반환하세요. JSON만 출력하고 key는 available로 하세요.', "expected": {"available": ["B", "C"]}},
    {"name": "json-extract", "prompt": '문서: 서버 이름은 atlas, port는 8488, reserve_mib는 8192, context는 262144입니다. port와 context만 정수로 추출한 JSON object만 출력하세요.', "expected": {"port": 8488, "context": 262144}},
    {"name": "copy-ascii", "prompt": '다음 문자열을 변경하지 말고 그대로 출력하세요. 다른 내용은 쓰지 마세요: KEEP-0O1l-7f29-262144', "expected": "KEEP-0O1l-7f29-262144"},
    {"name": "korean-extract", "prompt": '기록: 어제의 담당자는 민수, 오늘의 담당자는 지연, 내일의 담당자는 수빈입니다. 오늘의 담당자 이름만 출력하세요.', "expected": "지연"},
]


def parse_json_content(content: str) -> object:
    """JSON 응답의 바깥쪽 Markdown fence만 허용하고 전체 값을 파싱합니다."""
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return json.loads(text)


def measure_quality(measurement: BaselineMeasurement) -> list[dict]:
    """정답 부분 문자열이 아니라 전체 문자열 또는 JSON 값으로 판단해 즉시 저장합니다."""
    checks = []
    for case in QUALITY_CASES:
        payload = measurement.request_payload([{"role": "user", "content": case["prompt"]}], 1024)
        payload.update(reasoning_effort="medium", reasoning_budget_tokens=512, strata_checkpoint=False)
        result = measurement.measure("quality-suite-" + case["name"], payload)
        expected = case["expected"]
        actual = result["content"].strip()
        parse_error = None
        if isinstance(expected, dict):
            try:
                actual = parse_json_content(actual)
            except ValueError as error:
                parse_error = str(error)
        elif case["name"] == "logic-order":
            actual = actual.replace(" ", "")
        passed = result["passed"] and not result["completion_truncated"] and actual == expected
        checks.append({"case": result["case"], "passed": passed, "expected": expected, "actual": actual,
                       "parse_error": parse_error, "transport_passed": result["passed"],
                       "truncated": result["completion_truncated"], "elapsed_seconds": result["elapsed_seconds"]})
        atomic_json(measurement.output_directory / "quality-validation.json", checks)
        print(json.dumps({"quality_case": case["name"], "exact_passed": passed}), flush=True)
    style_prompts = {
        "style-korean-story": "한국어 소설의 한 장면을 길게 쓰세요. 늦가을 비가 내리는 공연장에서 두 성인 배우가 마지막 리허설을 합니다. 무대의 조명과 소리, 작은 동작과 인물의 감정을 구체적으로 묘사하세요. 요약이나 항목 목록 없이 자연스러운 문단으로 장면을 계속 이어가세요.",
        "style-korean-dialogue": "한국어로 긴 대화 장면을 쓰세요. 오래된 서점에서 십 년 만에 만난 두 친구가 함께 준비했던 공연과 지금의 삶을 이야기합니다. 대사 사이에 표정과 동작을 넣고 인물의 말투를 구별하세요. 결말을 서둘러 내지 말고 구체적인 대화를 충분히 이어가세요.",
    }
    for name, prompt in style_prompts.items():
        payload = measurement.request_payload([{"role": "user", "content": prompt}], 512)
        payload["strata_checkpoint"] = False
        measurement.measure(name, payload)
    return checks
