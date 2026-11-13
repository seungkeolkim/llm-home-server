"""실제 LLM을 호출하지 않고 인증, 동시 요청 및 process 소유권 경계를 검증합니다."""

from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
import threading

import httpx
import psutil
import pytest

from scripts.PiCodingAgent import service_runtime


class BackendFixtureHandler(BaseHTTPRequestHandler):
    """Event로 첫 요청을 유지하여 두 번째 요청이 upstream에 도착하지 않는지 검사합니다."""

    def do_POST(self):
        """허용 신호까지 실제 응답을 지연합니다."""
        self.server.received_requests += 1
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.request_received.set()
        self.server.release_response.wait(timeout=5)
        content = b'{"choices":[{"message":{"content":"ready"}}]}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, message_format, *arguments):
        """테스트 서버의 기본 로그를 생략합니다."""
        return


@pytest.fixture
def gateway(monkeypatch):
    """실제 서비스와 분리된 loopback gateway와 가짜 upstream을 생성합니다."""
    backend = ThreadingHTTPServer(("127.0.0.1", 0), BackendFixtureHandler)
    backend.received_requests = 0
    backend.request_received = threading.Event()
    backend.release_response = threading.Event()
    native_configuration = {"api_key": "test-key", "port": backend.server_port, "model_name": "fixture-model"}
    monkeypatch.setattr(service_runtime, "read_provider_configuration", lambda provider: native_configuration)
    server = service_runtime.PiGateway({"gateway_host": "127.0.0.1", "gateway_port": 0,
                                        "providers": {"fixture": {"gateway_route": "fixture"}}})
    for fixture_server in (backend, server):
        threading.Thread(target=fixture_server.serve_forever, daemon=True).start()
    with httpx.Client(base_url=f"http://127.0.0.1:{server.server_port}", trust_env=False, timeout=8) as client:
        yield client, backend, server
    backend.release_response.set()
    for fixture_server in (server, backend):
        fixture_server.shutdown()
        fixture_server.server_close()


def test_rejects_parallel_generation_before_upstream(gateway):
    """동시 두 번째 LLM 요청은 429이며 첫 요청만 backend에 도착합니다."""
    client, backend, server = gateway
    headers = {"Authorization": "Bearer test-key"}
    payload = {"model": "fixture-model", "messages": []}
    with ThreadPoolExecutor(max_workers=1) as executor:
        first_request = executor.submit(client.post, "/fixture/v1/chat/completions", headers=headers, json=payload)
        assert backend.request_received.wait(timeout=3)
        second_response = client.post("/fixture/v1/chat/completions", headers=headers, json=payload)
        assert second_response.status_code == 429
        assert backend.received_requests == 1
        assert client.get("/health").json()["in_flight"] == 1
        backend.release_response.set()
        assert first_request.result().status_code == 200
    assert not server.request_lock.locked()
    assert server.maximum_in_flight == 1


def test_rejects_authentication_model_and_route_mismatch(gateway):
    """key, Model ID, route가 올바르지 않으면 backend에 요청하지 않습니다."""
    client, backend, server = gateway
    endpoint = "/fixture/v1/chat/completions"
    assert client.post(endpoint, json={"model": "fixture-model"}).status_code == 401
    assert client.post(endpoint, headers={"Authorization": "Bearer test-key"}, json={"model": "other"}).status_code == 400
    assert client.post("/other/v1/chat/completions").status_code == 404
    assert client.get("/fixture/v1/anything").status_code == 404
    assert backend.received_requests == 0


def test_does_not_accept_reused_pid_or_unowned_process():
    """실제 PID라도 시작 시각 또는 script 소유권이 다르면 종료 대상으로 반환하지 않습니다."""
    process = psutil.Process(os.getpid())
    record = {"pid": process.pid, "created_at": process.create_time()}
    assert service_runtime.owned_process(record) is not None
    assert service_runtime.owned_process({**record, "created_at": record["created_at"] - 10}) is None
    assert service_runtime.owned_process(record, required_argument="unrelated-pi-process") is None
