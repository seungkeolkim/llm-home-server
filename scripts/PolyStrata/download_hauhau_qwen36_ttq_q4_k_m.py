"""선택한 Hauhau TTQ Q4_K_M 본체와 MTP sidecar를 이어받아 SHA-256을 검증합니다."""

from datetime import datetime, timezone
import json
import msvcrt
import os
from pathlib import Path

import download_qwen36_ud_q4_k_m as resumable_downloader


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
RUNTIME_DIRECTORY = WORKSPACE_DIRECTORY / "runtime/PolyStrata/downloads/hauhau-ttq-q4km-mtp"
MODEL_REPOSITORY = "TokenTinkerer/Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-TTQ-GGUF"
MODEL_REVISION = "b5f4c840a5cea7baa0fa98e80c780d5455af482c"
ARTIFACTS = [
    {
        "identifier": "model",
        "filename": "Qwen3.6-35B-A3B-Uncensored-HauhauCS-Aggressive-TTQ-4.90bpw-Q4_K_M.gguf",
        "expected_bytes": 21_219_227_776,
        "expected_sha256": "a761d83251604ed629729097f5036550d62c03c0fda9d7890fe74aa7b198a9fb",
    },
    {
        "identifier": "mtp",
        "filename": "Qwen3.6-35B-A3B-MTP-ONLY-Q4_K_M-shared.gguf",
        "expected_bytes": 557_655_776,
        "expected_sha256": "70c377fa0d30a6caca4c06e17ac32fa1692b7f840a527ef0fb825c2742443835",
    },
]


def save_job_status(state, download_directory, active_artifact=None, detail=""):
    """나중에 요청 시 전체 작업과 파일별 진행 기록을 찾을 수 있게 저장합니다."""
    document = {
        "state": state,
        "pid": os.getpid(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "repository": MODEL_REPOSITORY,
        "revision": MODEL_REVISION,
        "download_directory": str(download_directory),
        "expected_bytes": sum(artifact["expected_bytes"] for artifact in ARTIFACTS),
        "active_artifact": active_artifact,
        "artifacts": [
            {**artifact, "status_path": str(RUNTIME_DIRECTORY / artifact["identifier"] / "status.json")}
            for artifact in ARTIFACTS
        ],
        "detail": detail,
    }
    temporary_path = RUNTIME_DIRECTORY / "status.tmp"
    temporary_path.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary_path, RUNTIME_DIRECTORY / "status.json")


def download_artifact(artifact, download_directory):
    """기존 검증된 이어받기 worker에 이번 파일의 pinned 정보를 전달합니다."""
    resumable_downloader.DOWNLOAD_DIRECTORY = download_directory
    resumable_downloader.RUNTIME_DIRECTORY = RUNTIME_DIRECTORY / artifact["identifier"]
    resumable_downloader.MODEL_FILENAME = artifact["filename"]
    resumable_downloader.MODEL_REVISION = MODEL_REVISION
    resumable_downloader.EXPECTED_BYTES = artifact["expected_bytes"]
    resumable_downloader.EXPECTED_SHA256 = artifact["expected_sha256"]
    resumable_downloader.DOWNLOAD_URL = (
        f"https://huggingface.co/{MODEL_REPOSITORY}/resolve/{MODEL_REVISION}/{artifact['filename']}"
    )
    resumable_downloader.MODEL_PATH = download_directory / artifact["filename"]
    resumable_downloader.PARTIAL_PATH = download_directory / (artifact["filename"] + ".part")
    resumable_downloader.STATUS_PATH = resumable_downloader.RUNTIME_DIRECTORY / "status.json"
    resumable_downloader.main()


def main():
    """중복 작업을 차단하고 두 파일을 다운로드하며 Engine이나 model은 기동하지 않습니다."""
    environment_path = WORKSPACE_DIRECTORY / "config/Strata/environment.local.json"
    environment = json.loads(environment_path.read_text(encoding="utf-8-sig"))
    download_directory = Path(environment["data_directory"]) / "models/qwen36-HauhauCS-TTQ-Q4_K_M"
    RUNTIME_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with (RUNTIME_DIRECTORY / "job.lock").open("a+b") as lock_stream:
        if lock_stream.seek(0, 2) == 0:
            lock_stream.write(b"0")
            lock_stream.flush()
        lock_stream.seek(0)
        msvcrt.locking(lock_stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            save_job_status("preparing", download_directory)
            for artifact in ARTIFACTS:
                save_job_status("downloading", download_directory, artifact["identifier"])
                print("Downloading:", artifact["filename"], flush=True)
                download_artifact(artifact, download_directory)
            save_job_status("completed", download_directory, detail="Both files passed size and SHA-256 checks.")
            print("Model and MTP downloads completed; no model was loaded.", flush=True)
        except Exception as error:
            save_job_status("failed", download_directory, detail=str(error))
            raise


if __name__ == "__main__":
    main()
