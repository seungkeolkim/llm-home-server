/** 실제 Paseo Pi에서 승인 응답 전송 없이 write·edit·bash 완료를 확인합니다. */
import assert from "node:assert/strict";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createPaseoApi } from "../../data/Paseo/npm/node_modules/@getpaseo/client/dist/index.js";
import { createHostClient } from "../../data/Paseo/npm/node_modules/@getpaseo/client/dist/node/index.js";

const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const verificationDirectory = path.join(workspaceDirectory, "runtime/Paseo/verification");
const configuration = JSON.parse(await fs.readFile(path.join(workspaceDirectory, "config/Paseo/paseo.local.json"), "utf8"));
assert.equal(configuration.approval_mode, "auto", "이 검증은 Paseo auto 모드에서만 실행합니다.");
await fs.mkdir(verificationDirectory, { recursive: true });
const fixtureDirectory = await fs.mkdtemp(path.join(verificationDirectory, "automatic-approval-"));
const pairingLink = (await fs.readFile(path.join(workspaceDirectory, "data/Paseo/home/pairing-link.txt"), "utf8")).trim();
const driver = createHostClient(pairingLink, {
    clientId: "llm-home-automatic-approval-verification", clientType: "cli", appVersion: "0.15.4",
    connectTimeoutMs: 10000, reconnect: { enabled: false },
});
const client = createPaseoApi(driver);
const timelineEvents = [];
let agent;
let unsubscribeTimeline;
try {
    await driver.connect();
    agent = await client.agents.create({ cwd: fixtureDirectory, title: "Paseo 자동승인 확인",
        config: { provider: "pi/strata-local/sc117-qwen3.8-flash-next-abliterated-iq3_xxs", thinkingOptionId: "low" } });
    unsubscribeTimeline = agent.timeline.subscribe(event => timelineEvents.push(event));
    await unsubscribeTimeline.ready;
    const result = await agent.run(
        "자동승인 검증입니다. 반드시 다음 세 단계를 도구로 실행하세요. " +
        "1. write로 현재 폴더의 automatic-approval.txt에 PASEO_AUTO_BEFORE를 쓰세요. " +
        "2. edit로 그 파일의 PASEO_AUTO_BEFORE를 PASEO_AUTO_AFTER로 바꾸세요. " +
        "3. bash로 printf 'PASEO_SHELL_AUTO_OK\\n'만 실행하세요. " +
        "다른 파일과 명령은 건드리지 마세요. 모두 완료하면 AUTO_APPROVAL_DONE이라고만 답하세요.",
        { timeoutMs: 90000 },
    );
    await agent.refresh();
    assert.equal(result.status, "idle", JSON.stringify(result));
    assert.equal(result.error, null);
    assert.equal(agent.pendingPermissions.length, 0);
    const content = await fs.readFile(path.join(fixtureDirectory, "automatic-approval.txt"), "utf8");
    assert.equal(content.trim(), "PASEO_AUTO_AFTER");
    const timeline = await agent.timeline.refetch();
    const completedTools = timeline.entries.map(entry => entry.item).filter(item => item.type === "tool_call");
    for (const toolName of ["write", "edit", "bash"]) {
        assert.ok(completedTools.some(item => item.name === toolName && item.status === "completed" && !item.error));
    }
    assert.ok(completedTools.some(item => item.name === "bash" && item.detail.output?.includes("PASEO_SHELL_AUTO_OK")));
    const tools = [...new Set(timelineEvents.filter(event => event.event.type === "timeline")
        .map(event => event.event.item).filter(item => item.type === "tool_call").map(item => item.name ?? item.toolName))];
    const summary = { agentId: agent.id, status: agent.status, fileContent: content.trim(),
        pendingPermissions: agent.pendingPermissions.length, approvalResponsesSent: 0, tools,
        shellOutputObserved: true, relay: "azzi-home.duckdns.org:38789" };
    await fs.writeFile(path.join(verificationDirectory, "automatic-approval.json"), JSON.stringify({ summary, timeline }, null, 2));
    console.log(JSON.stringify(summary));
} finally {
    unsubscribeTimeline?.();
    if (agent) await driver.cancelAgent(agent.id).catch(() => {});
    await client.dispose();
    await driver.close();
}
