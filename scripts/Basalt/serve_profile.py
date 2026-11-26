"""공식 Basalt server를 수정 없이 실행하고 cache·DLL 경로만 시스템별로 격리합니다."""

import argparse
from pathlib import Path
import runpy
import sys


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]


def basalt_cache_directory() -> Path:
    """공식 server가 쓰는 모델별 engine log를 runtime/Basalt 아래에 보관합니다."""
    return WORKSPACE_DIRECTORY / "runtime/Basalt/cache"


def main() -> None:
    """공식 Python server에 고정 설정과 key 파일 경로를 그대로 전달합니다."""
    argument_parser = argparse.ArgumentParser(description=__doc__)
    argument_parser.add_argument("--config", type=Path, required=True)
    argument_parser.add_argument("--engine-bin", type=Path, required=True)
    argument_parser.add_argument("--api-key-file", type=Path, required=True)
    arguments = argument_parser.parse_args()
    engine_directory = arguments.engine_bin.resolve().parents[1]
    server_path = engine_directory / "serve/server.py"
    sys.path.insert(0, str(engine_directory))
    sys.path.insert(0, str(engine_directory / "tools"))
    from serve.engine import modelfile

    # 공식 파일은 보존하고 실행 중 cache 위치만 시스템별 경로로 바꿉니다.
    modelfile.cache_root = basalt_cache_directory
    sys.argv = [str(server_path), "--config", str(arguments.config),
                "--engine-bin", str(arguments.engine_bin), "--api-key-file", str(arguments.api_key_file)]
    runpy.run_path(str(server_path), run_name="__main__")


if __name__ == "__main__":
    main()
