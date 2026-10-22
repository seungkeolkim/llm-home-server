"""공식 PolyStrata server에 실행 model 일치 정책만 적용하는 외부 진입점입니다."""

from pathlib import Path
import sys


def main():
    """다른 model 요청과 model 전환 제어를 거부하고 공식 serving을 실행합니다."""
    source_directory = Path(__file__).resolve().parents[2] / "external_repo/PolyStrata"
    sys.path.insert(0, str(source_directory))
    from serve import server

    original_handler_factory = server.make_handler

    def make_profile_handler(service):
        """인증·body parsing은 upstream에 맡기고 관리 범위 밖 제어를 막습니다."""
        parent_handler = original_handler_factory(service)

        class ProfileHandler(parent_handler):
            """관리 서버 밖의 설정 변경·Load·Unload를 허용하지 않습니다."""

            def _post(self):
                """고정 profile에서는 생성·token 계산 API만 허용합니다."""
                if self.path.split("?")[0].rstrip("/") not in {
                    "/v1/chat/completions", "/v1/completions", "/v1/responses",
                    "/v1/messages", "/v1/messages/count_tokens", "/tokenize", "/detokenize",
                }:
                    if self._authorized():
                        self._json(403, {"error": {"message": "LLM Home Server에서 제어해 주세요."}})
                    return
                return super()._post()

        return ProfileHandler

    def requested_model(service, name):
        """미실행 model은 거부하며 자동 전환이나 현재 model 대체 응답을 막습니다."""
        if name is not None and name != service.model:
            raise ValueError("요청한 model이 실행 중이 아닙니다. LLM Home Server에서 선택해 주세요.")
        return None

    server.make_handler = make_profile_handler
    server.Service.requested_model = requested_model
    return server.main()


if __name__ == "__main__":
    raise SystemExit(main())
