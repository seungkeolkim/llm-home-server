"""LLM Home Server의 session, 상태 조회, 명시적 제어 API와 화면을 제공합니다."""

import asyncio
from contextlib import asynccontextmanager, suppress
import hmac
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from .configuration import WORKSPACE_DIRECTORY, load_configuration
from .monitoring import SnapshotMonitor
from .operations import OperationStore
from .security import COOKIE_NAME, SessionAccess


WEB_DIRECTORY = WORKSPACE_DIRECTORY / "web/ManagementServer"


class AccessInput(BaseModel):
    """계정명 없이 하나의 접속 문자열만 받습니다."""

    access_string: str = Field(min_length=1, max_length=256)


def asset_revision():
    """열린 브라우저가 HTML·CSS·JS 변경을 감지할 수 있는 revision을 만듭니다."""
    return "-".join(str((WEB_DIRECTORY / filename).stat().st_mtime_ns)
                    for filename in ("index.html", "application.css", "application.js"))


def create_app(configuration=None, operations=None, monitor=None):
    """독립 설정으로 앱을 만들고 하위 서비스의 수명에는 관여하지 않습니다."""
    configuration = configuration or load_configuration()
    operations = operations or OperationStore()
    monitor = monitor or SnapshotMonitor(configuration, operations)
    access = SessionAccess(configuration)

    @asynccontextmanager
    async def lifespan(application):
        """Reload 시 상태 수집만 재시작하고 작업 worker와 하위 서비스는 유지합니다."""
        collection_task = asyncio.create_task(monitor.run())
        yield
        collection_task.cancel()
        with suppress(asyncio.CancelledError):
            await collection_task
        await monitor.close()

    application = FastAPI(title="LLM Home Server", lifespan=lifespan,
                          docs_url=None, redoc_url=None, openapi_url=None)
    application.state.operations = operations
    application.state.monitor = monitor

    @application.middleware("http")
    async def protect_session(request, call_next):
        """제어·조회 API에 session을 적용하고 변경 요청은 동일 출처·CSRF를 검사합니다."""
        public_paths = {"/api/health", "/api/session", "/api/access"}
        session = access.validate(request.cookies.get(COOKIE_NAME, ""))
        if request.url.path.startswith("/api/") and request.url.path not in public_paths and not session:
            return JSONResponse({"detail": "접속 문자열을 확인해 주세요."}, status_code=401)
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            expected_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if request.headers.get("origin", expected_origin) != expected_origin:
                return JSONResponse({"detail": "다른 출처의 요청은 허용하지 않습니다."}, status_code=403)
            if request.url.path != "/api/access":
                if not session or not hmac.compare_digest(request.headers.get("x-csrf-token", "").encode(), session["csrf"].encode()):
                    return JSONResponse({"detail": "세션을 새로 확인해 주세요."}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        return response

    @application.get("/api/health")
    async def health():
        """비인증 health에는 민감한 상태를 포함하지 않습니다."""
        return {"status": "ok"}

    @application.get("/api/session")
    async def session_status(request: Request):
        """브라우저 세션과 화면 갱신 revision을 조회합니다."""
        session = access.validate(request.cookies.get(COOKIE_NAME, ""))
        return {"allowed": bool(session), "csrf": session["csrf"] if session else None,
                "asset_revision": asset_revision()}

    @application.post("/api/access")
    async def allow_access(request: Request, payload: AccessInput):
        """접속 문자열이 맞으면 서명된 HttpOnly session cookie를 발급합니다."""
        remote_address = request.client.host if request.client else "unknown"
        result = access.check_string(payload.access_string, remote_address)
        if result != "accepted":
            raise HTTPException(429 if result == "limited" else 401,
                                "잠시 후 다시 시도해 주세요." if result == "limited" else "접속 문자열이 맞지 않습니다.")
        cookie, session = access.issue()
        response = JSONResponse({"allowed": True, "csrf": session["csrf"], "asset_revision": asset_revision()})
        response.set_cookie(COOKIE_NAME, cookie, httponly=True, secure=False,
                            samesite="strict", max_age=access.lifetime_seconds)
        return response

    @application.post("/api/lock")
    async def lock_access():
        """현재 브라우저에서 관리 화면 접속 세션을 제거합니다."""
        response = JSONResponse({"allowed": False})
        response.delete_cookie(COOKIE_NAME)
        return response

    @application.get("/api/status")
    async def status():
        """브라우저 수와 관계없이 공통 snapshot을 반환합니다."""
        operations_snapshot = await asyncio.to_thread(operations.recent)
        return {**monitor.snapshot, "operations": operations_snapshot,
                "asset_revision": asset_revision(), "links": configuration["links"],
                "external_links": configuration.get("external_links", configuration["links"])}

    @application.post("/api/services/{target}/{action}", status_code=202)
    async def control_service(target: str, action: str):
        """미리 등록한 조작만 비동기로 접수하며 임의 command를 받지 않습니다."""
        try:
            identifier = await asyncio.to_thread(operations.create, target, action)
        except ValueError as error:
            raise HTTPException(404, str(error)) from None
        except RuntimeError as error:
            raise HTTPException(409, str(error)) from None
        try:
            await asyncio.to_thread(operations.launch, identifier)
        except OSError:
            raise HTTPException(500, "제어 worker를 시작하지 못했습니다.") from None
        return operations.get(identifier)

    @application.get("/api/operations")
    async def operation_history():
        """진행 중인 작업과 최근 결과를 즉시 조회합니다."""
        await asyncio.to_thread(operations.recover_interrupted)
        return await asyncio.to_thread(operations.recent)

    @application.get("/api/logs/{target}")
    async def read_logs(target: str):
        """허용된 로그의 끝부분만 읽고 local secret을 가립니다."""
        if target == "llm":
            log_path = WORKSPACE_DIRECTORY / "runtime/Strata/logs/strata-engine.log"
        elif target == "control":
            recent_operations = operations.recent()
            if not recent_operations:
                return {"text": "아직 제어 이력이 없습니다."}
            log_path = WORKSPACE_DIRECTORY / "runtime/ManagementServer/operations" / (recent_operations[0]["identifier"] + ".log")
        else:
            raise HTTPException(404, "지원하지 않는 로그입니다.")
        if not log_path.exists():
            return {"text": "로그 파일이 아직 없습니다."}
        with log_path.open("rb") as log_stream:
            log_stream.seek(max(0, log_path.stat().st_size - 12000))
            text = log_stream.read().decode("utf-8", errors="replace")
        for secret_value in (configuration["access_string"], configuration["session_secret"],
                             monitor.adapter.native_configuration.get("api_key", "")):
            if secret_value:
                text = text.replace(secret_value, "[REDACTED]")
        return {"text": text}

    @application.get("/")
    async def home():
        """모바일과 데스크톱의 공통 화면을 제공합니다."""
        return FileResponse(WEB_DIRECTORY / "index.html")

    @application.get("/application.css")
    async def styles():
        """화면 스타일을 cache 없이 제공합니다."""
        return FileResponse(WEB_DIRECTORY / "application.css", media_type="text/css")

    @application.get("/application.js")
    async def javascript():
        """브라우저 동작 코드를 cache 없이 제공합니다."""
        return FileResponse(WEB_DIRECTORY / "application.js", media_type="text/javascript")

    return application
