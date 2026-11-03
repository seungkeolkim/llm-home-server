"""보존한 API 입력을 SHA-256으로 검증하고 동일한 원문으로 다시 읽습니다."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
INPUT_DIRECTORY = WORKSPACE_DIRECTORY / "tests/Strata/fixtures/2026-11-03-api-inputs"


def read_input_manifest() -> dict:
    """중복 제거된 원본 입력과 canonical fixture의 manifest를 읽습니다."""
    return json.loads((INPUT_DIRECTORY / "manifest.json").read_text(encoding="utf-8"))


def read_archived_input(archive_entry: str) -> dict:
    """Archive와 개별 입력의 hash를 확인한 뒤 원본 JSON을 읽습니다."""
    manifest = read_input_manifest()
    archive_path = INPUT_DIRECTORY / "requests.zip"
    if hashlib.sha256(archive_path.read_bytes()).hexdigest() != manifest["archive_sha256"]:
        raise ValueError("The saved input archive SHA-256 does not match its manifest")
    with zipfile.ZipFile(archive_path) as archive:
        content = archive.read(archive_entry)
    if hashlib.sha256(content).hexdigest() != Path(archive_entry).stem:
        raise ValueError("The saved request SHA-256 does not match its entry name")
    return json.loads(content.decode("utf-8-sig"))


def saved_retrieval_input(target_tokens: int) -> tuple[dict, dict] | None:
    """해당 길이를 실제 사용했으면 요청과 정답 fixture를 반환합니다."""
    entries = read_input_manifest()["canonical_inputs"].get(str(target_tokens))
    if entries is None:
        return None
    return read_archived_input(entries["request"]), read_archived_input(entries["fixture"])


def saved_url_reproduction() -> dict:
    """Percent-encoded URL의 공개 issue 재현 입력을 그대로 반환합니다."""
    entry = read_input_manifest()["canonical_inputs"]["issue-3465"]["request"]
    return read_archived_input(entry)


def verify_saved_inputs() -> dict:
    """모든 원본 경로가 복원 가능한지 byte hash와 JSON 형식으로 검증합니다."""
    manifest = read_input_manifest()
    checked_entries = set()
    for entry in manifest["files"]:
        if entry["archive_entry"] not in checked_entries:
            read_archived_input(entry["archive_entry"])
            checked_entries.add(entry["archive_entry"])
    return {"source_files": len(manifest["files"]), "unique_files": len(checked_entries),
            "saved_lengths": [key for key in manifest["canonical_inputs"] if key.isdigit()]}


def main() -> None:
    """서비스에 접속하지 않고 보존 입력 전체의 무결성을 확인합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    print(json.dumps(verify_saved_inputs(), ensure_ascii=False))


if __name__ == "__main__":
    main()
