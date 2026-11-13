import path from "node:path";
import fs from "node:fs";
import { pathToFileURL, fileURLToPath } from "node:url";

/** 실제 Pi 요청 이후 Extension이 기본 Compaction을 취소하는지 검사합니다. */
async function verifyExtensionRuntime() {
    const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
    const sdk = await import(pathToFileURL(path.join(workspaceDirectory,
        "data/PiCodingAgent/npm/node_modules/@earendil-works/pi-coding-agent/dist/index.js")).href);
    const resourceLoader = new sdk.DefaultResourceLoader({
        cwd: workspaceDirectory, agentDir: process.env.PI_CODING_AGENT_DIR,
    });
    await resourceLoader.reload();
    const { session, extensionsResult } = await sdk.createAgentSession({
        cwd: workspaceDirectory, resourceLoader, sessionManager: sdk.SessionManager.inMemory(),
    });
    try {
        await session.bindExtensions({});
        await session.prompt("Reply exactly PI_EXTENSION_READY without tools.");
        const compactGate = await session.extensionRunner.emit({
            type: "session_before_compact", reason: "threshold", willRetry: false,
            preparation: {}, branchEntries: [], signal: new AbortController().signal,
        });
        const turnLockPath = path.join(workspaceDirectory, "runtime/PiCodingAgent/agent-turn.lock");
        const testOwnerToken = "verification-" + process.pid;
        fs.writeFileSync(turnLockPath, JSON.stringify({ pid: process.pid, ownerToken: testOwnerToken }), { flag: "wx" });
        let blockedInput;
        try {
            blockedInput = await session.extensionRunner.emitInput("Offline concurrency boundary test", undefined, "interactive");
        } finally {
            const lockRecord = JSON.parse(fs.readFileSync(turnLockPath, "utf8"));
            if (lockRecord.ownerToken === testOwnerToken) fs.unlinkSync(turnLockPath);
        }
        const summary = {
            extensionPaths: session.extensionRunner.getExtensionPaths(),
            extensionErrors: extensionsResult.errors,
            tools: session.getAllTools().map((tool) => tool.name),
            skills: resourceLoader.getSkills().skills.map((skill) => skill.name),
            defaultCompactionGate: compactGate,
            concurrentInputGate: blockedInput,
        };
        fs.writeFileSync(path.join(workspaceDirectory, "runtime/PiCodingAgent/verification/extension-summary.json"),
            JSON.stringify(summary, null, 2));
        process.stdout.write(JSON.stringify(summary, null, 2) + "\n");
        if (summary.extensionErrors.length || compactGate?.cancel !== true || blockedInput?.action !== "handled"
            || summary.tools.some((name) => name.includes("delegate") || name === "subagent")) {
            process.exitCode = 1;
        }
    } finally {
        session.dispose();
    }
}

await verifyExtensionRuntime();
