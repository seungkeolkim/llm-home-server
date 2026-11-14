/** Paseo 자동·수동 승인과 기존 Pi 승인·Subagent 차단을 LLM 없이 확인합니다. */
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createJiti } from "../../data/PiCodingAgent/npm/node_modules/jiti/lib/jiti.mjs";

const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const verificationDirectory = path.join(workspaceDirectory, "runtime/Paseo/verification");
await fs.mkdir(verificationDirectory, { recursive: true });
const fixtureDirectory = await fs.mkdtemp(path.join(verificationDirectory, "approval-mode-"));
const configurationPath = path.join(fixtureDirectory, "paseo.local.json");
const moduleLoader = createJiti(import.meta.url);
const { createApprovalHandler, readApprovalMode } = await moduleLoader.import(path.join(workspaceDirectory,
    "scripts/Paseo/pi-policy-extension.ts"));
const approvalHandler = createApprovalHandler(configurationPath);
const confirmationRequests = [];
const context = {
    hasUI: true,
    ui: { confirm: async (title, message) => { confirmationRequests.push({ title, message }); return false; } },
};
const toolNames = ["write", "edit", "bash", "powershell"];

/** Fixture 설정만 바꿔 같은 Handler의 실시간 모드 변경을 검사합니다. */
async function setFixtureMode(mode) {
    await fs.writeFile(configurationPath, JSON.stringify({ approval_mode: mode }));
}

await setFixtureMode("auto");
for (const toolName of toolNames) {
    const result = await approvalHandler({ toolName, input: { path: "fixture.txt", command: "fixture" } }, context);
    assert.equal(result, undefined);
}
assert.equal(confirmationRequests.length, 0);
for (const toolName of ["subagent", "acp_delegate", "acp_delegate_task"]) {
    const result = await approvalHandler({ toolName, input: {} }, context);
    assert.equal(result.block, true);
}

await setFixtureMode("manual");
for (const toolName of toolNames) {
    const result = await approvalHandler({ toolName, input: { path: "fixture.txt", command: "fixture" } }, context);
    assert.equal(result.block, true);
}
assert.equal(confirmationRequests.length, 4);
const approvedContext = { hasUI: true, ui: { confirm: async () => true } };
assert.equal(await approvalHandler({ toolName: "write", input: { path: "fixture.txt" } }, approvedContext), undefined);
assert.equal((await approvalHandler({ toolName: "write", input: {} }, { ...context, hasUI: false })).block, true);
await setFixtureMode("invalid-value");
assert.equal(readApprovalMode(configurationPath), "manual");
await fs.writeFile(configurationPath, "malformed-json");
assert.equal(readApprovalMode(configurationPath), "manual");
assert.equal(readApprovalMode(path.join(fixtureDirectory, "missing.json")), "manual");

const { default: registerOriginalApproval } = await moduleLoader.import(path.join(workspaceDirectory,
    "scripts/PiCodingAgent/approval_extension.ts"));
const originalAgentDirectory = process.env.PI_CODING_AGENT_DIR;
process.env.PI_CODING_AGENT_DIR = path.join(fixtureDirectory, "agent");
const originalHandlers = new Map();
try {
    registerOriginalApproval({ on: (eventName, handler) => originalHandlers.set(eventName, handler) });
} finally {
    if (originalAgentDirectory === undefined) delete process.env.PI_CODING_AGENT_DIR;
    else process.env.PI_CODING_AGENT_DIR = originalAgentDirectory;
}
await setFixtureMode("auto");
const originalResult = await originalHandlers.get("tool_call")({ toolName: "write", input: { path: "fixture.txt" } }, context);
assert.equal(originalResult.block, true);
assert.equal(confirmationRequests.length, 5);
const summary = { autoApprovedTools: toolNames, autoConfirmationCount: 0,
    manualDenyCount: 4, manualAllowVerified: true, subagentBlocked: true,
    invalidConfigurationUsesManual: true, originalPiStillRequestsApproval: true };
await fs.writeFile(path.join(verificationDirectory, "approval-mode.json"), JSON.stringify(summary, null, 2));
console.log(JSON.stringify(summary));
