import assert from "node:assert/strict";
import { once } from "node:events";
import fs from "node:fs";
import https from "node:https";
import path from "node:path";
import tls from "node:tls";
import { fileURLToPath, pathToFileURL } from "node:url";

/** 기본 trust store를 사용해 hostname과 인증서 chain 검증 결과를 읽습니다. */
async function readVerifiedCertificate(relayUrl) {
    return new Promise((resolve, reject) => {
        const connection = tls.connect({
            host: relayUrl.hostname,
            port: Number(relayUrl.port || 443),
            servername: relayUrl.hostname,
            timeout: 10000,
        }, () => {
            const certificate = connection.getPeerCertificate();
            resolve({
                authorized: connection.authorized,
                hostname: relayUrl.hostname,
                issuer: certificate.issuer,
                subjectAlternativeName: certificate.subjectaltname,
                validFrom: certificate.valid_from,
                validTo: certificate.valid_to,
                serialNumber: certificate.serialNumber,
                fingerprint256: certificate.fingerprint256,
            });
            connection.end();
        });
        connection.on("error", reject);
        connection.on("timeout", () => connection.destroy(new Error("TLS verification timed out")));
    });
}

/** 인증서 검증을 유지한 HTTPS 요청으로 Relay health를 확인합니다. */
async function readRelayHealth(relayUrl) {
    return new Promise((resolve, reject) => {
        const request = https.get(new URL("/health", relayUrl), { timeout: 10000 }, (response) => {
            let responseBody = "";
            response.setEncoding("utf8");
            response.on("data", (chunk) => { responseBody += chunk; });
            response.on("end", () => resolve({ statusCode: response.statusCode, body: responseBody.trim() }));
        });
        request.on("error", reject);
        request.on("timeout", () => request.destroy(new Error("Relay health timed out")));
    });
}

/** Agent를 실행하지 않고 공식 transport의 WSS 인증 및 재연결을 검사합니다. */
async function verifyRelayTransport() {
    const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
    const configuration = JSON.parse(fs.readFileSync(path.join(workspaceDirectory,
        "config/RemotePi/remote-pi.local.json"), "utf8"));
    const relayUrl = new URL(configuration.relay_url);
    assert.equal(relayUrl.protocol, "https:");
    const extensionDirectory = path.join(workspaceDirectory, "data/RemotePi/npm/node_modules/remote-pi/dist");
    const { RelayClient } = await import(pathToFileURL(path.join(extensionDirectory, "transport/relay_client.js")).href);
    const { generateEd25519Keypair } = await import(pathToFileURL(path.join(extensionDirectory, "pairing/crypto.js")).href);
    const certificate = await readVerifiedCertificate(relayUrl);
    const health = await readRelayHealth(relayUrl);
    assert.equal(certificate.authorized, true);
    assert.equal(health.statusCode, 200);
    assert.equal(health.body, "OK");

    const ephemeralKeypair = generateEd25519Keypair();
    const connectionResults = [];
    for (let attemptNumber = 1; attemptNumber <= 2; attemptNumber += 1) {
        const relayClient = new RelayClient(configuration.relay_url.replace(/^https:/, "wss:"), ephemeralKeypair);
        try {
            await relayClient.connect({
                roomId: "verifyrelay1",
                roomMeta: { name: "Transport-Verification", cwd: "transport-verification" },
            });
            assert.equal(relayClient.isOpen(), true);
            connectionResults.push({ attempt: attemptNumber, authenticated: true });
        }
        finally {
            if (relayClient.isOpen()) {
                const closedEvent = once(relayClient, "close", { signal: AbortSignal.timeout(5000) });
                relayClient.close();
                await closedEvent;
            }
            else {
                relayClient.close();
            }
        }
    }
    const verificationResult = {
        relayUrl: configuration.relay_url,
        verifiedAt: new Date().toISOString(),
        certificate,
        health,
        connections: connectionResults,
        llmRequests: 0,
    };
    const verificationDirectory = path.join(workspaceDirectory, "runtime/RemotePi/verification");
    fs.mkdirSync(verificationDirectory, { recursive: true });
    fs.writeFileSync(path.join(verificationDirectory, "relay-transport.json"), JSON.stringify(verificationResult, null, 2));
    process.stdout.write(JSON.stringify(verificationResult, null, 2) + "\n");
}

await verifyRelayTransport();
