/** 자체 Relay를 통한 실제 Thinking streaming과 생성 중 취소를 확인합니다. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createPaseoApi } from "../../data/Paseo/npm/node_modules/@getpaseo/client/dist/index.js";
import { createHostClient } from "../../data/Paseo/npm/node_modules/@getpaseo/client/dist/node/index.js";

const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const verificationDirectory = path.join(workspaceDirectory, "runtime/Paseo/verification");
const previousResult = JSON.parse(await fs.readFile(path.join(verificationDirectory, "native-agent.json"), "utf8"));
const pairingLink = (await fs.readFile(path.join(workspaceDirectory, "data/Paseo/home/pairing-link.txt"), "utf8")).trim();
const driver = createHostClient(pairingLink, {
    clientId: "llm-home-streaming-verification", clientType: "cli", appVersion: "0.15.4",
    connectTimeoutMs: 12000, reconnect: { enabled: false },
});
const client = createPaseoApi(driver);
const events = [];

/** 실제 stream event를 기다리되 생성과 후속 확인을 무기한 기다리지 않습니다. */
async function waitForCondition(predicate, timeoutMilliseconds) {
    const deadline = Date.now() + timeoutMilliseconds;
    while (Date.now() < deadline) {
        if (await predicate()) return;
        await new Promise(resolve => setTimeout(resolve, 200));
    }
    throw new Error("Expected streaming state was not observed");
}

await driver.connect();
const agent = client.agents.ref(previousResult.agentId);
const subscription = agent.timeline.subscribe(event => events.push(event));
try {
    await subscription.ready;
    const result = await agent.run("도구를 사용하지 말고 7 곱하기 8의 숫자 값만 답하세요.", { timeoutMs: 60000 });
    const reasoningEvents = events.filter(event => event.event.type === "timeline" && event.event.item.type === "reasoning");
    if (!reasoningEvents.length || !result.lastMessage?.includes("56")) throw new Error("Reasoning or answer missing");
    const previousEventCount = events.length;
    await agent.send("도구를 사용하지 말고 1부터 10000까지의 정수를 한 줄에 하나씩 순서대로 써 주세요.");
    await waitForCondition(() => events.slice(previousEventCount).some(event =>
        event.event.type === "timeline" && ["reasoning", "assistant_message"].includes(event.event.item.type)), 45000);
    await driver.cancelAgent(agent.id);
    await waitForCondition(async () => { await agent.refresh(); return agent.status === "idle"; }, 12000);
    await waitForCondition(async () => {
        const response = await fetch("http://127.0.0.1:8490/health", { signal: AbortSignal.timeout(2000) });
        return (await response.json()).in_flight === 0;
    }, 12000);
    const record = { relay: "azzi-home.duckdns.org:38789", answer: result.lastMessage,
        reasoningEventCount: reasoningEvents.length, cancellationDuringStreaming: true,
        finalStatus: agent.status, gatewayInFlightAfterCancel: 0 };
    await fs.writeFile(path.join(verificationDirectory, "streaming.json"), JSON.stringify(record, null, 2));
    console.log(JSON.stringify(record));
} finally {
    subscription();
    await driver.cancelAgent(agent.id).catch(() => {});
    await client.dispose();
    await driver.close();
}
