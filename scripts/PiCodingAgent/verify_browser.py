"""실제 Windows Native agent-browser를 로컬 폼에서 검증합니다."""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import re
import subprocess
import threading

from service_runtime import WORKSPACE_DIRECTORY, RUNTIME_DIRECTORY


class BrowserFixtureHandler(BaseHTTPRequestHandler):
    """외부 연결 없이 클릭·입력·Console을 검증할 예제 페이지를 제공합니다."""

    def do_GET(self):
        """입력값을 화면에 표시하는 정적 HTML을 반환합니다."""
        content = b'''<!doctype html><html lang="en"><meta charset="utf-8"><title>Pi Browser Verification</title>
<style>body{font:20px system-ui;margin:60px;background:#f2f5fa;color:#14213d}main{max-width:700px;background:white;padding:32px;border-radius:16px}input,button{font:inherit;padding:12px;margin:8px}button{background:#245dcc;color:white;border:0;border-radius:8px}</style>
<main><h1>Pi Native Browser Verification</h1><label for="message">Message</label><input id="message"><button id="submit">Submit</button><p id="result">Waiting for input</p></main>
<script>/** Show the submitted message and a console marker. */ document.querySelector('#submit').onclick=function showResult(){document.querySelector('#result').textContent='Received: '+document.querySelector('#message').value;console.log('PI_BROWSER_READY')};</script></html>'''
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, message_format, *arguments):
        """예제 서버의 불필요한 access log를 생략합니다."""
        return


def run_browser_command(*arguments):
    """고정된 Pi wrapper를 통해 격리된 전용 브라우저에 순차 명령을 보냅니다."""
    completed = subprocess.run(["node", str(WORKSPACE_DIRECTORY / "scripts/PiCodingAgent/browser_cli.mjs"),
                                "--session", "pi-verification", *arguments], cwd=WORKSPACE_DIRECTORY,
                               capture_output=True, text=True, encoding="utf-8", timeout=60)
    if completed.returncode:
        raise RuntimeError(completed.stdout + completed.stderr)
    return completed.stdout.strip()


def main():
    """Snapshot, 입력, 클릭, Screenshot과 Console을 검증하고 항상 브라우저를 닫습니다."""
    server = HTTPServer(("127.0.0.1", 0), BrowserFixtureHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    verification_directory = RUNTIME_DIRECTORY / "verification"
    verification_directory.mkdir(parents=True, exist_ok=True)
    summary = {}
    try:
        summary["open"] = run_browser_command("open", f"http://127.0.0.1:{server.server_port}")
        snapshot = run_browser_command("snapshot", "-i")
        summary["snapshot"] = snapshot
        textbox_reference = re.search(r'textbox[^\n]*\[ref=(e\d+)\]', snapshot).group(1)
        button_reference = re.search(r'button[^\n]*\[ref=(e\d+)\]', snapshot).group(1)
        run_browser_command("fill", "@" + textbox_reference, "PiBrowserReady")
        run_browser_command("click", "@" + button_reference)
        summary["result"] = run_browser_command("snapshot")
        summary["screenshot"] = run_browser_command("screenshot", str(verification_directory / "browser.png"))
        summary["console"] = run_browser_command("console")
        summary["errors"] = run_browser_command("errors")
        if "Received: PiBrowserReady" not in summary["result"]:
            raise AssertionError("Browser 폼 실행 결과가 일치하지 않습니다.")
    finally:
        summary["close"] = run_browser_command("close")
        server.shutdown()
        server.server_close()
    (verification_directory / "browser-summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
