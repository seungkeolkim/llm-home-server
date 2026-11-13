"""기존 LLM 설정을 보존하면서 Pi Desktop과 단일 요청 gateway를 관리합니다."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import argparse
import hmac
import json
import os
import subprocess
import sys
import threading
import time

import httpx
import psutil


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
RUNTIME_DIRECTORY = WORKSPACE_DIRECTORY / "runtime/PiCodingAgent"
STATE_PATH = RUNTIME_DIRECTORY / "service-state.json"
CONFIGURATION_PATH = WORKSPACE_DIRECTORY / "config/PiCodingAgent/pi-coding-agent.local.json"
PACKAGE_DIRECTORY = WORKSPACE_DIRECTORY / "data/PiCodingAgent/npm"
PI_ENTRY_PATH = PACKAGE_DIRECTORY / "node_modules/@earendil-works/pi-coding-agent/dist/cli.js"


def read_json(configuration_path):
    """Windows BOM을 허용하면서 JSON 설정을 읽습니다."""
    return json.loads(Path(configuration_path).read_text(encoding="utf-8-sig"))


def load_configuration():
    """Pi 설정만 읽고 gateway를 loopback으로 제한합니다."""
    configuration = read_json(CONFIGURATION_PATH)
    if configuration["gateway_host"] != "127.0.0.1":
        raise ValueError("Pi gateway는 127.0.0.1에서만 실행할 수 있습니다.")
    return configuration


def read_provider_configuration(provider):
    """기존 LLM 설정을 읽기 전용으로 사용합니다."""
    return read_json(WORKSPACE_DIRECTORY / provider["configuration_path"])


def build_environment(configuration):
    """기존 key는 child 환경에만 전달하고 Pi의 모든 저장소를 격리합니다."""
    environment = os.environ.copy()
    environment.update({
        "PI_CODING_AGENT_DIR": str(RUNTIME_DIRECTORY / "agent"),
        "BILI_CONFIG_FILE": str(WORKSPACE_DIRECTORY / "config/PiCodingAgent/billion-context.local.json"),
        "BILI_SESSIONS_DIR": str(RUNTIME_DIRECTORY / "context/sessions"),
        "ACP_LOG_FILE": str(RUNTIME_DIRECTORY / "context/bili.log"),
        "ACP_AUTO_UPDATE": "0",
        "BILI_ADVISORY_CHECK": "0",
        "ACP_AUTO_RESTART_ON_UPDATE": "0",
        "XDG_CONFIG_HOME": str(RUNTIME_DIRECTORY / "xdg/config"),
        "XDG_DATA_HOME": str(RUNTIME_DIRECTORY / "xdg/data"),
        "XDG_STATE_HOME": str(RUNTIME_DIRECTORY / "xdg/state"),
        "PI_WEB_ACCESS_CACHE_ROOT": str(RUNTIME_DIRECTORY / "web-cache"),
        "AGENT_BROWSER_SESSION": "llm-home-pi",
        "PYTHONUTF8": "1",
        "PATH": str(WORKSPACE_DIRECTORY / "scripts/PiCodingAgent/bin") + os.pathsep
                + str(PACKAGE_DIRECTORY / "node_modules/.bin") + os.pathsep + environment.get("PATH", ""),
    })
    environment.pop("ELECTRON_RUN_AS_NODE", None)
    for provider in configuration["providers"].values():
        native_configuration = read_provider_configuration(provider)
        environment[provider["environment_key"]] = native_configuration.get("api_key") or "local-no-key"
    return environment


def owned_process(record, executable_path=None, required_argument=None):
    """PID 재사용과 다른 앱의 오종료를 방지하도록 생성 시각과 경로를 확인합니다."""
    if not record:
        return None
    try:
        process = psutil.Process(record["pid"])
        if abs(process.create_time() - record["created_at"]) > 0.05:
            return None
        if executable_path and Path(process.exe()).resolve() != Path(executable_path).resolve():
            return None
        if required_argument and required_argument not in process.cmdline():
            return None
        return process
    except (psutil.Error, KeyError, OSError):
        return None


def process_record(process_id):
    """비밀값 없이 프로세스의 소유 식별 정보를 만듭니다."""
    process = psutil.Process(process_id)
    return {"pid": process.pid, "created_at": process.create_time()}


def service_status():
    """준비 상태와 실제 Pi 프로세스 실행 상태를 구분합니다."""
    prepared = CONFIGURATION_PATH.exists() and PI_ENTRY_PATH.exists()
    result = {"state": "stopped", "prepared": prepared, "in_flight": 0,
              "desktop_running": False, "model_control": "independent"}
    try:
        record = read_json(STATE_PATH)
        service_process = owned_process(record.get("service"), required_argument=str(Path(__file__).resolve()))
        if not service_process:
            return result
        configuration = load_configuration()
        with httpx.Client(trust_env=False, timeout=2) as client:
            response = client.get(f"http://127.0.0.1:{configuration['gateway_port']}/health")
            response.raise_for_status()
            health = response.json()
        if health.get("pid") != service_process.pid:
            return {**result, "state": "unavailable", "error": "Pi gateway 소유 process 불일치"}
        return {**result, **health, "state": "running", "pid": service_process.pid}
    except (OSError, ValueError, KeyError, httpx.HTTPError):
        return result


@contextmanager
def control_lock():
    """동시 CLI와 관리 API에서 Pi를 중복 시작하지 못하도록 잠급니다."""
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


def start_service(headless=False):
    """Pi 전용 프로세스만 시작하고 기존 LLM과 LibreChat을 건드리지 않습니다."""
    with control_lock():
        current_status = service_status()
        if current_status["state"] == "running":
            if headless or current_status["desktop_running"]:
                return current_status
            if current_status["in_flight"]:
                raise RuntimeError("Pi 요청이 실행 중입니다. 완료 후 Desktop을 시작해 주세요.")
            record = read_json(STATE_PATH)
            existing_process = owned_process(record.get("service"), required_argument=str(Path(__file__).resolve()))
            if existing_process:
                stop_process_tree(existing_process)
            STATE_PATH.unlink(missing_ok=True)
        configuration = load_configuration()
        if not PI_ENTRY_PATH.exists():
            raise RuntimeError("Pi dependency를 먼저 준비해 주세요.")
        desktop_path = WORKSPACE_DIRECTORY / configuration["desktop_executable"]
        if not headless and not desktop_path.exists():
            raise RuntimeError("검증한 Pi Desktop 배포 파일이 없습니다.")
        command = [sys.executable, "-B", str(Path(__file__).resolve()), "serve"]
        if headless:
            command.append("--headless")
        with (RUNTIME_DIRECTORY / "service.log").open("ab") as log_stream:
            process = subprocess.Popen(command, cwd=WORKSPACE_DIRECTORY,
                                       env=build_environment(configuration), stdin=subprocess.DEVNULL,
                                       stdout=log_stream, stderr=subprocess.STDOUT,
                                       creationflags=subprocess.CREATE_NO_WINDOW)
        for attempt in range(100):
            if process.poll() is not None:
                raise RuntimeError("Pi 기동에 실패했습니다. runtime/PiCodingAgent/service.log를 확인해 주세요.")
            status = service_status()
            if status["state"] == "running":
                return status
            time.sleep(0.1)
        raise RuntimeError("Pi gateway의 기동 확인 시간이 초과됐습니다.")


def stop_process_tree(process):
    """이미 소유권을 확인한 Pi 프로세스와 자식만 종료합니다."""
    descendants = process.children(recursive=True)
    for child_process in reversed(descendants):
        try:
            child_process.terminate()
        except psutil.NoSuchProcess:
            pass
    process.terminate()
    remaining_processes = psutil.wait_procs([*descendants, process], timeout=5)[1]
    for remaining_process in remaining_processes:
        try:
            remaining_process.kill()
        except psutil.NoSuchProcess:
            pass


def stop_service():
    """Pi만 종료하며 세션, Extension 상태와 기존 서버는 보존합니다."""
    with control_lock():
        for client_path in (RUNTIME_DIRECTORY / "clients").glob("*.json"):
            try:
                client_process = owned_process(read_json(client_path), required_argument=str(PI_ENTRY_PATH))
                if client_process:
                    stop_process_tree(client_process)
                client_path.unlink(missing_ok=True)
            except (OSError, ValueError, psutil.Error):
                continue
        if not STATE_PATH.exists():
            return service_status()
        record = read_json(STATE_PATH)
        service_process = owned_process(record.get("service"), required_argument=str(Path(__file__).resolve()))
        if service_process:
            stop_process_tree(service_process)
        STATE_PATH.unlink(missing_ok=True)
        return service_status()


class PiGateway(ThreadingHTTPServer):
    """Pi 전체 세션에 대해 한 번에 한 개의 LLM HTTP 요청만 전달합니다."""

    daemon_threads = True

    def __init__(self, configuration):
        """loopback listener와 공통 비재진입 요청 잠금을 준비합니다."""
        super().__init__((configuration["gateway_host"], configuration["gateway_port"]), PiGatewayHandler)
        self.configuration = configuration
        self.request_lock = threading.Lock()
        self.desktop_process = None
        self.completed_requests = 0
        self.rejected_requests = 0
        self.maximum_in_flight = 0
        self.observed_tool_names = set()


class PiGatewayHandler(BaseHTTPRequestHandler):
    """허용한 models/chat endpoint만 기존 서버로 전달하며 본문과 key를 기록하지 않습니다."""

    protocol_version = "HTTP/1.1"

    def log_message(self, message_format, *arguments):
        """URL·요청 본문·인증정보의 HTTP 기본 로그 출력을 차단합니다."""
        return

    def send_json(self, status_code, payload):
        """길이를 명시한 JSON 응답으로 연결 종료를 명확히 합니다."""
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(content)
        self.close_connection = True

    def do_GET(self):
        """health에는 비밀값 없이 Pi 프로세스·동시성 상태만 제공합니다."""
        if self.path == "/health":
            desktop_process = self.server.desktop_process
            self.send_json(200, {"pid": os.getpid(), "in_flight": int(self.server.request_lock.locked()),
                                 "desktop_running": bool(desktop_process and desktop_process.poll() is None),
                                 "completed_requests": self.server.completed_requests,
                                 "rejected_requests": self.server.rejected_requests,
                                 "maximum_in_flight": self.server.maximum_in_flight,
                                 "observed_tool_names": sorted(self.server.observed_tool_names)})
            return
        self.forward_request()

    def do_POST(self):
        """chat 요청을 단일 실행 경계에서 처리합니다."""
        self.forward_request()

    def forward_request(self):
        """등록된 backend로만 전달하며 두 번째 동시 LLM 요청은 전송 전에 거절합니다."""
        path_parts = self.path.strip("/").split("/")
        expected_endpoint = "models" if self.command == "GET" else "chat/completions"
        if len(path_parts) < 3 or "/".join(path_parts[1:]) != "v1/" + expected_endpoint:
            self.send_json(404, {"error": "등록되지 않은 Pi endpoint입니다."})
            return
        provider = next((provider for provider in self.server.configuration["providers"].values()
                         if provider["gateway_route"] == path_parts[0]), None)
        if not provider:
            self.send_json(404, {"error": "등록되지 않은 Provider입니다."})
            return
        native_configuration = read_provider_configuration(provider)
        expected_key = native_configuration.get("api_key") or "local-no-key"
        if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + expected_key):
            self.send_json(401, {"error": "Provider 인증이 필요합니다."})
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "요청 길이가 올바르지 않습니다."})
            return
        if content_length < 0 or content_length > 32 * 1024 * 1024:
            self.send_json(413, {"error": "요청 크기를 초과했습니다."})
            return
        request_body = self.rfile.read(content_length) if content_length else None
        is_generation = self.command == "POST"
        if is_generation:
            try:
                request_payload = json.loads(request_body or b"{}")
                if request_payload.get("model") != native_configuration["model_name"]:
                    self.send_json(400, {"error": "선택한 Provider의 Model ID와 일치하지 않습니다."})
                    return
                for tool_definition in request_payload.get("tools", []):
                    tool_name = tool_definition.get("function", {}).get("name", "")
                    if tool_name:
                        self.server.observed_tool_names.add(tool_name[:128])
            except (ValueError, AttributeError):
                self.send_json(400, {"error": "올바른 JSON chat 요청이 필요합니다."})
                return
        if is_generation and not self.server.request_lock.acquire(blocking=False):
            self.server.rejected_requests += 1
            self.send_json(429, {"error": {"message": "다른 Pi 요청이 실행 중입니다. 종료 후 다시 실행해 주세요.",
                                          "type": "pi_single_request_only"}})
            return
        if is_generation:
            self.server.maximum_in_flight = 1
        response_started = False
        try:
            upstream_url = f"http://127.0.0.1:{int(native_configuration['port'])}/v1/{expected_endpoint}"
            headers = {"Content-Type": "application/json", "Authorization": "Bearer " + expected_key}
            with httpx.Client(trust_env=False, timeout=httpx.Timeout(1800, connect=10)) as client:
                with client.stream(self.command, upstream_url, content=request_body, headers=headers) as response:
                    self.send_response(response.status_code)
                    response_started = True
                    self.send_header("Content-Type", response.headers.get("content-type", "application/json"))
                    self.send_header("Connection", "close")
                    self.end_headers()
                    self.close_connection = True
                    for response_chunk in response.iter_raw():
                        self.wfile.write(response_chunk)
                        self.wfile.flush()
            if is_generation:
                self.server.completed_requests += 1
        except (BrokenPipeError, ConnectionResetError):
            pass
        except httpx.HTTPError:
            if not response_started:
                self.send_json(502, {"error": {"message": "선택한 LLM 서버에 연결할 수 없습니다. 기존 LLM 제어에서 준비 상태를 확인해 주세요."}})
            self.close_connection = True
        finally:
            if is_generation:
                self.server.request_lock.release()


def serve(headless=False):
    """gateway와 Desktop을 동일한 소유 프로세스 트리에서 실행합니다."""
    configuration = load_configuration()
    server = PiGateway(configuration)
    record = {"service": process_record(os.getpid())}
    temporary_state_path = STATE_PATH.with_suffix(".tmp")
    temporary_state_path.write_text(json.dumps(record), encoding="utf-8")
    temporary_state_path.replace(STATE_PATH)
    if not headless:
        desktop_temporary_directory = RUNTIME_DIRECTORY / "desktop-temp"
        desktop_temporary_directory.mkdir(parents=True, exist_ok=True)
        desktop_environment = build_environment(configuration)
        desktop_environment.update({"TEMP": str(desktop_temporary_directory), "TMP": str(desktop_temporary_directory)})
        desktop_command = [str(WORKSPACE_DIRECTORY / configuration["desktop_executable"]),
                           "--user-data-dir=" + str(RUNTIME_DIRECTORY / "desktop")]
        with (RUNTIME_DIRECTORY / "desktop.log").open("ab") as desktop_log:
            server.desktop_process = subprocess.Popen(desktop_command, cwd=WORKSPACE_DIRECTORY,
                                                      env=desktop_environment,
                                                      stdin=subprocess.DEVNULL, stdout=desktop_log,
                                                      stderr=subprocess.STDOUT)
    print("Pi gateway listening on 127.0.0.1:" + str(configuration["gateway_port"]), flush=True)
    server.serve_forever(poll_interval=0.3)


def main():
    """공개 CLI에는 사전에 정한 Pi 동작만 노출합니다."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["start", "stop", "status", "serve", "cli"])
    parser.add_argument("--headless", action="store_true")
    parsed_arguments, pi_arguments = parser.parse_known_args()
    if parsed_arguments.action == "serve":
        serve(parsed_arguments.headless)
    elif parsed_arguments.action == "start":
        print(json.dumps(start_service(parsed_arguments.headless), ensure_ascii=False))
    elif parsed_arguments.action == "stop":
        print(json.dumps(stop_service(), ensure_ascii=False))
    elif parsed_arguments.action == "status":
        print(json.dumps(service_status(), ensure_ascii=False))
    else:
        start_service(headless=True)
        if pi_arguments[:1] == ["--"]:
            pi_arguments = pi_arguments[1:]
        client_directory = RUNTIME_DIRECTORY / "clients"
        client_directory.mkdir(parents=True, exist_ok=True)
        process = subprocess.Popen(["node", str(PI_ENTRY_PATH), *pi_arguments], cwd=os.getcwd(),
                                   env=build_environment(load_configuration()))
        client_path = client_directory / f"{process.pid}.json"
        client_path.write_text(json.dumps(process_record(process.pid)), encoding="utf-8")
        try:
            exit_code = process.wait()
        except KeyboardInterrupt:
            client_process = owned_process(read_json(client_path), required_argument=str(PI_ENTRY_PATH))
            if client_process:
                stop_process_tree(client_process)
            exit_code = 130
        finally:
            client_path.unlink(missing_ok=True)
        raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
