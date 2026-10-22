"""실제 model Load 없이 Strata request 정책과 managed launch 연결을 검증합니다."""

import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
import urllib.error
import urllib.request


WORKSPACE_DIRECTORY = Path(__file__).resolve().parents[2]
SOURCE_DIRECTORY = WORKSPACE_DIRECTORY / "external_repo/Strata"
sys.path.insert(0, str(SOURCE_DIRECTORY))
entrypoint_specification = importlib.util.spec_from_file_location(
    "strata_profile_entrypoint", WORKSPACE_DIRECTORY / "scripts/Strata/strata_entrypoint.py")
entrypoint = importlib.util.module_from_spec(entrypoint_specification)
entrypoint_specification.loader.exec_module(entrypoint)
from serve import server
from serve.frontend import ChatTemplate


class RequestPolicyTests(unittest.TestCase):
    """공식 HTTP handler에 외부 정책을 연결하되 mock Engine만 사용합니다."""

    @classmethod
    def setUpClass(cls):
        """테스트 전용 port·인증·mock Engine을 준비합니다."""
        entrypoint.install_request_policy(server)
        tokenizer = server.ByteTokenizer()
        cls.engine = server.MockEngine(tokenizer, ["Ready."], max_context=100000)
        cls.engine.generate = Mock(wraps=cls.engine.generate)
        cls.service = server.Service(cls.engine, tokenizer, ChatTemplate(SOURCE_DIRECTORY / "serve/chat_template.jinja"),
                                     model_name="fixture-qfn")
        cls.service.api_key = "fixture-key"
        cls.http_server = server.serve(cls.service, port=0)
        cls.base_url = f"http://127.0.0.1:{cls.http_server.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        """테스트 server만 종료하며 실제 서비스에는 접근하지 않습니다."""
        cls.http_server.shutdown()
        cls.http_server.server_close()

    def post_request(self, route, payload, authenticated=True):
        """테스트 전용 HTTP 요청의 상태·header·JSON을 반환합니다."""
        headers = {"Content-Type": "application/json"}
        if authenticated:
            headers["Authorization"] = "Bearer fixture-key"
        request = urllib.request.Request(self.base_url + route, data=json.dumps(payload).encode(), headers=headers)
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, response.headers.get("Content-Type", ""), json.load(response)

    def test_other_models_are_rejected_before_generation_or_streaming(self):
        """PolyStrata model·임의 model은 모든 생성 API에서 SSE 전에 400으로 거부합니다."""
        initial_calls = self.engine.generate.call_count
        for route in ("/v1/chat/completions", "/v1/messages", "/v1/responses", "/v1/messages/count_tokens",
                      "/v1/v1/messages?beta=true"):
            for model_name in ("qwen3.6-35b-a3b-hauhau-ttq-q4_k_m", "nonexistent-model"):
                for streaming in (False, True):
                    with self.subTest(route=route, model=model_name, stream=streaming):
                        status, content_type, body = self.post_request(route, {"model": model_name, "stream": streaming,
                            "messages": [{"role": "user", "content": "test"}], "input": "test", "max_tokens": 32})
                        self.assertEqual(status, 400)
                        self.assertIn("application/json", content_type)
                        self.assertIn("model", body["error"]["message"])
        self.assertEqual(self.engine.generate.call_count, initial_calls)

    def test_authentication_is_checked_before_model_policy(self):
        """인증되지 않은 요청에는 model 정보 대신 원래 401을 반환합니다."""
        status, _, _ = self.post_request("/v1/chat/completions", {"model": "nonexistent-model"}, authenticated=False)
        self.assertEqual(status, 401)

    def test_active_or_omitted_model_keeps_normal_generation(self):
        """현재 model과 model을 생략한 기존 client는 정상 동작합니다."""
        for model_name in ("fixture-qfn", None):
            with self.subTest(model=model_name):
                payload = {"messages": [{"role": "user", "content": "hello"}], "max_tokens": 32,
                           "reasoning_effort": "none"}
                if model_name is not None:
                    payload["model"] = model_name
                status, _, body = self.post_request("/v1/chat/completions", payload)
                self.assertEqual(status, 200)
                self.assertEqual(body["model"], "fixture-qfn")


class ManagedLaunchTests(unittest.TestCase):
    """Managed process의 소유권·pipe·환경 전달을 보존하는지 검증합니다."""

    def test_only_managed_python_modules_are_redirected(self):
        """Host와 server 진입점만 바꾸며 config·attestation·stdio 인자는 보존합니다."""
        for module_name, mode in (("strata_control.runtime", "--managed-host"), ("serve.server", "--managed-server")):
            with self.subTest(module=module_name):
                popen = Mock()
                runtime = SimpleNamespace(subprocess=SimpleNamespace(Popen=popen, PIPE=object()))
                entrypoint.redirect_managed_launches(runtime)
                environment = {"STRATA_OWNER_ATTEST_KEY": "fixture-attestation"}
                command = [sys.executable, "-m", module_name, "--config", "fixture.json", "--owner-fd", "0"]
                runtime.subprocess.Popen(command, env=environment, stdin="fixture-pipe", close_fds=True)
                arguments, options = popen.call_args
                self.assertEqual(arguments[0], [sys.executable, "-B", str(entrypoint.ENTRYPOINT_PATH), mode, *command[3:]])
                self.assertIs(options["env"], environment)
                self.assertEqual(options["stdin"], "fixture-pipe")
                self.assertTrue(options["close_fds"])
                self.assertEqual(command[1:3], ["-m", module_name])

    def test_engine_and_unrelated_commands_are_not_redirected(self):
        """Native Engine이나 다른 Python module의 실행 command는 그대로 전달합니다."""
        for command in (["strata.exe", "--serve"], [sys.executable, "-m", "unrelated.module"]):
            with self.subTest(command=command):
                popen = Mock()
                runtime = SimpleNamespace(subprocess=SimpleNamespace(Popen=popen))
                entrypoint.redirect_managed_launches(runtime)
                runtime.subprocess.Popen(command)
                self.assertIs(popen.call_args.args[0], command)


if __name__ == "__main__":
    unittest.main()
