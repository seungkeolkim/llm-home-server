/** 공식 Pairing offer와 Node transport로 자체 Relay의 E2EE 재접속을 확인합니다. */
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { createPaseoApi } from "../../data/Paseo/npm/node_modules/@getpaseo/client/dist/index.js";
import { createHostClient } from "../../data/Paseo/npm/node_modules/@getpaseo/client/dist/node/index.js";
import { generateLocalPairingOffer } from "../../data/Paseo/npm/node_modules/@getpaseo/server/dist/server/server/pairing-offer.js";

const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
const homeDirectory = path.join(workspaceDirectory, "data/Paseo/home");
const deadline = setTimeout(() => { console.error("Relay verification timed out"); process.exit(2); }, 45000);

/** 동일한 Pairing Link로 별도 transport 두 개를 순차 연결합니다. */
async function verifyRelayReconnect() {
    const configuration = JSON.parse(await fs.readFile(path.join(homeDirectory, "config.json"), "utf8"));
    const relay = configuration.daemon.relay;
    const offer = await generateLocalPairingOffer({
        paseoHome: homeDirectory, relayEnabled: true,
        relayEndpoint: relay.endpoint, relayPublicEndpoint: relay.publicEndpoint,
        relayUseTls: true, relayPublicUseTls: true,
        relayRequireProtectedSecurity: true, includeQr: false,
    });
    await fs.writeFile(path.join(homeDirectory, "pairing-link.txt"), offer.url + "\n");
    const connections = [];
    for (let attempt = 0; attempt < 2; attempt += 1) {
        const driver = createHostClient(offer.url, {
            clientId: `llm-home-relay-verification-${attempt}`, clientType: "cli", appVersion: "0.15.4",
            connectTimeoutMs: 12000, reconnect: { enabled: false },
        });
        const client = createPaseoApi(driver);
        try {
            await driver.connect();
            const agents = await client.agents.list();
            connections.push({ attempt: attempt + 1, state: driver.getConnectionState(), agentCount: agents.entries.length });
        } finally {
            await client.dispose();
            await driver.close();
        }
    }
    const record = { relay: relay.publicEndpoint, tlsValidation: true, protectedE2ee: true, connections };
    await fs.writeFile(path.join(workspaceDirectory, "runtime/Paseo/verification/relay.json"), JSON.stringify(record, null, 2));
    console.log(JSON.stringify(record));
}

try {
    await verifyRelayReconnect();
} finally {
    clearTimeout(deadline);
}
