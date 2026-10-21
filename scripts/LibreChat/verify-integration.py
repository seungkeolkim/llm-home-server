"""Python 표준 라이브러리로 LibreChat 로그인과 Strata·검색 연결을 검증합니다."""

import argparse
import datetime
import http.cookiejar
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request
import uuid


WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
CONFIGURATION_DIRECTORY = WORKSPACE_ROOT / "config/LibreChat"
DIAGNOSTICS_DIRECTORY = WORKSPACE_ROOT / "runtime/LibreChat/diagnostics"


def read_environment_settings():
    """실제 운영 port와 origin을 local env에서 읽고 출력하지 않습니다."""
    settings = {}
    for environment_line in (CONFIGURATION_DIRECTORY / ".env.local").read_text(encoding="utf-8-sig").splitlines():
        if environment_line.strip() and not environment_line.startswith("#") and "=" in environment_line:
            setting_name, setting_value = environment_line.split("=", 1)
            settings[setting_name] = setting_value
    return settings


def send_json_request(client, request_url, payload=None):
    """Cookie와 인증 header를 유지하며 JSON 요청을 보내고 HTTP 오류를 전달합니다."""
    request_body = None
    request_headers = {}
    if payload is not None:
        request_body = json.dumps(payload).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(request_url, data=request_body, headers=request_headers)
    with client.open(request, timeout=90) as response:
        return json.load(response)


def create_authenticated_client(base_url, public_url):
    """local 관리자 정보로 로그인하되 비밀번호와 token을 출력하지 않습니다."""
    credentials_path = CONFIGURATION_DIRECTORY / "admin-credentials.local.json"
    credentials = json.loads(credentials_path.read_text(encoding="utf-8-sig"))
    client = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
    )
    client.addheaders = [
        ("Origin", public_url),
        ("Host", urllib.parse.urlsplit(public_url).netloc),
        ("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"),
    ]
    login_result = send_json_request(client, base_url + "/api/auth/login", {
        "email": credentials["email"],
        "password": credentials["password"],
    })
    client.addheaders.append(("Authorization", "Bearer " + login_result["token"]))
    print("Administrator login: HTTP 200", flush=True)
    return client


def submit_chat_turn(client, base_url, prompt_text, search_enabled=False):
    """공식 Agent route로 검증 대화를 만들고 최종 응답을 기다립니다."""
    configuration_path = WORKSPACE_ROOT / "config/Strata/strata.local.json"
    configuration = json.loads(configuration_path.read_text(encoding="utf-8-sig"))
    message_identifier = str(uuid.uuid4())
    response_message_identifier = message_identifier + "_response"
    payload = {
        "text": prompt_text,
        "sender": "User",
        "clientTimestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "isCreatedByUser": True,
        "parentMessageId": "00000000-0000-0000-0000-000000000000",
        "conversationId": "new",
        "messageId": message_identifier,
        "responseMessageId": response_message_identifier,
        "endpoint": "Strata",
        "endpointType": "custom",
        "model": configuration["model_name"],
        "isTemporary": False,
        "isRegenerate": False,
        "error": False,
        "ephemeralAgent": {"web_search": search_enabled},
    }
    admitted_job = send_json_request(client, base_url + "/api/agents/chat/Strata", payload)
    conversation_identifier = admitted_job["conversationId"]
    print("Chat admitted:", conversation_identifier, flush=True)
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        messages = send_json_request(client, base_url + "/api/messages/" + conversation_identifier)
        for message in reversed(messages):
            if message.get("messageId") != response_message_identifier or message.get("unfinished", False):
                continue
            if message.get("error"):
                raise RuntimeError("LibreChat returned a failed response")
            return {"conversationId": conversation_identifier, "response": message, "messages": messages}
        job_status = send_json_request(client, base_url + "/api/agents/chat/status/" + conversation_identifier)
        if job_status.get("status") in ("failed", "error"):
            raise RuntimeError("LibreChat generation failed")
        time.sleep(2)
    raise TimeoutError("LibreChat response was not completed within 240 seconds")


def main():
    """선택한 검증을 실행하고 결과만 Git 제외 diagnostics에 저장합니다."""
    settings = read_environment_settings()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=int(settings.get("LIBRECHAT_PORT", "8588")))
    parser.add_argument("--public-url", default=settings["DOMAIN_CLIENT"])
    parser.add_argument("--mode", choices=("login", "chat", "search"), default="login")
    arguments = parser.parse_args()
    base_url = f"http://127.0.0.1:{arguments.port}"
    client = create_authenticated_client(base_url, arguments.public_url)
    if arguments.mode == "login":
        send_json_request(client, base_url + "/api/convos")
        evidence = {"login": "ok", "conversation_list": "ok"}
    else:
        prompt_text = "Connection verification: reply with exactly STRATA_LIBRECHAT_READY."
        if arguments.mode == "search":
            prompt_text = "Use web_search to find Python's official asyncio documentation. Read a result and provide its title and URL."
        evidence = submit_chat_turn(client, base_url, prompt_text, arguments.mode == "search")
        if arguments.mode == "chat":
            visible_text = []
            for content_part in evidence["response"].get("content", []):
                if content_part.get("type") == "text":
                    visible_text.append(content_part.get("text", ""))
            if "STRATA_LIBRECHAT_READY" not in "\n".join(visible_text):
                raise RuntimeError("Strata verification marker was not returned")
    DIAGNOSTICS_DIRECTORY.mkdir(parents=True, exist_ok=True)
    evidence_path = DIAGNOSTICS_DIRECTORY / f"verification-{arguments.mode}.json"
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Verification completed:", arguments.mode, flush=True)
    print("Evidence:", evidence_path, flush=True)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
