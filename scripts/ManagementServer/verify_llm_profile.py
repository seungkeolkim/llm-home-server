"""명시적으로 선택한 profile을 관리 API로 기동하고 Load·생성 리소스를 기록합니다."""

import argparse
import base64
import json
from pathlib import Path
import subprocess
import struct
import sys
import threading
import time
import uuid
import zlib

import httpx
import psutil


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY))
from management_server.configuration import load_configuration, read_json, resolve_workspace_path
from management_server.llm_profiles import ProfileCatalog


def sample_resources():
    """GPU 전체 사용량과 OS 가용 RAM을 함께 측정합니다."""
    completed = subprocess.run(["nvidia-smi", "--query-gpu=memory.used,memory.free", "--format=csv,noheader,nounits"],
                               capture_output=True, text=True, check=True, timeout=5,
                               creationflags=subprocess.CREATE_NO_WINDOW)
    used_mib, free_mib = map(int, completed.stdout.strip().split(","))
    return {"at": time.time(), "gpu_used_mib": used_mib, "gpu_free_mib": free_mib,
            "system_available_bytes": psutil.virtual_memory().available}


def sample_until_stopped(stop_event, samples):
    """Load와 요청 처리 중 GPU peak를 1초 간격으로 수집합니다."""
    while not stop_event.is_set():
        samples.append(sample_resources())
        stop_event.wait(1)


def process_memory():
    """실행 instance와 child의 working set·private commit을 별도로 기록합니다."""
    instance = read_json(WORKSPACE_DIRECTORY / "runtime/ManagementServer/llm/instance.json")
    process = psutil.Process(instance["pid"])
    records = []
    for owned_process in [process, *process.children(recursive=True)]:
        memory = owned_process.memory_info()
        records.append({"pid": owned_process.pid, "name": owned_process.name(),
                        "working_set_bytes": memory.rss, "private_bytes": getattr(memory, "private", None)})
    return records


def blue_image_fixture():
    """외부 파일이나 image dependency 없이 단색 PNG 검증 입력을 만듭니다."""
    def png_chunk(chunk_type, payload):
        """PNG chunk 길이와 CRC를 기록합니다."""
        return struct.pack(">I", len(payload)) + chunk_type + payload + struct.pack(">I", zlib.crc32(chunk_type + payload))

    pixels = (b"\x00" + b"\x00\x00\xff" * 128) * 128
    image_bytes = b"\x89PNG\r\n\x1a\n" + png_chunk(b"IHDR", struct.pack(">IIBBBBB", 128, 128, 8, 2, 0, 0, 0))
    image_bytes += png_chunk(b"IDAT", zlib.compress(pixels)) + png_chunk(b"IEND", b"")
    return base64.b64encode(image_bytes).decode("ascii")


def main():
    """실제 기동·짧은 생성 검증을 수행하고 secret 없는 증거를 보관합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--settle-seconds", type=int, default=15)
    parser.add_argument("--vision", action="store_true")
    arguments = parser.parse_args()
    configuration = load_configuration()
    catalog = ProfileCatalog(configuration["llm"])
    profile = catalog.get(arguments.profile)
    native = catalog.native_configuration(profile)
    evidence = {"profile_id": arguments.profile, "baseline": sample_resources(), "samples": []}
    destination = WORKSPACE_DIRECTORY / f"runtime/ManagementServer/verification-{arguments.profile}.json"
    stop_event = threading.Event()
    sampler = threading.Thread(target=sample_until_stopped, args=(stop_event, evidence["samples"]), daemon=True)
    sampler.start()
    try:
        with httpx.Client(base_url="http://127.0.0.1:8788", trust_env=False, timeout=15) as client:
            login = client.post("/api/access", json={"access_string": configuration["access_string"]})
            login.raise_for_status()
            response = client.post("/api/services/llm/start", headers={"x-csrf-token": login.json()["csrf"]},
                                   json={"identifier": uuid.uuid4().hex, "profile_id": arguments.profile,
                                         "configuration_revision": catalog.revision(profile)})
            response.raise_for_status()
            identifier = response.json()["identifier"]
            print("Management start accepted:", identifier, flush=True)
            deadline = time.monotonic() + 650
            while time.monotonic() < deadline:
                operation = next(operation for operation in client.get("/api/operations").json()
                                 if operation["identifier"] == identifier)
                if operation["status"] not in {"queued", "running"}:
                    evidence["operation"] = operation
                    if operation["status"] != "succeeded":
                        raise RuntimeError("Management start failed: " + operation["message"])
                    break
                time.sleep(2)
            else:
                raise TimeoutError("Management start timeout")
        time.sleep(arguments.settle_seconds)
        evidence["loaded"] = sample_resources()
        evidence["loaded_process_memory"] = process_memory()
        print("Loaded:", evidence["loaded"], flush=True)
        with httpx.Client(trust_env=False, timeout=180,
                          headers={"Authorization": "Bearer " + native["api_key"]}) as client:
            started_at = time.monotonic()
            response = client.post("http://127.0.0.1:8488/v1/chat/completions", json={
                "model": native["model_name"], "messages": [{"role": "user", "content": "Reply with exactly PROFILE_READY."}],
                "max_tokens": 256, "reasoning_effort": "none", "temperature": 0})
            response.raise_for_status()
            evidence["chat"] = response.json()
            evidence["chat_seconds"] = time.monotonic() - started_at
            if "PROFILE_READY" not in json.dumps(evidence["chat"]):
                raise RuntimeError("Verification response marker missing")
            invalid = client.post("http://127.0.0.1:8488/v1/chat/completions", json={
                "model": "inactive-verification-model", "messages": [{"role": "user", "content": "Do not generate."}],
                "max_tokens": 1})
            evidence["inactive_model_http_status"] = invalid.status_code
            if profile["engine"] == "polystrata" and invalid.status_code != 400:
                raise RuntimeError("Inactive model request was not rejected")
            if arguments.vision:
                encoded_image = blue_image_fixture()
                vision_response = client.post("http://127.0.0.1:8488/v1/chat/completions", json={
                    "model": native["model_name"], "max_tokens": 128, "reasoning_effort": "none",
                    "messages": [{"role": "user", "content": [
                        {"type": "text", "text": "What single color fills this image? Answer in one word."},
                        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + encoded_image}}
                    ]}]})
                vision_response.raise_for_status()
                evidence["vision"] = vision_response.json()
                if "blue" not in json.dumps(evidence["vision"]).lower():
                    raise RuntimeError("Vision color verification failed")
            longer_response = client.post("http://127.0.0.1:8488/v1/chat/completions", json={
                "model": native["model_name"], "max_tokens": 128, "reasoning_effort": "none",
                "messages": [{"role": "user", "content": "Summarize the following repeated operational note in three sentences. " +
                              "The local LLM uses CPU Vision, a Q8 KV cache, and one active execution profile. " * 180}]})
            longer_response.raise_for_status()
            evidence["longer_chat"] = longer_response.json()
        evidence["after_chat"] = sample_resources()
        evidence["after_chat_process_memory"] = process_memory()
        print("Chat verified; inactive model HTTP:", invalid.status_code, flush=True)
    finally:
        stop_event.set()
        sampler.join(timeout=6)
        evidence["peak_gpu_used_mib"] = max(sample["gpu_used_mib"] for sample in evidence["samples"])
        destination.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Evidence:", destination, flush=True)


if __name__ == "__main__":
    main()
