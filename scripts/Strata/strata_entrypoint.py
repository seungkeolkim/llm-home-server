"""공식 Strata managed runtime을 유지하며 외부 request 정책을 연결합니다."""

from pathlib import Path
import sys
from types import SimpleNamespace


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = WORKSPACE_DIRECTORY / "external_repo/Strata"
ENTRYPOINT_PATH = Path(__file__).resolve()


def validate_requested_model(service, request):
    """요청이 다른 model을 명시하면 현재 model로 대체하지 않고 거부합니다."""
    requested_model = request.get("model")
    if requested_model is not None and requested_model != service.model:
        raise ValueError("요청한 model이 실행 중이 아닙니다. LLM Home Server에서 선택해 주세요.")


def install_request_policy(server_module):
    """인증·JSON parsing 후, prompt 처리와 SSE 응답 전에 model ID를 검증합니다."""
    if getattr(server_module, "_llm_home_policy_installed", False):
        return
    original_handler_factory = server_module.make_handler

    def make_profile_handler(service):
        """Upstream의 인증·오류 응답·lifecycle을 보존한 handler를 만듭니다."""
        parent_handler = original_handler_factory(service)

        class ProfileHandler(parent_handler):
            """공식 생성·token 계산 경로에서 실행 model 일치를 강제합니다."""

            def _openai(self, request):
                """Chat Completions는 stream 시작 전 model ID를 확인합니다."""
                validate_requested_model(service, request)
                return super()._openai(request)

            def _anthropic(self, request):
                """Anthropic Messages는 생성 전 model ID를 확인합니다."""
                validate_requested_model(service, request)
                return super()._anthropic(request)

            def _responses(self, request):
                """Responses는 stream·tool 처리 전 model ID를 확인합니다."""
                validate_requested_model(service, request)
                return super()._responses(request)

            def _count_tokens(self, request):
                """Token 계산도 미실행 model의 요청을 받지 않습니다."""
                validate_requested_model(service, request)
                return super()._count_tokens(request)

        return ProfileHandler

    server_module.make_handler = make_profile_handler
    server_module._llm_home_policy_installed = True


def redirect_managed_launches(runtime_module):
    """Managed host와 server의 진입점만 바꾸고 나머지 Popen 인자를 보존합니다."""
    original_subprocess = runtime_module.subprocess

    def launch_profile_process(command, *arguments, **options):
        """서버 소유권 pipe·env·attestation 인자를 변경하지 않고 wrapper를 거칩니다."""
        redirected_command = command
        if isinstance(command, (list, tuple)) and len(command) >= 3:
            module_modes = {"strata_control.runtime": "--managed-host", "serve.server": "--managed-server"}
            if command[0] == sys.executable and command[1] == "-m" and command[2] in module_modes:
                redirected_command = [command[0], "-B", str(ENTRYPOINT_PATH), module_modes[command[2]], *command[3:]]
        return original_subprocess.Popen(redirected_command, *arguments, **options)

    # subprocess 전역 module을 바꾸지 않고 Strata runtime의 참조만 교체합니다.
    runtime_module.subprocess = SimpleNamespace(**vars(original_subprocess))
    runtime_module.subprocess.Popen = launch_profile_process


def main():
    """공식 CLI·managed host·server 각각을 원래 수명 관리 경로로 실행합니다."""
    sys.path.insert(0, str(SOURCE_DIRECTORY))
    from serve import server
    from strata_control import runtime

    install_request_policy(server)
    redirect_managed_launches(runtime)
    arguments = sys.argv[1:]
    if arguments and arguments[0] == "--managed-host":
        return runtime.main(arguments[1:])
    if arguments and arguments[0] == "--managed-server":
        return server.main(arguments[1:])
    from strata import _preflight
    from strata_cli.cli import main as cli_main

    preflight_result = _preflight(arguments)
    return preflight_result or cli_main(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
