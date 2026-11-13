import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

/** LLM 호출과 relay 연결 없이 실제 Windows Pi SDK의 Extension load를 검사합니다. */
async function verifyRemotePiExtensionCompatibility() {
    const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
    const verificationDirectory = path.join(workspaceDirectory, "runtime/RemotePi/verification");
    const verificationAgentDirectory = path.join(verificationDirectory, "agent");
    fs.mkdirSync(verificationAgentDirectory, { recursive: true });
    for (const configurationName of ["settings.json", "models.json"]) {
        fs.copyFileSync(
            path.join(workspaceDirectory, "runtime/PiCodingAgent/agent", configurationName),
            path.join(verificationAgentDirectory, configurationName),
        );
    }

    process.env.PI_CODING_AGENT_DIR = verificationAgentDirectory;
    process.env.REMOTE_PI_HOME = path.join(verificationDirectory, "remote-home");
    const remoteConfiguration = JSON.parse(fs.readFileSync(path.join(workspaceDirectory,
        "config/RemotePi/remote-pi.local.json"), "utf8"));
    process.env.REMOTE_PI_RELAY = remoteConfiguration.relay_url;
    process.env.REMOTE_PI_DIRECT_CONFIG = JSON.stringify({
        agent_name: "Windows-Native-Pi-Verification",
        auto_start_relay: false,
    });
    process.env.BILI_CONFIG_FILE = path.join(workspaceDirectory, "config/PiCodingAgent/billion-context.local.json");
    process.env.BILI_SESSIONS_DIR = path.join(verificationDirectory, "billion-context-sessions");
    process.env.ACP_LOG_FILE = path.join(verificationDirectory, "billion-context.log");
    process.env.ACP_AUTO_UPDATE = "0";
    process.env.BILI_ADVISORY_CHECK = "0";

    const piSdk = await import(pathToFileURL(path.join(workspaceDirectory,
        "data/PiCodingAgent/npm/node_modules/@earendil-works/pi-coding-agent/dist/index.js")).href);
    const verifyInstalledLoader = process.argv.includes("--installed-loader");
    const verifyPolicyWrapper = process.argv.includes("--wrapped") || verifyInstalledLoader;
    process.env.REMOTE_PI_VERIFY_OFFLINE = "1";
    const extensionRelativePath = verifyInstalledLoader
        ? "runtime/PiCodingAgent/agent/extensions/remote-pi.ts"
        : verifyPolicyWrapper ? "scripts/RemotePi/remote-pi-extension.ts"
            : "data/RemotePi/npm/node_modules/remote-pi/dist/index.js";
    const extensionEntryPath = path.join(workspaceDirectory, extensionRelativePath);
    const resourceLoader = new piSdk.DefaultResourceLoader({
        cwd: workspaceDirectory,
        agentDir: verificationAgentDirectory,
        additionalExtensionPaths: [extensionEntryPath],
    });
    await resourceLoader.reload();
    const { session, extensionsResult } = await piSdk.createAgentSession({
        cwd: workspaceDirectory,
        agentDir: verificationAgentDirectory,
        resourceLoader,
        sessionManager: piSdk.SessionManager.inMemory(),
    });

    try {
        await session.bindExtensions({});
        const verificationResult = {
            platform: process.platform,
            nodeVersion: process.version,
            extensionErrors: extensionsResult.errors,
            extensionPaths: session.extensionRunner.getExtensionPaths(),
            tools: session.getAllTools().map((tool) => tool.name),
            commands: resourceLoader.getExtensions().extensions.flatMap((extension) =>
                [...extension.commands.keys()]),
            llmRequests: 0,
            relayAutoStart: false,
            policyWrapper: verifyPolicyWrapper,
        };
        fs.writeFileSync(path.join(verificationDirectory, "extension-compatibility.json"),
            JSON.stringify(verificationResult, null, 2));
        process.stdout.write(JSON.stringify(verificationResult, null, 2) + "\n");
        assert.equal(verificationResult.extensionErrors.length, 0);
        assert.ok(verificationResult.commands.includes("remote-pi"));
        if (verifyPolicyWrapper) {
            for (const blockedToolName of ["agent_send", "agent_request", "list_peers"]) {
                assert.ok(!verificationResult.tools.includes(blockedToolName));
            }
        }
    }
    finally {
        await session.extensionRunner.emit({ type: "session_shutdown" });
        session.dispose();
    }
}

await verifyRemotePiExtensionCompatibility();
