"""접근 경계, queue 조회, 허용한 제어와 reload 내구성을 검증합니다."""

import asyncio
import json
import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest

from management_server.application import create_app
from management_server.integrations import comfy_queue, run_command
from management_server.operations import OperationStore
from management_server.security import COOKIE_NAME, SessionAccess
from management_server.worker import execute_operation


@pytest.fixture
def configuration():
    """실제 local secret과 분리한 테스트 설정을 만듭니다."""
    return {"access_string": "test-access", "session_secret": "test-secret-" * 6, "session_hours": 1,
            "host": "127.0.0.1", "port": 8788, "links": {}, "comfy_url": "http://comfy",
            "llm": {"adapter": "strata"}}


class DummyMonitor:
    """실제 서비스와 무관한 snapshot 수집기를 제공합니다."""

    def __init__(self):
        """검증에 필요한 최소 상태만 준비합니다."""
        self.snapshot = {"ready": True}
        self.adapter = SimpleNamespace(native_configuration={"api_key": "test-api-key"})

    async def run(self):
        """앱 lifespan 동안 취소 가능한 수집 작업을 대신합니다."""
        await asyncio.Event().wait()

    async def close(self):
        """실제 연결을 만들지 않았으므로 즉시 종료합니다."""
        return None


def test_session_and_csrf_boundaries(configuration, tmp_path, monkeypatch):
    """미인증·잘못된 키·위조 cookie·cross-origin 요청을 거부합니다."""
    store = OperationStore(tmp_path / "operations.sqlite3")
    monkeypatch.setattr(store, "launch", lambda identifier: None)
    application = create_app(configuration, store, DummyMonitor())
    with TestClient(application) as client:
        assert client.get("/api/status").status_code == 401
        assert client.get("/api/health").json() == {"status": "ok"}
        assert client.get("/docs").status_code == 404
        assert client.post("/api/access", json={"access_string": "incorrect"}).status_code == 401
        unlocked = client.post("/api/access", json={"access_string": "test-access"})
        assert "HttpOnly" in unlocked.headers["set-cookie"]
        assert "SameSite=strict" in unlocked.headers["set-cookie"]
        assert client.get("/api/status").status_code == 200
        assert client.post("/api/services/comfy/unload").status_code == 403
        headers = {"X-CSRF-Token": unlocked.json()["csrf"]}
        assert client.post("/api/services/comfy/unload", headers={**headers, "Origin": "http://elsewhere"}).status_code == 403
        assert client.post("/api/services/comfy/cancel", headers=headers).status_code == 404
        assert client.post("/api/services/comfy/unload", headers=headers).status_code == 202
        assert client.post("/api/services/llm/start", headers=headers).status_code == 409
        client.cookies.set(COOKIE_NAME, "forged.payload")
        assert client.get("/api/status").status_code == 401


def test_session_survives_reload(configuration):
    """같은 local secret을 쓰는 새 앱에서도 기존 session을 인식합니다."""
    cookie, payload = SessionAccess(configuration).issue()
    assert SessionAccess(configuration).validate(cookie) == payload
    changed_configuration = {**configuration, "session_secret": "different-secret" * 4}
    assert SessionAccess(changed_configuration).validate(cookie) is None


def test_operation_store_survives_reload_and_serializes(tmp_path):
    """새 store 객체에서도 진행 중 작업을 보존하고 중복 조작을 막습니다."""
    database_path = tmp_path / "operations.sqlite3"
    first_store = OperationStore(database_path)
    identifier = first_store.create("llm", "start")
    second_store = OperationStore(database_path)
    with pytest.raises(RuntimeError):
        second_store.create("librechat", "stop")
    first_store.finish(identifier, "succeeded", "done")
    assert second_store.get(identifier)["status"] == "succeeded"
    assert second_store.create("comfy", "unload")
    with pytest.raises(ValueError):
        second_store.create("comfy", "cancel")


def test_comfy_queue_reads_without_prompt_or_cancellation():
    """Comfy queue를 조회할 때 POST나 취소 API를 호출하지 않습니다."""
    requests = []

    def respond(request):
        """현행 ComfyUI job 목록을 재현합니다."""
        requests.append(request)
        return httpx.Response(200, json={"jobs": [{"id": "active", "status": "in_progress"},
                                                  {"id": "waiting", "status": "pending"}]})

    async def exercise():
        """Mock transport로 실제 HTTP 요청 방식을 검증합니다."""
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            queue = await comfy_queue(client, "http://comfy")
        assert queue["running"][0]["identifier"] == "active"
        assert queue["pending"][0]["identifier"] == "waiting"

    asyncio.run(exercise())
    assert len(requests) == 1
    assert requests[0].method == "GET"
    assert requests[0].url.path == "/api/jobs"


def test_comfy_unload_sets_both_flags_without_interrupt(configuration, monkeypatch):
    """메모리 해제는 두 flag를 보내고 취소·interrupt를 호출하지 않습니다."""
    requests = []
    original_client = httpx.AsyncClient

    def respond(request):
        """ComfyUI가 빈 성공 응답을 보내는 상황을 재현합니다."""
        requests.append(request)
        return httpx.Response(200, content=b"")

    def create_client(**arguments):
        """Mock transport를 사용한 HTTP client를 만듭니다."""
        return original_client(transport=httpx.MockTransport(respond), **arguments)

    monkeypatch.setattr(httpx, "AsyncClient", create_client)
    status, message = asyncio.run(execute_operation({"target": "comfy", "action": "unload"}, configuration))
    assert status == "accepted"
    assert "접수" in message
    assert len(requests) == 1 and requests[0].url.path == "/free"
    assert json.loads(requests[0].content) == {"unload_models": True, "free_memory": True}


def test_commands_do_not_depend_on_windows_subprocess_event_loop(monkeypatch):
    """Windows reload의 Selector loop에서도 상태 조회 명령을 실행할 수 있습니다."""
    async def unsupported_subprocess(*arguments, **keywords):
        """Selector event loop의 subprocess 미지원을 재현합니다."""
        raise NotImplementedError

    monkeypatch.setattr(asyncio, "create_subprocess_exec", unsupported_subprocess)
    result = asyncio.run(run_command([sys.executable, "-c", "print('command-ready')"]))
    assert result.strip() == "command-ready"
