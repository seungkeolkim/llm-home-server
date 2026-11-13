import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

/** Native browser CLI의 cache와 socket을 Pi runtime 안으로 한정합니다. */
function runBrowserCommand() {
    const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
    const browserHomeDirectory = path.join(workspaceDirectory, "runtime/PiCodingAgent/browser-home");
    const browserSocketDirectory = path.join(workspaceDirectory, "runtime/PiCodingAgent/browser/sockets");
    fs.mkdirSync(browserHomeDirectory, { recursive: true });
    fs.mkdirSync(browserSocketDirectory, { recursive: true });
    const nativeBrowserPath = path.join(workspaceDirectory,
        "data/PiCodingAgent/npm/node_modules/@agent-browser/cli-win32-x64-msvc/bin/agent-browser.exe");
    const completed = spawnSync(nativeBrowserPath, process.argv.slice(2), {
        stdio: "inherit", windowsHide: true,
        env: { ...process.env, USERPROFILE: browserHomeDirectory,
            AGENT_BROWSER_SOCKET_DIR: browserSocketDirectory,
            AGENT_BROWSER_NO_VERSION_CHECK: "1", AGENT_BROWSER_NO_WEBMCP: "1" },
    });
    if (completed.error) throw completed.error;
    process.exitCode = completed.status ?? 1;
}

runBrowserCommand();
