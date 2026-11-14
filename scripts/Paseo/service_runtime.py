"""Paseo daemon과 Desktop을 소유 프로세스 기준으로 제어합니다."""

import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import httpx
import psutil


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WORKSPACE_DIRECTORY))

from scripts.PiCodingAgent.service_runtime import (
    owned_process, process_record, service_status as pi_status,
    start_service as start_pi, stop_process_tree,
)


RUNTIME_DIRECTORY = WORKSPACE_DIRECTORY / "runtime/Paseo"
HOME_DIRECTORY = WORKSPACE_DIRECTORY / "data/Paseo/home"
CONFIGURATION_PATH = WORKSPACE_DIRECTORY / "config/Paseo/paseo.local.json"
STATE_PATH = RUNTIME_DIRECTORY / "service-state.json"
CLI_ENTRY_PATH = WORKSPACE_DIRECTORY / "data/Paseo/npm/node_modules/@getpaseo/cli/bin/paseo"


def read_json(configuration_path):
    """Windows BOM을 허용하여 Paseo 전용 JSON을 읽습니다."""
    return json.loads(Path(configuration_path).read_text(encoding="utf-8-sig"))


def read_state():
    """아직 시작한 적이 없는 경우 빈 process 상태를 반환합니다."""
    try:
        return read_json(STATE_PATH)
    except (OSError, ValueError):
        return {}


def save_state(state):
    """API key 없이 PID와 생성 시각만 저장합니다."""
    RUNTIME_DIRECTORY.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def build_environment():
    """부모 shell의 daemon 설정 override를 제거하고 격리된 home을 선택합니다."""
    environment = {name: value for name, value in os.environ.items()
                   if not name.startswith("PASEO_") and name != "ELECTRON_RUN_AS_NODE"}
    environment["PASEO_HOME"] = str(HOME_DIRECTORY)
    environment["PASEO_ELECTRON_USER_DATA_DIR"] = str(RUNTIME_DIRECTORY / "desktop-profile")
    return environment


