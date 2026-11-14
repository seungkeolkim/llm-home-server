/** 테스트 폴더의 파일 하나만 허용하고 두 번째 쓰기는 거절하여 승인 왕복을 확인합니다. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createPaseoApi } from "../../data/Paseo/npm/node_modules/@getpaseo/client/dist/index.js";
import { createHostClient } from "../../data/Paseo/npm/node_modules/@getpaseo/client/dist/node/index.js";

const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const verificationDirectory = path.join(workspaceDirectory, "runtime/Paseo/verification");
const fixtureDirectory = path.join(verificationDirectory, "workspace");
const previousResult = JSON.parse(await fs.readFile(path.join(verificationDirectory, "native-agent.json"), "utf8"));
const driver = createHostClient("127.0.0.1:6767", {
    clientId: "llm-home-approval-verification", clientType: "cli", appVersion: "0.15.4",
    connectTimeoutMs: 10000, reconnect: { enabled: false },
});
const client = createPaseoApi(driver);
const deadline = setTimeout(() => { console.error("Approval verification timed out"); process.exit(2); }, 170000);

/** 승인 전 파일이 없으며 승인 뒤에만 작성되는지 확인합니다. */
async function verifyFileApproval(agent, filename, approved) {
    const targetPath = path.join(fixtureDirectory, filename);
    if (await fs.stat(targetPath).catch(() => null)) throw new Error("Fixture file already exists");
    const initialResult = await agent.run(
        `write 도구로 현재 폴더의 ${filename} 파일에 PASEO_APPROVAL_TEST를 쓰세요. 다른 도구는 사용하지 마세요. 승인이 거절되면 재시도하지 말고 중지하세요.`,
        { timeoutMs: 70000 },
    );
    await agent.refresh();
    const permission = agent.pendingPermissions?.[0];
    if (!permission || permission.metadata?.extensionUiMethod !== "confirm") {
        throw new Error(`Expected confirmation: ${JSON.stringify({ initialResult, permission })}`);
    }
    const permissionText = JSON.stringify(permission);
    if (!permissionText.includes(filename) || !permissionText.includes("write")) {
        throw new Error("Unexpected operation requested; no approval sent");
    }
    if (await fs.stat(targetPath).catch(() => null)) throw new Error("File was written before approval");
    await agent.respondToPermission({ requestId: permission.id,
        response: { behavior: "allow", updatedInput: { answers: { Response: approved ? "Yes" : "No" } } } });
    const result = await agent.waitForFinish(45000);
    const content = await fs.readFile(targetPath, "utf8").catch(() => null);
    if (approved ? content?.trim() !== "PASEO_APPROVAL_TEST" : content !== null) {
        throw new Error("Approval result did not match file state");
    }
    return { filename, approved, resultStatus: result.status, fileExists: content !== null };
}

try {
    await driver.connect();
    const agent = client.agents.ref(previousResult.agentId);
    await agent.refresh();
    const results = [];
    try {
        results.push(await verifyFileApproval(agent, "paseo-approved.txt", true));
        console.log(JSON.stringify(results[0]));
        results.push(await verifyFileApproval(agent, "paseo-denied.txt", false));
        console.log(JSON.stringify(results[1]));
        await fs.writeFile(path.join(verificationDirectory, "approval.json"), JSON.stringify(results, null, 2));
    } finally {
        await driver.cancelAgent(agent.id);
    }
} finally {
    clearTimeout(deadline);
    await client.dispose();
    await driver.close();
}
