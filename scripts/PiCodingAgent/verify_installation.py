"""작은 순차 LLM 요청으로 Pi Extension을 검사하고 APK 서명을 검증합니다."""

import subprocess
import sys

from service_runtime import WORKSPACE_DIRECTORY, build_environment, load_configuration, start_service


def main():
    """API key는 child 환경으로만 전달하고 검증 실패를 exit code에 반영합니다."""
    start_service(headless=True)
    environment = build_environment(load_configuration())
    commands = [
        ["node", str(WORKSPACE_DIRECTORY / "scripts/PiCodingAgent/verify_extensions.mjs")],
        [sys.executable, "-X", "utf8", "-B", str(WORKSPACE_DIRECTORY / "scripts/PiCodingAgent/verify_android_apk.py")],
    ]
    for command in commands:
        subprocess.run(command, env=environment, cwd=WORKSPACE_DIRECTORY, check=True)


if __name__ == "__main__":
    main()
