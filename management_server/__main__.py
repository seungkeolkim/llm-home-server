"""LLM Home Server를 수동 실행하고 코드 변경만 reload합니다."""

import argparse

import uvicorn

from .configuration import WORKSPACE_DIRECTORY, load_configuration


def main():
    """기본 reload를 켜고 관리 서버 코드와 화면 디렉터리만 감시합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-reload", action="store_true")
    arguments = parser.parse_args()
    configuration = load_configuration()
    reload_enabled = not arguments.no_reload
    uvicorn.run("management_server.application:create_app", factory=True,
                host=configuration["host"], port=configuration["port"], reload=reload_enabled,
                reload_dirs=[str(WORKSPACE_DIRECTORY / relative_path) for relative_path in (
                    "management_server", "web/ManagementServer", "config/ManagementServer")] if reload_enabled else None,
                reload_includes=["*.py", "*.html", "*.css", "*.js", "*.json"] if reload_enabled else None,
                timeout_graceful_shutdown=10, access_log=False)


if __name__ == "__main__":
    main()
