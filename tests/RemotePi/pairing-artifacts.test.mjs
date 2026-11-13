import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { setTimeout as waitForTimer } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { publishPairingArtifacts } from "../../scripts/RemotePi/pairing-artifacts.mjs";

/** 오래된 만료 timer가 새 QR를 삭제하지 않으며 현재 QR는 만료 후 제거되는지 검사합니다. */
async function verifyPairingArtifactExpiration() {
    const workspaceDirectory = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
    const verificationDirectory = path.join(workspaceDirectory, "runtime/RemotePi/verification");
    fs.mkdirSync(verificationDirectory, { recursive: true });
    const artifactDirectory = fs.mkdtempSync(path.join(verificationDirectory, "pairing-test-"));
    assert.ok(artifactDirectory.startsWith(verificationDirectory + path.sep));
    try {
        await assert.rejects(publishPairingArtifacts({
            uri: "https://example.invalid/not-a-pairing-code",
            expiresAt: Date.now() + 1000,
        }, artifactDirectory));
        await publishPairingArtifacts({
            uri: "remotepi://pair?t=first-test-token&epk=test-public-key",
            expiresAt: Date.now() + 1000,
            name: "Artifact-Test",
        }, artifactDirectory);
        const latestPublication = await publishPairingArtifacts({
            uri: "remotepi://pair?t=second-test-token&epk=test-public-key",
            expiresAt: Date.now() + 2500,
            name: "Artifact-Test",
        }, artifactDirectory);
        const pngSignature = fs.readFileSync(path.join(artifactDirectory, "pairing-qr-code.png")).subarray(0, 8);
        assert.equal(pngSignature.toString("hex"), "89504e470d0a1a0a");
        await waitForTimer(1250);
        const currentPublication = JSON.parse(fs.readFileSync(path.join(artifactDirectory, "pairing-status.json"), "utf8"));
        assert.equal(currentPublication.publicationIdentifier, latestPublication.publicationIdentifier);
        assert.ok(fs.readFileSync(path.join(artifactDirectory, "pairing-code.txt"), "utf8").includes("second-test-token"));
        await waitForTimer(1500);
        assert.equal(fs.readdirSync(artifactDirectory).length, 0);
    }
    finally {
        for (const artifactFileName of ["pairing-qr-code.png", "pairing-code.txt", "pairing-status.json"]) {
            fs.rmSync(path.join(artifactDirectory, artifactFileName), { force: true });
        }
        fs.rmdirSync(artifactDirectory);
    }
}

await test("pairing QR validates input and expires only its current publication", verifyPairingArtifactExpiration);
