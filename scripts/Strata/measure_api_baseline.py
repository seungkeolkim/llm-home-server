"""실행 중인 Strata API의 Context·생성·회귀 검사를 재현 가능한 결과로 보존합니다."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import io
import json
from pathlib import Path
import random
import re
import statistics
import subprocess
import threading
import time

from PIL import Image
import psutil
import requests


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
DEFAULT_CONFIGURATION = WORKSPACE_DIRECTORY / "config/Strata/strata.local.json"


def write_json(output_path: Path, value: object) -> None:
    """결과를 UTF-8 JSON으로 저장합니다."""
    output_path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def command_output(arguments: list[str]) -> str:
    """환경 정보 조회 실패는 측정 결과에 오류 문자열로 남깁니다."""
    try:
        return subprocess.check_output(arguments, text=True, encoding="utf-8", stderr=subprocess.STDOUT, timeout=15).strip()
    except (OSError, subprocess.SubprocessError) as error:
        return str(error)


def gpu_measurement() -> dict:
    """전체 GPU의 사용량을 조회하며 Strata 단독 사용량으로 해석하지 않습니다."""
    query = "memory.used,memory.free,utilization.gpu"
    raw = command_output(["nvidia-smi", "--query-gpu=" + query, "--format=csv,noheader,nounits"])
    try:
        used, free, utilization = [float(value.strip()) for value in raw.splitlines()[0].split(",")]
        return {"gpu_used_mib": used, "gpu_free_mib": free, "gpu_utilization_percent": utilization}
    except (ValueError, IndexError):
        return {"gpu_query_error": raw}


class ResourceSampler:
    """API 요청 중 시스템 RAM·GPU와 Strata 프로세스의 Working Set을 관측합니다."""

    def __init__(self) -> None:
        """독립적인 sampling thread와 중지 신호를 준비합니다."""
        self.samples: list[dict] = []
        self.stop_event = threading.Event()
        self.worker = threading.Thread(target=self.collect, daemon=True)

    def collect(self) -> None:
        """2초 간격으로 리소스를 기록하며 종료된 프로세스는 건너뜁니다."""
        while not self.stop_event.is_set():
            memory = psutil.virtual_memory()
            working_set = 0
            for process in psutil.process_iter(["name", "memory_info"]):
                try:
                    if process.info["name"] in ("strata.exe", "strata-runtime-python.exe", "strata-vision.exe"):
                        working_set += process.info["memory_info"].rss
                except (psutil.Error, TypeError):
                    continue
            sample = {"at": datetime.now().astimezone().isoformat(), "ram_available_bytes": memory.available,
                      "ram_used_bytes": memory.used, "strata_working_set_sum_bytes": working_set,
                      **gpu_measurement()}
            self.samples.append(sample)
            self.stop_event.wait(2)

    def start(self) -> None:
        """요청 직전에 관측을 시작합니다."""
        self.worker.start()

    def finish(self) -> dict:
        """관측을 종료하고 peak와 최소 여유량을 계산합니다."""
        self.stop_event.set()
        self.worker.join(timeout=10)
        if not self.samples:
            return {"samples": []}
        gpu_samples = [sample for sample in self.samples if "gpu_used_mib" in sample]
        summary = {
            "ram_min_available_gib": min(sample["ram_available_bytes"] for sample in self.samples) / 2**30,
            "ram_peak_used_gib": max(sample["ram_used_bytes"] for sample in self.samples) / 2**30,
            "strata_peak_working_set_sum_gib": max(sample["strata_working_set_sum_bytes"] for sample in self.samples) / 2**30,
        }
        if gpu_samples:
            summary["gpu_peak_used_mib"] = max(sample["gpu_used_mib"] for sample in gpu_samples)
            summary["gpu_min_free_mib"] = min(sample["gpu_free_mib"] for sample in gpu_samples)
        return {"summary": summary, "samples": self.samples}


class BaselineMeasurement:
    """Synthetic 요청·원본 응답·API timing과 검증 결과를 하나의 run으로 관리합니다."""

    def __init__(self, configuration_path: Path, output_directory: Path) -> None:
        """API key는 메모리에서만 사용하고 저장할 metadata에서는 제거합니다."""
        self.configuration = json.loads(configuration_path.read_text(encoding="utf-8-sig"))
        self.output_directory = output_directory
        self.output_directory.mkdir(parents=True, exist_ok=True)
        self.session = requests.Session()
        self.session.headers["Authorization"] = "Bearer " + self.configuration["api_key"]
        self.base_url = "http://127.0.0.1:" + str(self.configuration["port"])
        self.results: list[dict] = []

    def get_json(self, route: str) -> dict:
        """인증된 읽기 API의 응답을 반환합니다."""
        response = self.session.get(self.base_url + route, timeout=15)
        response.raise_for_status()
        return response.json()

    def record_environment(self) -> None:
        """실제 설정·source commit·하드웨어·기동 API 상태를 기록합니다."""
        configuration = {key: value for key, value in self.configuration.items() if key != "api_key"}
        metadata = {
            "started_at": datetime.now().astimezone().isoformat(),
            "configuration": configuration,
            "source_commit": command_output(["git", "-C", str(WORKSPACE_DIRECTORY / "external_repo/Strata"), "rev-parse", "HEAD"]),
            "outer_commit": command_output(["git", "-C", str(WORKSPACE_DIRECTORY), "rev-parse", "HEAD"]),
            "gpu": command_output(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"]),
            "ram_total_gib": psutil.virtual_memory().total / 2**30,
            "cpu_logical_count": psutil.cpu_count(), "cpu_physical_count": psutil.cpu_count(logical=False),
            "harness_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "health": self.get_json("/health"),
            "method": "Sequential API requests; deterministic synthetic prompts; 2-second whole-system resource samples; no cache flush or OS page-cache flush.",
        }
        write_json(self.output_directory / "environment.json", metadata)

    def request_payload(self, messages: list[dict], maximum_tokens: int = 256) -> dict:
        """비교용 Sampling을 명시하고 일반 속도 측정에서는 thinking을 끕니다."""
        return {"model": self.configuration["model_name"], "messages": messages, "max_tokens": maximum_tokens,
                "stream": True, "stream_options": {"include_usage": True}, "reasoning_effort": "none",
                "temperature": 0, "top_p": 0.95, "top_k": 20, "min_p": 0,
                "frequency_penalty": 0, "presence_penalty": 0, "repeat_penalty": 1.0, "seed": 20261103}

    def count_prompt(self, content: str) -> int:
        """생성을 실행하지 않는 API로 thinking off Prompt 길이를 확인합니다."""
        request = {"model": self.configuration["model_name"], "messages": [{"role": "user", "content": content}],
                   "thinking": {"type": "disabled"}}
        response = self.session.post(self.base_url + "/v1/messages/count_tokens", json=request, timeout=120)
        response.raise_for_status()
        return response.json()["input_tokens"]

    def measure(self, identifier: str, payload: dict, expected_fragments: list[str] | None = None,
                expected_http_status: int = 200) -> dict:
        """SSE 응답의 첫 token·첫 본문·전체 시간과 Engine timing을 별도로 보존합니다."""
        if psutil.virtual_memory().available < 3 * 2**30:
            raise RuntimeError("Available RAM is below the 3 GiB baseline guard")
        write_json(self.output_directory / (identifier + ".request.json"), payload)
        print(json.dumps({"event": "start", "case": identifier, "at": datetime.now().astimezone().isoformat()}), flush=True)
        sampler = ResourceSampler()
        sampler.start()
        started_at = time.perf_counter()
        first_token_seconds = None
        first_content_seconds = None
        fragments: list[str] = []
        reasoning_fragments: list[str] = []
        chunks: list[dict] = []
        done_received = False
        status = None
        error = None
        usage: dict = {}
        timings: dict = {}
        finish_reason = None
        try:
            with self.session.post(self.base_url + "/v1/chat/completions", json=payload, stream=True,
                                   timeout=(10, 1800)) as response:
                status = response.status_code
                if status != 200:
                    error = response.text
                elif not payload.get("stream"):
                    chunk = response.json()
                    chunks.append(chunk)
                    usage = chunk.get("usage") or {}
                    timings = chunk.get("timings") or {}
                    error = chunk.get("error")
                    for choice in chunk.get("choices", []):
                        message = choice.get("message") or {}
                        fragments.append(message.get("content") or "")
                        if message.get("reasoning_content"):
                            reasoning_fragments.append(message["reasoning_content"])
                        finish_reason = choice.get("finish_reason") or finish_reason
                else:
                    for line in response.iter_lines(chunk_size=1):
                        if not line.startswith(b"data: "):
                            continue
                        data = line[6:]
                        if data == b"[DONE]":
                            done_received = True
                            if identifier == "done-disconnect":
                                break
                            continue
                        chunk = json.loads(data)
                        chunks.append(chunk)
                        if chunk.get("error"):
                            error = chunk["error"]
                        usage = chunk.get("usage") or usage
                        timings = chunk.get("timings") or timings
                        for choice in chunk.get("choices", []):
                            delta = choice.get("delta") or {}
                            content = delta.get("content") or ""
                            reasoning = delta.get("reasoning_content") or ""
                            if (content or reasoning or delta.get("tool_calls")) and first_token_seconds is None:
                                first_token_seconds = time.perf_counter() - started_at
                            if content:
                                if first_content_seconds is None:
                                    first_content_seconds = time.perf_counter() - started_at
                                fragments.append(content)
                            if reasoning:
                                reasoning_fragments.append(reasoning)
                            finish_reason = choice.get("finish_reason") or finish_reason
        except (requests.RequestException, ValueError) as exception:
            error = str(exception)
        elapsed_seconds = time.perf_counter() - started_at
        resources = sampler.finish()
        content = "".join(fragments)
        tool_deltas = []
        for chunk in chunks:
            for choice in chunk.get("choices", []):
                tool_deltas.extend((choice.get("delta") or choice.get("message") or {}).get("tool_calls") or [])
        expected_present = all(fragment in content for fragment in expected_fragments or [])
        passed = status == expected_http_status
        if expected_http_status == 200:
            completed = done_received if payload.get("stream") else bool(chunks)
            passed = passed and not error and completed and expected_present and bool(content or reasoning_fragments or tool_deltas)
        if identifier == "tool-call":
            tool_names = "".join(delta.get("function", {}).get("name", "") for delta in tool_deltas)
            tool_arguments = "".join(delta.get("function", {}).get("arguments", "") for delta in tool_deltas)
            passed = passed and "lookup_code" in tool_names and "BASELINE-262K" in tool_arguments
        if identifier in ("tool-literal-without-tools", "tool-literal-with-tools"):
            passed = passed and not tool_deltas
        if identifier == "cpu-vision-red":
            passed = passed and "red" in content.lower()
        result = {"case": identifier, "http_status": status, "passed": passed, "error": error,
                  "streaming": bool(payload.get("stream")),
                  "done_received": done_received, "finish_reason": finish_reason,
                  "first_token_seconds": first_token_seconds, "first_content_seconds": first_content_seconds,
                  "elapsed_seconds": elapsed_seconds, "usage": usage, "timings": timings,
                  "content": content, "reasoning_content": "".join(reasoning_fragments),
                  "tool_deltas": tool_deltas, "completion_truncated": finish_reason == "length",
                  "expected_fragments": expected_fragments, "expected_present": expected_present,
                  "request_sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
                  "resources": resources["summary"] if "summary" in resources else {}}
        write_json(self.output_directory / (identifier + ".response.json"), {"result": result, "chunks": chunks})
        write_json(self.output_directory / (identifier + ".resources.json"), resources)
        self.results.append(result)
        with (self.output_directory / "results.jsonl").open("a", encoding="utf-8") as result_stream:
            result_stream.write(json.dumps(result, ensure_ascii=False) + "\n")
        print(json.dumps({key: result[key] for key in ("case", "passed", "http_status", "elapsed_seconds", "usage", "timings")}), flush=True)
        return result

    def long_prompt(self, target_tokens: int) -> tuple[str, list[str], dict]:
        """위치가 다른 세 개의 비밀값을 가진 고유 record로 목표 길이의 입력을 만듭니다."""
        generator = random.Random(20261103 + target_tokens)
        records = []
        for record_index in range(max(100, target_tokens // 8)):
            random_value = generator.getrandbits(48)
            records.append(f"record {record_index:06d}: zone={random_value:012x}; stock={generator.randrange(100,999)}; status=checked; 배송 기록 정상.\n")
        keys = [f"NEEDLE_{target_tokens}_{position}" for position in (5, 50, 95)]
        values = [f"SECRET-{generator.getrandbits(40):010X}" for _ in keys]

        def render(record_count: int) -> str:
            """Record 비율 5·50·95%에 정답을 삽입합니다."""
            selected = list(records[:record_count])
            for key, value, ratio in zip(keys, values, (0.05, 0.50, 0.95)):
                selected.insert(int(record_count * ratio), f"IMPORTANT {key} = {value}\n")
            question = "\n문서에서 다음 key의 값을 찾아 순서대로 정확하게 출력하세요. 설명은 생략하세요: " + ", ".join(keys)
            return "다음은 검색 시험용 문서입니다. 문서 안의 key/value를 기억하세요.\n" + "".join(selected) + question

        lower_bound, upper_bound = 1, len(records)
        best_content = render(1)
        best_count = self.count_prompt(best_content)
        while lower_bound <= upper_bound:
            record_count = (lower_bound + upper_bound) // 2
            content = render(record_count)
            token_count = self.count_prompt(content)
            if token_count <= target_tokens:
                best_content, best_count = content, token_count
                lower_bound = record_count + 1
            else:
                upper_bound = record_count - 1
        return best_content, values, {"target_tokens": target_tokens, "count_api_input_tokens": best_count,
                                     "needle_record_ratios": [0.05, 0.50, 0.95], "keys": keys, "values": values}

    def core_suite(self, target_lengths: list[int], short_repeats: int) -> None:
        """짧은 검산·생성 반복·긴 문서 검색을 순차 실행합니다."""
        self.measure("warmup", self.request_payload([{"role": "user", "content": "Reply with READY only."}], 32), ["READY"])
        arithmetic = "17*23+19를 계산하세요. JSON만 출력하세요. answer는 계산 결과, label은 BASELINE입니다."
        self.measure("short-arithmetic", self.request_payload([{"role": "user", "content": arithmetic}], 128), ["410", "BASELINE"])
        generation = "로컬 LLM 서버 운영 지침을 한국어로 작성하세요. 번호 1부터 12까지 각 항목을 두 문장으로 쓰세요. RAM, VRAM, Context, API, 로그, 백업을 포함하고 마지막 항목까지 완성하세요."
        for repetition in range(short_repeats):
            self.measure(f"short-generation-{repetition + 1:02d}", self.request_payload([{"role": "user", "content": generation}], 512))
        for target_tokens in target_lengths:
            content, expected, details = self.long_prompt(target_tokens)
            identifier = f"retrieval-{target_tokens}"
            write_json(self.output_directory / (identifier + ".fixture.json"), details)
            result = self.measure(identifier, self.request_payload([{"role": "user", "content": content}], 256), expected)
        if target_lengths and result["passed"]:
            records = re.findall(r"record (\d+): zone=([0-9a-f]+);", content)
            selected_record, expected_zone = records[len(records) // 2]
            followup_messages = [{"role": "user", "content": content},
                                 {"role": "assistant", "content": result["content"]},
                                 {"role": "user", "content": f"원래 문서에서 record {selected_record}의 zone 값을 찾아 정확히 출력하세요."}]
            self.measure("long-followup", self.request_payload(followup_messages, 128), [expected_zone])
            unrelated_content = ("Read the record below and reply with the value only.\n"
                                 + "This is an unrelated conversation.\n" * 200 + "value=UNRELATED-52648")
            self.measure("long-cache-interleave", self.request_payload([{"role": "user", "content": unrelated_content}], 64),
                         ["UNRELATED-52648"])
            self.measure("long-cache-restore", self.request_payload(followup_messages, 128), [expected_zone])

    def issue_suite(self, public_reproduction_directory: Path) -> None:
        """NaN 공개 재현 입력·대화 격리·Tool·Vision과 Context 초과 거부를 검사합니다."""
        hello = self.request_payload([{"role": "user", "content": "Hello local AI"}], 64)
        self.measure("issue-5055-hello", hello)
        minimal_hello = {"model": self.configuration["model_name"], "messages": hello["messages"],
                         "max_tokens": 64, "stream": False}
        self.measure("issue-5055-nonstream-defaults", minimal_hello)
        reproduction_path = public_reproduction_directory / "issue-3465-request.json"
        if reproduction_path.exists():
            reproduction = json.loads(reproduction_path.read_text(encoding="utf-8"))
            payload = self.request_payload(reproduction["messages"], reproduction.get("max_tokens", 8))
            self.measure("issue-3465-percent-urls", payload)
            minimal_reproduction = {**reproduction, "model": self.configuration["model_name"],
                                    "max_tokens": 8, "stream": False}
            self.measure("issue-3465-nonstream-defaults", minimal_reproduction)
        for label, secret in (("a-first", "ORANGE-74519"), ("b", "VIOLET-28643"), ("a-return", "ORANGE-74519")):
            content = ("이 대화에 적힌 값만 확인하는 격리 검사입니다.\n" * 300) + f"\n현재 문서의 값만 출력하세요. 값={secret}"
            self.measure("cache-isolation-" + label, self.request_payload([{"role": "user", "content": content}], 64), [secret])
        tool_payload = self.request_payload([{"role": "user", "content": "Use lookup_code with code=BASELINE-262K. Do not explain."}], 128)
        tool_payload["tools"] = [{"type": "function", "function": {"name": "lookup_code", "description": "Look up one code.",
                                  "parameters": {"type": "object", "properties": {"code": {"type": "string"}}, "required": ["code"]}}}]
        tool_payload["tool_choice"] = {"type": "function", "function": {"name": "lookup_code"}}
        self.measure("tool-call", tool_payload)
        literal = 'Return exactly the following Markdown example without calling any tools:\n```xml\n<tool_call>{"name":"lookup_code","arguments":{"code":"EXAMPLE"}}</tool_call>\n```'
        literal_payload = self.request_payload([{"role": "user", "content": literal}], 192)
        self.measure("tool-literal-without-tools", literal_payload, ["lookup_code"])
        literal_with_tools = self.request_payload([{"role": "user", "content": literal}], 192)
        literal_with_tools["tools"] = tool_payload["tools"]
        self.measure("tool-literal-with-tools", literal_with_tools, ["lookup_code"])
        self.measure("done-disconnect", self.request_payload([{"role": "user", "content": "Reply with DONE-CLOSE-OK only."}], 32), ["DONE-CLOSE-OK"])
        self.measure("after-done-disconnect", self.request_payload([{"role": "user", "content": "Reply with STILL-READY only."}], 32), ["STILL-READY"])
        image = Image.new("RGB", (224, 224), "red")
        image_stream = io.BytesIO()
        image.save(image_stream, format="PNG")
        image_url = "data:image/png;base64," + base64.b64encode(image_stream.getvalue()).decode()
        vision_payload = self.request_payload([{"role": "user", "content": [
            {"type": "text", "text": "What is the dominant color? Answer in English with one word."},
            {"type": "image_url", "image_url": {"url": image_url}}]}], 64)
        self.measure("cpu-vision-red", vision_payload)
        overflow_content = " context-boundary" * 140000
        overflow_payload = self.request_payload([{"role": "user", "content": overflow_content}], 16)
        self.measure("context-overflow-rejected", overflow_payload, expected_http_status=400)
        wrong_model = self.request_payload([{"role": "user", "content": "hello"}], 16)
        wrong_model["model"] = "not-the-running-model"
        self.measure("wrong-model-rejected", wrong_model, expected_http_status=400)
        reasoning_payload = self.request_payload([{"role": "user", "content": "검산 후 답하세요. 23*17+19의 값은?"}], 512)
        reasoning_payload.update(reasoning_effort="medium", reasoning_budget_tokens=256)
        self.measure("reasoning-medium", reasoning_payload, ["410"])

    def finish(self) -> None:
        """개별 측정의 결과와 반복 생성 중앙값을 요약합니다."""
        generation_results = [result for result in self.results if result["case"].startswith("short-generation-")]
        rates = [result["timings"].get("predicted_per_second") for result in generation_results]
        rates = [rate for rate in rates if rate is not None]
        try:
            health_after = self.get_json("/health")
        except requests.RequestException as error:
            health_after = {"error": str(error)}
        summary = {"finished_at": datetime.now().astimezone().isoformat(), "results": self.results,
                   "short_generation_median_tokens_per_second": statistics.median(rates) if rates else None,
                   "passed": sum(result["passed"] for result in self.results), "total": len(self.results),
                   "health_after": health_after}
        write_json(self.output_directory / "summary.json", summary)


def main() -> None:
    """측정 suite와 길이를 선택하며 실제 서비스 lifecycle은 변경하지 않습니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--configuration", type=Path, default=DEFAULT_CONFIGURATION)
    parser.add_argument("--output-directory", type=Path, required=True)
    parser.add_argument("--suite", choices=("core", "issues", "all"), default="all")
    parser.add_argument("--target-lengths", nargs="+", type=int, default=[8192, 32768, 131072, 260000])
    parser.add_argument("--short-repeats", type=int, default=3)
    parser.add_argument("--public-reproduction-directory", type=Path)
    arguments = parser.parse_args()
    measurement = BaselineMeasurement(arguments.configuration, arguments.output_directory)
    if (arguments.output_directory / "results.jsonl").exists():
        parser.error("Use a new output directory; existing results are never overwritten")
    measurement.record_environment()
    try:
        if arguments.suite in ("core", "all"):
            measurement.core_suite(arguments.target_lengths, arguments.short_repeats)
        if arguments.suite in ("issues", "all"):
            measurement.issue_suite(arguments.public_reproduction_directory or arguments.output_directory)
    finally:
        measurement.finish()
    if any(not result["passed"] for result in measurement.results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
