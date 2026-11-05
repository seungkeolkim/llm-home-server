"""Pinned Infernix 모델·PLE·drafter를 이어받고 파일 hash와 진행 상태를 기록합니다."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.client
import json
import msvcrt
import os
from pathlib import Path
import shutil
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


BLOCK_BYTES = 1024 * 1024
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
DOWNLOAD_ROOT = WORKSPACE_ROOT / "data/Infernix"
RUNTIME_DIRECTORY = WORKSPACE_ROOT / "runtime/Infernix/downloads/orcarouter-nvfp4"


def save_status(progress: dict, state: str, detail: str = "") -> None:
    """Windows의 일시적인 파일 잠금을 재시도하며 기존 정상 status를 보존합니다."""
    progress["state"] = state
    progress["detail"] = detail
    progress["updated_at"] = datetime.now(timezone.utc).isoformat()
    received_bytes = progress["completed_bytes"] + progress["current_received_bytes"]
    progress["received_bytes"] = received_bytes
    progress["progress_percent"] = round(received_bytes / progress["expected_bytes"] * 100, 3)
    temporary_path = RUNTIME_DIRECTORY / f"status.{os.getpid()}.tmp"
    temporary_path.write_text(json.dumps(progress, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for attempt_number in range(20):
        try:
            temporary_path.replace(RUNTIME_DIRECTORY / "status.json")
            return
        except PermissionError:
            if attempt_number == 19:
                raise
            time.sleep(0.2)


def hash_existing(file_path: Path, expected_bytes: int, progress: dict) -> tuple:
    """기존 파일을 작은 block으로 읽어 SHA-256과 Git blob SHA-1 상태를 구성합니다."""
    sha256_digest = hashlib.sha256()
    git_blob_digest = hashlib.sha1(f"blob {expected_bytes}\0".encode("ascii"))
    last_status_time = time.monotonic()
    with file_path.open("rb") as existing_stream:
        while block := existing_stream.read(BLOCK_BYTES):
            sha256_digest.update(block)
            git_blob_digest.update(block)
            if time.monotonic() - last_status_time >= 5:
                save_status(progress, "hashing_existing")
                last_status_time = time.monotonic()
    return sha256_digest, git_blob_digest


def verify_digests(entry: dict, sha256_digest: object, git_blob_digest: object) -> None:
    """LFS는 SHA-256, 일반 metadata 파일은 pinned Git blob SHA-1과 비교합니다."""
    expected_sha256 = entry.get("sha256")
    if expected_sha256:
        if sha256_digest.hexdigest() != expected_sha256:
            raise ValueError(f"SHA-256 불일치: {entry['filename']}; 파일은 보존합니다.")
    elif git_blob_digest.hexdigest() != entry["git_blob_sha1"]:
        raise ValueError(f"Git blob SHA-1 불일치: {entry['filename']}; 파일은 보존합니다.")


def download_entry(entry: dict, progress: dict) -> dict:
    """부분 파일을 유지하며 Range로 이어받고 검증한 파일만 최종 이름으로 변경합니다."""
    destination_path = DOWNLOAD_ROOT / entry["destination"]
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path = destination_path.with_name(destination_path.name + ".part")
    expected_bytes = entry["expected_bytes"]
    progress["current_file"] = entry["filename"]
    progress["current_destination"] = str(destination_path)
    progress["current_expected_bytes"] = expected_bytes
    progress["current_received_bytes"] = 0
    if destination_path.exists():
        if destination_path.stat().st_size != expected_bytes:
            raise ValueError(f"기존 최종 파일 크기 불일치: {destination_path}")
        save_status(progress, "verifying_existing")
        sha256_digest, git_blob_digest = hash_existing(destination_path, expected_bytes, progress)
        verify_digests(entry, sha256_digest, git_blob_digest)
    else:
        received_bytes = partial_path.stat().st_size if partial_path.exists() else 0
        if received_bytes > expected_bytes:
            raise ValueError(f"부분 파일이 공식 크기보다 큽니다: {partial_path}")
        progress["current_received_bytes"] = received_bytes
        save_status(progress, "preparing")
        if received_bytes:
            sha256_digest, git_blob_digest = hash_existing(partial_path, expected_bytes, progress)
        else:
            sha256_digest = hashlib.sha256()
            git_blob_digest = hashlib.sha1(f"blob {expected_bytes}\0".encode("ascii"))
        for attempt_number in range(1, 31):
            if received_bytes == expected_bytes:
                break
            encoded_repository = quote(entry["repository"], safe="/")
            encoded_filename = quote(entry["filename"], safe="/")
            download_url = (
                f"https://huggingface.co/{encoded_repository}/resolve/{entry['revision']}/{encoded_filename}"
                f"?download=true&resume_offset={received_bytes}&request_time={time.time_ns()}"
            )
            request_headers = {"Accept-Encoding": "identity"}
            if received_bytes:
                request_headers["Range"] = f"bytes={received_bytes}-"
            save_status(progress, "connecting", f"attempt {attempt_number}")
            try:
                request = Request(download_url, headers=request_headers)
                with urlopen(request, timeout=90) as response:
                    expected_status = 206 if received_bytes else 200
                    if response.status != expected_status:
                        raise ValueError(f"예상하지 않은 HTTP status: {response.status}")
                    if received_bytes and not response.headers.get("Content-Range", "").startswith(f"bytes {received_bytes}-"):
                        raise ValueError("이어받기 응답의 시작 위치가 다릅니다.")
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) != expected_bytes - received_bytes:
                        raise ValueError("서버의 파일 크기가 pinned metadata와 다릅니다.")
                    last_status_time = time.monotonic()
                    measured_bytes = received_bytes
                    with partial_path.open("ab") as destination_stream:
                        while True:
                            block = response.read(BLOCK_BYTES)
                            if not block:
                                break
                            if received_bytes + len(block) > expected_bytes:
                                raise ValueError("다운로드 크기가 공식 파일 크기를 넘습니다.")
                            destination_stream.write(block)
                            sha256_digest.update(block)
                            git_blob_digest.update(block)
                            received_bytes += len(block)
                            progress["current_received_bytes"] = received_bytes
                            elapsed_seconds = time.monotonic() - last_status_time
                            if elapsed_seconds >= 5:
                                destination_stream.flush()
                                progress["speed_mib_per_second"] = round((received_bytes - measured_bytes) / elapsed_seconds / BLOCK_BYTES, 2)
                                save_status(progress, "downloading")
                                measured_bytes = received_bytes
                                last_status_time = time.monotonic()
                if received_bytes != expected_bytes:
                    raise ConnectionError("전송 완료 전에 연결이 종료됐습니다.")
                break
            except (URLError, TimeoutError, ConnectionError, http.client.IncompleteRead) as error:
                if isinstance(error, HTTPError) and error.code not in (408, 429, 500, 502, 503, 504):
                    raise RuntimeError(f"다운로드 HTTP {error.code}: {entry['filename']}") from None
                if attempt_number == 30:
                    raise RuntimeError(f"재시도 횟수 초과: {entry['filename']}") from None
                # Signed CDN URL을 로그에 남기지 않고 다음 연결에서 새 주소를 받습니다.
                save_status(progress, "retrying", f"{type(error).__name__}; attempt {attempt_number}")
                print(f"retry {attempt_number}: {entry['filename']} at {received_bytes} bytes", flush=True)
                time.sleep(min(attempt_number * 5, 30))
        save_status(progress, "verifying")
        verify_digests(entry, sha256_digest, git_blob_digest)
        partial_path.rename(destination_path)
    print(f"verified: {entry['filename']} ({expected_bytes} bytes)", flush=True)
    return {"path": str(destination_path), "bytes": expected_bytes, "sha256": sha256_digest.hexdigest()}


def main() -> None:
    """Manifest를 검증하고 중복 worker를 차단한 뒤 다운로드만 수행합니다."""
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--manifest", type=Path, required=True)
    arguments = argument_parser.parse_args()
    manifest = json.loads(arguments.manifest.read_text(encoding="utf-8-sig"))
    entries = manifest["files"]
    for entry in entries:
        destination_path = (DOWNLOAD_ROOT / entry["destination"]).resolve()
        if not destination_path.is_relative_to(DOWNLOAD_ROOT.resolve()):
            raise ValueError("다운로드 경로가 data/Infernix 밖을 가리킵니다.")
        if not entry.get("sha256") and not entry.get("git_blob_sha1"):
            raise ValueError("파일 검증용 hash가 없습니다.")
    RUNTIME_DIRECTORY.mkdir(parents=True, exist_ok=True)
    DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    with (RUNTIME_DIRECTORY / "download.lock").open("a+b") as lock_stream:
        if lock_stream.seek(0, 2) == 0:
            lock_stream.write(b"0")
            lock_stream.flush()
        lock_stream.seek(0)
        msvcrt.locking(lock_stream.fileno(), msvcrt.LK_NBLCK, 1)
        remaining_bytes = 0
        for entry in entries:
            destination_path = DOWNLOAD_ROOT / entry["destination"]
            partial_path = destination_path.with_name(destination_path.name + ".part")
            existing_bytes = 0
            if destination_path.exists():
                existing_bytes = destination_path.stat().st_size
            elif partial_path.exists():
                existing_bytes = partial_path.stat().st_size
            remaining_bytes += max(0, entry["expected_bytes"] - existing_bytes)
        if shutil.disk_usage(DOWNLOAD_ROOT).free < remaining_bytes + 16 * 1024**3:
            raise ValueError("남은 다운로드와 여유 16 GiB를 저장할 디스크 공간이 부족합니다.")
        progress = {
            "pid": os.getpid(),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "manifest_path": str(arguments.manifest.resolve()),
            "expected_bytes": sum(entry["expected_bytes"] for entry in entries),
            "completed_bytes": 0,
            "current_received_bytes": 0,
            "verified_files": [],
        }
        try:
            save_status(progress, "starting")
            for entry in entries:
                verified_file = download_entry(entry, progress)
                progress["verified_files"].append(verified_file)
                progress["completed_bytes"] += entry["expected_bytes"]
                progress["current_received_bytes"] = 0
                save_status(progress, "file_completed")
            save_status(progress, "completed", "모든 파일 크기와 pinned hash 검증 완료")
        except Exception as error:
            save_status(progress, "failed", f"{type(error).__name__}: {error}")
            raise


if __name__ == "__main__":
    main()
