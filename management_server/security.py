"""계정 없이 접속 문자열과 서명된 session cookie만 사용합니다."""

import base64
import hashlib
import hmac
import json
import secrets
import time


COOKIE_NAME = "llm_home_session"


class SessionAccess:
    """Reload 후에도 local secret으로 기존 session을 검증합니다."""

    def __init__(self, configuration):
        """접속 문자열과 session 만료 시간을 보관합니다."""
        self.access_string = configuration["access_string"]
        self.secret = configuration["session_secret"].encode("utf-8")
        self.lifetime_seconds = int(configuration.get("session_hours", 168)) * 3600
        self.failed_attempts = {}

    def issue(self):
        """서명된 session과 요청 위조 방지 token을 생성합니다."""
        payload = {"expires": int(time.time()) + self.lifetime_seconds, "csrf": secrets.token_urlsafe(24)}
        encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
        signature = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
        return encoded + "." + signature, payload

    def validate(self, cookie_value):
        """서명과 만료 시간을 검증하고 유효하지 않은 cookie는 거부합니다."""
        try:
            encoded, signature = cookie_value.split(".", 1)
            expected = hmac.new(self.secret, encoded.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(signature, expected):
                return None
            payload = json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))
            if payload["expires"] <= time.time() or not isinstance(payload["csrf"], str):
                return None
            return payload
        except (ValueError, KeyError, TypeError, UnicodeError):
            return None

    def check_string(self, supplied_string, remote_address):
        """반복 실패를 제한하면서 입력 문자열을 일정 시간 비교합니다."""
        current_time = time.monotonic()
        recent_failures = [moment for moment in self.failed_attempts.get(remote_address, [])
                           if current_time - moment < 60]
        if len(recent_failures) >= 10:
            return "limited"
        if not hmac.compare_digest(supplied_string.encode(), self.access_string.encode()):
            recent_failures.append(current_time)
            if len(self.failed_attempts) > 1000:
                self.failed_attempts.clear()
            self.failed_attempts[remote_address] = recent_failures
            return "incorrect"
        self.failed_attempts.pop(remote_address, None)
        return "accepted"
