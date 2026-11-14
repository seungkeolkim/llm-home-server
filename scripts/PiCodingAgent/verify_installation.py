"""작은 순차 LLM 요청으로 Paseo와 공유하는 Pi Extension을 검사합니다."""

import subprocess

from service_runtime import WORKSPACE_DIRECTORY, build_environment, load_configuration, start_service


def main():
    """API key는 child 환경으로만 전달하고 검증 실패를 exit code에 반영합니다."""
    start_service(headless=True)
    environment = build_environment(load_configuration())
    commands = [
        ["node", str(WORKSPACE_DIRECTORY / "scripts/PiCodingAgent/verify_extensions.mjs")],
    ]
    for command in commands:
        subprocess.run(command, env=environment, cwd=WORKSPACE_DIRECTORY, check=True)


if __name__ == "__main__":
    main()
