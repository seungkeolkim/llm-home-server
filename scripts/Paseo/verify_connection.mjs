/** 공식 SDK로 Native Pi와 Relay 연결을 제한 시간 안에 확인합니다. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createPaseoClient } from "../../data/Paseo/npm/node_modules/@getpaseo/client/dist/index.js";

const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const verificationDirectory = path.join(workspaceDirectory, "runtime/Paseo/verification");
const fixtureDirectory = path.join(verificationDirectory, "workspace");
const client = createPaseoClient({
    url: "ws://127.0.0.1:6767/ws", connectTimeoutMs: 10000, reconnect: { enabled: false },
});
const deadline = setTimeout(() => { console.error("Paseo verification timed out"); process.exit(2); }, 180000);

/** 테스트 전용 Agent의 상태와 timeline을 증거 파일로 남깁니다. */
async function verifyNativeAgent() {
    await fs.mkdir(fixtureDirectory, { recursive: true });
    await client.connect();
    const models = await client.providers.listModels("pi", { cwd: fixtureDirectory });
    if (models.error) throw new Error(models.error);
    const agent = await client.agents.create({
        config: { provider: "pi/strata-local/sc117-qwen3.8-flash-next-abliterated-iq3_xxs", thinkingOptionId: "low" },
        cwd: fixtureDirectory, title: "Paseo 연결 확인",
    });
    const events = [];
    const subscription = agent.timeline.subscribe((event) => events.push(event));
    await subscription.ready;
    console.log("AGENT_CREATED", agent.id);
    try {
        const result = await agent.run("도구를 사용하지 말고 17 곱하기 23의 값만 짧게 답하세요.", { timeoutMs: 100000 });
        await agent.refresh();
        const timeline = await agent.timeline.refetch();
        const record = { agentId: agent.id, result, agent: agent.current(), events, timeline };
        await fs.writeFile(path.join(verificationDirectory, "native-agent.json"), JSON.stringify(record, null, 2));
        console.log(JSON.stringify({ agentId: agent.id, result, status: agent.status,
            error: agent.lastError, eventTypes: [...new Set(events.map(event => event.event.type))] }));
    } finally {
        subscription();
    }
}

try {
    await verifyNativeAgent();
} finally {
    clearTimeout(deadline);
    await client.close();
}
