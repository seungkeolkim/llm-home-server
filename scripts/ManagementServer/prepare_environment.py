"""사용자가 template에서 복사해 작성한 관리 서버 설정을 검증합니다."""

from pathlib import Path
import sys


def main():
    """접속 문자열과 session secret을 확인하고 실행 산출물 경로만 준비합니다."""
    workspace_directory = Path(__file__).resolve().parents[2]
    sys.path.insert(0, str(workspace_directory))
    from management_server.configuration import load_configuration

    load_configuration()
    (workspace_directory / "runtime/ManagementServer").mkdir(parents=True, exist_ok=True)
    print("LLM Home Server local configuration ready.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError) as error:
        raise SystemExit(str(error)) from None