@contextmanager
def control_lock():
    """동시 runner가 Paseo를 중복 기동하거나 상태 파일을 덮어쓰지 못하도록 합니다."""
    import msvcrt

    RUNTIME_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with (RUNTIME_DIRECTORY / "control.lock").open("a+b") as lock_stream:
        lock_stream.seek(0)
        if not lock_stream.read(1):
            lock_stream.write(b"0")
            lock_stream.flush()
        lock_stream.seek(0)
        msvcrt.locking(lock_stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            lock_stream.seek(0)
            msvcrt.locking(lock_stream.fileno(), msvcrt.LK_UNLCK, 1)


def service_status():
    """설치 준비와 실제 daemon·Desktop·gateway 상태를 구분합니다."""
    prepared = CLI_ENTRY_PATH.exists() and (HOME_DIRECTORY / "config.json").exists()
    result = {"state": "stopped", "prepared": prepared, "desktop_running": False,
              "model_control": "independent", "listen_port": 6767}
    if not prepared:
        return result
    configuration = read_json(CONFIGURATION_PATH)
    result["listen_port"] = configuration["listen_port"]
    state = read_state()
    desktop_path = WORKSPACE_DIRECTORY / configuration["desktop_executable"]
    result["desktop_running"] = owned_process(state.get("desktop"), executable_path=desktop_path) is not None
    daemon_process = owned_process(state.get("daemon"), required_argument=str(CLI_ENTRY_PATH))
    if daemon_process is None:
        return result
    result["pid"] = daemon_process.pid
    result["state"] = "starting"
    try:
        with httpx.Client(trust_env=False, timeout=2) as client:
            response = client.get(f"http://127.0.0.1:{configuration['listen_port']}/api/health")
            response.raise_for_status()
        result["state"] = "running"
        processes = [daemon_process, *daemon_process.children(recursive=True)]
        result["working_set_mib"] = round(sum(process.memory_info().rss for process in processes) / 1024 ** 2)
    except (httpx.HTTPError, psutil.Error):
        pass
    return result


def start_service():
    """Paseo와 필요한 loopback gateway만 시작하며 LLM은 기동하지 않습니다."""
    with control_lock():
        return start_service_under_lock()


def start_service_under_lock():
    """제어 잠금을 획득한 호출에서 기존 daemon을 확인하거나 새로 시작합니다."""
    status = service_status()
    if status["state"] in ("running", "starting"):
        return status
    if not status["prepared"]:
        raise RuntimeError("Paseo 환경 준비가 필요합니다.")
    if pi_status()["state"] != "running":
        start_pi(headless=True)
    configuration = read_json(CONFIGURATION_PATH)
    with socket.socket() as port_probe:
        try:
            port_probe.bind(("127.0.0.1", configuration["listen_port"]))
        except OSError as error:
            raise RuntimeError("Paseo port에 소유권을 확인하지 못한 서비스가 있습니다.") from error
    RUNTIME_DIRECTORY.mkdir(parents=True, exist_ok=True)
    with (RUNTIME_DIRECTORY / "daemon-output.log").open("a", encoding="utf-8") as output_stream:
        process = subprocess.Popen(
            ["node", str(CLI_ENTRY_PATH), "daemon", "run", "--home", str(HOME_DIRECTORY)],
            cwd=WORKSPACE_DIRECTORY, env=build_environment(), stdin=subprocess.DEVNULL,
            stdout=output_stream, stderr=output_stream, creationflags=subprocess.CREATE_NO_WINDOW,
        )
    state = read_state()
    state["daemon"] = process_record(process.pid)
    save_state(state)
    for _attempt in range(60):
        status = service_status()
        if status["state"] == "running":
            return status
        if process.poll() is not None:
            raise RuntimeError("Paseo 기동 실패: runtime/Paseo/daemon-output.log를 확인하세요.")
        time.sleep(0.5)
    raise RuntimeError("Paseo가 30초 안에 health 응답을 시작하지 않았습니다.")


def open_desktop():
    """격리 profile을 사용하는 공식 Windows Desktop을 엽니다."""
    start_service()
    with control_lock():
        return open_desktop_under_lock()


def open_desktop_under_lock():
    """제어 잠금 안에서 Desktop 중복 실행을 피하고 소유 정보를 기록합니다."""
    configuration = read_json(CONFIGURATION_PATH)
    desktop_path = WORKSPACE_DIRECTORY / configuration["desktop_executable"]
    state = read_state()
    if owned_process(state.get("desktop"), executable_path=desktop_path):
        return service_status()
    process = subprocess.Popen([str(desktop_path)], cwd=WORKSPACE_DIRECTORY, env=build_environment())
    state["desktop"] = process_record(process.pid)
    save_state(state)
    return service_status()


def stop_service():
    """Paseo 소유 프로세스만 종료하고 기존 Pi gateway·LLM·Relay는 유지합니다."""
    with control_lock():
        return stop_service_under_lock()


def stop_service_under_lock():
    """제어 잠금 안에서 소유권을 재확인하고 Paseo 프로세스만 종료합니다."""
    state = read_state()
    configuration = read_json(CONFIGURATION_PATH)
    desktop_path = WORKSPACE_DIRECTORY / configuration["desktop_executable"]
    for process in (owned_process(state.get("desktop"), executable_path=desktop_path),
                    owned_process(state.get("daemon"), required_argument=str(CLI_ENTRY_PATH))):
        if process is not None:
            stop_process_tree(process)
    STATE_PATH.unlink(missing_ok=True)
    return service_status()


def main():
    """절대경로 runner에서 요청한 제한된 Paseo 조작만 실행합니다."""
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument("action", choices=("start", "stop", "status", "desktop", "pair"))
    arguments = argument_parser.parse_args()
    if arguments.action == "pair":
        start_service()
        response = subprocess.run(
            ["node", str(CLI_ENTRY_PATH), "daemon", "pair", "--home", str(HOME_DIRECTORY), "--json"],
            env=build_environment(), check=True, capture_output=True, text=True, encoding="utf-8", timeout=20,
        )
        pairing_offer = json.loads(response.stdout)
        pairing_url = pairing_offer.get("url") or pairing_offer.get("pairingUrl")
        if not pairing_url:
            raise RuntimeError("Paseo CLI 응답에 Pairing Link가 없습니다.")
        (HOME_DIRECTORY / "pairing-link.txt").write_text(pairing_url + "\n", encoding="utf-8")
        print(pairing_url)
        return
    actions = {"start": start_service, "stop": stop_service, "status": service_status, "desktop": open_desktop}
    print(json.dumps(actions[arguments.action](), ensure_ascii=False))


if __name__ == "__main__":
    main()
