"""공식 Windows ZIP의 GitHub digest를 검증하고 격리된 Desktop 경로에 풉니다."""

import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
RELEASE_VERSION = "0.15.4"
ASSET_NAME = f"Paseo-Setup-{RELEASE_VERSION}-x64.zip"


def prepare_desktop_release():
    """공식 Release asset을 검증하며 기존 설치가 있으면 그대로 재사용합니다."""
    metadata_url = f"https://api.github.com/repos/getpaseo/paseo/releases/tags/v{RELEASE_VERSION}"
    with urllib.request.urlopen(metadata_url, timeout=30) as response:
        release_metadata = json.load(response)
    asset = next(record for record in release_metadata["assets"] if record["name"] == ASSET_NAME)
    expected_digest = asset["digest"].removeprefix("sha256:")
    download_directory = WORKSPACE_DIRECTORY / "data/Paseo/downloads"
    download_directory.mkdir(parents=True, exist_ok=True)
    archive_path = download_directory / ASSET_NAME
    if not archive_path.exists():
        temporary_path = archive_path.with_suffix(".zip.partial")
        urllib.request.urlretrieve(asset["browser_download_url"], temporary_path)
        temporary_path.replace(archive_path)
    with archive_path.open("rb") as archive_stream:
        actual_digest = hashlib.file_digest(archive_stream, "sha256").hexdigest()
    if actual_digest != expected_digest:
        raise RuntimeError("Paseo ZIP SHA256이 공식 GitHub asset digest와 다릅니다.")
    installation_directory = WORKSPACE_DIRECTORY / "data/Paseo/desktop" / RELEASE_VERSION
    desktop_executable = installation_directory / "Paseo.exe"
    if not desktop_executable.exists():
        installation_directory.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive_path) as release_archive:
            for archive_member in release_archive.infolist():
                target_path = (installation_directory / archive_member.filename).resolve()
                if not target_path.is_relative_to(installation_directory.resolve()):
                    raise RuntimeError("Paseo ZIP에 설치 경로 밖의 항목이 있습니다.")
            release_archive.extractall(installation_directory)
    if not desktop_executable.exists():
        raise RuntimeError("압축 해제 후 Paseo.exe가 없습니다.")
    manifest = {"version": RELEASE_VERSION, "asset": ASSET_NAME,
                "sha256": actual_digest, "desktop_executable": str(desktop_executable)}
    manifest_path = WORKSPACE_DIRECTORY / "data/Paseo/downloads/desktop-release.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    prepare_desktop_release()
