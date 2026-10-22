"""공식 pinned Qwen3.6 Q4 GGUF만 이어받고 진행 상태와 SHA-256 검증 결과를 남깁니다."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import msvcrt
import os
from pathlib import Path
import time

import requests


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_DIRECTORY = Path("C:/Strata-data/models/qwen36-UD-Q4_K_M")
RUNTIME_DIRECTORY = WORKSPACE_ROOT / "runtime/PolyStrata/downloads/qwen36-UD-Q4_K_M"
MODEL_FILENAME = "Qwen3.6-35B-A3B-UD-Q4_K_M.gguf"
MODEL_REVISION = "5bc3e238d916f48a861bac2f8a1990a0e9b7e98d"
EXPECTED_BYTES = 22_663_387_424
EXPECTED_SHA256 = "0b21525e972670ed59e1812e170b27c26355381f0656ecc4e25617ece7dac58b"
DOWNLOAD_URL = (
    "https://huggingface.co/unsloth/Qwen3.6-35B-A3B-MTP-GGUF/resolve/"
    f"{MODEL_REVISION}/{MODEL_FILENAME}"
)
MODEL_PATH = DOWNLOAD_DIRECTORY / MODEL_FILENAME
PARTIAL_PATH = DOWNLOAD_DIRECTORY / f"{MODEL_FILENAME}.part"
STATUS_PATH = RUNTIME_DIRECTORY / "status.json"


def save_status(state: str, received_bytes: int, detail: str = "") -> None:
    """별도 조회로 읽을 수 있도록 진행 상태를 atomic replace로 기록합니다."""
    status = {
        "state": state,
        "pid": os.getpid(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "model_path": str(MODEL_PATH),
        "partial_path": str(PARTIAL_PATH),
        "revision": MODEL_REVISION,
        "expected_bytes": EXPECTED_BYTES,
        "received_bytes": received_bytes,
        "progress_percent": round(received_bytes / EXPECTED_BYTES * 100, 3),
        "expected_sha256": EXPECTED_SHA256,
        "detail": detail,
    }
    temporary_path = STATUS_PATH.with_suffix(".tmp")
    temporary_path.write_text(json.dumps(status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary_path.replace(STATUS_PATH)


def hash_file(file_path: Path) -> object:
    """재개할 파일의 기존 부분을 작은 block으로 읽어 SHA-256 상태를 구성합니다."""
    digest = hashlib.sha256()
    with file_path.open("rb") as source_stream:
        while True:
            block = source_stream.read(1024 * 1024)
            if not block:
                break
            digest.update(block)
    return digest


def receive_remaining(digest: object) -> None:
    """부분 파일을 보존하며 단일 HTTP 연결로 이어받고 전송 중 hash를 계산합니다."""
    received_bytes = PARTIAL_PATH.stat().st_size if PARTIAL_PATH.exists() else 0
    last_status_time = 0.0
    for attempt_number in range(1, 31):
        if received_bytes == EXPECTED_BYTES:
            return
        save_status("connecting", received_bytes, f"attempt {attempt_number}")
        try:
            request_headers = {"Accept-Encoding": "identity"}
            if received_bytes:
                request_headers["Range"] = f"bytes={received_bytes}-"
            with requests.get(
                DOWNLOAD_URL,
                params={"download": "true", "resume_offset": received_bytes},
                headers=request_headers,
                stream=True,
                timeout=(20, 90),
            ) as response:
                response.raise_for_status()
                if received_bytes:
                    if response.status_code != 206:
                        raise ValueError("서버가 이어받기를 거부했습니다. 기존 부분 파일은 보존합니다.")
                    expected_range = f"bytes {received_bytes}-"
                    if not response.headers.get("Content-Range", "").startswith(expected_range):
                        raise ValueError("이어받기 응답의 시작 위치가 다릅니다.")
                elif response.status_code != 200:
                    raise ValueError("전체 파일 요청에 대한 응답이 아닙니다.")
                content_length = response.headers.get("Content-Length")
                if content_length and int(content_length) != EXPECTED_BYTES - received_bytes:
                    raise ValueError("서버가 알려준 파일 크기가 공식 pinned 크기와 다릅니다.")
                with PARTIAL_PATH.open("ab") as destination_stream:
                    for block in response.iter_content(chunk_size=1024 * 1024):
                        if not block:
                            continue
                        if received_bytes + len(block) > EXPECTED_BYTES:
                            raise ValueError("다운로드 크기가 공식 파일 크기를 넘습니다.")
                        destination_stream.write(block)
                        digest.update(block)
                        received_bytes += len(block)
                        if time.monotonic() - last_status_time >= 10:
                            destination_stream.flush()
                            save_status("downloading", received_bytes)
                            last_status_time = time.monotonic()
            if received_bytes == EXPECTED_BYTES:
                return
            raise requests.ConnectionError("파일 전송이 끝나기 전에 연결이 종료됐습니다.")
        except requests.RequestException as error:
            if attempt_number == 30:
                raise
            save_status("retrying", received_bytes, str(error))
            time.sleep(30)


def main() -> None:
    """중복 worker를 차단하고 다운로드가 검증된 뒤에만 최종 GGUF 이름으로 변경합니다."""
    RUNTIME_DIRECTORY.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with (RUNTIME_DIRECTORY / "download.lock").open("a+b") as lock_stream:
        if lock_stream.seek(0, 2) == 0:
            lock_stream.write(b"0")
            lock_stream.flush()
        lock_stream.seek(0)
        msvcrt.locking(lock_stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            if MODEL_PATH.exists():
                save_status("verifying", MODEL_PATH.stat().st_size)
                if MODEL_PATH.stat().st_size != EXPECTED_BYTES or hash_file(MODEL_PATH).hexdigest() != EXPECTED_SHA256:
                    raise ValueError("기존 최종 파일의 크기 또는 SHA-256이 다릅니다. 파일은 보존합니다.")
            else:
                received_bytes = PARTIAL_PATH.stat().st_size if PARTIAL_PATH.exists() else 0
                if received_bytes > EXPECTED_BYTES:
                    raise ValueError("부분 파일이 공식 크기보다 큽니다. 파일은 보존합니다.")
                save_status("preparing", received_bytes)
                digest = hash_file(PARTIAL_PATH) if received_bytes else hashlib.sha256()
                receive_remaining(digest)
                save_status("verifying", EXPECTED_BYTES)
                if digest.hexdigest() != EXPECTED_SHA256:
                    raise ValueError("SHA-256 검증에 실패했습니다. 부분 파일은 보존합니다.")
                PARTIAL_PATH.rename(MODEL_PATH)
            save_status("completed", EXPECTED_BYTES, "size and SHA-256 verified")
        except Exception as error:
            received_bytes = PARTIAL_PATH.stat().st_size if PARTIAL_PATH.exists() else 0
            save_status("failed", received_bytes, str(error))
            raise


if __name__ == "__main__":
    main()
